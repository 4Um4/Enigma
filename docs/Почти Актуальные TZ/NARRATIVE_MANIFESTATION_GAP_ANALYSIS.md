# Narrative Manifestation Gap Analysis — Forensic Audit v2

**Status:** Architectural Audit (не контракт, не дизайн)
**Scope:** NPC social behavior, identity dynamics, memory, dialogue, movement
**Date:** 2026-07-21
**Version audited:** Enigma V.0.5.3.5.4_-_-_-
**Methodology:** Forensic — `State → Reader → Transformation → Decision → Action → Observable Consequence`
**Baseline:** FORENSIC-1 (V.0.5.3.5.3, 2026-07-20, 12 gaps in 8 bridges)
**Current audit:** FORENSIC-2 (V.0.5.3.5.4, 2026-07-21)

---

## Δ Progress v5353 → v5354 (one day of work)

| Bridge | v5353 Status | v5354 Status | Net Change |
|---|---|---|---|
| 1 RelationshipStore → NPC-NPC cache | propagation gap | **IMPROVED** — graph populated per-tick | ✅ fixed |
| 2 L1Chronicle NPC-NPC TraitDriftEvent | propagation gap | **REGRESSED COSMETICALLY** — ghost param accepted but never called | ⚠️ ghost |
| 3 BeliefState + ALLY_NEARBY | propagation gap | UNCHANGED | 0 |
| 4 DialogueQueue | WORKING (with bug) | UNCHANGED (same bug) | 0 |
| 5 TemporaryDrive threshold | propagation gap | UNCHANGED | 0 |
| 6 LifeProject → schedule | decision gap | UNCHANGED | 0 |
| 7 ResponseGenerator | execution gap | **PARTIALLY FIXED** — wired end-to-end but producer drops `target_id` | +0.5 (one-line fix away) |
| 8 player_cognition | bridge gap (dead) | UNCHANGED | 0 |

**Acceptance test:** 2/11 steps worked in v5353. **Still 2/11 in v5354.** Bridge 1 enables cache population but acceptance test breaks earlier at step 3 (belief formation).

---

## 0. Главный тезис

> **A simulated state is not yet a simulated world.**
>
> State becomes gameplay only when it can alter perception, memory, decision, speech, movement, or future social propagation.

> **Do not ask: «What system is missing?»**
> **Ask: «Where does an existing causal chain stop before producing an observable consequence?»**

---

## 1. Executive Finding

Enigma вычисляет substantial объём внутреннего состояния:

- trust, fear, respect, debt, attraction
- stress, identity_integrity, affective_load
- trait drift, temporary drives
- life projects, beliefs
- social propagation

Однако **наличие переменной состояния ≠ gameplay**.

Центральный архитектурный разрыв:

> **Latent simulation state is not consistently converted into observable world behavior.**

Engine может «знать», что NPC A не доверяет NPC B — но это не вызывает:
- avoidance (избегание)
- confrontation (конфронтация)
- warning a third NPC (предупреждение третьего)
- memory of the reason (запоминание причины)
- changed future dialogue (изменение будущих реплик)
- changed location (смену локации)
- changed activity (смену активности)
- social propagation (распространение информации)

Система рискует производить мир, где внутренние числа **causally active but narratively invisible**.

---

## 2. The Core Distinction

**State ≠ Behavior**

### Текущий паттерн (работает):

```
NPC A говорит
   ↓
NpcDialogueSubscriber
   ↓
RelationshipStore
   ↓
trust = -0.1, fear = +0.1
   ↓
social_pressure (скаляр)
   ↓
identity_integrity
   ↓
TraitDriftEvent (в L1Chronicle)
```

Это валидная causal chain.

### Требуемый manifestation chain (отсутствует):

```
trust уменьшается
   ↓
opinion NPC A о NPC B меняется (semantic layer)
   ↓
NPC A воспринимает NPC B иначе
   ↓
NPC A принимает другое решение
   ↓
NPC A говорит / избегает / конфронтирует / предупреждает
   ↓
NPC B или NPC C наблюдает событие
   ↓
новая memory + belief
   ↓
future behavior меняется
```

Первая цепочка существует **значительной частью**.
Вторая цепочка **неполна**.

---

## 3. Audit of Existing Bridges

### Bridge 1: RelationshipStore → NPC-NPC Behavior

#### Current chain

```
NpcDialogueSubscriber.on_npc_spoke
   ↓
RelationshipStore.update (JSON, scale ±100)
   ↓
[BREAK: NPC-NPC entries never re-read into state_l2.relationship_cache]
   ↓
social_pressure formula (decision.py:73-79, scale -1..1)
   ↓
BreakProgressEngine
   ↓
LifeProjectResolver (FSM only)
```

#### Evidence (file:line)

