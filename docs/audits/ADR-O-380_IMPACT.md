
# ADR-O-380 Impact Audit — BeliefState Write Guard (L14.5)

> Детальный аудит ОДНОГО ADR. Единый атлас: docs/ADR (Architecture Decision Records).md (DOM-06&09, L14.5).
> Сессия: S243 (AG1). Runtime-часть в истории (параллельная серия, full-save); настоящий файл — документальное закрытие по мандату 11.4.

## Решение
BeliefState.update() — caller-based write-guard эпистемического субстрата. ADR-SSOT-EPISTEMIC («commit генерирует BeliefDelta; применяется через StateApplicator.apply_belief_delta — единственный физический write-path») доведён до runtime-мембраны: вызов update() вне цензуса → ArchitecturalViolationError("beliefs.update(<key>)", <caller>).

## Whitelist (дословно из кода, beliefs.py:101-116)
| Модуль | Основание |
|---|---|
| app.models.npc.beliefs | self (конструкция/round-trip) |
| app.models.npc_state | загрузка psyche["beliefs"] (npc_state:1022) |
| app.services.npc.npc_loader | _beliefs_from_persistence (npc_loader:583; вызовы 561/661) — легальный писатель, найден замком round-trip (test_beliefs_round_trip_full_cycle, 44/45) |
| app.services.npc.belief_transition_engine | R8-канал №1: тиковая ветка, генерирует BeliefDelta (causal_parent) |
| app.services.npc.state_applicator | apply_belief_delta — единственный физический write-path |
| app.services.memory.belief_aggregator | R8-канал №2: CoherenceBeliefAggregator (pattern-based) |
| tests.sandbox.SUPERBOX.npc_sandbox | тест-исключение (цензус E2.0-c) |
| tests.sandbox.SUPERBOX.scenarios.epistemic_runtime_closure_test | тест-исключение (S201) |
| tests.sandbox.SUPERBOX.scenarios.epistemic_scheduler_closure_test | тест-исключение (S203) |

ЗАПРЕЩЕНО к внесению: causal_state_test — его D3-атака обязана поднимать ArchitecturalViolationError (замок экзамена B0).

## Changed Domains
- Эпистемика (L2): запись убеждений — единая точка.
- Закрывает enforcement-дыру ADR-SSOT-EPISTEMIC: beliefs.update был открыт, запись DANGER мимо BTE/DeltaGate проходила молча (D3-атака экзамена).

## Downstream Consumers
- Writers (цензус): два R8-канала + загрузка + applicator.
- Readers: EpistemicContextResolver → epistemic_modifiers → DecisionHub (изоляция Store↔Hub не менялась); контракт BeliefDelta (frozen) не тронут.
- Открытый вопрос (досье S243, №3): мёрджа двух R8-каналов (BTE ∨ Aggregator в один ключ) НЕТ — guard фиксирует writer'ов, не разрешает конфликт семантик.

## Runtime Impact
~0 (одна проверка caller-строки на update()). IPT 45/45, замки 45/45, серии causal_state_test стабильны.

## Sandbox Tests
- backend/tests/sandbox/SUPERBOX/scenarios/causal_state_test.py — D-группа: D3_beliefs → REJECTED (мембрана цела).
- backend/tests/test_phase_a_memory_fixes.py (round-trip-замок, поймал npc_loader) — 45/45.

## Rollback
Удалить guard: вырезать _UPDATE_ALLOWED_WRITERS + проверку caller в update() (mod/npc/beliefs.py). Откат бесследен; урок в MUTATIONS S243.

## Урок
Тот же, что O-379 (D-группа = замок экзамена), плюс: легальные писатели находятся только цензусом по замку round-trip (npc_loader-прецедент) — расширение whitelist «по интуиции» = путь к телепатии.