# ADR-O-355 Impact Audit: Modifier Contract v1

> Этот файл — детальный аудит ADR-O-355. Единый атлас: `docs/ADR (Architecture Decision Records).md`

## Changed Domains
- Decision (DecisionHub.apply_modifiers)
- Cognitive Interface (все источники модификаторов: social, epistemic, drive, reputation, memory, contract, eco)

## Downstream Consumers
- `DecisionHub.compute()` — вызывает `apply_modifiers()` вместо inline циклов
- Все источники модификаторов (`social_modifiers`, `epistemic_modifiers`, `drive_modifiers`, и т.д.) — должны предоставлять `Dict[str, float]`
- `NpcTickPipeline.run()` — собирает модификаторы и передаёт в `compute()`

## Runtime Impact
- RAM: нет изменений (копия scores ~1KB)
- Latency: O(n×m) где n = количество словарей модификаторов, m = размер каждого. Раньше тоже O(n×m), но inline. Выделение в функцию не добавляет overhead.
- Purity: `apply_modifiers` создаёт копию `dict(scores)`, не мутирует вход.

## Sandbox Tests
- SUPERBOX-011: Modifier composition (social + epistemic = additive) — PASS
- SUPERBOX-012: Isolation / additivity (ΔE=E, ΔS=S, ΔE+S=E+S, coupling=0) — PASS
- SUPERBOX-013: Commutativity + purity (apply(E,S)==apply(S,E), non-mutating) — PASS

## Rollback
1. Восстановить inline циклы `if eco_modifiers: for ...` в `DecisionHub.compute()`
2. Удалить `apply_modifiers` static method
3. Удалить `epistemic_modifiers` параметр из `compute()`