| Role | Location |
|---|---|
| Producer | `services/events/npc_dialogue_subscriber.py:135` |
| Data structure | `services/memory/relationship_store.py:26-189` (JSON, key=`"source→target"`, clamped ±100 at line 23) |
| Reader | `services/phases/decision.py:64` (`get_all_for_source`) |
| Transformation | `services/phases/decision.py:73-79` (trust трактуется как -1..1, нейтраль = 0.5) |
| Terminal consumer | `services/npc/break_progress_engine.py` (via `social_pressure` arg) |
| Missing transition | `services/phases/decision.py:251` — `assemble_preloaded_data` calls `get_weights_for_decision(target_id="player")` ONLY. NPC-NPC weights never preloaded. |
| Config-time drop | `services/npc/npc_loader.py:630-634` — `relationship_cache` инициализируется из `social_stats` (только player scalars). NPC-NPC entries из `_enrich_with_social_relations` **отбрасываются**. |

#### Classification

- [x] State exists
- [x] State is read (by `decision.py:64` for social_pressure)
- [x] State is transformed (BreakProgressEngine.calculate)
- [x] Decision generated (LifeProjectResolver FSM advances)
- [ ] Action scheduled (no CommunicationIntent results from pressure)
- [x] Action executed (FSM state mutation visible in NPCState)
- [ ] Consequence propagated (life_project string change has no downstream schedule/role mutation)

#### Gap type

**PROPAGATION GAP** — NPC→NPC entries пишутся в JSON, но никогда не перечитываются в `state_l2.relationship_cache` для DecisionHub. Плюс **scale mismatch** (3 шкалы одновременно: clamp ±100, formula ±1, deltas 0..0.05).

#### Observable consequence?

**PARTIAL.** `social_pressure` теперь использует реальные данные (улучшение относительно v5.1), но `trust=0.005` после одного диалога падает ниже порога 0.5 → преждевременная эмоция "angry". NPC-NPC trust никогда не достигает DecisionHub `_get_rel_value(state, other_npc, "trust")` → возвращает `None` (vacuum).

---

### Bridge 2: L1Chronicle → Belief Crystallization

#### Current chain

```
BreakProgressEngine (decision.py:130-185)
reduction.py:88-113
idle_services.py:107-127
dm_phase.py:139-144
   ↓
L1Chronicle.commit_tick_buffer
   ↓
query_raw
   ↓
PatternDetector.detect
   ↓
BeliefCrystallizationEngine.crystallize
   ↓
CrystallizedBeliefStore.update_beliefs
   ↓
[BREAK: NPC-NPC dialogue never written as TraitDriftEvent]
```

#### Evidence (file:line)

| Role | Location |
|---|---|
| Producer | `services/phases/decision.py:170` (`l1_chronicle.commit_tick_buffer(_events_to_log, tick_number)`) |
| Data structure | `services/npc/l1_chronicle.py:36` (per-NPC dict + SQLite persistence) |
| Reader | `services/phases/integration.py:393` (`deps.l1_chronicle.query_raw(_npc_id)`) |
| Transformation | `services/npc/pattern_detector.py:42-136` (группировка по source_id, требует `MIN_EVENTS_FOR_PERSISTENCE=3`) |
| Terminal consumer | `services/phases/integration.py:416-422` (crystallize → update_beliefs) |
| Missing transition | `services/events/npc_dialogue_subscriber.py` — НЕ эмиттит `TraitDriftEvent` для NPC-NPC диалогов. Только `decision.py`, `reduction.py`, `idle_services.py`, `dm_phase.py` пишут в L1Chronicle. |

#### Classification

- [x] State exists
- [x] State is read (integration.py:393)
- [x] State is transformed (PatternDetector → BeliefCrystallizationEngine)
- [x] Decision generated (CrystallizedBeliefModifierResolver → drive_modifiers → DecisionHub)
- [x] Action scheduled (DecisionHub applies drive_modifiers at decision_hub.py:504-507)
- [x] Action executed (intent scores modified)
- [ ] Consequence propagated (только combat/threat events кормят chain; NPC-NPC dialogue исключён)

#### Gap type

**PROPAGATION GAP** — chain работает для combat/threat, но NPC-NPC social dialogue никогда не пишется в L1Chronicle → crystallized beliefs о других NPC никогда не формируются.

#### Observable consequence?

**PARTIAL.** L1Chronicle персистится, PatternDetector читает, CrystallizedBeliefModifierResolver подключён к DecisionHub. Но для NPC-NPC отношений специально — нет `TraitDriftEvent` → нет `fear`/`trust` beliefs о других NPC.

---

### Bridge 3: BeliefState → DecisionHub

#### Current chain

```
BeliefTransitionEngine.integrate (npc_tick_pipeline.py:303)
   ↓
state.beliefs.update
   ↓
[BREAK: BeliefState ephemeral, never serialized]
[BREAK: BeliefType.ALLY_NEARBY never written]
[BREAK: CoherenceBeliefAggregator dead code]
   ↓
BeliefModifierResolver.resolve
   ↓
drive_modifiers
   ↓
DecisionHub.compute
```

#### Evidence (file:line)

