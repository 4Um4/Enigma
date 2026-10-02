`ADR-O-408` [STANDARD] **IMPACT**
# ADR-O-408 Impact Audit — Canonical Attention→Action Integration
> Единый атлас ADR: `docs/ADR (Architecture Decision Records).md`. Сессия: S304.

## Changed Domains
- Внимание→решение→исполнение (perception pipeline, DecisionHub-интеграция, Гейт①-источник)
- Диагностическая гигиена (KILLER_SPIRIT, INV-N18-SOURCE)

## Downstream Consumers
- Гейт① N18-фильтра (simulation.py) — единственный reader npc_intents-канона;
- Любые будущие читатели npc_dict["intent"]: OBS-DICT-1 (лаг life-кэша) не закрыт
  как долг — читатели обязаны знать: кэш-проекция не получает intent-обновлений.

## Runtime Impact
- П-1: +~0 (один dict-update на тик при применении TickMutation; блок за N18_EXP);
- KILLER_SPIRIT: ≤2 сек на IPT-запуск (psutil-снимок);
- Память: scene_state["npc_intents"] ~N×20 байт на кампанию.

## Evidence (12 прогонов)
- P3e ×5 (контрактная эволюция G1–G6): tornin T50 — поворот + остановка при E=0.95;
- Integration ×6 (I–V): E=1.0, cog→hub, retry-пул; orm T33 — reactive:approach
  (первая живая встречная реакция); goran T20–24 — observe×5, Δp=0;
- Case C: не воспроизведён ни разу.

## Sandbox Tests
- test_gate1_source.py (матрица 5×SUPPRESS/PASS + writer/fallback) — 6/6
- INV-N18-SOURCE (IPT, AST-структурный)
- cognition_p3e_test.py — GREEN ×2, STIM-DIFF=0
- cognition_attention_integration_test.py — GREEN ×2, STIM-DIFF=0

## Rollback
- N18_EXP=OFF (default) — весь блок П-1/Гейт① байтово прежний;
- ghost_reaper: IPT_NO_REAPER=1 или удаление вызова из IPT.py;
- INV-N18-SOURCE: удалить inv_n18_source из списка INVARIANTS.

## Open Debts (не attention-зона)
- NEED-EXEC-1 (главный следующий вопрос): need-интенты без исполнения;
- NEED-SAT-1, TZ-GHOST-1, LANG_LEAK/RE-D2, TZ-OBS-5, неснятые DIAG-зонды.