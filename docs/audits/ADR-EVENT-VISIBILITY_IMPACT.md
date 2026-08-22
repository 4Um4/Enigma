# ADR-EVENT-VISIBILITY Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: docs/ADR (Architecture Decision Records).md

## Changed Domains
- Perception & Phenomenology (CFRM)
- Epistemic Core (Event filtering)

## Downstream Consumers
- models/npc_state.py (PerceptualKernel.can_observe)
- services/events/claim_event_subscriber.py (использует can_observe)

## Runtime Impact
- **RAM:** Нет изменений.
- **Latency:** Нет изменений. Фильтрация происходит на уровне подписчика.

## Sandbox Tests
- 	ests/test_stage0_and_1_invariants.py (косвенно, через IPT INV-PLAYER-EPISTEMIC-CLOSURE)

## Rollback
- Вернуть жестко заданный HEARING_RADIUS в ClaimEventSubscriber (НЕ рекомендуется, игнорирует event.radius и visibility).
