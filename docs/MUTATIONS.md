"""
Формат:
[SESS_01] 02.05.26: Создан domain/deltas.py. Внедрен DamageDelta. Изменен NPCState (добавлено поле pain_threshold).[SESS_02] 03.05.26: Ошибка. CombatResolver мутировал стейт напрямую. Исправлено: вынесено в StateApplicator.
Запиши в формате MUTATIONS лог того, какие сущности и DTO были созданы или изменены в этой сессии. Формат: [ID_СЕССИИ] Дата: Описание изменения (что добавлено/удалено).
"""
---
[SESS_05] 27.04.26: Изменен `ProactiveDecision` (поле `deltas_dict: Dict[str, Any]` заменено на `deltas: StateDeltas`). Изменен `phase_2_world_tick.py` (ручная мутация стейта заменена на `StateApplicator.apply_deltas_only()`). Обновлены комментарии в `state_delta.py` и `state_applicator.py`.

[SESS_06] 27.04.26: Создан `backend/app/models/phase8.py` (сущности: `Phase8Context(frozen=True)`, `Phase8Result`, `Phase8Handler(Protocol)`). Изменен `PerceptionSubscriber` (добавлены `name`, `drain_events()`, метод `apply()` заменен на `handle(events, ctx) -> Phase8Result`). Изменен `SocialSubscriber` (добавлены `name`, `drain_events()`, метод `apply()` заменен на `handle(events, ctx) -> Phase8Result`). Изменен `TickOrchestrator` (методы `_phase_8_handlers` и `_phase_8_player_handlers` заменены на `_phase_8_drain_secondary()`, добавлен `_apply_phase8_result()`, удалены DEPRECATED-методы `apply_perception` и `propagate_social`).

[SESS_07] 27.04.26: Изменен `TickOrchestrator` (добавлен фасад `get_current_tick()`). Изменен `GameLoop` (добавлен фасад `get_current_tick()`). Изменен `WorldRoutes` (чтение `snapshot_tick` заменено на `_game_loop.get_current_tick()`). Изменен `WorldSnapshotBuilder` (поле `version` берется из аргумента `tick`, а не из `scene_state`). Изменен `SceneStateManager` (удалена инициализация и инкремент `snapshot_tick`, добавлен инкремент `_version` в `commit()`, добавлена миграция и очистка `snapshot_tick` в `get_scene_state()` и `save_scene_state()`).

[SESS_08] 27.04.26: Изменен `StateDeltas` (добавлено поле `npc_id: Optional[str] = None` для маршрутизации дельт). Изменена функция `propagate_social_rumors()` (сигнатура изменена на чистую функцию, возвращающую `Tuple[int, List[StateDeltas]]`, удалена мутация `all_npcs_raw` и `tick_ctx`). Изменен `SocialSubscriber.handle()` (возвращает `Phase8Result(deltas=...)` вместо мутации и флага `prop_dirty`). Изменен `TickOrchestrator._apply_phase8_result()` (добавлено применение `StateDeltas` с `npc_id` к `all_npcs_raw`).
---

---
[SESS_01] Дата: Текущая: GameLoop.idle_tick() — новый метод, делегирует в TickOrchestrator.execute() (idle mode). TickResultDTO импортирован.
[SESS_02] Дата: Текущая: GameLoopBridge.idle_tick() — новый метод, конвертирует WorldSnapshotDTO→dict через asdict(). Удалены get_life_engine() и get_npc_runtime_path() (deprecated, нет потребителей).
[SESS_03] Дата: Текущая: DirectGateway.idle_tick() — переписан: ~50 строк ручной работы с LifeEngine → 5 строк делегирования в bridge.idle_tick().
[SESS_04] Дата: Текущая: routes.py idle_tick() — переписан: ~30 строк ручного извлечения scene_state + отдельный TickOrchestrator → 5 строк через game_loop.idle_tick(). Устранён баг: старый TickOrchestrator создавался без memory_manager и event_bus.
[SESS_05] Дата: Текущая: game_screen.py idle_tick обработка — npc_positions теперь читается из world_snapshot (канонический источник, фаза 9) с fallback. Добавлена синхронизация player_position, time_of_day, weather из world_snapshot. Исправлен баг: setdefault("npc_id") → setdefault("npc_positions").
[SESS_06] Дата: Текущая: phase_1_input.py — добавлен _INTENSITY_MAP, publish_classified_player_event() теперь включает intensity в EventDTO.payload.
[SESS_07] Дата: Текущая: propagation.py — propagate_social_rumors() +параметр events. Канонический путь: intensity/event_type/actor_id из EventDTO.payload. Fallback на dm_result.event_context. Заменены _evt.* на локальные переменные.
[SESS_08] Дата: Текущая: social_subscriber.py — handle() передаёт events в propagate_social_rumors().
[SESS_09] Дата: Текущая: perception_subscriber.py — handle() обрабатывает ВСЕ накопленные события вместо только events[-1]. set.update() для объединения.
[SESS_10] Дата: Текущая: TickOrchestrator.finalize_and_commit() — удалён (deprecated, заменён на execute_player_finalize(), нет потребителей).

[SESS_01] idle_tick реформа: GameLoop.idle_tick() — новый метод (делегирует в TickOrchestrator). GameLoopBridge.idle_tick() — новый метод (конвертация WorldSnapshotDTO→dict). DirectGateway.idle_tick() — 50→5 строк. routes.py idle_tick — 30→5 строк. Устранён баг: TickOrchestrator без memory_manager/event_bus.
[SESS_02] world_snapshot миграция: game_screen.py читает npc_positions из world_snapshot (фаза 9) с fallback. Синхронизация player_position/time_of_day/weather. Баг: setdefault("npc_id")→"npc_positions".
[SESS_03] intensity из EventDTO: phase_1_input.py +_INTENSITY_MAP, payload.intensity. propagation.py +events param, канонический путь EventDTO.payload, fallback dm_result.event_context. social_subscriber.py передаёт events.
[SESS_04] Perception мультисобытийность: perception_subscriber.py handle() — цикл по events, set.update() вместо events[-1].
[SESS_05] Удаление deprecated: TickOrchestrator.finalize_and_commit(), GameLoopBridge.get_life_engine(), GameLoopBridge.get_npc_runtime_path().
---
[SESS_03] 04.05.26: Интегрирован SpatialService v1.2. NpcTickServices: добавлено поле spatial_service. LifeEngine: добавлен DI через set_spatial_service, _make_random_events стал методом класса, хардкод "bar_area" заменен на svc.resolve_node(NodeRole.BAR). MovementEngine: добавлен DI, LocationGraph.find_path заменен на svc.find_path. SceneStateManager: _position_map удален, заменен на svc.get_node_label. GraphCompiler: добавлен _PROJECT_ROOT и get_connections. Данные: удалены _BUILTIN_NODES, блоки positions из location_templates.json, дубликат tavern.json.
---
---
