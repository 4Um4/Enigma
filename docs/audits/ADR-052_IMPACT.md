# ADR-052 Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

`ADR-052` [STANDARD] **IMPACT**
# ADR-052 Impact Audit: LOD0 Micro-Movement Pipeline Restoration
## Changed Domains
- spatial (movement resolution), npc_tick_pipeline (intent generation)

## Downstream Consumers
- MovementEngine (теперь гарантированно получает local_target_xy при совпадении зон)
- SceneStateManager (корректно применяет SceneChange(field="local_position"))

## Runtime Impact
- Снижение Tick Latency: макро-путь (load_graph/get_nearest) полностью обходится при микро-сближении.
- Устранение Phantom-бага: NPC больше не замирают при попытке подойти к игроку в той же макро-зоне из-за несовпадения строк ("main_hall" vs "tavern:main_hall").

## Sandbox Tests
- backend/tests/sandbox/test_micro_macro_locomotion.py (2 passed)

## Rollback
- Удалить нормализацию current_base/target_base в _resolve_reactive_movement.
- Вернуть строгое сравнение target_node_id == current_node.

