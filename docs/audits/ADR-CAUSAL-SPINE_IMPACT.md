# ADR-CAUSAL-SPINE Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: docs/ADR (Architecture Decision Records).md

## Changed Domains
- Foundation (Pipeline, Provenance)
- Observability & Enforcement (CausalLedger)

## Downstream Consumers
- 	ick_orchestrator.py (создаёт WorldSnapshot)
- state_applicator.py (принимает cause, пишет CausalEntry)
- models/npc_state.py (API ledger: query, trace)
- models/psychological.py (Cause, CausalChain)
- event_compiler.py (потребляет WorldSnapshot)

## Runtime Impact
- **RAM:** Увеличение из-за хранения deep copy снапшота и объектов Cause/CausalEntry.
- **Latency:** Микро-overhead на создание снапшота и trace provenance, но это фундамент для детерминированного реплея.

## Sandbox Tests
- 	ests/test_stage0_and_1_invariants.py::TestStage1Invariants::test_I1_2_provenance_required
- 	ests/test_stage0_and_1_invariants.py::TestStage1Invariants::test_I1_4_causal_ledger_api_exists
- DriftLaboratory (0.0% drift, replay determinism)

## Rollback
- Удалить cause из StateApplicator.apply, убрать создание WorldSnapshot из TickOrchestrator (НЕ рекомендуется, разрушает causality и replay).
