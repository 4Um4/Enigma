# ADR-O-301 Impact Audit: Kernel Isolation Repair v0.1
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

## Changed Domains
- DOM-01: FOUNDATION (Core Pipeline)
- DOM-02: WILL, PRESSURE & DECISION
- DOM-04: SPATIAL & LOCOMOTION
- DOM-05: PHYSIOLOGY & COMBAT

## Downstream Consumers
- `DecisionHub` (получает deterministic RNG)
- `MovementEngine` (коллизии и микро-перемещения)
- `StateApplicator` (генерация ран)
- `LifeEngine` (события idle и Social Drift)

## Runtime Impact
- **CPU:** Незначительное увеличение из-за хэширования SHA256 при создании RNG (компенсируется O(1) доступом).
- **RAM:** +N байт на каждый `KernelRNG` экземпляр (передаётся по ссылке, не кэшируется).
- **Каузальность:** 100% Replay Determinism. Same (tick, npc_id) → same RNG sequence.

## Sandbox Tests
- `backend/tests/test_kernel_rng.py` (6 passed)
- `DriftLaboratory` (comparisons=308, rate=1.540/tick — стабильно)

## Rollback
- Откатить STEP 8 (state_applicator) → STEP 1 (kernel_rng.py).
- Возврат к `random.Random(seed)` в `DecisionHub` и `random.*` в сервисах.
