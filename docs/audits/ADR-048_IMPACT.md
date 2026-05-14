# ADR-048 Impact Audit

## Измененный АДР
ADR-048 (Single Source Spatial Authority)

## Тип изменения
STANDARD

## Измененные домены (Changed Domains)
- SPATIAL
- SOCIAL (utility calculation)

## Связанные потребители (Downstream Consumers)
- MovementEngine (читает MovementIntent.target_node_id)
- SceneStateManager (читает MovementIntent.local_target_xy)
- TransitTracker (вычисляет длительность транзита)
- Frontend SceneRenderer (читает active_traversals)

## Влияние на производительность (Runtime Impact)
- RAM Delta: 0
- VRAM Delta: 0
- Tick Latency Delta: -0.5ms (устранен вызов spatial_service.get_nearest для известных сущностей)

## Песочные тесты (Sandbox Tests)
- tests/sandbox/oscilloscope_closed_loop.py — Проверка замкнутости: Команда → fear_delta → Резолв позиции Игрока → Движение

## Откат (Rollback)
1. Вернуть чтение scene_state.get("player_spatial", {}) в _resolve_reactive_movement
2. Вернуть хардкод _MACRO_ZONES и поиск через get_nearest(x, y)
3. Удалить тест oscilloscope_closed_loop.py
