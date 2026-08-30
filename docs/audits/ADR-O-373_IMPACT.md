# ADR-O-373 Impact Audit
> Детальный аудит ОДНОГО ADR. Единый атлас: `docs/ADR (Architecture Decision Records).md`

## Changed Domains
- Физиология: fatigue — единственная per-tick проекция в BodyEngine; legacy-писатели dormant (decay / сон / reconcile).
- Агрегация дельт: Enum Identity Split устранён; PHYSICS_COMPOSITE = pass-through; канон enum+registry — models/state_delta.py.
- Idle-проекция Phase 0.5: NPCStateSnapshot +4 плоских READ-ONLY поля; единый shape всех трёх билдеров.

## Downstream Consumers
- StateApplicator — код не менялся; sequential-применение PHYSIOLOGY подтверждено композиционным тестом.
- Combat (ImpactEngine) — event-продюсер fatigue; билдеры снапшота приведены к единому shape.
- SleepLifecycleService — fatigue-восстановление передано BodyEngine; sleep_pressure/arousal/stress не тронуты.
- Читатели body_state["fatigue"] (arousal gate /100, drive_resolver, manifestation, avatar presentation) — без изменений; шкала 0–100 сохранена.
- temporal_specs — читатель, не менялся.

## Runtime Impact
- +4 плоских поля на снапшот/NPC/тик (копии значений) — O(N), пренебрежимо.
- BodyEngine — чистая функция; p95 не измерялся (budget-класс ТЗ Stage 2.5 §8.2).
- Активация energy/hydration/nutrition в production — intended (Q5): первый реальный расход с S227.

## Sandbox Tests
- tests/test_action_commitment.py: TestS2B5ProjectionContract (FLAT-гард), TestS2B5Fatigue (8; вкл. composition: структура/сохранность/порядок), TestDeltaPolicyIdentity (identity-гвард), миграция S2B1–2B.4 на плоский снапшот.
- tests/test_physiology_decay_handler.py: TestFatigueDecay (dormant-контракт).
- tests/sandbox/system/test_temporal_reconciliation.py: fatigue-frozen на skip.
- Поведенческий гейт (зонд, реверсирован): n=6; e=−0.1 / h=−0.3 / nut=−0.0625 / fat=+0.075 при load=0.5 — сверено с формулой; snap_fat 0→3.0 монотонно.

## Rollback
- Revert патчей сессии возвращает: dto-дубль enum (Enum Identity Split), прямые записи fatigue (W3/W4/W5), FLAT-слепоту Phase 0.5. Dormant-ветки помечены комментариями ADR-O-373 на местах.
- Тесты-гарды (identity / FLAT / composition) упадут первыми при частичном откате — в этом их назначение.