# ADR-O-366 [ONTOLOGY] OpportunityProducer: Production Wiring

> **Статус:** APPROVED (S216, Master v2)
> **Тип:** ONTOLOGY
> **Сессия:** S216

## Context

DEBT-OPP-PRODUCER: живой пайплайн (npc_tick_pipeline.py:559) не передаёт
`opportunity_ctx` → `OpportunityContext()` дефолт (attention=1.0, allies=0)
→ score=0.0 → скрытые действия (S209 STEAL + R6.3 BROKEN-unlocks)
недостижимы в живых тиках. Доказано в vivo: `thief_shadow:
intent=Intent.IDLE score=0.0` в 7 прогонах SMOKE-GORAN β.

## Decision

Минимальная инлайн-конструкция OpportunityContext в npc_tick_pipeline.py
перед compute (pipeline:559), из живого состояния мира per NPC per tick. O(1).

### Phase 1 (этот ADR)

| Поле | Источник | Реализация |
|---|---|---|
| player_attention | proximity proxy | clamp(1 − dist/R, 0, 1), R=10m |
| distance | SpatialQueryService.distance_player(npc_id) | real |
| allies | EpistemicContext.perceived_allies (len) | real, subjective |
| weapon_access | False (constant) | Phase 2, separate ADR |

### Architectural Invariant

Producer → OpportunityContext (DATA only).
Engine → score + unlocked_intents (EVALUATION).
DecisionHub → Intent selection (DECISION).

Producer MUST NOT produce Intent, unlocked_intents, scores, or filter actions.

### OpportunityEngine Formula (opportunity_engine.py:169-188)

    score = min(
      (1 - player_attention) × 0.35
    + min(distance / 30.0, 1.0) × 0.30
    + (weapon_access ? 1 : 0) × 0.20
    + min(allies / 4, 1.0) × 0.15
    , 1.0)
    threshold = 0.65; will_state gate: ("broken", "deceptive") only

### Behavioral Table (Phase 1: weapon=False)

allies=0: 0m→0.000 | 3m→0.135 | 10m→0.450 | 20m→0.550 | 30m→0.650✅
allies=3: 10m→0.5625 | 15m→0.6125 | 20m→0.6625✅ | 30m→0.7625✅

### Acceptance

A. Control (no producer): STEAL not in possible → IDLE (7 runs, baseline)
B. Experiment (producer): STEAL in live ticks when player ≥20m + allies≥3
C. Geometry: player close → score<0.65 → IDLE; player far → score≥0.65 → STEAL

## Files

- backend/app/services/npc/npc_tick_pipeline.py (inline construction + 1 param)

## Downstream

- DecisionHub.compute (already accepts:413)
- OpportunityEngine.calculate (already computes:145-206)
- SUPERBOX-AGENCY-STEAL S209 (β-harness injects explicitly — unaffected)

## Rollback

Remove `opportunity_ctx=_opp_ctx` from compute call → default OpportunityContext()

## NOT in this ADR

Phase 2: weapon_access from BodyTopology
Phase 3: facing-based attention (player body_heading → FOV → occlusion)
Calibration: W_*, thresholds, R → CalibrationProfile (021)