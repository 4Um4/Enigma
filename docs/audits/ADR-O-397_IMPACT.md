# ADR-O-397 Impact Audit
> Детальный аудит ОДНОГО ADR. Единый атлас: `docs/ADR (Architecture Decision Records).md`

## Changed Domains
- Причинный слой: третий продюсер (grievance) + фабрика + REASON_GRIEVANCE
- Чтение (не запись): оси RelationshipStore (trust/fear), disposition S211, drives L3

## Downstream Consumers
- SOCIAL S264/ADR-O-396: causal_addressee grievance-продюсера — готовый вход их
  target-stage (2b-ii); order event.target_id > causal_addressee > resolver
- SocialTargetResolver: не тронут (интерим-контекст-гейт в МОЕЙ проводке)
- Cascade причин npc_tick_pipeline: threat > hunger > grievance

## Runtime Impact
- O(пары отношений A→NPC) на NPC в холодной фазе; микросекунды; RAM ноль
- Production-эффект: 3 живых обиды таверны получают причинные веса каждый тик

## Sandbox Tests
- test_r7_causal_slice_grievance.py: 10 (T1-T3 пины / W1-W5 контрфакты / A-A)
- Production probe: guard_borko→thief_shadow, thief_shadow→maid_lusya,
  tavern_keeper_tornin→thief_shadow — БЕЗ инъекций, контраст натур живой

## Rollback
- Удалить causal_slice_grievance.py + тест; из desired_change.py — REASON_GRIEVANCE
  + grievance_hold; из npc_tick_pipeline.py — блок R7 + контекст-гейт. Ядро не задето.

## Уроки
- D-R7-WHO-CONTRACT: единый контракт продюсеров (who явным аргументом, hunger-
  паттерн) — threat-паттерн state.npc_id падает в TickState-проводке.
- D-R7-LIVE-TRIGGER: живой причинный срез вскрывает спящие дыры чужих слоёв
  (intent-without-target, Stage-1-валидатор) — дефект-детектор, не демонстрация.
