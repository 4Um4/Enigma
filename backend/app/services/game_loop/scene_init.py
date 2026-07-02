"""
path: backend/app/services/game_loop/scene_init.py
Назначение: Инициализация состояния сцены на старте тика.
Зависимости: SceneManager, LifeEngine, EconomyTracker, Calendar
Основные сущности: init_scene_state, ensure_scene_initialized
"""

import logging
import time as _time
from typing import Any

from app.core.calendar import Calendar

logger = logging.getLogger(__name__)


# ── Подфункции init_scene_state ───────────────────────────────────────


def _resolve_initial_time(preserved_game_time: float | None, campaign_state: Any) -> str:
    """Определяет время суток для новой сцены.
    Приоритет: preserved_game_time (аккумулирует дни) > campaign_state > 07:00.
    """
    if preserved_game_time is not None:
        return Calendar.format_time(preserved_game_time)
    if campaign_state:
        return campaign_state.metadata.get("time_of_day", "07:00")
    return "07:00"


def _extract_preserved_time(shared_context: Any) -> float | None:
    """БАГ H: Извлекает абсолютное время из shared_context до реинициализации."""
    if shared_context and hasattr(shared_context, "game_time_seconds") and shared_context.game_time_seconds is not None:
        return shared_context.game_time_seconds
    return None


def _materialize_npc_inventory(loop: Any, scene_state: dict) -> None:
    """Материализует инвентарь NPC из вероятностных правил L0 (только для новой сцены)."""
    from app.services.npc.npc_loader import materialize_inventory, get_item_display_name

    npc_scene_ids = set(scene_state.get("npc_positions", {}).keys())
    for raw_npc in loop._load_npcs():
        npc_id = raw_npc.get("id") or raw_npc.get("npc_id")
        if npc_id not in npc_scene_ids or not raw_npc.get("carried_objects"):
            continue
        try:
            for item_id, qty in materialize_inventory(raw_npc).items():
                obj_key = f"{item_id}_owned_by_{npc_id}"
                if obj_key not in scene_state["objects"]:
                    scene_state["objects"][obj_key] = {
                        "name": get_item_display_name(item_id),
                        "state": "present", "interactable": True,
                        "owner": npc_id, "count": qty,
                    }
        except Exception as e:
            logger.warning(f"[GAME_LOOP] Ошибка материализации инвентаря {npc_id}: {e}")


def _update_player_position(scene_state: dict, player_position: tuple[float, float] | None) -> None:
    """ADR-048 Phase 3: Позиция игрока пишется ТОЛЬКО в npc_positions.player."""
    if player_position is None:
        return
    node = scene_state.setdefault("npc_positions", {}).setdefault("player", {})
    node["local_position"] = {"x": player_position[0], "y": player_position[1]}
    # ADR-048: Player как полноправный агент npc_positions. _resolve_reactive_movement ищет position.
    if not node.get("position"):
        _ps = scene_state.get("player_spatial", {})
        if _ps and _ps.get("position"):
            node["position"] = _ps["position"]


def _sync_game_time(scene_state: dict, shared_context: Any) -> None:
    """Синхронизирует game_time_seconds: scene_state → shared_context."""
    if scene_state.get("game_time_seconds") is not None:
        shared_context.game_time_seconds = scene_state["game_time_seconds"]
    else:
        env_time = scene_state.get("environment", {}).get("time_of_day", "07:00")
        shared_context.game_time_seconds = Calendar.parse_hhmm(env_time)


def _inject_spatial_service(life_engine: Any, campaign_id: str, scene_state: dict) -> None:
    """Инжектирует SpatialService в LifeEngine для семантической навигации."""
    from app.services.spatial.spatial_service import SpatialService

    loc_id = scene_state.get("location_id", "")
    if not loc_id:
        return
    from app.services.spatial.spatial_factory import SpatialFactory
    svc = SpatialFactory.build_for_campaign(
        campaign_id=campaign_id, location_id=loc_id, scene_state=scene_state,
    )
    if svc:
        life_engine.set_spatial_service(svc)