| Role | Location |
|---|---|
| Producer | `services/npc/belief_transition_engine.py:152-198` (пишет только `DANGER` + `PLAYER_HOSTILE`) |
| Data structure | `models/npc/beliefs.py:46-93` (dict of BeliefType → BeliefFragment) |
| Reader | `services/npc/belief_modifier_resolver.py:35-87` |
| Transformation | `services/npc/npc_tick_pipeline.py:363` (`_belief_mods = BeliefModifierResolver().resolve(state_l2.beliefs)`) |
| Terminal consumer | `services/npc/decision_hub.py:504-507` (drive_modifiers added to scores) |
| Missing transition | `models/npc_state.py:605` — `beliefs: BeliefState = field(default_factory=BeliefState)` — свежий каждый tick. `services/npc/npc_loader.py:616-644` (`load_l2_state_from_runtime_dict`) НЕ читает beliefs из raw_data. `services/memory/memory_manager.py:676` (`assess_beliefs()`) — DEAD CODE, 0 callers. |

#### Classification

- [x] State exists
- [x] State is read
- [x] State is transformed (DANGER/PLAYER_HOSTILE only)
- [x] Decision generated
- [x] Action scheduled
- [x] Action executed
- [ ] Consequence propagated (beliefs reset every tick; ALLY_NEARBY never written; CoherenceBeliefAggregator dead)

#### Gap type

**PROPAGATION GAP** (multiple sub-gaps):
- (a) BeliefState не сериализуется → resets каждый tick
- (b) `ALLY_NEARBY` (beliefs.py:42) объявлен, но нет writer
- (c) `CoherenceBeliefAggregator` path (R8) никогда не вызывается
- (d) Только `DANGER` + `PLAYER_HOSTILE` пишутся, и только от player threats

#### Observable consequence?

**PARTIAL.** `DANGER` и `PLAYER_HOSTILE` работают для combat threats. Но для dialogue-based suspicion (acceptance test step 3: "Lusya forms belief or suspicion") — `BeliefTransitionEngine._THREAT_TYPES` НЕ включает `PLAYER_SPOKE` → belief не формируется.

---

### Bridge 4: DialogueQueue → NPC_SPOKE event

#### Current chain

```
DecisionHub._build_communication
   ↓
CommunicationIntent (npc_tick_pipeline.py:501)
   ↓
post_decision.py:54-89 (QueuedTask in scene_state["pending_tasks"])
   ↓
game_loop/__init__.py:852-853 (execute_pending)
   ↓
DialogueQueue.enqueue
   ↓
dequeue_next
   ↓
_process_tasks_async
   ↓
DialogueExecutor.execute
   ↓
DialogueMaterializer.materialize
   ↓
bus.publish(NPC_SPOKE)
```

#### Evidence (file:line)

| Role | Location |
|---|---|
| Producer | `services/phases/post_decision.py:89` |
| Data structure | `services/execution/dialogue_queue.py:18-25` (QueuedDialogue с priority heap) |
| Reader | `services/game_loop/task_scheduler.py:123` (`dequeue_next()`) |
| Transformation | `services/game_loop/task_scheduler.py:114-121` (priority из tone) |
| Terminal consumer | `services/execution/dialogue_executor.py:35-74` (LLM call) → `services/execution/dialogue_materializer.py:18-53` (EventDTO published) |
| Minor bug | `services/game_loop/task_scheduler.py:157` — references `_eligible` outside scope when called via `process_tasks` |

#### Classification

- [x] State exists
- [x] State is read
- [x] State is transformed (priority-based ordering)
- [x] Decision generated
- [x] Action scheduled
- [x] Action executed (LLM call, NPC_SPOKE published)
- [x] Consequence propagated (NpcDialogueSubscriber picks up NPC_SPOKE)

#### Gap type

**NONE** — chain end-to-end functional. Самый рабочий из всех 8.

#### Observable consequence?

**YES.** NPC говорит, event эмиттится, subscribers реагируют.

---

### Bridge 5: TemporaryDrive → DecisionHub scoring

#### Current chain

```
StateApplicator._apply_social_delta (state_applicator.py:1016-1057)
   ↓
CausalEntry with emotional_impact
   ↓
[BREAK: impact threshold 0.7 rarely reached]
   ↓
TemporaryDrive created (state_applicator.py:1083)
   ↓
age_temporary_drives (npc_tick_pipeline.py:208)
   ↓
compute_drive_modifiers
   ↓
drive_modifiers → DecisionHub.compute
```

#### Evidence (file:line)

| Role | Location |
|---|---|
| Producer | `services/npc/state_applicator.py:1083` (только при `CausalEntry.emotional_impact > 0.7`) |
| Data structure | `models/npc_state.py:429-478` (TemporaryDrive + DRIVE_INTENT_MODIFIERS) |
| Reader | `services/npc/npc_tick_pipeline.py:357` (`compute_drive_modifiers(_drives)`) |
| Transformation | `models/npc_state.py:481-496` (urgency × decay) |
| Terminal consumer | `services/npc/decision_hub.py:504-507` |
| Missing transition | `services/npc/state_applicator.py:1060-1069` — `_DRIVE_TYPE_MAP` обрабатывает только `player_attacks`/`player_insults`/`player_threatens`/`theft`/`betrayal`/`help`/`saved_life`. Нет NPC-NPC источников. |

