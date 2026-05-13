"""
Инициализация состояния сцены на старте тика.
1. Загрузка или инициализация scene_state из SceneManager.
2. Патчинг shared_context из scene_state (для доступа в пайплайне   без передачи аргументов).
3. Тик LifeEngine для обновления NPC (без LLM, чистая логика    поведения).
4. Проверка EconomyTracker для ежедневных INCOME/SOCIAL драйвов.

На выходе — обновлённый scene_state, сохранённый в SceneManager, и патчинг shared_context.
На этом этапе НЕ происходит никаких LLM-вызовов, только чистая логика и обновление стейта.
Например, LifeEngine может переместить NPC, и эти изменения будут сохранены в scene_state и доступны в пайплайне для рендера и взаимодействия.
Например, EconomyTracker может обновить статус драйвов NPC, и эти изменения также будут сохранены и доступны для рендера и взаимодействия.

Назначение — обеспечить, что к моменту рендера у нас уже есть актуальное состояние мира с учётом логики NPC и экономики, без блокирующих LLM-вызовов.

Зависимости:
- SceneManager для загрузки/сохранения состояния сцены.
- LifeEngine для тика NPC.
- EconomyTracker для ежедневной проверки драйвов.

Основные сущности:
- scene_state: dict, центральный стейт для сцены, который сохраняется в SceneManager и патчится в shared_context.
- shared_context: объект, который передаётся в пайплайн и патчится из   scene_state для доступа к данным сцены без передачи аргументов. 
- campaign_state: состояние кампании, которое может содержать метаданные, например, время дня, используемое при инициализации новой сцены.
- life_changes: список изменений от LifeEngine, которые применяются к scene_state.
- npc_arrivals: список NPC, которые прибыли в сцену в результате тика LifeEngine, сохраняется в shared_context для использования в пайплайне (например, для триггеров прибытия).
- economy_check: результат проверки EconomyTracker, который может логироваться или использоваться для обновления состояния NPC. 
- Возвращаемое значение: обновлённый scene_state dict, который уже сохранён в SceneManager и патчен в shared_context.  Этот dict будет использоваться в дальнейшем в пайплайне для рендера, взаимодействия и других систем.

TODO: по мере роста логики и количества данных в scene_state может потребоваться реорганизация в отдельные функции/классы для управления сложностью (например, отдельные функции для LifeEngine и EconomyTracker, или даже отдельные сервисы).
TODO: добавить более детальное логирование для каждой фазы, чтобы облегчить отладку и понимание происходящего (например, сколько изменений от LifeEngine, какие NPC прибыли, результаты проверки EconomyTracker).
TODO: рассмотреть возможность добавления метрик для мониторинга производительности и поведения (например, время выполнения каждой фазы, количество изменений от LifeEngine, удовлетворённость драйвов в EconomyTracker).

path: backend/app/services/game_loop/scene_init.py
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


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
    # Удалено: import patch_scene_state (ADR-0015)
    from app.services.npc.npc_loader import materialize_inventory, get_item_display_name
    from app.services.npc.life_engine import get_life_engine
    from app.core.calendar import Calendar

    scene_state: dict = {}
    try:
        scene_state = loop.scene_manager.get_scene_state(campaign_id, location)
        if scene_state is None:
            time_of_day = "07:00"
            if campaign_state:
                time_of_day = campaign_state.metadata.get("time_of_day", "07:00")
            scene_state = loop.scene_manager.initialize_scene(
                campaign_id, location, time_of_day
            )
            # Материализуем инвентарь NPC из вероятностных правил L0.
            # Только для новой сцены — при рестарте стейт уже содержит objects.
            _npc_scene_ids = set(scene_state.get("npc_positions", {}).keys())
            for _raw_npc in loop._load_npcs():
                _npc_id = _raw_npc.get("id") or _raw_npc.get("npc_id")
                if _npc_id not in _npc_scene_ids:
                    continue
                if not _raw_npc.get("carried_objects"):
                    continue
                try:
                    _inv = materialize_inventory(_raw_npc)
                    for _item_id, _qty in _inv.items():
                        _obj_key = f"{_item_id}_owned_by_{_npc_id}"
                        if _obj_key not in scene_state["objects"]:
                            scene_state["objects"][_obj_key] = {
                                "name":         get_item_display_name(_item_id),
                                "state":        "present",
                                "interactable": True,
                                "owner":        _npc_id,
                                "count":        _qty,
                            }
                except Exception as _e:
                    logger.warning(f"[GAME_LOOP] Ошибка материализации инвентаря {_npc_id}: {_e}")
            loop.scene_manager.save_scene_state(campaign_id, scene_state)
            logger.info(f"[GAME_LOOP] Новая сцена: {location}")

        # Применяем позицию игрока от фронтенда в памяти (атомарный commit_tick сохранит)
        if player_position is not None and scene_state.get("player_spatial", {}).get("local_position"):
            scene_state["player_spatial"]["local_position"]["x"] = player_position[0]
            scene_state["player_spatial"]["local_position"]["y"] = player_position[1]

        # Контекст будет перестроен на следующем тике с актуальным scene_state (ADR-0015)

        # Инициализация game_time_seconds из scene_state (абсолютное время, переживающее дни)
        if scene_state.get("game_time_seconds"):
            shared_context.game_time_seconds = scene_state["game_time_seconds"]
        else:
            # Fallback: legacy time_of_day (теряет день/год, но часы идут)
            _env_time = scene_state.get("environment", {}).get("time_of_day", "07:00")
            shared_context.game_time_seconds = Calendar.parse_hhmm(_env_time)
    except Exception as e:
        logger.warning(f"[GAME_LOOP] SceneState error: {e}")

    # 4.1. LifeEngine — тик расписания NPC (без LLM, чистая логика)
    try:
        _life_engine = get_life_engine()
        # ADR-043: Ретроактивная симуляция (TICK_CATCHUP) запрещена.
        # Выполняется ровно ОДИН тик для инициализации расписания при загрузке сцены.
        from app.services.spatial.spatial_service import SpatialService
        _loc_id = scene_state.get("location_id", "")
        _spatial_svc = None
        if _loc_id:
            _spatial_svc = SpatialService.build_for_location(
                campaign_id=campaign_id,
                location_id=_loc_id,
                scene_state=scene_state,
            )
        if _spatial_svc:
            _life_engine.set_spatial_service(_spatial_svc)

        _life_changes = _life_engine.tick(campaign_id, scene_state, runtime_path=loop._get_npc_runtime_path(campaign_id))
        if _life_changes:
            loop.scene_manager.apply_changes(campaign_id, _life_changes, scene_state)
            # Восстанавливаем visual-координаты после мутаций LifeEngine/MovementEngine
            # MovementEngine резолвит узлы графа в local_position — перебивая editor JSON
            loop.scene_manager._enrich_local_positions(campaign_id, scene_state)
            logger.warning(f"[LIFE_ENGINE] {len(_life_changes)} изменений применено")
            _arrivals = list({
                c.target for c in _life_changes
                if c.type.value == "npc_position"
                and c.field == "location"
                and c.value == location
            })
            if _arrivals:
                shared_context.npc_arrivals = _arrivals
                logger.warning(f"[LIFE_ENGINE] Прибыли в сцену: {_arrivals}")
    except Exception as _le:
        logger.warning(f"[LIFE_ENGINE] Ошибка тика: {_le}")

    # 4.2. EconomyTracker — дневная проверка INCOME/SOCIAL (раз в TICKS_PER_DAY)
    try:
        from app.core.constants import TICKS_PER_DAY
        _current_tick = _life_engine.get_current_tick(campaign_id)
        if _current_tick > 0 and _current_tick % TICKS_PER_DAY == 0:
            _eco_profiles = loop._svc.get_or_create_economic_profiles(campaign_id)
            _base_drives = loop._svc.collect_base_drives(campaign_id)
            _inc_sat, _soc_sat = loop._svc.economy_tracker.check_daily_needs(
                profiles=_eco_profiles,
                npc_drives=_base_drives,
                tick=_current_tick,
                # TODO: временная заглушка — нужно определить из scene_state (editor JSON)
                # будет удалено после: добавление флага "locked_location" в структуру локации
                location_locked=False,
            )
            loop._svc.economy_tracker.reset_daily()
            if _inc_sat or _soc_sat:
                logger.warning(f"[ECO_TRACKER] day_end: income={_inc_sat} social={_soc_sat} satisfied")
    except Exception as _et_err:
        logger.warning(f"[ECO_TRACKER] Error (non-blocking): {_et_err}")

    return scene_state


def ensure_scene_initialized(loop: Any, campaign_id: str) -> dict:
    """Гарантирует что scene_state существует и содержит стены из editor JSON.
    Если сцена есть но стены пустые — только добавляет стены, не трогает NPC и location_id.
    """
    from app.services.campaign_state_service import get_campaign_state_service

    campaign_state = get_campaign_state_service().get_campaign_state(campaign_id)

    # Определяем текущую локацию из сохранения
    location = "tavern_silver_wolf"  # fallback
    try:
        existing = loop.scene_manager._read_campaign_json(campaign_id)
        _ss_raw = existing.get("scene_state", existing)
        loc_id = _ss_raw.get("location_id") if isinstance(_ss_raw, dict) else None
        if loc_id:
            location = loc_id
    except Exception as e:
        logger.warning(f"[GAME_LOOP] Ошибка получения location_id: {e}")

    scene_state = loop.scene_manager.get_scene_state(campaign_id, location)

    # Сцена не существует — полная инициализация
    if scene_state is None:
        time_of_day = campaign_state.metadata.get("time_of_day", "12:00") if campaign_state else "12:00"
        return loop.scene_manager.initialize_scene(campaign_id, location, time_of_day)

    # Сцена есть — проверяем стены
    if scene_state.get("spatial_walls"):
        loop.scene_manager.save_scene_state(campaign_id, scene_state)
        return scene_state

    # Стены пустые — добавляем из editor JSON без переинициализации
    editor_data = loop.scene_manager._find_editor_location(campaign_id, location)
    if editor_data is None:
        editor_data = loop.scene_manager._find_first_editor_location(campaign_id)

    if editor_data:
        walls = []
        for wall in editor_data.get("walls", []):
            walls.append({"x1": wall["x1"], "y1": wall["y1"], "x2": wall["x2"], "y2": wall["y2"]})
        # Объекты из editor
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
        if walls:
            scene_state["spatial_walls"] = walls
            loop.scene_manager.save_scene_state(campaign_id, scene_state)

    return scene_state