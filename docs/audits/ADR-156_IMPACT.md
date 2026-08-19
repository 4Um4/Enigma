# ADR-156 Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

`ADR-156` [STANDARD] **IMPACT**
# ADR-156 Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас: `docs/ADR (Architecture Decision Records).md`

## Changed Domains
- Spatial & Locomotion (Frontend)
- Player Cognition Pipeline

## Downstream Consumers
- `frontend/game_screen.py` (чтение позиции игрока для рендера и коллизий)
- `frontend/api_client.py` (сборка `scene_state`)

## Runtime Impact
- Устранён DOUBLE TRUTH: позиция игрока больше не хранится и не читается из двух разных мест (`player_spatial` и `npc_positions`).
- Снижено потребление RAM (удалён лишний словарь в `scene_state`).

## Sandbox Tests
- `backend/tests/test_player_cognition_pipeline.py`
- `backend/tests/test_player_target_extractor_r4.py`
- `backend/tests/test_spatial_runtime_r4.py`
- `backend/tests/test_tick_orchestrator_full_loop.py`

## Rollback
- Откатить изменения в `frontend/game_screen.py` (вернуть чтение `scene_state.get("player_spatial", {})`).
- Восстановить блоки `"player_spatial": {...}` в моках `scene_state` в указанных тестах.

