from __future__ import annotations

# backend/app/services/npc/npc_loader.py
"""
NPC Profile Loader (Config -> L0 Profile).
Загружает статичные данные NPC из config/npc/ с поддержкой наследования:
  base → archetype → mixins → individual
Приоритет: individual > mixin > archetype > base
Зависимости: app.models.npc_profile, typing, json, pathlib
"""


import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.models.npc_profile import NPCProfileL0, PsycheBase
from app.models.npc_state import NPCState, WillState, _emotion_from_str, _pk_from_dict

# Путь к статичным конфигам NPC (read-only зона)
_CONFIG_NPC_ROOT = Path(__file__).parent.parent.parent.parent.parent / "config" / "npc"

logger = logging.getLogger(__name__)


# Локализация стандартных предметов инвентаря NPC
_ITEM_DISPLAY_NAMES: Dict[str, str] = {
    "apron": "фартук",
    "keys": "ключи",
    "coin_pouch": "кошелёк",
    "dagger": "кинжал",
    "sword": "меч",
    "bow": "лук",
    "torch": "факел",
    "lantern": "фонарь",
    "rope": "верёвка",
    "lock": "замок",
    "tray": "поднос",
    "maid_dress": "платье служанки",
    "notebook": "записная книжка",
    "scales": "весы",
    "pipe": "трубка",
    "cloak": "плащ",
}


def get_item_display_name(item_id: str) -> str:
    """Возвращает локализованное имя предмета или сам item_id как fallback."""
    return _ITEM_DISPLAY_NAMES.get(item_id, item_id)


# =============================================================================
# СИСТЕМА НАСЛЕДОВАНИЯ КОНФИГОВ
# =============================================================================


