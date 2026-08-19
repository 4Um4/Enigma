# ADR-O-358 Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

`ADR-O-358` [STANDARD] **Epistemic Player Integration**`

## Changed Domains
- epistemology (belief revision, epistemic store)
- social (trust-based reliability)
- execution (dialogue materializer, task scheduler)

## Downstream Consumers
- WorldSnapshotBuilder (читает EpistemicStore.to_dict() для UI "Мои убеждения")
- DecisionHub (читает EpistemicContext, но для player не используется — игрок не имеет DecisionHub)
- ClaimEventSubscriber (слушает NPC_SPOKE и COMMUNICATION_CLAIM)

## Runtime Impact
- RAM: +1 запись в EpistemicStore на каждый услышанный игроком ClaimEvent
- Latency: +1 подписчик на NPC_SPOKE (минимальное влияние, синхронная шина)

## Sandbox Tests
- IPT: 43/43 passed (3 новых инварианта эпистемической честности)
- ClaimEventSubscriber.on_npc_spoke() fallback протестирован через IPT и SUPERBOX-014/015/016
- SUPERBOX-016: Полная рантайм-труба TaskScheduler → EpistemicStore[player]

## Rollback
1. Убрать `_bus.subscribe(EventType.NPC_SPOKE, _subscriber.on_npc_spoke)` из GameLoop
2. Вернуть `if _nid == "player": continue` в ClaimEventSubscriber
3. Вернуть `max(0.0, min(1.0, ...))` в RelationshipReliabilityProvider
4. Убрать `max(0.0, ...)` в BeliefRevisionEngine
5. Убрать `"intent_type": req.intent_type` из DialogueExecutor Artifact.data
6. Исправить маппинг subject_id/object_id в ClaimEventSubscriber.on_npc_spoke для intimidate/attack

Files: backend/app/services/events/claim_event_subscriber.py, backend/app/services/npc/belief_revision_engine.py, backend/app/services/game_loop/__init__.py, backend/app/services/execution/dialogue_executor.py, backend/tests/sandbox/SUPERBOX/scenarios/epistemic_player_belief_test.py, backend/tests/sandbox/SUPERBOX/scenarios/epistemic_runtime_closure_test.py, backend/tests/sandbox/SUPERBOX/scenarios/epistemic_scheduler_closure_test.py, backend/tests/IPT.py