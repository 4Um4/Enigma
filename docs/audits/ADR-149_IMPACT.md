# ADR-149 Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

`ADR-149` [STANDARD] **IMPACT**
# ADR-149 Impact Audit: Schedule Freeze — Need Override & Two-Layer Dispatch

## Changed Domains
- LifeEngine (need-driven dispatch, schedule generation, routine state)
- DecisionHub (indirect — receives different intents)

## Downstream Consumers
- MovementEngine (receives need-driven intents instead of schedule intents)
- StateApplicator (applies routine.current updates from need-driven wins)
- _tick_needs (reads routine.current to reset need values)
- SpatialService.resolve_node() (used by need-driven semantic fallback)

## Runtime Impact
- RAM: No change (same data structures)
- Tick Latency: Slight decrease (schedule generation skipped when need-driven wins)
- Rate: 0.070 → 2.0/tick (28.5x improvement)

## Sandbox Tests
- DriftLaboratory mass_traversal (200 ticks): rate=2.0/tick, drift_C=0.25%

## Rollback
1. Remove need_intent.priority=0.8 override in life_engine.py:_simulate_major
2. Remove _has_critical_need check before schedule generation
3. Remove routine["current"] sync after need-driven win
4. Revert _NEED_THRESHOLD to 0.7 and _NEED_DECAY_PER_TICK to 0.05

## Key Files Changed
- backend/app/services/npc/life_engine.py (3 fixes + 2 parameter changes)



Files: N/A