#### Classification

- [x] State exists
- [x] State is read
- [x] State is transformed (aging, urgency decay)
- [x] Decision generated
- [x] Action scheduled
- [x] Action executed (ATTACK boosted для vengeance drive)
- [ ] Consequence propagated (thresholds too high; player_attacks produces impact=0.5, никогда 0.7)

#### Gap type

**PROPAGATION GAP** — chain подключён, но thresholds делают его почти инертным. Плюс нет NPC-NPC drive generation path.

#### Observable consequence?

**NO in practice.** Требуется `stress_delta > 14` OR `trust_delta < -14` OR `fear_delta > 10.5` (state_applicator.py:1017-1053). SocialDeltaEngine outputs `trust=-10/-11`, `fear=+8` для `player_attacks` — falls short. Почти ни один TemporaryDrive не создаётся.

---

### Bridge 6: LifeProjectResolver → Behavior change

#### Current chain

```
phases/decision.py:123 (LifeProjectResolver.resolve)
   ↓
state.life_project_state FSM advances
   ↓
state.life_project swapped via _CRISIS_TRANSITIONS
   ↓
[BREAK: no consumer mutates schedule/activity_map/role/position]
   ↓
DecisionHub reads life_project at decision_hub.py:1447
   ↓
minor intent boost
```

#### Evidence (file:line)

| Role | Location |
|---|---|
| Producer | `services/phases/decision.py:123` |
| Data structure | `models/npc_state.py:610-611` (life_project: str, life_project_state: str FSM) |
| Reader | `services/npc/decision_hub.py:1446-1463` (boosts intents in `_direction_intents[life_project]`) |
| Transformation | `services/npc/life_project_resolver.py:38-77` (FSM: ACTIVE→COLLAPSING→LOST→SEARCHING→COMMITTED→ACTIVE) |
| Terminal consumer | `services/npc/decision_hub.py:1462-1463` (`if intent in _expected_intents: base += _desire * 1.5 + _significance * 0.5`) |
| Missing transition | `services/npc/life_engine.py:2078-2282` (`update_routine`) — читает ТОЛЬКО `npc.routine.schedule`. LifeProject change НИКОГДА не мутирует schedule, activity_map, role, или position. |

#### Classification

- [x] State exists
- [x] State is read
- [x] State is transformed (FSM transitions)
- [x] Decision generated (slight intent boost)
- [x] Action scheduled
- [x] Action executed (e.g., "isolation" boosts FLEE)
- [ ] Consequence propagated (no workplace change, no relocation, no schedule change)

#### Gap type

**DECISION GAP** — FSM string меняется, DecisionHub читает, но observable world consequence (NPC должен релоцироваться, менять работу, менять schedule) структурно отсутствует.

#### Observable consequence?

**WEAK.** DecisionHub может чаще выбирать "flee" при `life_project="isolation"`. Но SocialTargetResolver выбирает nearest NPC как flee target (случайный), не meaningful "isolation" behavior. Никакой schedule/workplace мутации.

---

### Bridge 7: NpcDialogueSubscriber → ResponseGenerator

#### Current chain

```
NPC_SPOKE event
   ↓
NpcDialogueSubscriber.on_npc_spoke
   ↓
add_dialogue_turn (STM)
   +
[DEAD: affective.apply (affective_integrator=None)]
   +
RelationshipStore.update
   ↓
[BREAK: no ResponseGenerator class exists]
   ↓
NPC B's next DecisionHub tick runs with NO knowledge of A's speech
```

#### Evidence (file:line)

| Role | Location |
|---|---|
| Producer | `services/execution/dialogue_materializer.py:39-52` (publishes NPC_SPOKE EventDTO) |
| Data structure | `services/events/npc_dialogue_subscriber.py:18-44` (NpcDialogueSubscriber class) |
| Reader | `services/events/npc_dialogue_subscriber.py:46-90` (on_npc_spoke) |
| Transformation | `services/events/npc_dialogue_subscriber.py:132-146` (compute_rel_delta → RelationshipStore.update) |
| Terminal consumer | `services/memory/relationship_store.py:94-118` (update JSON) |
| Missing transition | NO class named "ResponseGenerator" exists. `grep -r "ResponseGenerator" backend/app/` → 0 hits. Subscriber пишет trust/fear, но НЕ создаёт `CommunicationIntent` для NPC B чтобы ответить. |

#### Classification

- [x] State exists (NPC_SPOKE event)
- [x] State is read (subscriber processes it)
- [x] State is transformed (trust/fear delta computed)
- [ ] Decision generated (no response intent created)
- [ ] Action scheduled
- [ ] Action executed
- [ ] Consequence propagated

#### Gap type

**EXECUTION GAP** — trust обновлён, но у NPC B нет механизма сгенерировать response intent. DecisionHub tick NPC B видит vacuum для отношения к NPC A (`memory_weights_map` содержит только "player" key).

