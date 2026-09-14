# ADR-O-389 Impact Audit
> Детальный аудит ОДНОГО ADR. Единый атлас: `docs/ADR (Architecture Decision Records).md`

## Changed Domains
intent (память решений: модель→проекция→round-trip), состояние задач (терминал INTERRUPTED/TASK_STALE_INTENT), dispatch-гейты TaskScheduler (4 точки), StateDeltas-контракт (intent/intent_tick), агрегатор (перенос), outbox (4-кортеж).

## Downstream Consumers
EpistemicCore (не тронут — свидетель не «понимает»); SpeechScheduler/DialogueQueue (не тронуты; DialogueQueue-инверсия — долг); commitment-зеркала (INTERRUPTED уже в словаре mirror_task_terminal — нулевое расширение); DecisionHub (читает intent T-1 — теперь реально читает: инерция/switching-cost впервые видят историю); resurrected readers: spatial_observatory (intent_data), smoke_goran_beta steal_rate (слепая фикстура — долг), test_gc11 last_intent-ветка (мёртвая — долг).

## Runtime Impact
intent-дельта: +1 StateDeltas/NPC/тик (амортизируется агрегатором); гейт: 1 провайдер-вызов на задачу ×4 точкам максимум (тот же провайдер, что death — дельта ≈ 0); поведение: инерция интентов ожила (golden: diversity↑, events↓ — подпись, A/B за lab).

## Sandbox Tests
tests/micro/test_intent_roundtrip.py (10), tests/micro/test_intent_liveness_gate.py (12), SUPERBOX gc_interrupt_test (GREEN, v1.3), e1_intent_liveness_check (golden замер), батарея трека 52/52.

## Rollback
Удалить flee-гейт: 4 блока [GC-I01-E2] в task_scheduler + константа в action_commitment (гейты смерть-only возвращаются сами). Откат субстрата: снять [GC-I01-E1] проекцию + [GC-I01-E1b] правки 5 файлов — мир возвращается к DEBT-INTENT-SOURCE (решения эфемерны), гейт вырождается в fail-open-no-op (intent всегда None). Частичный откат невозможен и запрещён: проекция без применения = ложь инерции.
