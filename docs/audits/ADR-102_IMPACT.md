# ADR-102 Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

`ADR-102` [STANDARD] **IMPACT**
# ADR-102 Impact Audit: SpatialService replaces load_graph() + FLEE Fix

## Changed Domains
- SPATIAL (spatial_runtime.py, spatial_service.py, scene_state_manager.py)
- MOVEMENT (npc_tick_pipeline.py)
- PRESENTATION (game_screen.py, scene_renderer.py)

## Downstream Consumers
- `spatial_query_service.py` — читает `resolve_distance_between_entities`
- `perception_filter.py` — вызывает `extract_scene_for_npc`
- `scene_renderer.py` — читает `spatial_obstacles[].type` для спрайтов
- `sprite_resolver.py` — маппит `type` на тайлы

## Runtime Impact
- RAM: Нет изменений (SpatialService уже кэшируется в TickOrchestrator)
- Latency: `build_for_location` warm = 0.8ms, не влияет на тиковый бюджет
- VRAM: Нет изменений

## Fixes Applied
1. **spatial_obstacles.type** — проброс `type` из editor JSON через бэкенд на фронтенд (2 места в scene_state_manager.py)
2. **campaign_id в scene_state** — инжект для SpatialService.build_for_location()
3. **load_graph() → SpatialService** — замена мёртвого load_graph() (возвращал 0 узлов) на работающий SpatialService
4. **get_furthest exclude_node_ids** — исключение текущего узла NPC из FLEE-кандидатов
5. **FLEE normalize_id** — нормализация legacy ID перед сравнением (room_1 != tavern:room_1)
6. **_old_lp UnboundLocalError** — фикс в game_screen.py
7. **Двойной else блок** — синтаксический фикс в game_screen.py

## Known Remaining Issues
1. **TraversalState from_node** — обновляется после position change, показывает тот же узел что и target
2. **Node roles** — комнаты из Map Editor не имеют ролей (все DEFAULT), нет ENTRANCE/TRANSITION для реального бегства
3. **Только 2 узла** — граф таверны имеет только room_0 и room_1, FLEE осциллирует между ними

## Sandbox Tests
- `test_spatial_service_flee_excludes_current` — ручная верификация через python -c
- `test_obstacle_type_propagation` — ручная верификация через python -c
- Runtime: `python game_launcher.py` — FLEE чередует room_0↔room_1 корректно

## Rollback
1. Восстановить `from app.services.spatial.location_graph import load_graph` в spatial_runtime.py
2. Удалить `"type": obj.get("type", "decoration")` из scene_state_manager.py (2 места)
3. Удалить `scene["campaign_id"] = campaign_id` из scene_state_manager.py
4. Убрать `exclude_node_ids` из get_furthest() и вызова в npc_tick_pipeline.py
5. Убрать `_canonical_current` нормализацию в npc_tick_pipeline.py


Files: N/A
