"""
DEGOD ITER4: фабрика канонического scene_state (перенос из scene_state_manager.py).
Назначение: сборка канонического scene_state новой сцены из editor-JSON/template (initialize-фабрика). DEGOD ITER4: байт-в-байт перенос тела initialize_scene (:687–925) + _select_time_variant (:927–953) из scene_state_manager.py.
Зависимости: hashlib, random, app.core.calendar, app.services.scene_state.environment_modifiers, editor_locator, npc_display_name
Основные сущности: build_initial_scene, select_time_variant
"""

import hashlib
import logging
import random

from app.core.calendar import Calendar
from app.services.scene_state.editor_locator import _nearest_node_to_xy
from app.services.scene_state.environment_modifiers import _derive_environment_modifiers
from app.services.scene_state.npc_display_name import _npc_id_to_display

logger = logging.getLogger(__name__)


def select_time_variant(template: dict, time_of_day: str) -> dict:
    try:
        h, m = map(int, time_of_day.split(":"))
        minutes = h * 60 + m
    except (ValueError, AttributeError):
        minutes = 12 * 60

    for time_range, variant in template.get("time_variants", {}).items():
        try:
            start_str, end_str = time_range.split("-")
            sh, sm = map(int, start_str.split(":"))
            eh, em = map(int, end_str.split(":"))
            start_min = sh * 60 + sm
            end_min = eh * 60 + em
            if start_min > end_min:
                if minutes >= start_min or minutes < end_min:
                    return variant
            else:
                if start_min <= minutes < end_min:
                    return variant
        except (ValueError, AttributeError) as e:
            logger.debug(f"[SCENE] Пропуск time_variant {variant}: {e}")
            continue

    variants = list(template.get("time_variants", {}).values())
    return variants[0] if variants else {}