def _reconcile_elapsed_time(life_engine: Any, campaign_id: str, scene_state: dict) -> None:
    """ADR-047: Аналитический декэй вместо TICK_CATCHUP (если >60с реального времени)."""
    last_save_ts = scene_state.get("last_save_real_time", 0)
    elapsed_real = _time.time() - last_save_ts if last_save_ts else 0
    if elapsed_real > 60:
        life_engine.reconcile_state(campaign_id, elapsed_real)
        logger.info(f"[SCENE_INIT] Reconciled state for {elapsed_real:.0f}s elapsed")


def _apply_life_changes(
    loop: Any, campaign_id: str, location: str,
    scene_state: dict, shared_context: Any,
    life_changes: list, life_intents: list,
) -> None:
    """Применяет изменения LifeEngine: сцена, координаты, прибытия NPC."""
    if not life_changes:
        return
    loop.scene_manager.apply_changes(campaign_id, life_changes, scene_state)
    logger.warning(f"[LIFE_ENGINE] {len(life_changes)} изменений применено")

    if life_intents:
        logger.info(f"[SCENE_INIT] {len(life_intents)} MovementIntents (deferred)")
        loop.scene_manager._enrich_local_positions(campaign_id, scene_state)

    arrivals = list({
        c.target for c in life_changes
        if c.type.value == "npc_position" and c.field == "location" and c.value == location
    })
    if arrivals:
        shared_context.npc_arrivals = arrivals
        logger.warning(f"[LIFE_ENGINE] Прибыли в сцену: {arrivals}")


def _run_life_engine_tick(
    loop: Any, campaign_id: str, location: str,
    scene_state: dict, shared_context: Any,
) -> None:
    """LifeEngine: аналитическое согласование + 1 тик расписания."""
    from app.services.npc.life_engine import get_life_engine

    engine = get_life_engine()
    _inject_spatial_service(engine, campaign_id, scene_state)
    _reconcile_elapsed_time(engine, campaign_id, scene_state)

    life_changes, life_intents = engine.tick(
        campaign_id, scene_state, runtime_path=loop._get_npc_runtime_path(campaign_id),
    )
    _apply_life_changes(loop, campaign_id, location, scene_state, shared_context, life_changes, life_intents)


def _check_economy_tracker(loop: Any, campaign_id: str) -> None:
    """EconomyTracker: дневная проверка INCOME/SOCIAL (раз в TICKS_PER_DAY)."""
    from app.core.constants import TICKS_PER_DAY
    from app.services.npc.life_engine import get_life_engine

    current_tick = get_life_engine().get_current_tick(campaign_id)
    if current_tick <= 0 or current_tick % TICKS_PER_DAY != 0:
        return

    eco_profiles = loop._svc.get_or_create_economic_profiles(campaign_id)
    base_drives = loop._svc.collect_base_drives(campaign_id)
    inc_sat, soc_sat = loop._svc.economy_tracker.check_daily_needs(
        profiles=eco_profiles, npc_drives=base_drives,
        tick=current_tick, location_locked=False,
    )
    loop._svc.economy_tracker.reset_daily()
    if inc_sat or soc_sat:
        logger.warning(f"[ECO_TRACKER] day_end: income={inc_sat} social={soc_sat} satisfied")


def _load_or_create_scene(
    loop: Any, campaign_id: str, location: str,
    preserved_game_time: float | None, campaign_state: Any,
) -> dict:
    """Загружает scene_state или создаёт новую сцену с сохранением времени."""
    scene_state = loop.scene_manager.get_scene_state(campaign_id, location)
    if scene_state is not None:
        return scene_state

    # Новая сцена — не сбрасываем время (БАГ H FIX)
    time_of_day = _resolve_initial_time(preserved_game_time, campaign_state)
    scene_state = loop.scene_manager.initialize_scene(campaign_id, location, time_of_day)

    if preserved_game_time is not None:
        scene_state["game_time_seconds"] = preserved_game_time

    # ADR-0XX: Сохраняем монотонный тик при перезагрузке сцены
    if hasattr(loop, '_preserved_tick') and loop._preserved_tick:
        scene_state["tick"] = loop._preserved_tick

    _materialize_npc_inventory(loop, scene_state)
    loop.scene_manager.save_scene_state(campaign_id, scene_state)
    logger.info(f"[GAME_LOOP] Новая сцена: {location}")
    return scene_state


# ── Публичные функции ─────────────────────────────────────────────────