def _load_json_file(path: Path) -> Dict[str, Any]:
    """Загружает JSON файл. Падает при ошибке — конфиги критичны."""
    if not path.exists():
        raise FileNotFoundError(f"[NPC_LOADER] Config not found: {path}")
    with open(path, "rb") as bf:
        return json.loads(bf.read().decode("utf-8-sig"))


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """
    Рекурсивный мерж двух словарей.
    override имеет приоритет над base.
    Списки ЗАМЕНЯЮТСЯ (для visible_markers и т.д. это правильно — individual определяет свой список).
    Ключи с '_' (метаданные) пропускаются.
    """
    result = base.copy()
    for key, value in override.items():
        if key.startswith("_"):
            continue  # _version, _type, _inherits — метаданные, не мержим
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _load_archetype_chain(individual_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Собирает полную статику NPC по цепочке наследования.
    Порядок мержа определяет приоритет: individual > mixin > archetype > base
    """
    # 1. Базовый гуманоид (фундамент)
    base_path = _CONFIG_NPC_ROOT / "archetypes" / "_base_humanoid.json"
    merged = _load_json_file(base_path)

    # 2. Архетип (профессия)
    archetype_name = individual_data.get("_archetype", "")
    if archetype_name:
        archetype_path = _CONFIG_NPC_ROOT / "archetypes" / f"{archetype_name}.json"
        archetype_data = _load_json_file(archetype_path)
        merged = _deep_merge(merged, archetype_data)

    # 3. Миксины (модификаторы, применяются в порядке объявления)
    for mixin_name in individual_data.get("_mixins", []):
        mixin_path = _CONFIG_NPC_ROOT / "mixins" / f"{mixin_name}.json"
        mixin_data = _load_json_file(mixin_path)
        merged = _deep_merge(merged, mixin_data)

    # 4. Индивидуальные данные (высший приоритет — конкретный NPC)
    merged = _deep_merge(merged, individual_data)

    # v2.2 Spatial Ontology: Сохраняем _archetype для инъекции в NPCProfileL0.
    # _deep_merge пропускает ключи с '_', поэтому инъектируем явно после мержа.
    if "_archetype" in individual_data:
        merged["_archetype"] = individual_data["_archetype"]

    return merged


def reload_archetype_for(npc_dict: Dict[str, Any], new_archetype: str) -> Dict[str, Any]:
    """Перезагружает schedule + activity_map из нового архетипа, сохраняя runtime-overlay (P2-11).

    ADR-TIFL-003: При кризисе идентичности NPC может сменить архетип.
    Эта функция перезагружает статические данные (schedule, activity_map) из нового архетипа,
    но сохраняет все runtime-поля (stress, relationship_cache, body_state и т.д.).
    """
    # Stage 0: Упразднён whitelist _RUNTIME_TOP_LEVEL_KEYS. 
    # Сохраняем ВЕСЬ текущий словарь как overlay, затем накладываем его поверх новой статики.
    _runtime_overlay = npc_dict.copy()
    
    # Удаляем метаданные, чтобы они не затёрли новые
    _runtime_overlay.pop("_archetype", None)
    _runtime_overlay.pop("_mixins", None)

    npc_dict["_archetype"] = new_archetype
    _new_static = _load_archetype_chain(npc_dict)

    # Глубоко мержим runtime поверх новой статики
    _merged = _deep_merge(_new_static, _runtime_overlay)
    logger.info(f"[NPC_LOADER] Reloaded archetype for {npc_dict.get('id')}: -> {new_archetype}")
    return _merged


def load_npc_profiles_from_config() -> Dict[str, NPCProfileL0]:
    """
    Загружает все NPC из config/npc/individuals/.
    Для каждого: собирает цепочку наследования → парсит в NPCProfileL0.
    Возвращает словарь {npc_id: NPCProfileL0}.
    """
    profiles: Dict[str, NPCProfileL0] = {}
    individuals_dir = _CONFIG_NPC_ROOT / "individuals"

    if not individuals_dir.exists():
        logger.warning(
            f"[NPC_LOADER] Individuals directory not found: {individuals_dir}"
        )
        return profiles

    for json_file in individuals_dir.glob("*.json"):
        try:
            individual_data = _load_json_file(json_file)
            merged = _load_archetype_chain(individual_data)
            profile = load_profile_from_legacy_json(merged)
            profiles[profile.id] = profile
            logger.debug(
                f"[NPC_LOADER] Loaded profile: {profile.id} from {json_file.name}"
            )
        except Exception as e:
            logger.error(f"[NPC_LOADER] Failed to load {json_file.name}: {e}")
            raise

    return profiles


def load_social_base() -> Dict[str, Any]:
    """
    Загружает статичные социальные связи из config/npc/social/.
    Runtime-мутации хранятся отдельно в saves/.
    """
    social_dir = _CONFIG_NPC_ROOT / "social"
    relations: Dict[str, Any] = {}

    if not social_dir.exists():
        return relations

    for json_file in social_dir.glob("*.json"):
        data = _load_json_file(json_file)
        relations.update(data.get("relations", {}))

    return relations


def _enrich_with_social_relations(
    npcs: List[Dict[str, Any]],
    relations: Dict[str, Any],
) -> None:
    """Обогащает NPC dict связями из village_relations.json.

    village_relations.json использует шкалу 0-1 (base_trust: 0.3).
    SocialDecayHandler ожидает шкалу 0-100.
    Конвертация: base_trust * 100.

    Формат обогащения:
      relationship_cache[target] = {trust, fear, base_trust, nature}
      base_values[target] = base_trust * 100

    Не перезаписывает существующие записи (runtime мог мутировать).
    Мутирует NPC dicts in-place — вызывается только при загрузке.
    """
    # Индекс NPC по ID для быстрого поиска
    npc_by_id: Dict[str, Dict[str, Any]] = {}
    for npc in npcs:
        if isinstance(npc, dict):
            _id = npc.get("id", "")
            if _id:
                npc_by_id[_id] = npc

    for source_id, targets in relations.items():
        if source_id not in npc_by_id:
            logger.debug(
                f"[NPC_LOADER] Social relation source '{source_id}' "
                f"not found in loaded NPCs, skipping"
            )
            continue

        npc = npc_by_id[source_id]

        # Инициализация relationship_cache
        if "relationship_cache" not in npc or not isinstance(
            npc["relationship_cache"], dict
        ):
            npc["relationship_cache"] = {}
        rc = npc["relationship_cache"]

        # Инициализация base_values
        if "base_values" not in npc or not isinstance(npc["base_values"], dict):
            npc["base_values"] = {}
        bv = npc["base_values"]

        for target_id, rel_data in targets.items():
            if not isinstance(rel_data, dict):
                continue

            base_trust_01 = float(rel_data.get("base_trust", 0.0))
            base_trust_100 = base_trust_01 * 100.0
            nature = rel_data.get("nature", "unknown")

            # Не перезаписываем существующие (runtime мог мутировать)
            if target_id not in rc:
                rc[target_id] = {
                    "trust": base_trust_100,
                    "fear": 0.0,
                    "base_trust": base_trust_100,
                    "nature": nature,
                }

            if target_id not in bv:
                bv[target_id] = base_trust_100

    logger.debug(f"[NPC_LOADER] Enriched {len(npcs)} NPCs with social relations")


# =============================================================================
# СИСТЕМА МЕРЖА STATIC + RUNTIME (ШАГ 1.5.3b)
# =============================================================================

# Поля, которые являются RUNTIME и перезаписываются из npc_runtime.json
# Static поля (willpower, breakpoint, drives, description и т.д.) НЕ перезаписываются
# Stage 0: Упразднены whitelist'ы _RUNTIME_PSYCHE_KEYS, _RUNTIME_TOP_LEVEL_KEYS, 
# _RUNTIME_FLAGS_KEYS, _RUNTIME_ROUTINE_KEYS (ADR-118 DOUBLE TRUTH fix).
# Теперь мерж выполняется рекурсивно через _deep_merge, сохраняя все runtime-поля.


def _apply_runtime_overlay(
    static_npc: Dict[str, Any], runtime_npc: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Глубоко мержит runtime-поля из runtime_npc поверх static_npc.
    Static поля НЕ перезаписываются на верхнем уровне, но runtime-данные 
    внутри словарей (psyche, body_state и т.д.) обновляются рекурсивно.
    Stage 0: Упразднён whitelist _RUNTIME_TOP_LEVEL_KEYS (DOUBLE TRUTH fix).
    """
    result = _deep_merge(static_npc, runtime_npc)
    
    # Возвращаем метаданные static, если они были затёрты runtime-дампом
    if "_archetype" in static_npc:
        result["_archetype"] = static_npc["_archetype"]
    if "_mixins" in static_npc:
        result["_mixins"] = static_npc["_mixins"]
        
    return result


def load_npcs_merged(runtime_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """
    Загружает NPC из config/npc/ с наложением runtime из файла сохранения.
    Возвращает List[Dict] в формате совместимом с game_loop.

    Если runtime_path не указан или не существует — возвращается чистый static.
    Это позволяет:
    - Начать новую игру: static из config, runtime пустой
    - Продолжить игру: static из config + runtime из npc_runtime.json
    - Обновить конфиг: static меняется, runtime сохраняется
    """
    # 1. Загружаем static из config/npc/individuals/ с наследованием
    individuals_dir = _CONFIG_NPC_ROOT / "individuals"
    static_npcs: List[Dict[str, Any]] = []

    if not individuals_dir.exists():
        logger.warning(
            f"[NPC_LOADER] Individuals directory not found: {individuals_dir}"
        )
        return static_npcs

    for json_file in sorted(individuals_dir.glob("*.json")):
        try:
            individual_data = _load_json_file(json_file)
            merged_static = _load_archetype_chain(individual_data)
            static_npcs.append(merged_static)
        except Exception as e:
            logger.error(f"[NPC_LOADER] Failed to load {json_file.name}: {e}")
            raise

    # 1.5 Загружаем социальные связи для обогащения NPC→NPC
    social_base = load_social_base()

    # 2. Если нет runtime — обогащаем и возвращаем static
    if not runtime_path or not runtime_path.exists():
        _enrich_with_social_relations(static_npcs, social_base)

        # ENTITY BIRTH CONTRACT (дублируется для обоих путей выхода из функции)
        from app.models.npc_state import BODY_STATE_HEALTHY

        for npc in static_npcs:
            if not npc.get("body_state"):
                npc["body_state"] = dict(BODY_STATE_HEALTHY)
            if "npc_id" not in npc and "id" in npc:
                npc["npc_id"] = npc["id"]

        logger.info(
            f"[NPC_LOADER] No runtime file, loaded {len(static_npcs)} NPCs from config only"
        )
        return static_npcs

    # 3. Загружаем runtime и строим индекс по ID
    try:
        with open(runtime_path, "r", encoding="utf-8") as f:
            runtime_list = json.load(f)
        runtime_by_id: Dict[str, Dict[str, Any]] = {
            npc["id"]: npc for npc in runtime_list if "id" in npc
        }
    except Exception as e:
        logger.warning(
            f"[NPC_LOADER] Failed to load runtime {runtime_path}: {e}, using static only"
        )
        _enrich_with_social_relations(static_npcs, social_base)

        from app.models.npc_state import BODY_STATE_HEALTHY

        for npc in static_npcs:
            if not npc.get("body_state"):
                npc["body_state"] = dict(BODY_STATE_HEALTHY)
            if "npc_id" not in npc and "id" in npc:
                npc["npc_id"] = npc["id"]

        return static_npcs

    # 4. Мержим runtime поверх static
    result: List[Dict[str, Any]] = []
    for static_npc in static_npcs:
        npc_id = static_npc.get("id")
        if npc_id and npc_id in runtime_by_id:
            merged = _apply_runtime_overlay(static_npc, runtime_by_id[npc_id])
            result.append(merged)
            logger.debug(f"[NPC_LOADER] {npc_id}: static + runtime merged")
        else:
            result.append(static_npc)
            logger.debug(f"[NPC_LOADER] {npc_id}: static only (no runtime data)")

    _enrich_with_social_relations(result, social_base)

    # ENTITY BIRTH CONTRACT: NPC входит в систему как полностью валидная сущность.
    # Без этого idle path (LifeEngine.tick → load_npcs_merged) получает NPC без body_state
    # → SOMATIC_VETO блокирует когнитивный pipeline → NPC = инертные объекты.
    # GameLoop._load_npcs_with_runtime дублировал эту логику (ADR-O-146) —
    # но idle path обходит GameLoop, вызывая load_npcs_merged напрямую.
    from app.models.npc_state import BODY_STATE_HEALTHY

    for npc in result:
        if not npc.get("body_state"):
            npc["body_state"] = dict(BODY_STATE_HEALTHY)
        # npc_id из "id" — единый инвариант идентичности
        if "npc_id" not in npc and "id" in npc:
            npc["npc_id"] = npc["id"]

    logger.info(
        f"[NPC_LOADER] Loaded {len(result)} NPCs (config + runtime from {runtime_path.name})"
    )
    return result


def materialize_inventory(raw_npc: Dict[str, Any]) -> Dict[str, int]:
    """
    Материализует физический инвентарь NPC из seed-данных JSON.
    Читает carried_objects — явный список физических предметов роли.
    Валидирует каждый предмет через world_ontology перед регистрацией.
    Вызывается один раз при инициализации новой сцены — не в рантайме.
    """
    from app.services.world.world_ontology import is_physical_object

    result: Dict[str, int] = {}
    for obj_id in raw_npc.get("carried_objects", []):
        if is_physical_object(obj_id):
            result[obj_id] = 1
        else:
            logger.debug(
                f"[NPC_LOADER] Пропущен non-physical маркер '{obj_id}' у NPC {raw_npc.get('id')}"
            )
    return result


def load_profile_from_legacy_json(raw_data: Dict[str, Any]) -> NPCProfileL0:
    """
    Парсит словарь в строгий NPCProfileL0.
    Работает как с legacy major_npcs.json, так и со смерженным конфигом из config/npc/.

    ПРАВИЛО: Если обязательного поля нет — падаем сразу.
    Ошибки в JSON профиля — это критический сбой кампании.
    """
    try:
        psyche_raw = raw_data.get("psyche", {})

        psyche_base = PsycheBase(
            willpower=int(psyche_raw.get("willpower", 50)),
            breakpoint=int(psyche_raw.get("breakpoint", 80)),
            loyalty_base=int(
                psyche_raw.get("loyalty_true", psyche_raw.get("loyalty_base", 50))
            ),
        )

        # Извлекаем только базовые драйвы. Динамические веса (social_stats) игнорируются.
        drives_raw = raw_data.get("drives", {})
        drives_base = {
            "control": float(drives_raw.get("control", 0.0)),
            "significance": float(drives_raw.get("significance", 0.0)),
            "fear": float(drives_raw.get("fear", 0.0)),
            "desire": float(drives_raw.get("desire", 0.0)),
        }

        # ADR-O-MEMETIC-002: Загрузка VoiceArchetype из Canon.
        # Если указан voice_archetype_id, он переопределяет voice_profile из JSON.
        _archetype_id = raw_data.get("voice_archetype_id")
        _voice_profile = raw_data.get("voice_profile", "")

        if _archetype_id:
            from app.domain.memetic.voice_archetype import load_voice_archetype
            _archetype_data = load_voice_archetype(_archetype_id)
            if _archetype_data and _archetype_data.voice_profile:
                _voice_profile = _archetype_data.voice_profile

        profile = NPCProfileL0(
            id=raw_data["id"],
            name=raw_data.get("name", "Unknown"),
            tier=raw_data.get("tier", "minor"),
            gender=raw_data.get("gender", "male"),
            archetype=raw_data.get("_archetype", "commoner"),
            drives_base=drives_base,
            psyche_base=psyche_base,
            # voice_profile берётся из архетипа (если есть), иначе из JSON.
            voice_profile=_voice_profile,
            backstory=raw_data.get("backstory", raw_data.get("description", "")),
            author_notes=raw_data.get("author_notes", ""),
            core_orientation=raw_data.get("core_orientation", "survival"),
            voice_archetype_id=_archetype_id,
        )

        return profile

    except (KeyError, ValueError, TypeError) as e:
        logger.error(
            f"[NPC_LOADER] Failed to parse profile from JSON: {e}. Raw keys: {raw_data.keys()}"
        )
        raise ValueError(
            f"Invalid NPC profile format for id={raw_data.get('id', 'UNKNOWN')}: {e}"
        )


def _convert_origin_events(origin_list: List[Dict], npc_id: str) -> Tuple[Any, ...]:
    """Конвертирует origin_events из JSON-конфига в кортеж EventMemory.
    Вызывается только при новой игре, когда narrative_cache ещё пуст."""
    if not origin_list:
        return ()
    from app.models.npc_state import EventMemory

    _result = []
    for _d in origin_list:
        # JSON даёт list, модель требует tuple (frozen dataclass)
        _tags = tuple(_d["tags"]) if isinstance(_d.get("tags"), list) else tuple()
        _known = (
            tuple(_d["known_by"]) if isinstance(_d.get("known_by"), list) else tuple()
        )
        _hidden = (
            tuple(_d["hidden_from"])
            if isinstance(_d.get("hidden_from"), list)
            else tuple()
        )
        _mem = EventMemory(
            event_type=_d.get("event_type", "origin"),
            target_id=_d.get("target_id", ""),
            emotion_tag=_d.get("emotion_tag", "neutral"),
            day=_d.get("day", -1000),
            importance=_d.get("importance", 0.5),
            clarity=_d.get("clarity", 1.0),
            confidence=_d.get("confidence", 1.0),
            decay_rate=_d.get("decay_rate", 0.001),  # origin забываются медленно
            summary=_d.get("summary", ""),
            npc_id=npc_id,
            tags=_tags,
            is_secret=_d.get("is_secret", False),
            known_by=_known,
            hidden_from=_hidden,
            accessibility=_d.get("accessibility", 1.0),
        )
        _result.append(_mem)
    return tuple(_result)


def _restore_narrative_cache(cache_list: List[Dict]) -> Tuple[Any, ...]:
    """Восстанавливает narrative_cache из JSON в кортеж EventMemory."""
    if not cache_list:
        return ()
    from app.models.npc_state import EventMemory

    _result = []
    for _d in cache_list:
        _type_name = _d.pop("_memory_type", None)
        if _type_name == "EventMemory":
            # JSON даёт list, модель требует tuple (frozen dataclass)
            if "tags" in _d and isinstance(_d["tags"], list):
                _d["tags"] = tuple(_d["tags"])
            if "known_by" in _d and isinstance(_d["known_by"], list):
                _d["known_by"] = tuple(_d["known_by"])
            if "hidden_from" in _d and isinstance(_d["hidden_from"], list):
                _d["hidden_from"] = tuple(_d["hidden_from"])
            _mem = EventMemory(**_d)
            # Decay при загрузке — NPC загружается раз в тик
            _mem = _mem.decayed(game_days=1.0)
            if not _mem.is_forgotten:
                _result.append(_mem)
    return tuple(_result)


def load_l2_state_from_runtime_dict(raw_data: Dict[str, Any]) -> NPCState:
    """
    Извлекает ДИНАМИЧЕСКОЕ состояние из runtime-словаря (SceneState / JSON).
    В отличие от L0 (который immutable), это меняется каждый тик.

    ВНИМАНИЕ: Это временный мост. Когда будет реализован R1.8 (Iron-Man Persistence),
    L2 будет загружаться из SQLite/Сохранения, а не из сырого JSON.
    """
    psyche = raw_data.get("psyche", {})
    ss = raw_data.get("social_stats", {})

    # Безопасный маппинг строк из грязного JSON в строгие Enum'ы
    will_str = psyche.get("state", "free")
    try:
        will_enum = WillState(will_str)
    except ValueError:
        will_enum = WillState.FREE

    # L2.7: LifeProject — динамическая проекция L0.
    # P2: Обратная совместимость. Если нет life_project, берём старое life_direction или L0.
    _life_project = psyche.get("life_project", psyche.get("life_direction", raw_data.get("core_orientation", "survival")))
    _life_project_state = psyche.get("life_project_state", "ACTIVE")

    state = NPCState(
        npc_id=raw_data.get("id", "unknown"),
        # N-23 FIX: hp/max_hp удалены из NPCState, читаются только из body_state.
        stress=float(psyche.get("stress", 0.0)),
        will_state=will_enum,
        life_project=_life_project,
        life_project_state=_life_project_state,
        # Система слома
        identity_integrity=float(psyche.get("identity_integrity", 1.0)),
        pressure_resistance=float(psyche.get("pressure_resistance", 0.0)),
        resentment=float(psyche.get("resentment", 0.0)),
        dependency=float(psyche.get("dependency", 0.0)),
        trauma_markers=set(psyche.get("trauma_flags", [])),
        relationship_cache={
            "player": {
                "trust": float(ss.get("trust", 0.0)),
                "fear": float(ss.get("fear_of_player", 0.0)),
                "debt": float(ss.get("debt", 0.0)),
            }
        },
        # Роль из статического профиля — нужна для фильтрации интентов
        current_role=raw_data.get("status_profile", {}).get("title", ""),
        # ADR-116: emotion/affective_load/body_state/perceptual_kernel —
        # без этого DecisionHub видит emotion=NEUTRAL каждый тик → utility=0.0
        emotion=_emotion_from_str(raw_data.get("emotion", "neutral")),
        emotion_delta=float(raw_data.get("emotion_delta", 0.0)),
        affective_load=float(raw_data.get("affective_load", 0.0)),
        body_state=dict(raw_data.get("body_state", {})),
        perceptual_kernel=_pk_from_dict(raw_data.get("perceptual_kernel", {})),
    )

    # Восстановление narrative_cache: из runtime-дампа или из origin_events
    _cache = _restore_narrative_cache(raw_data.get("narrative_cache", []))
    if not _cache:
        _npc_id = raw_data.get("id", "unknown")
        _cache = _convert_origin_events(raw_data.get("origin_events", []), _npc_id)
    object.__setattr__(state, "narrative_cache", _cache)

    return state
