# ADR-SSOT-EPISTEMIC Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: docs/ADR (Architecture Decision Records).md

## Changed Domains
- Epistemic Core (Belief State)
- Foundation (State Mutation)

## Downstream Consumers
- elief_transition_engine.py (генерирует BeliefDelta)
- state_applicator.py (применяет BeliefDelta)
- 
pc_tick_pipeline.py (вызывает commit)
- models/npc/beliefs.py (хранит BeliefDelta)

## Runtime Impact
- **RAM:** Минимальное увеличение из-за создания BeliefDelta объектов.
- **Latency:** Микро-overhead на генерацию и применение delta вместо прямой мутации.

## Sandbox Tests
- 	ests/test_belief_single_writer.py
- 	ests/test_stage0_and_1_invariants.py::TestStage0Invariants::test_I0_4_no_belief_writers_outside_engine

## Rollback
- Вернуть прямую мутацию state.beliefs.update() в BeliefTransitionEngine (НЕ рекомендуется, возвращает Multi-Writer проблему).