def init_scene_state(
    loop: Any,
    campaign_id: str,
    location: str,
    shared_context: Any,
    campaign_state: Any = None,
    player_position: tuple[float, float] | None = None,
) -> dict:
    """Фаза 1: загрузка/инициализация сцены, LifeEngine, EconomyTracker.

    Возвращает scene_state dict — центральный state для всего пайплайна.
    """
    preserved_game_time = _extract_preserved_time(shared_context)

    # 1. Загрузка или создание сцены
    try:
        scene_state = _load_or_create_scene(
            loop, campaign_id, location, preserved_game_time, campaign_state,
        )
    except Exception as e:
        logger.warning(f"[GAME_LOOP] SceneState error: {e}")
        return {}

    # 2. Позиция игрока + синхронизация времени
    _update_player_position(scene_state, player_position)
    _sync_game_time(scene_state, shared_context)

    # 3. LifeEngine: согласование + тик расписания
    try:
        _run_life_engine_tick(loop, campaign_id, location, scene_state, shared_context)
    except Exception as e:
        logger.warning(f"[LIFE_ENGINE] Ошибка тика: {e}")

    # 4. EconomyTracker: дневная проверка
    try:
        _check_economy_tracker(loop, campaign_id)
    except Exception as e:
        logger.warning(f"[ECO_TRACKER] Error (non-blocking): {e}")

    return scene_state


def _resolve_location_from_save(loop: Any, campaign_id: str) -> str:
    """Определяет текущую локацию из сохранения, fallback — DEFAULT_LOCATION_ID."""
    try:
        existing = loop.scene_manager._read_campaign_json(campaign_id)
        raw = existing.get("scene_state", existing)
        if isinstance(raw, dict) and raw.get("location_id"):
            return raw["location_id"]
    except Exception as e:
        logger.warning(f"[GAME_LOOP] Ошибка получения location_id: {e}")
    from app.core.constants import DEFAULT_LOCATION_ID
    return DEFAULT_LOCATION_ID


def _enrich_walls_from_editor(scene_state: dict, editor_data: dict) -> list:
    """Извлекает стены и объекты из editor JSON, возвращает список стен."""
    walls = [
        {"x1": w["x1"], "y1": w["y1"], "x2": w["x2"], "y2": w["y2"]}
        for w in editor_data.get("walls", [])
    ]
    for i, obj in enumerate(editor_data.get("objects", [])):
        obj_id = obj.get("id", f"obj_{i}")
        if obj_id not in scene_state.get("objects", {}):
            scene_state.setdefault("objects", {})[obj_id] = {
                "name": obj.get("name", obj.get("type", "объект")),
                "type": obj.get("type", ""),
                "state": obj.get("properties", {}).get("open", True) and "intact" or "closed",
                "position": obj.get("position", {}),
                "size": obj.get("size", {}),
                "interactable": True,
            }
    return walls


def ensure_scene_initialized(loop: Any, campaign_id: str) -> dict:
    """Гарантирует что scene_state существует и содержит стены из editor JSON.
    Если сцена есть но стены пустые — только добавляет стены, не трогает NPC и location_id.
    """
    from app.services.campaign_state_service import get_campaign_state_service

    campaign_state = get_campaign_state_service().get_campaign_state(campaign_id)
    location = _resolve_location_from_save(loop, campaign_id)
    scene_state = loop.scene_manager.get_scene_state(campaign_id, location)

    # Сцена не существует — полная инициализация
    if scene_state is None:
        time_of_day = campaign_state.metadata.get("time_of_day", "12:00") if campaign_state else "12:00"
        return loop.scene_manager.initialize_scene(campaign_id, location, time_of_day)

    # Стены уже есть — ничего не делаем
    if scene_state.get("spatial_walls"):
        loop.scene_manager.save_scene_state(campaign_id, scene_state)
        return scene_state

    # Стены пустые — обогащаем из editor JSON
    editor_data = (
        loop.scene_manager._find_editor_location(campaign_id, location)
        or loop.scene_manager._find_first_editor_location(campaign_id)
    )
    if editor_data:
        walls = _enrich_walls_from_editor(scene_state, editor_data)
        if walls:
            scene_state["spatial_walls"] = walls
            loop.scene_manager.save_scene_state(campaign_id, scene_state)

    return scene_state