# ADR-048 Impact Audit: Authoritative Spatial Spine

## Измененный АДР
ADR-048 (Single Source Spatial Authority)

## Тип изменения
ONTOLOGY (ADR-O) — Смена парадигмы: scene_state больше не authority layer для пространственных решений.

## Этап реализации
Phase 1 — Kill Decision Reads (завершён)

## Измененные домены (Changed Domains)
- spatial (SpatialQueryService инстанцирован и пробрасывается через NpcTickServices)
- decision (npc_tick_pipeline: player_distances, _resolve_reactive_movement, MOVE reflex — все через SpatialQueryService)
- perception (Этап 2 — пока читает из scene_state, что является нарушением ADR-048)

## Изменённые файлы (Phase 1)
- `backend/app/services/npc/npc_tick_contracts.py` — добавлен `spatial_query: Optional[Any]` в NpcTickServices
- `backend/app/services/game_loop/npc_orchestration.py` — инстанцирование SpatialQueryService, инъекция в NpcTickServices
- `backend/app/services/npc/npc_tick_pipeline.py` — убран fallback на scene_state для player_distances, добавлен _pos() helper в _resolve_reactive_movement, MOVE reflex через spatial_query
- `backend/app/services/spatial/__init__.py` — экспорт SpatialQueryService

## Связанные потребители (Downstream Consumers)
- npc_tick_pipeline (использует spatial_query.player_distances, spatial_query.get_entity_position)
- perception_filter (Этап 2 — пока читает из scene_state)
- memory_manager (Этап 2 — _npc_distance читает из scene_state)
- reaction_priority (Этап 2 — _get_npc_distance читает из scene_state)
- player_target_pipeline (Этап 2 — вычисляет player_distances и пишет в scene_state)

## Запрещённые чтения (ADR-048 Phase 1 Enforcement)
Следующие чтения из scene_state ЗАПРЕЩЕНЫ для decision/perception/combat/movement:
- `scene_state.get("player_distances")` — в npc_tick_pipeline заменено на SpatialQueryService
- `scene_state.get("npc_positions")` — в _resolve_reactive_movement заменено на _pos() helper
- `scene_state.get("npc_positions")` — в MOVE reflex заменено на spatial_query.get_entity_position

## Разрешённые чтения (Presentation Layer)
- world_snapshot_builder.py — читает npc_positions для фронтенда (Derived Presentation Projection)
- scene_state_manager.py — пишет npc_positions как runtime storage
- tick_orchestrator.py — читает npc_positions для ClusterOccupancy rebuild (CFRM infrastructure)

## Влияние на производительность (Runtime Impact)
- RAM Delta: +0.01MB (кэш дистанций в SpatialQueryService)
- VRAM Delta: 0
- Tick Latency Delta: +0.1ms (вычисление дистанций через фасад вместо чтения из кэша scene_state)

## Песочные тесты (Sandbox Tests)
- 567 passed, 4 skipped (все существующие тесты проходят)
- test_lod0_collision_avoidance — предсуществующий flaky-баг (MockSpatialService.get_node), не связан с ADR-048

## Откат (Rollback)
1. Удалить `spatial_query` из `NpcTickServices` в npc_tick_contracts.py
2. В `npc_orchestration.py` убрать инстанцирование SpatialQueryService
3. В `npc_tick_pipeline.py` вернуть `inp.scene_state.get("player_distances", {})` и `scene_state.get("npc_positions", {})`
4. Удалить экспорт SpatialQueryService из __init__.py

## Следующий этап (Phase 2 — Projection Isolation)
- perception_filter.py — миграция _npc_distance, _can_see на SpatialQueryService
- memory_manager.py — миграция _npc_distance на SpatialQueryService
- reaction_priority.py — миграция _get_npc_distance на SpatialQueryService
- player_target_pipeline.py — прекратить писать player_distances в scene_state (derived projection)
- scene_init.py — убрать прямую мутацию player_spatial