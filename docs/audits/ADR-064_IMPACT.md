# ADR-064 Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

`ADR-064` [STANDARD] **IMPACT**
# ADR-064 Impact Audit: Directive Pipeline Data Continuity
## Changed Domains
- Will (ObediencePressure), Social (Legitimacy)

## Downstream Consumers
- DirectiveInterpretationSubscriber
- DecisionHub (через PerceptionPayload)
- StateApplicator

## Runtime Impact
- RAM: 0 (использует существующую ссылку на dm_ctx.all_npcs_raw)
- Latency: 0 (одна проверка условия)

## Sandbox Tests
- test_will_directive_conflict (PASSED)
- test_legitimacy_gate_allows_high_fear (SKIPPED - LLM)
- test_legitimacy_gate_blocks_low_fear_thief (SKIPPED - LLM)

## Rollback
Удалить блок `if not ctx.all_npcs_raw and ctx.dm_ctx...` в tick_orchestrator.py:538


Files: N/A
