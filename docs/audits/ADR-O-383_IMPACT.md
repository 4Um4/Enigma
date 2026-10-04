# Impact Audit — ADR-O-383 [ONTO] Embodied Constraint — Chronic Body Axes → Feasibility (V1)
`ADR-O-383` [ONTO] **Embodied Constraint — Chronic Body Axes → Feasibility (V1)**
Files: backend/app/services/cfrm/pressure_translator.py, backend/tests/gameplay/test_gc09_body_causality.py
> Детальный аудит ОДНОГО ADR. Единый атлас: `docs/ADR (Architecture Decision Records).md`

## Changed Domains
- cfrm/body → decision: chronic-оси fatigue/energy в veto-словаре pressure_translator (cap 0.3, CALIBRATION_CANDIDATE)

## Downstream Consumers
- backend/app/services/cfrm/pressure_translator.py, backend/app/services/npc/decision_hub.py (feasibility-слой), ActionSpaceCompression

## Runtime Impact
- availability измотанного NPC сужается (FLEE/ATTACK/APPROACH/MANIPULATE, cap 0.3); прочие контуры байт-идентичны

## Sandbox Tests
- backend/tests/gameplay/test_gc09_body_causality.py (A Body Runtime / B-full Embodied Constraint oracle)

## Rollback
- исключить fatigue/energy из veto-словаря pressure_translator (возврат к acute-only: pain/shock/blood_loss)
