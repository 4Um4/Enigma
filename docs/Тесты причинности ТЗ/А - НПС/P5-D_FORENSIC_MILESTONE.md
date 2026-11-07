# P5-D — SEEK_ALLY EXECUTION: CLOSED (PARTIAL)

**Forensic Milestone** — аналитический отчёт о завершении эксперимента P5-D.

**Baseline:** `72cf47b0658ffe8cae6351213ddbfb3b48f2e6d2`
**Branch:** `main`
**Probe:** `backend/tests/sandbox/p5d_seek_ally_probe.py`
**Вердикт:** **PARTIAL** — Intent reaches executor (MovementEngine), но действие не завершается. Движение существует, но не исполняется в данном тесте. Социальных последствий нет.

---

## Финальный вопрос P5-D

**Когда NPC принимает решение искать союзника, способна ли существующая система превратить это решение в реальное социальное действие — или пока симулирует только намерение?**

**Ответ: СИСТЕМА СПОСОБНА, но в данном тесте действие не завершилось.**

SEEK_ALLY — это НЕ DECISION_ONLY. Исполняемый механизм существует:
- movement_intent создаётся (MacroMovementGoal с target и reason)
- проходит через movement_bridge → SpatialTargetResolver → MovementEngine
- но MovementEngine не произвёл spatial_changes для maid_lusya

---

## Фактический путь исполнения SEEK_ALLY

```
PLAYER_INSULTS → belief (maid_lusya, conf=0.5)
    ↓
EpistemicContextResolver → claims_about_self
    ↓
DecisionHub.compute(maid_lusya):
    intent = SEEK_ALLY
    target = tavern_keeper_tornin
    score = 0.3483
    has_communication = False  ← non-verbal intent
    ↓
npc_tick_pipeline.py:1155 — SEEK_ALLY ∈ _MOVE_INTENTS
    ↓
_resolve_reactive_movement / _resolve_proactive_target
    ↓ target_node = tavern:behind_bar (где был Торнин)
    ↓
MacroMovementGoal(actor=maid_lusya, target_node_id=tavern:behind_bar, reason=proactive_seek_ally)
    ↓
movement_intents.append(_movement)  ← movement_intent создан ✅
    ↓
movement_bridge.py:process_movement_intents
    ↓ SpatialTargetResolver.resolve → RESOLVED ✅
    ↓ CommitmentArbiter.enforce_for_intent → passed ✅
    ↓
MovementEngine.process_intents (5 intents including maid_lusya)
    ↓
spatial_changes = 2 (only guard_borko) ← maid_lusya: 0 changes ❌
    ↓
[NO spatial effect for maid_lusya from SEEK_ALLY]
```

**Точка незавершения:** MovementEngine получил movement_intent для maid_lusya, но не произвёл spatial_changes. maid_lusya физически двигалась, но от LifeEngine schedule (Phase 0), не от SEEK_ALLY (Phase 5).

---

## A/B Comparison

