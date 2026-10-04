# ADR-O-R2 Impact Audit
`ADR-O-R2` [STANDARD] **Feasibility Enforcement Law**
Files: backend/app/services/cfrm/pressure_translator.py, backend/tests/gameplay/test_gc09_body_causality.py
> Единый атлас: docs/ADR (Architecture Decision Records).md (L5.3)

## Changed Domains
- Decision (DecisionHub ФАЗА 1), CFRM (pressure_translator constraints), Body (SOMATIC_VETO оживлён)

## Downstream Consumers
- gc09-B: ✅ 2/2 (мандат S254 исполнен)
- f1_trade_materialization: ❌ коллизия S189×economic — TRADE блокируется в транзите; данные [R2_DIAG] в reports/f1_trade_tb.txt; решение владельца ADR-O-412
- SOMATIC_VETO (NPIC): body_state missing → FLEE/ATTACK/APPROACH/MANIPULATE реально вырезаются (раньше игнор)
- ActiveCommitment (S189): 10 проактивных интентов реально блокируются в транзите (раньше игнор)

## Runtime Impact
- O(len(constraints)) на NPC-тик — пренебрежимо; scores_trace отражает множитель (калибровка R4.2 честнее)

## Sandbox Tests
- tests/gameplay/test_gc09_body_causality.py (R1 A/A + cap-матрица) — GREEN
- tests/IPT.py 49/49 — GREEN
- pytest полный: 2149 passed / 3 known-red (атрибуция в MUTATIONS-хвостах)

## Rollback
- git revert патча ФАЗЫ 1 (decision_hub.py ~:606-620) — возвращается мёртвый матч 'FLEE'-uppercase; gc09-B вернётся в RED (маркер S254)