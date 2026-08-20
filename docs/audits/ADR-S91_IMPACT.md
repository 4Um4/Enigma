# ADR-S91 Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

`ADR-S91` [STANDARD] **IMPACT**
# ADR-S91 Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

## Changed Domains
- DOM-04: SPATIAL & LOCOMOTION

## Downstream Consumers
- `SteeringResolver` (читает `AffordanceVector`)
- `CollisionAvoidance` (читает `can_pass`)
- `TickOrchestrator` (владеет `DynamicAffordanceField`, вызывает `purge_hard_overrides` и `step_decay`)

## Runtime Impact
- RAM: `+50KB` на регион (кэш деформаций и следов в памяти).
- Tick Latency: `+0.1ms` (O(1) dict lookup при мерже базовой геометрии, Hard Overrides и Soft Traces).
- Очистка в Фазе 0.5 (TTL purge и exponential decay) предотвращает memory leak.

## Sandbox Tests
- `test_dynamic_affordance_field.py` (проверка применения, изоляции по регионам, TTL purge, decay).

## Rollback
- Удалить `DynamicAffordanceField` из `TickOrchestrator`.
- Вернуть `WorldTopologyProvider` к чистому чтению `is_point_in_bounds` без мержа деформаций.
- Удалить `DeformationRecord` и `TracePayload` из `motion_core.py`.


Files: N/A
