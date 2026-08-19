# ADR-S199 Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

`ADR-S199` [STANDARD] **IMPACT**
# ADR-S199 Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

## Changed Domains
- `DOM-01`: Foundation (State Mutation Law, Runtime Purity Law)
- `DOM-02`: Will, Pressure & Decision
- `DOM-06`: Social, Memory & Affective
- `DOM-07`: Frontend, Presentation & Input

## Downstream Consumers
- `backend/app/services/game_loop/__init__.py`: `GameLoop._execute_dm_and_intent_resolution()`
- `backend/app/services/social/mvp_tavern_controller.py`: `MvpTavernController.action_compiler.process_action()`
- `backend/app/services/player_cognition/npc_confession_parser.py`: `NpcConfessionParser.parse_and_record()`

## Runtime Impact
- RAM: Увеличение на ~2KB на тик из-за расширенного IntentSemanticField.
- Latency: Увеличение времени LLM-вызова на ~50-100ms из-за более сложного промпта и большего JSON-ответа.

## Sandbox Tests
- `backend/tests/sandbox/phenomenology/test_dialogue_thread_continuity.py`
- `backend/tests/IPT.py:check_inv_semantic_unification`

## Rollback
- Удалить `IntentSemanticField.action` и вернуть `action_type` как канонический ключ.
- Восстановить вызов `ActionSemanticResolver` в `GameLoop._execute_dm_and_intent_resolution()`.
- Удалить `legacy_bridge.py` и `PropositionMatcher`.
- Удалить `SOCIAL_ACTION` из `EventType`.
