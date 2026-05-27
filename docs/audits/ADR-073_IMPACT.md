# ADR-073 Impact Audit: Каузальное Сшивание GAP8, GAP3, GAP12

## Changed Domains
- **SOCIAL** (GAP8: semantic_action, target_id в CommunicationIntent и EventDTO payload)
- **WILL/DECISION** (GAP3: body_state инъекция в translate_kernel_to_context, Somatic Veto)
- **SPATIAL** (GAP12: интерполяция local_position при LOD1-транзите)

## Downstream Consumers
- `DirectiveInterpretationSubscriber` — теперь получает семантику из `NPC_SPOKE` (GAP8)
- `DecisionHub` — получает `ActionSpaceCompression.constraints` из `body_state` (GAP3)
- `CFRM / ImpactEngine` — читают актуальную `local_position` вместо позиции-призрака (GAP12)

## Runtime Impact
- RAM: +0 (добавлено 2 Optional поля в frozen dataclass, 1 dict-аргумент в функции)
- Latency: +0.1ms на тик (вычисление интерполяции для движущихся NPC)

## Sandbox Tests
- `test_intent_event_adapter_preserves_semantic_action`
- `test_somatic_veto_pain_blocks_flee`
- `test_somatic_veto_shock_blocks_attack`
- `test_somatic_veto_blood_loss_limits_physical`
- `test_transit_interpolated_position_updates_local`

## Rollback
1. Удалить `semantic_action`, `target_id` из `CommunicationIntent`
2. Удалить проброс из `IntentEventAdapter`
3. Убрать `body_state` из `translate_kernel_to_context`
4. Вернуть `continue` без интерполяции в `_enrich_local_positions`