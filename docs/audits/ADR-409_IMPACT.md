ADR-409 [FIX] **IMPACT** (S350)

## Changed Domains
- will (запись/чтение BehaviorMask), сериализация psyche (to_persistence_dict / from_legacy), загрузчик state'а хаба (npc_loader).

## Downstream Consumers
- DecisionHub._behavior_mask_modifier (decision_hub.py:1139-1191) — получает живой вход (было: state всегда NONE).
- OpportunityEngine (opportunity_engine.py:62-76) — карта маска-действия оживлена.
- NPCStateAdapter.from_legacy — читатель существовал (V8-PSY-5), добавлен только guard applied_at_day.

## Runtime Impact
- RAM: +3 psyche-поля на NPC в dict. Latency ~0: проекций не прибавилось (V3 — перенос), чтение в load_l2 — O(1)/NPC/тик.

## Sandbox Tests
- backend/tests/sandbox/SUPERBOX/scenarios/behavior_mask_closure_test.py: r1-r7; итог r7 PASS=14 FAIL=4 NOT_IMPLEMENTED=2 NOT_PROVEN=1; гейты OK; красные легитимны (A2/B3/B7-cluster/B12 — уровни B/D и решения Мастера).
- IPT 52/52; ruff чист по всем изменённым файлам.

## Rollback
- Три независимых хунка (decision.py / npc_state.py / npc_loader.py) revert по одному; данные обратно совместимы (отсутствие ключей = None-семантика «никогда»).

## Open (не этот ADR)
- Инверсия множителя на отрицательных скорах — доказана игрой (B12) — этап B.
- Кластер resentment/dependency — писатель-only — вердикт Мастера.
- Мёртвые входы willpower/hidden_truth; шкала порога; сессионный сброс; вербальный слой D.