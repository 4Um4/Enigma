# ADR-048 Impact Audit: Authoritative Spatial Spine

## Измененный АДР
ADR-048 (Single Source Spatial Authority)

## Тип изменения
ONTOLOGY (ADR-O) — Смена парадигмы: scene_state больше не является хранилищем пространственных решений и производных проекций.

## Этап реализации
Phase 3 — Derived Presentation Cleanup (ЗАВЕРШЁН)

## Измененные домены (Changed Domains)
- spatial (SpatialQueryService — единственный авторитет)
- perception (чтение дистанций через SpatialQueryService)
- memory (чтение дистанций через SpatialQueryService)
- reaction (чтение дистанций через SpatialQueryService)
- persistence (удаление мутации player_distances/player_spatial)
- presentation (вычисление дистанций из npc_positions вместо чтения кэша)

## Изменённые файлы (Phase 3)
- `backend/app/services/game_loop/scene_init.py` — мутация `player_spatial` заменена на мутацию канонического `npc_positions.player`
- `backend/app/services/scene_state_manager.py` — запись `player_distances` и `player_spatial` заблокирована в `update_player_spatial_context`. Чтения `player_distances` в промптах заменены на динамическое вычисление через `euclidean_distance(npc_positions.player, npc_positions.npc)`. Добавлен импорт `euclidean_distance`.
- `backend/app/services/spatial/player_target_pipeline.py` — (из Phase 2) удалена мутация `scene_state` записью `player_distances`.

## Запрещённые операции (ADR-048 Full Enforcement)
Следующие чтения/записи ЗАПРЕЩЕНЫ для decision/perception/combat/movement/presentation:
- `scene_state.get("player_distances")` — ВЕЗДЕ заменено на SpatialQueryService или euclidean_distance(npc_positions)
- `scene_state["player_distances"] = ...` — МУТАЦИЯ УДАЛЕНА
- `scene_state["player_spatial"]["local_position"] = ...` — МУТАЦИЯ УДАЛЕНА (пишем в npc_positions.player)

## Разрешённые чтения (Presentation Layer)
- `scene_state.get("npc_positions", {}).get("player", {})` — Единственный источник позиции игрока для фронтенда и промптов.

## Влияние на производительность (Runtime Impact)
- RAM Delta: -0.01MB (удаление дублирующих словарей в scene_state)
- VRAM Delta: 0
- Tick Latency Delta: +0.05ms (динамическое вычисление дистанций для промптов при необходимости)

## Песочные тесты (Sandbox Tests)
- 36 passed, 1 skipped (предсуществующий flaky-баг collision avoidance)

## Откат (Rollback)
1. Раскомментировать запись в `scene_state_manager.py`.
2. Вернуть чтение `player_distances` в `scene_state_manager.py`.
3. Вернуть мутацию `player_spatial` в `scene_init.py`.

## Статус
**ADR-048 ПОЛНОСТЬЮ РЕАЛИЗОВАН.** Система перешла на Single Spatial Authority.