def build_initial_scene(
    campaign_id: str,
    location_id: str,
    time_of_day: str,
    template: dict,
    editor_data: dict | None,
    build_spatial_data,
) -> dict:
    """
    Собирает SceneState из шаблона локации с учётом времени суток.
    Случайные вариации ±20% для count объектов.
    НЕ сохраняет — сохранение остаётся за вызывающим (save_scene_state).

    S.0: добавлены поля player_target_npc, player_target_object,
         player_position, player_distances.
    """
    objects: dict = {}
    npc_positions: dict = {}
    player_spawn_node: str = ""
    spatial_walls: list[dict] = []
    spatial_obstacles: list[dict] = []

    if editor_data:
        # --- Объекты из editor JSON ---
        for i, obj in enumerate(editor_data.get("objects", [])):
            obj_id = obj.get("id", f"obj_{i}")
            objects[obj_id] = {
                "name": obj.get("name", obj.get("type", "объект")),
                "type": obj.get("type", ""),
                "state": obj.get("properties", {}).get("open", True)
                and "intact"
                or "closed",
                "position": obj.get("position", {}),
                "size": obj.get("size", {}),
                "interactable": True,
            }

        # --- NPC из editor JSON — только те что на этой карте ---
        for npc in editor_data.get("npcs", []):
            ref_id = npc.get("ref_id", "")
            if not ref_id:
                continue
            pos = npc.get("position", {})
            node = _nearest_node_to_xy(editor_data, pos.get("x", 0), pos.get("y", 0))
            npc_positions[ref_id] = {
                "name": _npc_id_to_display(ref_id),
                "location_id": location_id,
                "position": node,
                "activity": "",
                "visible": True,
                "local_position": {"x": pos.get("x", 0.0), "y": pos.get("y", 0.0)},
                "editor_room_id": npc.get("room_id", ""),
            }

        # --- Точка спавна игрока ---
        if spawn := editor_data.get("player_spawn"):
            player_spawn_node = _nearest_node_to_xy(
                editor_data, spawn.get("x", 0), spawn.get("y", 0)
            )
            # S144 FIX: Игрок добавляется в npc_positions как полноправный агент (ADR-O-315).
            # Без этого SpatialService и MovementEngine не могут разрешить цели, и все coords=None.
            npc_positions["player"] = {
                "name": "player",
                "location_id": location_id,
                "position": player_spawn_node or "entrance",
                "activity": "",
                "visible": True,
                "local_position": {
                    "x": spawn.get("x", 0.0),
                    "y": spawn.get("y", 0.0),
                },
            }
        else:
            # V8-SP-3 FIX: Если player_spawn отсутствует, спавним рядом с первым NPC.
            # Это гарантирует валидность координат (SC-1) и наличие в графе локации.
            _first_npc = next(iter(npc_positions.values()), None)
            if _first_npc:
                npc_positions["player"] = {
                    "name": "player",
                    "location_id": location_id,
                    "position": _first_npc.get("position", "entrance"),
                    "activity": "",
                    "visible": True,
                    "local_position": _first_npc.get("local_position", {"x": 1.0, "y": 1.0}),
                }
            else:
                # V8-SP-3 FALLBACK: Если NPC тоже нет, спавним на entrance с дефолтными координатами
                npc_positions["player"] = {
                    "name": "player",
                    "location_id": location_id,
                    "position": "entrance",
                    "activity": "",
                    "visible": True,
                    "local_position": {"x": 1.0, "y": 1.0},
                }

        # --- Стены и блокирующие объекты для коллизий (делегирование в GraphCompiler) ---
        spatial_walls, spatial_obstacles = build_spatial_data(editor_data)

        logger.info(
            f"[SCENE] Editor JSON: {len(objects)} объектов, "
            f"{len(npc_positions)} NPC, spawn_node={player_spawn_node}"
        )
    else:
        # --- Fallback: старая логика из location_templates.json ---
        for obj_id, obj_data in template.get("default_objects", {}).items():
            obj = dict(obj_data)
            if "count" in obj and obj.get("interactable", False):
                base = obj["count"]
                delta = max(1, int(base * 0.2))
                # BUG-RNG-001 FIX: Детерминированный сид от location+obj для ADR-O-301.
                _seed_str = f"{location_id}:{obj_id}"
                _seed = int(hashlib.md5(_seed_str.encode("utf-8")).hexdigest(), 16)
                count = base + random.Random(_seed).randint(-delta, delta)
                for i in range(1, count + 1):
                    instance = {k: v for k, v in obj.items() if k != "count"}
                    instance["instance_of"] = obj_id
                    instance["name"] = f"{obj['name']} #{i}"
                    objects[f"{obj_id}_{i}"] = instance
            else:
                objects[obj_id] = obj

        for npc_id, pos_data in template.get("npc_defaults", {}).items():
            if npc_id in npc_positions:
                # Дополняем editor JSON данными из шаблона (activity, visible)
                # Но НЕ перезаписываем local_position — он уже правильный из editor
                for k, v in pos_data.items():
                    if k not in npc_positions[npc_id]:
                        npc_positions[npc_id][k] = v
            else:
                # NPC нет в editor JSON — это data integrity bug.
                # BUG-SPATIAL-006a FIX: Запрещено создавать фантомные позиции (0.0, 0.0) (SC-1).
                logger.error(
                    f"[SCENE_INIT] NPC '{npc_id}' отсутствует в editor JSON локации '{location_id}'. "
                    f"Создание позиции с (0.0, 0.0) запрещено. NPC пропущен."
                )
                continue

    # --- Среда (всегда из шаблона — время/свет/шум) ---
    time_variant = select_time_variant(template, time_of_day)
    environment = {
        "light_level": time_variant.get("light_level", "dim"),
        "noise_level": time_variant.get("noise_level", "low"),
        "time_of_day": time_of_day,
        "weather_inside": time_variant.get("weather_inside", "neutral"),
    }
    if candle_data := time_variant.get("candles"):
        base_count = candle_data.get("count", 0)
        if base_count > 0:
            delta = max(1, int(base_count * 0.2))
            # BUG-RNG-001 FIX: Детерминированный сид от location+candles для ADR-O-301.
            _seed_str = f"{location_id}:candles_main"
            _seed = int(hashlib.md5(_seed_str.encode("utf-8")).hexdigest(), 16)
            objects["candles_main"] = {
                "name": "свечи",
                "state": candle_data.get("state", "unlit"),
                "count": base_count + random.Random(_seed).randint(-delta, delta),
                "interactable": True,
                "owner": None,
            }
        else:
            objects["candles_main"] = {
                "name": "свечи",
                "state": "unlit",
                "count": 0,
                "interactable": True,
                "owner": None,
            }

    scene_state = {
        "location_id": location_id,
        "objects": objects,
        "npc_positions": npc_positions,
        "environment": environment,
        "player_body_topology": None,  # ТЗ Presentation v2.0: BodyTopology (сериализованный)
        "active_effects": [],
        # ── S.0: пространственный контекст игрока ────────────────────────
        # Обновляется каждый ход через update_player_target()
        # Используется в build_npc_context_block() и _build_scene_description()
        "player_position": "стоит",  # текущая поза/позиция игрока
        # BUG-SPATIAL-004 FIX: Блок пространственного контекста удалён (ADR-O-314).
        # Игрок инициализируется в npc_positions как обычный агент.
        "player_target_npc": None,  # id NPC к которому обращается
        "player_target_npc_name": None,  # читаемое имя (для промпта)
        "player_target_object": None,  # id объекта взаимодействия
        "player_distances": {},  # {npc_id: float} метры
        "environment_modifiers": _derive_environment_modifiers(
            time_variant, template.get("type", "")
        ),
        # ── Пространственные данные для коллизий (из editor JSON) ─────
        "spatial_walls": spatial_walls,
        "spatial_obstacles": spatial_obstacles,
        # ── ADR-019: Traversal Registry (процесс во времени, а не стейт) ──
        "active_traversals": {},  # dict[npc_id, traversal_dict]
        # ── S203.1 (Stage 2A): Behavioral Ownership Registry (shadow) ──
        # Только НОВЫЕ сцены. Загруженные из persistence самовосстанавливаются
        # через setdefault в CommitmentRegistry (ключи едут в atomic_commit,
        # Foundation Freeze: scene_state round-trip без whitelist).
        "active_commitments": {},  # dict[npc_id, commitment_dict] — только активные
        "commitment_history": {},  # dict[npc_id, list] — bounded terminal (cap 10)
        "commitment_ordinals": {},  # dict[npc_id, int] — монотонные счётчики идентичностей
        # ── ADR-O-370 (RE M1a): субстрат потребностей — ПУСТОЙ корень ──
        # Заполнение только через RelationshipStateStore (ленивые записи);
        # загруженные сейвы самовосстанавливаются: ключ отсутствует →
        # read-дефолты стора (Foundation Freeze, без whitelist).
        "relationship_state": {},
        # ── W1/W3 (ADR-O-371/O-376): семантическая объектная топология ──
        # Пустой корень; заполнение — WorldObjectSpawner через
        # WorldObjectStore.spawn (единственный путь записи), ниже.
        # Загруженные сейвы не перезатираются (сейв выигрывает).
        "world_objects": {},
        # ── ADR-O-146: Новая игра начинается с tick=0, время 12:00 ──
        "tick": 0,
        # ── S139 FIX: SSOT времени — всегда инициализируем game_time_seconds ──
        "game_time_seconds": Calendar.parse_hhmm(time_of_day),
        # ─────────────────────────────────────────────────────────────────
    }

    # ── W3 (ADR-O-376): production-spawn семантических объектов ──
    # editor objects → WorldObject (SpawnMapping; вердикт Мастера:
    # door+door_transition→door, chair; state-проекция locked/open).
    # Только НОВЫЕ сцены: загруженные сейвы возвращаются выше без
    # спавна — сейв выигрывает. Локальный импорт — прецедент
    # _build_spatial_data (нулевое влияние на import-граф SSM).
    from app.services.world.world_object_spawner import WorldObjectSpawner
    _spawn_report = WorldObjectSpawner.spawn_from_editor(
        scene_state, campaign_id, location_id, editor_data)
    if _spawn_report.spawned or _spawn_report.faults:
        logger.info(f"[W3_SPAWN] {_spawn_report.summary()}")

    return scene_state
