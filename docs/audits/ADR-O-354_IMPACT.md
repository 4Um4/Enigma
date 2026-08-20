# ADR-O-354 Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

`ADR-O-354` [STANDARD] **IMPACT**
# ADR-O-354 Impact Audit: Epistemic Core Foundation

> Этот файл — детальный аудит ADR-O-354. Единый атлас: `docs/ADR (Architecture Decision Records).md`

## Changed Domains
- Epistemic (новый домен)
- Decision (DecisionHub, DecisionContext)
- Events (COMMUNICATION_CLAIM, ClaimEventSubscriber)
- Identity (граница с L1Chronicle)

## Downstream Consumers
- `DecisionHub.compute()` — получает `epistemic_modifiers: Dict[str, float]`
- `DecisionContext` — содержит `epistemic_context: Optional[EpistemicContext]`
- `NpcTickPipeline.run()` — будущая точка вызова `EpistemicContextResolver` (Phase 8, не реализовано)
- `GameLoop._register_npc_dialogue_subscriber()` — будущая точка регистрации `ClaimEventSubscriber` (Phase 8, не реализовано)

## Runtime Impact
- RAM: `EpistemicStore` — in-memory dict, ~1KB per NPC per belief. 20 NPC × 10 beliefs = ~200KB.
- Latency: `BeliefRevisionEngine.revise()` — O(1) per claim. `EpistemicContextResolver.resolve()` — O(n) где n = beliefs per agent.
- LLM: НЕ требуется. Все операции детерминированы.

## Sandbox Tests
- SUPERBOX-002: Proposition → Belief (pure unit test) — PASS
- SUPERBOX-003: EventBus → ClaimSubscriber → Belief — PASS
- SUPERBOX-006: EpistemicContext DTO — PASS
- SUPERBOX-007: DecisionContext composition — PASS
- SUPERBOX-008: EpistemicContextResolver — PASS
- SUPERBOX-010: Epistemic causality (score 0.19 → 0.79) — PASS

## Rollback
1. Удалить `backend/app/domain/epistemology.py`
2. Удалить `backend/app/services/npc/epistemic_store.py`
3. Удалить `backend/app/services/npc/belief_revision_engine.py`
4. Удалить `backend/app/services/npc/epistemic_context_resolver.py`
5. Удалить `backend/app/services/events/claim_event_subscriber.py`
6. Удалить `COMMUNICATION_CLAIM` из `event_types.py`
7. Удалить `epistemic_context` из `DecisionContext`
8. Удалить `epistemic_modifiers` параметр из `DecisionHub.compute()`
9. Удалить `apply_modifiers` static method из `DecisionHub`
10. Удалить все `backend/tests/sandbox/SUPERBOX/scenarios/epistemic_*.py`


Files: N/A