#### Observable consequence?

**NO.** NPC B обновляет trust в JSON, но никогда не генерирует defensive/angry response. Шаг 7 acceptance test ("Borko responds defensively") не может сработать из этого пути. Любой ответ NPC B приходит от generic proactive TALK на следующем тике — но target это nearest NPC, не конкретно A.

---

### Bridge 8: player_cognition pipeline

#### Current chain

```
[DEAD: build_perceived_scene has 0 production callers]
```

#### Evidence (file:line)

| Role | Location |
|---|---|
| Producer | `services/player_cognition/pipeline.py:146-215` (`build_perceived_scene` — 8-layer pipeline) |
| Data structure | `services/player_cognition/types.py` (PerceivedScene dataclass) |
| Reader | ONLY `tests/test_player_cognition_pipeline.py` |
| Transformation | pipeline.py lines 171-205 (spatial → perception → attention → recognition → interpretation → distortion → memory → uncertainty → PerceivedScene) |
| Terminal consumer | NONE in production code |
| Missing transition | N/A — chain stops at definition. `grep "from app.services.player_cognition"` → 0 hits вне `player_cognition/` folder. |

#### Classification

- [x] State exists (pipeline defined)
- [ ] State is read (no production caller)
- [ ] State is transformed
- [ ] Decision generated
- [ ] Action scheduled
- [ ] Action executed
- [ ] Consequence propagated

#### Gap type

**BRIDGE GAP** — pure dead code. Нет consumer вообще. Даже если подключить, pipeline.py docstring (line 152) подтверждает что это "для UI" — read-only perception, не autonomy driver.

#### Observable consequence?

**NO.** Pipeline никогда не запускается. 8 слоёв архитектурно полны, но runtime-dead.

---

## 4. 11-step Acceptance Test — Backward Trace

**Test:** Player tells Lusya "Borko is spying on you" → chain reaction → Orm avoids Borko.

