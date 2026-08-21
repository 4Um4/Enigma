# ADR-314 Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

`ADR-314` [STANDARD] **IMPACT**
# ADR-314 Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

## Changed Domains
- `foundation` (Core Pipeline, TickContext)
- `will` (CausalValidator, BreakProgressEngine)
- `spatial` (CombatSubscriber Range Gate)

## Downstream Consumers
- `CombatSubscriber`: Получает рабочий `SpatialQueryService` через `ctx.shared_context.spatial_query`.
- `CausalValidator` (Sandbox Tests): Тесты COMMAND, COMBAT, RECOVERY, BREAK проходят.
- `BreakProgressEngine`: Эмитит `TraitDriftEvent` с корректным `event_type="pressure"`.

## Runtime Impact
- Восстановлена работоспособность `range gate` в бою. Атаки на дистанции > 3.0м теперь корректно блокируются.
- `compliance_bias` и `recent_directive` перестали затираться между Фазой 8 и 9, что позволяет NPC подчиняться приказам.
- `L1Chronicle` фиксирует событие `"pressure"` при сломе воли.

## Sandbox Tests
- `causal_validation.py`: 15 passed (включая COMMAND, COMBAT, RECOVERY, BREAK).
- `IPT.py`: 5 passed.
- `test_lod_arbitration.py`, `test_causal_bridge_integration.py`: 7 passed.

## Rollback
- Откатить изменения в `tick_utils.py`, `tick_orchestrator.py`, `integration.py` и `break_progress_engine.py` до состояния S115.
