# Narrative Manifestation Gap Analysis — Current State

**Дата:** 2026-07-23
**Версия кода:** V.0.5.3.5.6
**Принцип:** Только незакрытые разрывы. Закрытые — удалены.

---

## 0. Главный тезис

> **A simulated state is not yet a simulated world.**
>
> State becomes gameplay only when it can alter perception, memory, decision, speech, movement, or future social propagation.

> **Do not ask: «What system is missing?»**
> **Ask: «Where does an existing causal chain stop before producing an observable consequence?»**

---

## 1. Текущее состояние: что работает

| Компонент | Статус |
|---|---|
| LLM | ✅ Работает (qwen_7b, «доступен» за 3 сек) |
| Factions | ✅ Loaded 4 factions |
| NPC-NPC отношения | ✅ trust=-6.0 для ANGRY (шкала ±100) |
| NPC-NPC cache в DecisionHub | ✅ Graph populated per-tick |
| Bridge 7 ResponseGenerator | ✅ NPC_B отвечает конкретно NPC_A |
| Bridge 2 L1Chronicle | ✅ NPC-NPC диалоги пишутся в L1Chronicle |
| TopicExtractor | ✅ 5+ тем (желания, встреча, власть, наблюдение, безопасность) |
| LLM получает beliefs | ✅ "Ты боишься X (0.8)" в промпте |
| NPC имена | ✅ Держатся после прямого вопроса |
| Spatial navigation | ✅ NO_DETOUR: 0, MICRO: 446 |
| NPC движение | ✅ 238 RELOCATE (schedule, need_driven, proactive) |
| Drift B | ✅ 0 |
| TICK_CRASH | ✅ 0 |
| KeyError: 0 | ✅ 0 |
| BELIEF_STORE errors | ✅ 0 |

**Движок жив.** NPC двигаются, говорят, меняют отношения, LLM видит beliefs.

---

## 2. Что ещё сломано — 3 bridge gaps

### Bridge 3: BeliefState — PLAYER_SPOKE не формирует beliefs
- **Файл:** `services/npc/belief_transition_engine.py:_THREAT_TYPES`
- **Что сломано:** `_THREAT_TYPES` содержит только `player_attacks`, `player_insults`, `player_threatens`. `PLAYER_SPOKE` НЕ включён. Когда игрок говорит Люсе «Борко подглядывает» — Lusya НЕ формирует DANGER belief.
- **Gap type:** propagation gap
- **Fix:** Добавить `PLAYER_SPOKE` в `_THREAT_TYPES` + обработка semantic content реплики.
- **Unblocks:** Acceptance test step 3.

### Bridge 6: LifeProject → schedule mutation
- **Файл:** `services/npc/life_engine.py:update_routine`, `services/npc/life_project_resolver.py`
- **Что сломано:** `life_project` меняется (FSM: ACTIVE→COLLAPSING→LOST→...), но `update_routine` читает ТОЛЬКО `npc.routine.schedule`. LifeProject change НИКОГДА не мутирует schedule, activity_map, role, position.
- **Gap type:** decision gap
- **Fix:** При `family_builder → isolation` — загрузить новый `routine.schedule` + `activity_map` + эмиттить `MacroMovementGoal` к уединённому узлу.
- **Unblocks:** Долгосрочные fate events.

### Bridge 8: player_cognition pipeline — dead code
- **Файл:** `services/player_cognition/pipeline.py:build_perceived_scene`
- **Что сломано:** 9-слойный pipeline существует, но `grep "from app.services.player_cognition"` возвращает 0 production callers вне `player_cognition/` folder.
- **Gap type:** bridge gap (pure dead code)
- **Fix:** Подключить `build_perceived_scene` в `game_loop` или `world_snapshot_builder`.
- **Unblocks:** Epistemic asymmetry — игрок знает только то, что аватар воспринял.

---

## 3. Что ещё сломано — 5 disconnect wires (T-03..T-07)

| ID | Что отключено | Impact | Priority |
|---|---|---|---|
| **T-03** | STM (DialogueSession) in-memory, не персистится | После рестарта NPC забывает последние диалоги | MEDIUM |
| **T-04** | `npc_npc_context` поле есть, НЕ заполняется | NPC_A не знает историю с NPC_B | CRITICAL |
| **T-05** | `npc_topics` reset every tick, нет continuity | NPC меняет тему каждые 5 секунд | MEDIUM |
| **T-06** | `CrystallizedBeliefModifierResolver` не вызывается для NPC-NPC пар | Beliefs кристаллизуются, но не меняют intent | MEDIUM |
| **T-07** | Player phrases ("как дела") не в `_TOPIC_KEYWORDS` | Игрок спрашивает «как дела» → topic="наблюдение" | LOW |

---

## 4. Acceptance Test — текущее состояние

**Тест:** Player tells Lusya "Borko is spying on you" → chain reaction → Orm avoids Borko.

| Step | Статус | Blocker |
|---|---|---|
| 1 Player → Lusya | ✅ | — |
| 2 Lusya receives | ✅ | — |
| 3 Lusya forms belief | ❌ | Bridge 3: PLAYER_SPOKE ∉ _THREAT_TYPES |
| 4 Lusya approaches Borko | ❌ | SocialTargetResolver: trust=0, не prefer>30 |
| 5 Lusya asks "Were you watching?" | ❌ | T-07: "как дела" не маппится |
| 6 Borko responds defensively | ✅ | Bridge 7 + T-02 работают |
| 7 Orm hears exchange | ❌ | T-04: npc_npc_context пустой |
| 8 Orm stores episodic memory | ❌ | T-04: Orm не listener |
| 9 Orm updates opinion of Borko | ❌ | T-06: beliefs не влияют на DecisionHub |
| 10 Orm avoids Borko | ❌ | T-06: нет FLEE bias от beliefs |
| 11 Final state | ❌ | Chain ломается на step 3 |

**Текущий результат: 4/11** (шаги 1, 2, 6 + частично T-01/T-02)

---

## 5. Приоритет замыкания

| # | Пункт | Время | Acceptance test |
|---|---|---|---|
| 1 | **T-07** Player phrases → topic | 30 мин | → step 5 |
| 2 | **T-04** npc_npc_context populated | 2 ч | → steps 7, 8 |
| 3 | **T-06** Beliefs → DecisionHub | 2 ч | → steps 9, 10 |
| 4 | **T-05** Topic continuity | 1 ч | — |
| 5 | **T-03** STM persistence | 1 ч | — |
| 6 | **Bridge 3** PLAYER_SPOKE → beliefs | 1 день | → step 3 |

**После всех 6: 6/11 → можно начинать TZ Люси.**

---

## 6. Memory system — архитектура (работает)

```
Event → L1Chronicle.commit_tick_buffer([TraitDriftEvent])
   → PatternDetector.query_evidence(npc_id, source_id)
   → BeliefCrystallizationEngine.crystallize(evidence, drives, existing_beliefs)
   → CrystallizedBeliefStore.update_beliefs(npc_id, beliefs)
   → CrystallizedBeliefModifierResolver.resolve(beliefs) → drive_modifiers
   → DecisionHub.compute(state, drive_modifiers)
```

**Эта цепочка РАБОТАЕТ.** Проблема НЕ в памяти — проблема в **связанности**: LLM не видит все beliefs (T-02 сделано, но T-04 npc_npc_context ещё пустой), beliefs не влияют на DecisionHub для NPC-NPC пар (T-06), PLAYER_SPOKE не формирует beliefs (Bridge 3).

**Архитектура ПРАВИЛЬНАЯ. Провода недостраиваются.**
