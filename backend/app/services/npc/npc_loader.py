# backend/app/services/npc/npc_loader.py
"""
NPC Profile Loader (Config -> L0 Profile).
Загружает статичные данные NPC из config/npc/ с поддержкой наследования:
  base → archetype → mixins → individual
Приоритет: individual > mixin > archetype > base
Зависимости: app.models.npc_profile, typing, json, pathlib
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.models.npc_profile import NPCProfileL0, PsycheBase
from app.models.npc_state import NPCStateL2, WillState

from app.services.npc.decision_hub import DecisionHub, EventContext

# Путь к статичным конфигам NPC (read-only зона)
_CONFIG_NPC_ROOT = Path(__file__).parent.parent.parent.parent.parent / "config" / "npc"

logger = logging.getLogger(__name__)


# Локализация стандартных предметов инвентаря NPC
_ITEM_DISPLAY_NAMES: Dict[str, str] = {
    "apron":      "фартук",
    "keys":       "ключи",
    "coin_pouch": "кошелёк",
    "dagger":     "кинжал",
    "sword":      "меч",
    "bow":        "лук",
    "torch":      "факел",
    "lantern":    "фонарь",
    "rope":       "верёвка",
    "lock":       "замок",
    "tray":       "поднос",
    "maid_dress": "платье служанки",
    "notebook":   "записная книжка",
    "scales":     "весы",
    "pipe":       "трубка",
    "cloak":      "плащ",
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
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


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
    
    return merged


def load_npc_profiles_from_config() -> Dict[str, NPCProfileL0]:
    """
    Загружает все NPC из config/npc/individuals/.
    Для каждого: собирает цепочку наследования → парсит в NPCProfileL0.
    Возвращает словарь {npc_id: NPCProfileL0}.
    """
    profiles: Dict[str, NPCProfileL0] = {}
    individuals_dir = _CONFIG_NPC_ROOT / "individuals"
    
    if not individuals_dir.exists():
        logger.warning(f"[NPC_LOADER] Individuals directory not found: {individuals_dir}")
        return profiles
    
    for json_file in individuals_dir.glob("*.json"):
        try:
            individual_data = _load_json_file(json_file)
            merged = _load_archetype_chain(individual_data)
            profile = load_profile_from_legacy_json(merged)
            profiles[profile.id] = profile
            logger.debug(f"[NPC_LOADER] Loaded profile: {profile.id} from {json_file.name}")
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


# =============================================================================
# СИСТЕМА МЕРЖА STATIC + RUNTIME (ШАГ 1.5.3b)
# =============================================================================

# Поля, которые являются RUNTIME и перезаписываются из npc_runtime.json
# Static поля (willpower, breakpoint, drives, description и т.д.) НЕ перезаписываются
_RUNTIME_PSYCHE_KEYS = frozenset({
    "stress", "state", "trauma_flags",
    "identity_integrity", "pressure_resistance", "resentment", "dependency"
})
_RUNTIME_TOP_LEVEL_KEYS = frozenset({"social_stats", "location", "hp"})
_RUNTIME_FLAGS_KEYS = frozenset({
    "has_gold", "knows_secret", "is_enslaved", "planning_revenge", "is_dead"
})
_RUNTIME_ROUTINE_KEYS = frozenset({"next_task"})


def _apply_runtime_overlay(static_npc: Dict[str, Any], runtime_npc: Dict[str, Any]) -> Dict[str, Any]:
    """
    Накладывает runtime-поля из runtime_npc на static_npc.
    Static поля НЕ перезаписываются — сохраняют значения из config/.
    """
    result = static_npc.copy()
    
    # Runtime поля внутри psyche
    if "psyche" in runtime_npc:
        if "psyche" not in result:
            result["psyche"] = {}
        result["psyche"] = result["psyche"].copy()
        for key in _RUNTIME_PSYCHE_KEYS:
            if key in runtime_npc["psyche"]:
                result["psyche"][key] = runtime_npc["psyche"][key]
    
    # Runtime поля верхнего уровня
    for key in _RUNTIME_TOP_LEVEL_KEYS:
        if key in runtime_npc:
            result[key] = runtime_npc[key]
    
    # Runtime флаги
    if "flags" in runtime_npc:
        if "flags" not in result:
            result["flags"] = {}
        result["flags"] = result["flags"].copy()
        for key in _RUNTIME_FLAGS_KEYS:
            if key in runtime_npc["flags"]:
                result["flags"][key] = runtime_npc["flags"][key]
    
    # Runtime в routine (next_task — текущая задача, schedule — static)
    if "routine" in runtime_npc:
        if "routine" not in result:
            result["routine"] = {}
        result["routine"] = result["routine"].copy()
        for key in _RUNTIME_ROUTINE_KEYS:
            if key in runtime_npc["routine"]:
                result["routine"][key] = runtime_npc["routine"][key]
    
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
        logger.warning(f"[NPC_LOADER] Individuals directory not found: {individuals_dir}")
        return static_npcs
    
    for json_file in sorted(individuals_dir.glob("*.json")):
        try:
            individual_data = _load_json_file(json_file)
            merged_static = _load_archetype_chain(individual_data)
            static_npcs.append(merged_static)
        except Exception as e:
            logger.error(f"[NPC_LOADER] Failed to load {json_file.name}: {e}")
            raise
    
    # 2. Если нет runtime — возвращаем чистый static
    if not runtime_path or not runtime_path.exists():
        logger.info(f"[NPC_LOADER] No runtime file, loaded {len(static_npcs)} NPCs from config only")
        return static_npcs
    
    # 3. Загружаем runtime и строим индекс по ID
    try:
        with open(runtime_path, "r", encoding="utf-8") as f:
            runtime_list = json.load(f)
        runtime_by_id: Dict[str, Dict[str, Any]] = {
            npc["id"]: npc for npc in runtime_list if "id" in npc
        }
    except Exception as e:
        logger.warning(f"[NPC_LOADER] Failed to load runtime {runtime_path}: {e}, using static only")
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
    
    logger.info(f"[NPC_LOADER] Loaded {len(result)} NPCs (config + runtime from {runtime_path.name})")
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
            print(f"[NPC_LOADER] Пропущен non-physical маркер '{obj_id}' у NPC {raw_npc.get('id')}")
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
            loyalty_base=int(psyche_raw.get("loyalty_true", psyche_raw.get("loyalty_base", 50)))
        )
        
        # Извлекаем только базовые драйвы. Динамические веса (social_stats) игнорируются.
        drives_raw = raw_data.get("drives", {})
        drives_base = {
            "control": float(drives_raw.get("control", 0.0)),
            "significance": float(drives_raw.get("significance", 0.0)),
            "fear": float(drives_raw.get("fear", 0.0)),
            "desire": float(drives_raw.get("desire", 0.0)),
        }

        profile = NPCProfileL0(
            id=raw_data["id"],
            name=raw_data.get("name", "Unknown"),
            tier=raw_data.get("tier", "minor"),
            drives_base=drives_base,
            psyche_base=psyche_base,
            # voice_profile и backstory пока берем как есть, если есть.
            # В будущем они будут формироваться из отдельных файлов лора.
            voice_profile=raw_data.get("voice_profile", ""),
            backstory=raw_data.get("description", ""),
        )
        
        return profile

    except (KeyError, ValueError, TypeError) as e:
        logger.error(f"[NPC_LOADER] Failed to parse profile from JSON: {e}. Raw keys: {raw_data.keys()}")
        raise ValueError(f"Invalid NPC profile format for id={raw_data.get('id', 'UNKNOWN')}: {e}")


def load_l2_state_from_runtime_dict(raw_data: Dict[str, Any]) -> NPCStateL2:
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

    return NPCStateL2(
        npc_id=raw_data.get("id", "unknown"),
        stress=float(psyche.get("stress", 0.0)),
        will_state=will_enum,
        
        # Система слома
        identity_integrity=float(psyche.get("identity_integrity", 1.0)),
        pressure_resistance=float(psyche.get("pressure_resistance", 0.0)),
        resentment=float(psyche.get("resentment", 0.0)),
        dependency=float(psyche.get("dependency", 0.0)),
        
        trauma_markers=set(psyche.get("trauma_flags", [])),
        relationship_cache={
            "trust": float(ss.get("trust", 0.0)),
            "fear": float(ss.get("fear_of_player", 0.0)),
            "debt": float(ss.get("debt", 0.0)),
        }
    )


def execute_npc_decision(raw_npc_dict: Dict[str, Any], event_ctx: EventContext, seed: Optional[int] = None) -> 'DecisionResult':
    """
    DM Execution Facade (Этап 5).
    Берет грязные данные NPC из сцены, приводит к чистым типам и получает решение.
    
    ВНИМАНИЕ: Эта функция не меняет состояние (StateApplicator вызывается отдельно).
    """
    # 1. Извлекаем статику и динамику в строгие контракты
    profile_l0 = load_profile_from_legacy_json(raw_npc_dict)
    state_l2 = load_l2_state_from_runtime_dict(raw_npc_dict)
    
    # 2. Вычисляем решение
    hub = DecisionHub(seed=seed)
    result = hub.compute(
        state=state_l2,
        personality=profile_l0,
        event=event_ctx
    )
    
    return result    