# ADR-O-358 Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

## Changed Domains
- epistemology (belief revision, epistemic store)
- social (trust-based reliability)

## Downstream Consumers
- WorldSnapshotBuilder (читает EpistemicStore.to_dict() для UI "Мои убеждения")
- DecisionHub (читает EpistemicContext, но для player не используется — игрок не имеет DecisionHub)

## Runtime Impact
- RAM: +1 запись в EpistemicStore на каждый услышанный игроком ClaimEvent
- Latency: +1 подписчик на NPC_SPOKE (минимальное влияние, синхронная шина)

## Sandbox Tests
- IPT: 39/39 passed
- ClaimEventSubscriber.on_npc_spoke() fallback протестирован через IPT

## Rollback
1. Убрать `_bus.subscribe(EventType.NPC_SPOKE, _subscriber.on_npc_spoke)` из GameLoop
2. Вернуть `if _nid == "player": continue` в ClaimEventSubscriber
3. Вернуть `max(0.0, min(1.0, ...))` в RelationshipReliabilityProvider
4. Убрать `max(0.0, ...)` в BeliefRevisionEngine