| Step | Producer | Data structure | Consumer | Transformation | Next producer | GAP |
|------|----------|----------------|----------|----------------|---------------|-----|
| 1. Player says phrase to Lusya | `phase_1_input.py:241` publishes PLAYER_SPOKE | EventDTO (event_type=PLAYER_SPOKE) | EventBus | classified_type="dialogue" | PerceptionSubscriber | NONE |
| 2. Lusya receives info | PerceptionSubscriber + filter_perceiving_npcs | perceiving_npc_ids set | reduction.py:247 filters npc_contexts | Lusya in perceiving set | apply_perception_memory | NONE (memory summary written) |
| 3. Lusya forms belief/suspicion | BeliefTransitionEngine.integrate (npc_tick_pipeline.py:303) | BeliefState dict | BeliefModifierResolver | _THREAT_TYPES check | (no belief formed) | **PROPAGATION GAP**: PLAYER_SPOKE ∉ _THREAT_TYPES (belief_transition_engine.py:40-48). DANGER/PLAYER_HOSTILE никогда не обновляются для диалога. ALLY_NEARBY никогда не пишется. |
| 4. After N ticks Lusya approaches Borko | DecisionHub selects APPROACH | AgentAction.intent=APPROACH | SocialTargetResolver | nearest NPC within 5m | MacroMovementGoal | **EXECUTION GAP**: SocialTargetResolver возвращает NEAREST NPC (social_target_resolver.py:31-37), не конкретно Borko. Lusya подходит к ближайшему. |
| 5. Lusya asks "Were you watching me?" | DecisionHub selects TALK, CommunicationIntent built | CommunicationIntent (speaker=Lusya, audience=Borko, topic) | post_decision.py → DialogueQueue → DialogueExecutor | LLM call | NPC_SPOKE event | **DECISION GAP**: topic_extractor.py:55-70 maps "борко" → "стража", но только если raw_input содержит keyword. На autonomous tick Lusya raw_input это NEXT action игрока, не original "Borko spying" speech. Topic defaults to "разговор". |
| 6. Borko responds defensively | NpcDialogueSubscriber.on_npc_spoke | RelationshipStore.update (Borko→Lusya trust+0.005 if NEUTRAL) | (next tick) Borko's DecisionHub | (none — emotion branch dead) | (no response intent) | **EXECUTION GAP**: affective_integrator=None. Borko's emotion stays neutral. Borko's relationship_cache[Lusya] never populated. |
| 7. Orm hears exchange | PerceptionSubscriber (NPC_SPOKE in _PERCEPTION_EVENT_TYPES) | perceiving_npc_ids set | reduction.py:247 | Orm in perceiving set if within 10m | (Orm's tick uses player's hub_event, not Lusya's NPC_SPOKE) | **PROPAGATION GAP**: apply_perception_memory использует state.hub_event (player's action), не accumulated NPC_SPOKE. Orm's memory write это player's action summary, не Lusya's speech. |
| 8. Orm stores episodic memory | apply_perception_memory creates EventDTO | EventMemory record | memory_manager.apply | filter_perceiving_npcs check | (Orm not in target_id; memory summary is player's action) | **PROPAGATION GAP**: NpcDialogueSubscriber пишет memory ТОЛЬКО для payload.target_id (Borko). Orm никогда не получает Lusya's actual dialogue text. |
| 9. Orm updates opinion of Borko | (nothing — SocialDeltaEngine._BASE_DELTAS has no npc_spoke entry) | (no StateDeltas generated) | (RelationshipStore.update never called for Orm→Borko) | N/A | N/A | **BRIDGE GAP**: SocialDeltaEngine._BASE_DELTAS (social_deltas.py:36-49) обрабатывает только player_* events. |
| 10. Orm begins avoiding Borko | (Orm's DecisionHub runs; relationship_cache[Borko] empty) | (vacuum — None) | DecisionHub._get_rel_value returns None | FLEE not biased toward Borko | (Orm picks nearest NPC for FLEE target) | **EXECUTION GAP**: Orm's relationship_cache[Borko] пуст (assemble_preloaded_data загружает только "player"). DecisionHub видит vacuum. |
| 11. Final state reflects causal chain | (audit) | (only Steps 1-2 produced observable state) | (Steps 3-10 broken) | (no causal chain) | N/A | **FAIL** — только 2 из 11 шагов производят observable consequences |

### Result: **9 из 11 шагов содержат gap. Цепочка сломана на шаге 3.**

---

## 5. Summary: Gap Taxonomy

| Gap Type | Count | Components |
|---|---|---|
| **bridge gap** | 2 | player_cognition pipeline (dead code), SocialDeltaEngine для NPC-NPC opinion updates (нет entries в `_BASE_DELTAS`) |
| **propagation gap** | 5 | RelationshipStore (NPC-NPC cache never populated), L1Chronicle (NPC-NPC dialogue never written), BeliefState (ephemeral + ALLY_NEARBY + CoherenceBeliefAggregator dead), Acceptance steps 7+8 (Orm eavesdrop), Acceptance step 3 (belief formation) |
| **decision gap** | 2 | LifeProjectResolver (FSM changes but no schedule mutation), Acceptance step 5 (topic_extractor doesn't carry forward Lusya's suspicion) |
| **execution gap** | 3 | NpcDialogueSubscriber→ResponseGenerator (no response intent class), Acceptance step 4 (SocialTargetResolver picks nearest), Acceptance step 10 (Orm's relationship_cache[Borko] empty → no FLEE bias) |

**Total gaps: 12**

---

## 6. The Actual Architectural Problem

```
┌───────────────────────────────┐
│       SIMULATION CORE          │
│                                │
│  RelationshipStore             │
│  DecisionHub                   │
│  BreakProgressEngine           │
│  LifeProjectResolver           │
│  TemporaryDrive                │
│  L1Chronicle                   │
│  BeliefState                   │
│  DialogueQueue                 │
└───────────────┬────────────────┘
                │
                │  incomplete bridges
                ▼
┌───────────────────────────────┐
│       OBSERVABLE WORLD         │
│                                │
│  Speech (частично — Bridge 4)  │
│  Movement (частично — schedule only) │
│  Avoidance (НЕТ)               │
│  Rumors (НЕТ)                  │
│  Episodic Memory (НЕТ для NPC-NPC) │
│  Social reactions (НЕТ — no ResponseGenerator) │
└────────────────────────────────┘
```

Core **не пустой**. Core **не обязательно сломан**.

Проблема: **многие causal chains термининируют в latent state, не в observable behavior.**

---

## 7. Definition of a Working Social Simulation

Социальная механика НЕ считается завершённой, просто потому что `trust` изменился.

Механика **функционально завершена**, когда:

```
event
   ↓
perception
   ↓
memory
   ↓
relationship change
   ↓
belief/opinion change
   ↓
decision
   ↓
observable action
   ↓
new perception by others
```

### Acceptance Test (финальный критерий)

1. Player tells Lusya: "Borko is spying on you."
2. Lusya receives the information.
3. Lusya forms a belief or suspicion.
4. After several ticks, Lusya approaches Borko.
5. Lusya asks: "Were you watching me?"
6. Borko responds defensively.
7. Orm hears the exchange.
8. Orm stores an episodic memory.
9. Orm updates his opinion of Borko.
10. Orm begins avoiding Borko.
11. Final state reflects causal chain.

**Important property:** не точная реплика. Важное свойство — **оригинальное событие создаёт цепочку observable consequences.**

**Текущий статус:** FAIL на шаге 3 (chain сломан). Только 2/11 шагов производят observable consequences.

---

## 8. Strategic Priority

Правильный вопрос не:
- «Should we fix SocialEngine?» vs «Should we build NPCJournal?»

Правильный вопрос:

> **«Which missing bridge currently prevents the largest number of existing simulation systems from becoming observable behavior?»**

### Вероятный приоритет (требует кодовой валидации)

1. **Bridge 7 (NpcDialogueSubscriber → ResponseGenerator)** — без этого NPC-NPC диалоги односторонние. Закрывает steps 5, 6, 7, 8 acceptance test.
2. **Bridge 1 (RelationshipStore NPC-NPC cache)** — без этого DecisionHub видит vacuum для NPC-NPC пар. Закрывает step 10.
3. **Bridge 3 (BeliefState serialization + ALLY_NEARBY writer)** — без этого Lusya не формирует suspicion. Закрывает step 3.
4. **Bridge 6 (LifeProject → schedule mutation)** — без этого crisis transitions косметика. Закрывает long-term fate events.
5. **Bridge 2 (L1Chronicle NPC-NPC TraitDriftEvent)** — без этого beliefs о других NPC не кристаллизуются. Закрывает step 9.
6. **Bridge 5 (TemporaryDrive threshold tuning)** — без этого эмерджентная мораль не активируется.
7. **Bridge 8 (player_cognition подключение)** — без этого epistemic asymmetry. Закрывает player perception layer.

### Принципы

- **Не строить параллельную архитектуру.**
- **Не дублировать RelationshipStore.**
- **Не давать LLM решать.** Backend определяет meaning, LLM рендерит language.
- **Не создавать story engine в обход causal simulation.**
- **Сначала audit, потом мост.** Не создавать NPCJournal, пока не доказано что существующая модель памяти не может быть расширена.

---

## 9. Final Principle

> **«Numbers become gameplay only when they can change what an entity perceives, remembers, believes, decides, says, or does.»**

Until then, the system has simulated state.
It does not yet have a living world.

---

## 10. Next Step

**Не:** сразу писать N-01..N-08.
**Да:** для каждого gap — найти **минимальный мост** (1-3 строки кода) который reconnects существующие провода, без создания нового слоя.

Каждый мост должен быть:
- Concrete (file:line)
- Minimal (не новая подсистема)
- Reconnecting (использует существующие data structures)
- Observable (производит видимый эффект)

После аудита мостов — обновить `ENIGMA_CLOSURE_CONTRACT.md` до v1.4 с фазой **N: Manifestation Bridges**, где каждый пункт это **достройка существующего провода**, не новый компонент.

---

## 11. Audit Status

| Что | Статус |
|---|---|
| 8 components audited | ✅ |
| 11-step acceptance test traced | ✅ |
| 12 gaps classified | ✅ |
| Minimal bridges identified | ⏳ (требует отдельной проработки) |
| Contract v1.4 update | ⏳ (после моста аудита) |

**Документ не завершён.** Это forensic audit, не дизайн. Следующий шаг — **карта минимальных мостов** для каждого из 12 gaps.

---

*Forensic audit completed: 2026-07-20*
*Source: V.0.5.3.5.3_-_-_-*
*Components audited: 8*
*Gaps found: 12 (2 bridge, 5 propagation, 2 decision, 3 execution)*
*Acceptance test result: 2/11 steps produce observable consequences*

---

# FORENSIC-2 UPDATE — 2026-07-21 (V.0.5.3.5.4)

## A. Concrete minimal bridges identified (next iteration)

### Bridge 7 — ONE-LINE FIX (highest priority)

**File:** `services/game_loop/task_scheduler.py:233-237`

**Bug:** `_dlg_entry` cache stores only `{"speaker_id", "text", "timestamp"}` — **drops `target_id`**. `tick_orchestrator.py:1048` checks `dialogue.get("target_id") == npc_id` → always False → `ctx.response_targets[npc_id]` never set → Bridge 7 producer never fires.

**Fix:**
```python
# task_scheduler.py:233
_dlg_entry = {
    "speaker_id": ev.source,
    "target_id": ev.payload.get("target_id"),  # ← ADD THIS LINE
    "text": ev.payload.get("text", ""),
    "timestamp": ev.timestamp,
}
```

**Unblocks:** NPC_B responds specifically to NPC_A (not nearest NPC). Acceptance test step 6.

---

### Bridge 2 — Wire L1Chronicle write in NpcDialogueSubscriber

**File:** `services/events/npc_dialogue_subscriber.py:127` (after RelationshipStore.update)

**Bug:** `self._l1_chronicle = l1_chronicle` stored but **never called**. NPC-NPC dialogue never written to L1Chronicle → BeliefCrystallizationEngine never sees NPC-NPC events.

**Fix:**
```python
# In _process_canonical, after RelationshipStore.update:
if self._l1_chronicle:
    from app.services.npc.l1_chronicle import TraitDriftEvent
    _event = TraitDriftEvent(
        tick_id=tick,
        target_id=listener,
        source_id=f"dialogue:{tone}",
        effect_value=delta_trust,
        observation_weight=1.0,
        event_type="social_dialogue",
    )
    self._l1_chronicle.commit_tick_buffer([_event], tick)
```

**Unblocks:** Bridge 2 → NPC-NPC dialogue flows to L1Chronicle → PatternDetector → BeliefCrystallizationEngine.

---

### Bridge 5 + Step 9 — P2-05 redemption

**Bug:** `social_deltas.py:49-55` adds 6 NPC-NPC event types (`npc_insults`, `npc_helps`, etc.) but:
- (a) No code emits these event_type strings — only `npc_spoke` exists
- (b) Line 177 hardcodes `target="player"` — would write NPC-NPC deltas to player relationship (WRONG)

**Fix (2 changes):**

1. **Map NPC_SPOKE + tone → event_type** in `services/events/npc_dialogue_subscriber.py`:
```python
_TONE_TO_NPC_EVENT = {
    "ANGRY": "npc_insults",
    "MANIPULATIVE": "npc_threatens",
    "FRIENDLY": "npc_helps",
    "FEARFUL": "npc_threatens",
    "FLIRTY": "npc_helps",
}
_npc_event_type = _TONE_TO_NPC_EVENT.get(tone)
if _npc_event_type:
    # emit EventContext(event_type=_npc_event_type, actor_id=speaker, target_id=listener)
```

2. **Fix target routing** in `services/npc/decision/social_deltas.py:177`:
```python
# Was: target="player"
target = event.actor_id if _et_val.startswith("npc_") else "player"
```

**Unblocks:** Bridge 5 (TemporaryDrive for NPC-NPC events) AND Step 9 (Orm updates opinion of Borko).

---

## B. New issues introduced by v5354 fixes

| # | Severity | File:line | Issue |
|---|---|---|---|
| NEW-1 | 🔴 CRITICAL | `task_scheduler.py:233-237` | `_dlg_entry` missing `target_id` — Bridge 7 producer dead (one-line fix) |
| NEW-2 | 🔴 HIGH | `social_deltas.py:49-55, 177` | P2-05 unreachable + misrouted — 6 new event types never fire, would write to player if they did |
| NEW-3 | 🟠 MEDIUM | `npc_dialogue_subscriber.py:36, 44` | `l1_chronicle` ghost parameter — stored, never called. Bridge 2 still broken. |
| NEW-4 | 🟡 LOW | `decision.py:271-275` | `compute_social_modifiers(player_distances={})` — no crash but produces 0 modifiers. TODO at line 269 acknowledged. |
| NEW-5 | 🟡 LOW | `service_factories.py` | SocialEngine source-fixed, runtime still shows "disabled" — possibly stale process or path mismatch on Windows |
| NEW-6 | 🟡 LOW | `movement_engine.py:195-226` | `_resolve_doorway` works but limited to 1.5m axial offsets — wider doorways still fall back to REJECTED |

---

## C. Updated acceptance test trace (v5354)

| Step | v5353 | v5354 | Blocker |
|---|---|---|---|
| 1 Player → Lusya | ✓ | ✓ | — |
| 2 Lusya receives | ✓ | ✓ | — |
| 3 Lusya forms belief | ✗ | ✗ | `_THREAT_TYPES` player-only; PLAYER_SPOKE not included |
| 4 Lusya approaches Borko | ✗ | ✗ | SocialTargetResolver picks nearest; trust=0 doesn't trigger prefer>30 |
| 5 Lusya asks "Were you watching?" | ✗ | ✗ | topic_extractor needs keyword in raw_input |
| 6 Borko responds defensively | ✗ | ✗ | **NEW-1: target_id dropped from _dlg_entry** |
| 7 Orm hears exchange | ✗ | ✗ | Orm's hub_event = player action, not Lusya's NPC_SPOKE |
| 8 Orm stores episodic memory | ✗ | ✗ | NpcDialogueSubscriber writes memory only for target_id listener |
| 9 Orm updates opinion of Borko | ✗ | ✗ | **NEW-2: P2-05 npc_* entries unreachable** |
| 10 Orm avoids Borko | ✗ | ✗ | Orm→Borko trust=0, no FLEE bias |
| 11 Final state | ✗ | ✗ | Causal chain breaks at step 3 |

**Same result as v5353: 2/11.** But Bridge 1 cache population enables future fixes — once NEW-1, NEW-2, NEW-3 fixed, steps 6, 7, 8, 9 will cascade.

---

## D. Top 3 priority fixes for next iteration

1. **ONE-LINE FIX — NEW-1**: `task_scheduler.py:233` add `"target_id": ev.payload.get("target_id")`. **Unblocks Bridge 7 end-to-end.**

2. **Bridge 2 — wire L1Chronicle write**: `npc_dialogue_subscriber.py` add `commit_tick_buffer` call. **Unblocks BeliefCrystallizationEngine for NPC-NPC.**

3. **NEW-2 — P2-05 redemption**: (a) Map NPC_SPOKE + tone → `npc_insults`/`npc_helps`/etc., (b) fix `social_deltas.py:177` to use `event.actor_id` for npc_* events. **Unlocks TemporaryDrive + Step 9.**

---

*Forensic-2 audit completed: 2026-07-21*
*Source: V.0.5.3.5.4_-_-_*
*Components re-audited: 8*
*New issues: 6 (2 critical, 1 high, 1 medium, 2 low)*
*Acceptance test result: 2/11 (unchanged from v5353)*
*Critical one-line fix identified: NEW-1*
