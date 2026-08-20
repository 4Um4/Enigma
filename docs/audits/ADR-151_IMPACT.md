# ADR-151 Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

`ADR-151` [STANDARD] **IMPACT**
# ADR-151 Impact Audit: Probe → Telemetry Transition

## Changed Domains
- TickOrchestrator (47 print probes reclassified)
- LifeEngine (5 probes reclassified)
- MovementEngine (6 probes reclassified)

## Downstream Consumers
- DriftLaboratory (reads print output for GATE_*/DRF_*/TIFL_DRIFT)
- CDS CausalObserver (reads stdout logs)
- Developer console (sees fewer verbose probes by default)

## Runtime Impact
- RAM: No change
- Tick Latency: Slight decrease (fewer print() syscalls in hot path)
- Observability: 🟢 Essential probes always visible, 🟡 Debug-level probes visible with DEBUG logging, 🔴 Noisy probes removed

## Sandbox Tests
- DriftLaboratory mass_traversal (200 ticks): rate=2.0/tick (stable after transition)
- Python compilation: All 3 files compile without errors

## Rollback
1. Convert logger.debug() back to print() for 🟡 Condensed probes
2. Restore 🔴 Removed probes from git history
3. Remove pass statements added for empty else blocks

## Key Files Changed
- backend/app/services/tick_orchestrator.py (12 removed, 10 condensed, 2 pass additions)
- backend/app/services/npc/life_engine.py (5 condensed)
- backend/app/services/spatial/movement_engine.py (1 condensed)



Files: N/A
