# ADR-311 Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

## Changed Domains
- Core Pipeline (TickOrchestrator)
- State Management (SceneStateManager)
- GameLoop

## Downstream Consumers
- SceneStateManager.commit_tick_result() — теперь принимает валидный, мутированный снимок.
- WorldSnapshotBuilder.build() — получает актуальные ctive_traversals и game_time_seconds.

## Runtime Impact
- Инвариант INV-TIME-GROW теперь проходит (время растёт).
- Инвариант INV-NPC-MOVE теперь проходит (транзиты завершаются и применяются).
- DriftLaboratory отрабатывает без ошибок.

## Sandbox Tests
- ackend/tests/IPT.py (5/5 passed)

## Rollback
- Удалить поле inal_scene_state из TickResultDTO.
- Убрать возврат ctx.scene_state из TickOrchestrator.execute().
- Верратить коммит _scene в GameLoop.idle_tick.