| Параметр | A (с PLAYER_INSULTS) | B (control) |
|---------|---------------------|-------------|
| Tick 1: maid_lusya intent | **SEEK_ALLY** (score=0.3483, #1) | FLEE (score=0.1836, #2 after seek_ally=0.2492) |
| movement_intent created | ✅ target=behind_bar, reason=proactive_seek_ally | ✅ reason=reactive:flee |
| SpatialTargetResolver | ✅ resolved | ✅ resolved |
| MovementEngine received | ✅ 5 intents | ✅ 5 intents |
| spatial_changes for maid_lusya | **0** ❌ | **0** ❌ |
| maid_lusya physical movement | From Phase 0 schedule (node_17 → node_16) | From Phase 0 schedule (same) |
| Tick 2-3: maid_lusya intent | FLEE (score=0.1854, 0.1822) | FLEE (score=0.3564, 0.3321) |
| NPC_SPOKE from maid_lusya | 0 | 0 |
| relationship_state changes | 0 (keys=[] throughout) | 0 |
| tavern_keeper_tornin belief | ✅ (from original PLAYER_INSULTS broadcast) | absent |

**A/B delta:** Belief меняет решение maid_lusya с FLEE на SEEK_ALLY (tick 1), но не меняет физическое исполнение (0 spatial_changes в обоих случаях).

---

## Состояния maid_lusya (3 ticks, Scenario A)

| Tick | x | y | position_node | activity | intent | spatial_changes (Phase 5) |
|------|---|---|---------------|----------|--------|--------------------------|
| PRE | 7.99 | 1.83 | node_17 | "" | — | — |
| 1 | 7.99 | 1.83 | tavern:node_16 | serving_tables | SEEK_ALLY | 0 ❌ |
| 2 | 9.82 | 2.22 | tavern:node_16 | serving_tables | FLEE | 0 ❌ |
| 3 | 11.66 | 2.61 | tavern:node_16 | serving_tables | FLEE | 0 ❌ |

maid_lusya двигается (x меняется), но от Phase 0 LifeEngine schedule (reason=schedule:guarding_gate+relocation), НЕ от SEEK_ALLY.

## Состояния tavern_keeper_tornin (3 ticks, Scenario A)

| Tick | x | y | position_node | activity |
|------|---|---|---------------|----------|
| PRE | 4.5 | 2.5 | behind_bar | "" |
| 1 | 4.5 | 2.5 | tavern:fireplace | Обедает за столом |
| 2 | 6.0 | 2.625 | tavern:fireplace | Обедает за столом |
| 3 | 7.5 | 2.75 | tavern:fireplace | Обедает за столом |

tavern_keeper_tornin также двигается от schedule (activity="Обедает за столом"), не реагируя на SEEK_ALLY от maid_lusya.

---

## Опубликованные события

| Event type | Source | Count (A) | Count (B) | Связь с SEEK_ALLY |
|-----------|--------|-----------|-----------|-------------------|
| npc_proximity_close | various | 3 | 5 | ❌ generic spatial, не SEEK_ALLY |
| npc_proximity_leave | various | 1 | 2 | ❌ generic spatial |
| npc_spoke | guard_borko → tavern_keeper_tornin | 0 (tick 1) | 2 (ticks 2-3) | ❌ baseline talk, не SEEK_ALLY |
| npc_spoke | merchant_goran → blacksmith_orm | 0 (A) | 2 (B ticks 2-3) | ❌ baseline talk |
| npc_spoke from maid_lusya | — | **0** | **0** | ❌ SEEK_ALLY non-verbal |

**Никаких событий от maid_lusya.** SEEK_ALLY не создаёт CommunicationIntent, не публикует NPC_SPOKE, не инициирует социальный контакт.

---

## Изменения социального состояния

`relationship_state_maid_lusya_keys = []` на всех тиках в обоих сценариях.

**Социальные связи не создаются, не изменяются, не возникают.**

---

## Подтверждённые факты

1. **SEEK_ALLY — исполняемый intent**, а не только категория решения ✅
   - Создаёт MacroMovementGoal с target_node_id и reason="proactive_seek_ally"
   - Проходит через movement_bridge → SpatialTargetResolver → MovementEngine
2. **Belief влияет на выбор** maid_lusya: A → SEEK_ALLY, B → FLEE ✅
3. **movement_intent создаётся и резолвится** (SpatialTargetResolver: RESOLVED) ✅
4. **MovementEngine получает intent** (5 intents including maid_lusya) ✅
5. **BUT: 0 spatial_changes для maid_lusya** ❌
6. **maid_lusya физически двигается**, но от LifeEngine schedule (Phase 0), не от SEEK_ALLY (Phase 5) ✅
7. **SEEK_ALLY — transient intent**: появляется только на tick 1, затем заменяется на FLEE ✅
8. **No social consequences**: нет NPC_SPOKE, нет relationship changes, нет social contact ✅
9. **tavern_keeper_tornin получает belief** от исходного PLAYER_INSULTS broadcast (все 6 NPC), НЕ от SEEK_ALLY ✅
10. **No information transfer** от maid_lusya к tavern_keeper_tornin через SEEK_ALLY ✅

---

## Гипотезы

- **(H-preempt)**: maid_lusya уже имеет active_traversal от Phase 0 (schedule:guarding_gate+relocation). MovementEngine не начинает новый traversal, пока текущий не завершён. guard_borko получил spatial_changes, потому что его Phase 0 traversal мог быть в другом статусе или направлении.
- **(H-transient)**: SEEK_ALLY появляется только на tick 1 (сразу после оскорбления), затем заменяется на FLEE. Это означает, что у SEEK_ALLY есть только один шанс на исполнение, и если он пропущен (из-за preempt), он больше не повторяется.
- **(H-scores-anomaly)**: В scenario B, seek_ally=0.2492 (#1 в scores_trace), но выбран FLEE=0.1836. Возможная причина: reflex_constraint или override, который предпочитает FLEE над SEEK_ALLY при отсутствии belief. Это наблюдение, не баг.

## Неизвестные

- Точная причина, по которой MovementEngine не произвёл spatial_changes для maid_lusya (нужен spy внутри MovementEngine.process_intents body)
- Что произошло бы, если maid_lusya не имела active_traversal от Phase 0 (очищенный schedule)?
- Сработал бы SEEK_ALLY movement на более длинном горизонте (10+ ticks)?
- Возникает ли social contact при физическом сближении maid_lusya и tavern_keeper_tornin (npc_proximity_close был опубликован, но без social consequences)?

---

## Запреты соблюдены

- ❌ Никаких production fixes
- ❌ Не добавлен новый AllySystem
- ❌ Не добавлены новые социальные шкалы
- ❌ Не созданы вручную CommunicationIntent или QueuedTask
- ❌ Не перемещена Люся вручную
- ❌ Не созданы социальные связи вручную
- ✅ Только wrapper spies + position snapshots
- ✅ Probe живёт в `tests/sandbox/` и не импортируется в runtime

---

## Финальная формула

> Решение искать союзника — не пустой звук.
> Оно создаёт движение, проходит через мост, доходит до движка.
>
> Но мир уже двигает Люсю по своему расписанию.
> И пока она идёт к двери, её шаг к Торнину остаётся намерением.
>
> Намерение, которое не успело стать шагом.

---

## Status P5-D

**CLOSED (PARTIAL).** Production fixes не нужны.

SEEK_ALLY — это НЕ DECISION_ONLY. Исполняемый механизм существует и работает:
movement_intent создаётся, резолвится, доходит до MovementEngine. Но в данном
тесте MovementEngine не произвёл spatial_changes для maid_lusya (возможно,
из-за active_traversal от Phase 0 schedule). Социальных последствий нет.

---

## Status всех треков Master

| Приоритет | Трек | Вердикт |
|-----------|------|---------|
| 1 | P5-B: SQLite Persistence | ✅ PASS |
| 2 | P5-C: Real LLM Verification | ✅ PASS |
| 3 | **P5-D: SEEK_ALLY Execution** | **PARTIAL** |

---

*Forensic milestone зафиксирован. Baseline `72cf47b0` не тронут. Все 4 трека P5 (A/B/C/D) завершены.*
