# Stage 2.1-R9 — Authorization Lifecycle Consistency Audit

**Mode:** READ-ONLY
**Date:** 2026-11-03
**Purpose:** Verify the four areas R8 left unresolved before Master approves implementation.

---

## Executive Summary

R9 found **three structural gaps** that must be resolved before implementation:

1. **`scene_state["intent_lifecycle"]` does NOT exist yet** — it is a proposed structure, not implemented code.
2. **`will_response` does NOT persist as a structured object** — it is a local variable in Phase 1, fragmented into `will_conflict_data` dict + delta_buffer + EventBus. BodyArbiter cannot read the full evaluation.
3. **Phase 5.5/5.6 does NOT exist** — the phase schedule runs 1→2→3→4→5→6→7→8→9→9.1→10. The INPUT_MERGE combat pipe publishes PLAYER_ATTACKED at Phase 1. A BodyArbiter at Phase 5.5 cannot gate a publication that already happened at Phase 1.

These are not bugs — they are prerequisites that must be designed before the bypass fix can be implemented.

---

## §1. Intent Lifecycle

### 1.1. What Exists Today

| Structure | Location | Status | Purpose |
|-----------|----------|--------|---------|
| `scene_state["npc_intents"]` | tick_orchestrator (writer), simulation.py (reader) | ✅ EXISTS | RAM-canonical source for NPC intents (ADR-O-408, Gate①). Single-writer: orchestrator at attention-bridge. Full selection, not just changes. |
| `scene_state["pending_tasks"]` | Phase 6 (QueuedTask) | ✅ EXISTS | DIALOGUE → QueuedTask (ADR-O-313) |
| `scene_state["windup_held_intents"]` | post_decision.py:343, test g3_execution_probe.py:52 | ✅ EXISTS | Held intents during windup creation. Key = `intent_id`, value = `intent.to_dict()` |
| `scene_state["intent_lifecycle"]` | — | ❌ NOT FOUND | **Does not exist.** No writer, no reader, no serialization. Searched all pasted content — zero matches. |

### 1.2. IntentIdentity — Exists but NOT Git-Tracked

```python
# backend/app/domain/intent_identity.py (NOT git-tracked — EXITCODE 1 from git ls-files)
class IntentIdentity:
    """R5.4: 4 поля Identity для event attribution."""
    intent_owner: str    # player name/id OR character_id for autonomous
    actor_id: str        # who executes (npc_id in world)
    body_id: str         # the body (= actor_id for single-body)
    control_source: ControlSource  # PLAYER_INPUT | NPC_DECISION | AVATAR_INITIATIVE

    @classmethod
    def for_npc(cls, npc_id: str) -> "IntentIdentity": ...
    @classmethod
    def for_player_input(cls, player_name: str, character_id: str) -> "IntentIdentity": ...
    @classmethod
    def for_avatar_initiative(cls, character_id: str) -> "IntentIdentity": ...
    @classmethod
    def unknown(cls) -> "IntentIdentity": ...
```

**Status:** File exists on disk, NOT committed to git. This is a new file from the R5.4 design, not yet integrated.

### 1.3. IntentDTO — No Lifecycle State

```python
# backend/app/domain/intent.py:57
class IntentDTO:
    # action, target, parameters — NO lifecycle_state field
    ...
```

IntentDTO is referenced as:
- `original_intent: IntentDTO` in WillResponseDTO (models/will.py:94)
- `counter_offer: Optional[IntentDTO]` in WillResponseDTO (models/will.py:75) — Avatar's alternative proposal

IntentDTO is a data carrier. It does NOT have lifecycle state. This is correct per Master's decision (DTO carries data, not state).

### 1.4. NPCState Intent Fields — Different Concept

NPCState has intent tracking fields:
- `intent_formed_at`, `intent_target`, `intent_duration`, `intent_progress_ticks`, `last_intent_change`, `intent_tick`

These track the NPC's CURRENT intent as part of NPC state. They are NOT a general intent lifecycle store. They are per-NPC, per-tick tracking, not a cross-cutting lifecycle manager.

### 1.5. `intent_id` Stability

The `held_intent_id` field in ActionWindup (action_windup.py:40) links a windup to its source intent. The `_held_store[_intent_id] = intent.to_dict()` at post_decision.py:343 stores intents by ID during windup creation.

**However:** I could NOT find where `intent_id` is GENERATED. Is it a UUID? A sequential counter? A hash of intent content? This is UNCONFIRMED — the generation point was not captured in any pasted content file.

**Risk:** If `intent_id` is content-based (hash), two identical intents in the same tick could collide. If it's sequential, replay must preserve the counter. This needs verification before implementation.

### 1.6. Gap: `scene_state["intent_lifecycle"]` Must Be Created

**Current:** No such structure exists.
**Target (per Master):** `scene_state["intent_lifecycle"]` — canonical lifecycle store.
**Required:**
- Format: dict keyed by `intent_id`, value = lifecycle record (state, timestamps, arbitration result)
- Writer: BodyArbiter ONLY (for state transitions)
- Reader: publication paths (check state before publishing)
- Serialization: must survive `atomic_commit` / load round-trip (Phase 10 persistence)
- Replay: deterministic — lifecycle transitions must be replayable

**UNCONFIRMED:** Whether existing `scene_state["npc_intents"]` can be extended to serve as the lifecycle store, or whether a separate structure is needed. `npc_intents` is described as "full selection, not just changes" — it may be a projection, not a lifecycle tracker.

---

## §2. Arbitration Handoff

### 2.1. WillpowerGate Output — WillResponseDTO

```python
# backend/app/models/will.py:61
class WillResponseDTO:
    state: WillState                    # COMPLY/RELUCTANT/CONDITIONED/RESIST/DELAY/etc.
    resistance: float                   # 0.0-1.0
    fear_delta: float                   # fear increment
    stress_delta: float                 # 0-100 scale
    identity_damage: float              # trauma
    generated_emotions: List[EmotionPayload]
    counter_offer: Optional[IntentDTO]  # Avatar's alternative
    embodied_vector: Optional[EmbodiedVector]
    social_signal: str                  # for CFRM
    crowd_threat_level: str             # for CFRM
    narration_hooks: ...
```

### 2.2. How will_response Flows Today

**will_response is a LOCAL VARIABLE** in `run_phase_1_input` (phases/input.py:123). It does NOT persist as a structured object on ctx or shared_context.

The data is DISPERSED into three channels:

| Channel | What's written | Where |
|----------|---------------|-------|
| `shared_context.will_conflict_data` (dict) | state, resistance, embodied_vector, counter_offer_text | phases/input.py:188 (COMPLY+damage), :234 (RESIST) |
| `ctx.delta_buffer` (StateDeltas) | WillConflictPayload, EmotionPayload (fear, stress), IdentityPayload | phases/input.py:157-185, :215-228, :265-291 |
| EventBus | WILL_CONFLICT event (state, resistance) | phases/input.py:253-262 |

**BodyArbiter at Phase 5.5 would need to read the evaluation result.** But the structured WillResponseDTO is gone — only the fragmented `will_conflict_data` dict persists. The dict lacks `fear_delta`, `stress_delta`, `identity_damage`, `generated_emotions`, `counter_offer` (as IntentDTO), `social_signal`, `crowd_threat_level`.

### 2.3. Problem: Psychological Effects Applied in Phase 1

WillpowerGate does NOT only evaluate — it ALSO applies effects immediately in Phase 1:

| Effect | When applied | Phase |
|--------|-------------|-------|
| `fear_delta` → EmotionPayload(stress) | L265-275 | Phase 1 |
| `stress_delta` → EmotionPayload(distress) | L278-291 | Phase 1 |
| `identity_damage` → IdentityPayload | L156-166 (COMPLY path) | Phase 1 |
| `affective conditioning` (trauma strengthening) | L293-304 | Phase 1 |
| `WILL_CONFLICT` event published | L253-262 | Phase 1 |

**If BodyArbiter reads the evaluation at Phase 5.5, the psych effects have ALREADY been applied.** The avatar has already taken stress/fear/trauma from the resistance, even if BodyArbiter later decides to authorize the action.

**This violates Master's principle:** WillpowerGate provides evaluation. BodyArbiter decides. But currently WillpowerGate both evaluates AND applies consequences in the same phase.

### 2.4. Required Separation

**Target:**
1. WillpowerGate (Phase 1): compute `WillResponseDTO`, store it for BodyArbiter. DO NOT apply psych effects yet.
2. BodyArbiter (Phase 5.5): read `WillResponseDTO`, make arbitration decision, transition intent lifecycle.
3. Psych effects applied AFTER BodyArbiter decides — based on the final decision, not just the evaluation.

**But:** This changes WillpowerGate's current behavior. Currently it applies effects immediately. Separating evaluation from effect-application is a design change, not just a gate insertion.

**UNCONFIRMED:** Whether the existing `will_conflict_data` dict is sufficient for BodyArbiter, or whether the full `WillResponseDTO` must be preserved on ctx. Given that BodyArbiter needs `counter_offer` (Avatar's alternative IntentDTO) to decide SUPERSEDED, and `will_conflict_data` only has `counter_offer_text` (string, not IntentDTO) — the full DTO must be preserved.

### 2.5. How to Pass will_response to BodyArbiter Without Second SSOT

**Option A:** Store `WillResponseDTO` on `ctx` (tick context) — not on shared_context, not on IntentDTO. ctx is the tick-scoped carrier. BodyArbiter reads `ctx.will_response`.

**Option B:** Store `WillResponseDTO` in `scene_state["intent_lifecycle"][intent_id]["evaluation"]` — the lifecycle record carries the evaluation alongside the state. BodyArbiter reads from the canonical store.

**Master's direction:** `scene_state["intent_lifecycle"]` is canonical. Option B aligns. But Option A is simpler and doesn't require the lifecycle store to exist first.

**UNCONFIRMED:** Which option Master prefers. Both avoid a second SSOT — the evaluation lives either on ctx (tick-scoped) or on the lifecycle record (intent-scoped).

---

## §3. Materialization — All Player Action Publication Paths

### 3.1. Phase Schedule (АРХИТЕКТУРНЫЙ_УСТАВ §3)

| Phase | Name | Key operations |
|-------|------|---------------|
| 1 | Input Merge | NPIC → Intervention Routing → **WillpowerGate** → delta_buffer. **INPUT_MERGE combat pipe publishes PLAYER_ATTACKED here.** |
| 2 | EventBus (primary) | SpatialEventDetector → NPC_MOVED, NPC_PROXIMITY |
| 3 | Memory | MemoryManager.apply() — **working_memory_tick.py:130 writes STM here** |
| 4 | Pre-Decision | TopicExtractor reads STM + phase_2_events |
| 5 | Decision | NpcTickPipeline.run() → TickMutation (npc_deltas, communication_intents) |
| — | **(no Phase 5.5)** | **GAP — does not exist** |
| — | **(no Phase 5.6)** | **GAP — does not exist** |
| 6 | Post-Decision | IntentEventAdapter → EventDTO; WindupWriteGate (NPC path); ATTACK → ActionWindup |
| 7 | Windup Resolution | windup_registry → completed → release held intent → publish or INTERRUPTED |
| 8 | Layered Reduction | drain_events → handle (perception → reaction → social → combat → homeostasis) → StateApplicator |
| 9 | Integration | CFRM, BeliefCrystallization, WorldSnapshot |
| 9.1 | Affective Pipeline | integrate_affective_pressure |
| 10 | Persistence | atomic_commit |

### 3.2. All Player Action Publication Sites — Exact Causal Chain

#### Site 1: `publish_player_intent` (Phase 1)
```
Player input → resolve_player_intent → IntentDTO → ctx.player_intent
    ↓ Phase 1: run_phase_1_input
    ↓ compute_willpower → will_response
    ↓ if will_response.state in (COMPLY, RELUCTANT, CONDITIONED):
        publish_player_intent(ctx, intent) → PLAYER_ATTACKS / PLAYER_INTERACTS
```
**Gate:** WillpowerGate (Phase 1). Already correct.
**Phase:** Phase 1.
**Expects arbitration:** YES — but arbitration IS the WillpowerGate check here.

#### Site 2: `publish_player_speech` (Phase 1 or pre-tick)
```
Player raw_input → DM classification → shared_context.action_type
    ↓ publish_player_speech(player_name, action_text, classified_type, ...)
    ↓ get_event_bus().publish(PLAYER_SPOKE)
```
**Gate:** NONE.
**Phase:** Called from DM phase (pre-tick) or Phase 1.
**Expects arbitration:** NO — must be added.

#### Site 3: `publish_classified_player_event` (Phase 1)
```
Player raw_input → DM classification → shared_context.action_type
    ↓ publish_classified_player_event(shared_context, location, campaign_id, raw_input)
    ↓ Fast-Path lexical override (if "удар/бей/атак..." → force "attack")
    ↓ _resolved_type = _evt_map.get(action_type, PLAYER_SPOKE)
    ↓ G3C: if PLAYER_ATTACKED → defer to INPUT_MERGE combat pipe
    ↓ else: publish directly
```
**Gate:** NONE (Fast-Path bypasses even DM classification).
**Phase:** Phase 1.
**Expects arbitration:** NO — must be added.

#### Site 4: INPUT_MERGE combat pipe (Phase 1)
```
G3C deferral → PLAYER_ATTACKED deferred to INPUT_MERGE
    ↓ tick_orchestrator.py:1690-1718
    ↓ if getattr(shared_context, "action_rejected", False):  ← DEAD (never True)
        suppress
    ↓ else:
        publish PLAYER_ATTACKED  (L1718)
```
**Gate:** Dead `action_rejected` check.
**Phase:** Phase 1.
**Expects arbitration:** YES (was supposed to) — but the gate is dead.

### 3.3. The Critical Timing Contradiction

**All four publication sites run in Phase 1.** The proposed BodyArbiter is at Phase 5.5.

```
Phase 1: WillpowerGate evaluates + publishes PLAYER_ATTACKED/PLAYER_SPOKE
    ...
Phase 5.5: BodyArbiter decides authorization  ← TOO LATE
```

**If BodyArbiter is at Phase 5.5, it CANNOT gate publications that already happened at Phase 1.** The events are already on the EventBus. Subscribers have already received them (immediate callback). CombatSubscriber has already accumulated them in `_pending_events`.

### 3.4. Resolution Options

**Option A: Move BodyArbiter to Phase 1 (before publication)**
- BodyArbiter runs after WillpowerGate evaluation, before any publication
- Publication paths check lifecycle state set by BodyArbiter
- NPC DecisionHub (Phase 5) still doesn't see current Player action (same as now)

**Option B: Defer Player action publication to after Phase 5.5**
- Phase 1: WillpowerGate evaluates, stores result. Does NOT publish.
- Phase 5.5: BodyArbiter decides.
- Phase 5.6: Authorized publication — PLAYER_ATTACKED/PLAYER_SPOKE published only if ACTIVE.
- This is the R8 proposal, but it requires DEFERRING all Phase 1 Player publications to Phase 5.6.

**Option C: BodyArbiter at Phase 1, publication at Phase 5.6**
- Phase 1: WillpowerGate evaluates. BodyArbiter decides. No publication yet.
- Phase 5.6: Publication of authorized actions.
- This combines A and B — BodyArbiter early, publication late.

**Master anticipated this:** "если INPUT_MERGE действительно выполняется до Phase 5.5, то BodyArbiter не может просто выставить разрешение, которое INPUT_MERGE уже должен был проверить."

**R9 confirms:** INPUT_MERGE (Phase 1) DOES execute before the proposed Phase 5.5. The contradiction is real. Option A or C is required.

### 3.5. NPC Publication Paths — For Reference (Not Player)

| Site | Phase | What | Gate |
|------|-------|------|------|
| IntentEventAdapter | Phase 6 | NPC CommunicationIntent → EventDTO | WindupWriteGate (attack/steal → ActionWindup) |
| Windup Resolution | Phase 7 | Completed windups → EventDTO publish | Stale Intent Validation |
| QueuedTask execution | Phase 6+ | DIALOGUE → QueuedTask → scene_state["pending_tasks"] | TaskScheduler |

These are NPC paths — different consciousness, different authorization (DecisionHub + CommitmentArbiter). Not in scope for Player bypass fix.

---

## §4. Memory — add_dialogue_turn Full Contract

### 4.1. Signature and Semantics

```python
# backend/app/services/memory/memory_manager.py:106
def add_dialogue_turn(
    self, campaign_id: str, npc_id: str, speaker: str, text: str,
    target_id: str = "", intent: str = "", tone: str = "", tick: int = 0,
    partner_id: str = "player"
) -> None:
    """Добавляет реплику в STM конкретного NPC."""
    session = self.get_dialogue_session(campaign_id, npc_id, partner_id)
    session.add_turn(...)
```

**Parameter semantics:**

| Parameter | Meaning | Example |
|-----------|---------|---------|
| `campaign_id` | Campaign | "tavern_mystery" |
| `npc_id` | **The LISTENER** — whose STM this writes to | "guard_borko" |
| `speaker` | **WHO SPOKE** | "player" or "guard_borko" |
| `text` | What was said | "сдайся" |
| `target_id` | Who the speech was directed at | "guard_borko" |
| `intent` | Speech intent classification | "ACCUSE" |
| `tone` | Emotional tone | "SUSPICIOUS" |
| `tick` | When it happened | 42 |
| `partner_id` | Dialogue session partner (defaults to "player") | "player" |

**Key distinction:** `npc_id` is the LISTENER (the NPC whose memory is being written). `speaker` is the one who spoke. `target_id` is who the speech was addressed to. These can differ — an NPC can overhear speech directed at someone else.

### 4.2. All Callers

| # | Caller | File:Line | Phase | `npc_id` (listener) | `speaker` | Gated? |
|---|--------|-----------|-------|---------------------|-----------|--------|
| 1 | **DM phase** | dm_phase.py:185 | Pre-tick | target NPC | "player" | ❌ NO — writes BEFORE WillpowerGate |
| 2 | **Working memory tick** | working_memory_tick.py:130 | Phase 3 | hearing NPC | from bus event | ⚠ Indirectly — processes PLAYER_SPOKE from bus. If PLAYER_SPOKE not published, this doesn't write. |
| 3 | **NPC dialogue subscriber** | npc_dialogue_subscriber.py:520 | Phase 8 (drain) | listener NPC | NPC speaker | ✅ NPC path — different authorization |
| 4 | Test harnesses | multiple | test | varies | varies | N/A |

### 4.3. The Six Events Master Identified

Master distinguished six events for speech:

| # | Event | Current mechanism | Status |
|---|-------|-------------------|--------|
| 1 | Player entered text | API receives raw_input | ✅ Happens |
| 2 | Player formed intent to speak | resolve_player_intent → IntentDTO | ✅ Happens |
| 3 | Avatar allowed body for speech | WillpowerGate COMPLY/RELUCTANT/CONDITIONED | ⚠ Evaluated but not enforced on DM path |
| 4 | Body actually spoke words | PLAYER_SPOKE published | ❌ Published regardless of #3 (R7 bypass) |
| 5 | NPC perceived speech | ObservationSubscriber / perception_filter | ⚠ If PLAYER_SPOKE published, NPC perceives |
| 6 | NPC saved it in memory | add_dialogue_turn | ❌ DM writes to STM before #3 (dm_phase.py:185) |

### 4.4. Two STM Write Paths for Player Speech

**Path A — DM direct write (dm_phase.py:185):**
```
Player raw_input
    ↓ dm_phase.py:185: add_dialogue_turn(npc_id=target, speaker="player", text=raw_input)
    ↓ STM[target] now contains {speaker: "player", text: raw_input}
    ↓ Phase 1: WillpowerGate → RESIST
    ↓ PLAYER_SPOKE not published (after R8 fix)
    ↓ BUT STM already has the speech — NPCs can recall it
```
**BYPASS:** Even if PLAYER_SPOKE is not published, the DM has already written the speech to the target NPC's STM. NPCs can "remember" words the body never spoke.

**Path B — Working memory tick (working_memory_tick.py:130):**
```
PLAYER_SPOKE published (if authorized)
    ↓ Phase 3: working_memory_tick processes bus events
    ↓ For each hearing NPC: add_dialogue_turn(npc_id=hearer, speaker="player", text=...)
```
**Gated by publication:** If PLAYER_SPOKE not published, this path doesn't write. Correct behavior — but only if Path A is also blocked.

### 4.5. What Counts as "Spoken Speech Fact"

**Current:** `add_dialogue_turn` is called with `speaker="player"` in two places:
1. dm_phase.py:185 — DM writes Player speech (BEFORE authorization) — treats input as spoken fact
2. working_memory_tick.py:130 — Phase 3 writes from bus event (AFTER publication) — treats published event as spoken fact

**The DM path (Path A) conflates "Player entered text" (event #1) with "Body spoke words" (event #4).** It writes to STM as if the speech happened, before the Avatar has authorized the body to speak.

### 4.6. What Counts as "Heard Speech Fact"

**Current:** `add_dialogue_turn` writes to a specific NPC's STM (`npc_id` = listener). But there's no check whether the NPC actually HEARD the speech:
- Was the NPC within perception radius? (`action_perception_radius`)
- Was the NPC alive/conscious?
- Was there an obstruction?

The `working_memory_tick.py:130` path processes bus events — but does it filter by perception radius? This is UNCONFIRMED. If it writes to ALL NPCs' STM regardless of distance, that's a separate bug (NPCs "remembering" speech they couldn't hear).

The `npc_dialogue_subscriber.py:520` path (NPC→NPC) likely has perception filtering (ObservationSubscriber filters by radius). But the Player speech path via working_memory_tick is UNCONFIRMED.

### 4.7. STM Consumers — Who Reads What add_dialogue_turn Writes

| Consumer | File:Line | What it reads | For what |
|----------|-----------|---------------|----------|
| `get_stm_prompt_block` | memory_manager.py:209 | Dialogue session for (npc_id, partner_id) | DM LLM context, NPC prompt building |
| `get_stm_prompt_block_pair` | memory_manager.py:215 | Dialogue session for (npc_a, npc_b) | TaskScheduler, post_decision checks |
| DM phase | dm_phase.py:72 | `shared_context.npc_stm_block_targeted` | DM LLM gets STM context for targeted NPC |
| TaskScheduler | task_scheduler.py:689 | STM pair check | Dialogue coherence check |
| Post-decision | post_decision.py:115 | STM pair check | NPC dialogue coherence |

**If DM writes Player speech to STM at dm_phase.py:185, then DM reads it back at dm_phase.py:72 in the NEXT turn** — the DM sees "player said X" in STM, reinforcing the fiction that the speech happened.

---

## §5. Phase Ordering Verification

### 5.1. Does Phase 5.5 Exist?

**NO.** The phase schedule (АРХИТЕКТУРНЫЙ_УСТАВ §3) runs:
```
Phase 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 9.1 → 10
```

There is no Phase 5.5 or Phase 5.6. These would be NEW phase insertions.

### 5.2. Do All Player Publication Paths Pass Through Phase 5.5?

**NO.** All four Player publication sites run in Phase 1:

| Site | Phase | Publishes |
|------|-------|-----------|
| publish_player_intent | Phase 1 | PLAYER_ATTACKS, PLAYER_INTERACTS |
| publish_player_speech | Pre-tick / Phase 1 | PLAYER_SPOKE |
| publish_classified_player_event | Phase 1 | PLAYER_ATTACKED, PLAYER_SPOKE, etc. |
| INPUT_MERGE combat pipe | Phase 1 | PLAYER_ATTACKED (deferred) |

**A BodyArbiter at Phase 5.5 cannot gate any of these.** They all execute before Phase 5.5.

### 5.3. What Would Need to Change

To make BodyArbiter the gate for Player action publication:

**Either:**
- Move BodyArbiter to Phase 1 (after WillpowerGate evaluation, before publication)
- OR defer ALL Player action publications from Phase 1 to a new Phase 5.6 (after BodyArbiter at 5.5)

**The second option is more disruptive** — it changes when NPCs can perceive Player actions (currently Phase 1 publication → Phase 8 subscriber drain; deferred would be Phase 5.6 publication → Phase 8 drain, but Phase 5 DecisionHub still doesn't see it).

**The first option is less disruptive** — BodyArbiter runs in Phase 1, right after WillpowerGate. Publication still happens in Phase 1, but only if BodyArbiter authorizes. This keeps the existing phase schedule and only inserts BodyArbiter as a sub-step of Phase 1.

### 5.4. NPC Perception Timing

**Current:** PLAYER_ATTACKED published at Phase 1 → CombatSubscriber receives immediately (Phase 1) → drains at Phase 8 → ImpactEngine → damage.

NPCs DON'T perceive the attack via DecisionHub (Phase 5) — they perceive it via ObservationSubscriber (Phase 8 drain) and ReactionSubscriber (Phase 8 drain). NPC reaction happens NEXT tick (Phase 5 of next tick).

**With BodyArbiter at Phase 1:** Same timing — BodyArbiter runs early in Phase 1, publication happens after. No change to NPC perception timing.

**With BodyArbiter at Phase 5.5:** Publication deferred to Phase 5.6. CombatSubscriber still drains at Phase 8. NPC perception timing unchanged (still next tick for DecisionHub). But all Phase 1-5 phases don't see the Player action — which is ALREADY the case for combat.

---

## §6. Contradictions and Unconfirmed Places

### 6.1. Confirmed Contradictions

| # | Contradiction | Impact |
|---|--------------|--------|
| C1 | `scene_state["intent_lifecycle"]` does not exist | Must be created before BodyArbiter can use it as canonical store |
| C2 | `will_response` is a local variable, not persisted | BodyArbiter cannot read the full evaluation — only fragmented `will_conflict_data` dict |
| C3 | WillpowerGate applies psych effects in Phase 1 | Effects applied before BodyArbiter decides — violates separation of evaluation and decision |
| C4 | Phase 5.5/5.6 does not exist | Must be inserted into phase schedule — or BodyArbiter placed at Phase 1 |
| C5 | INPUT_MERGE publishes at Phase 1 | BodyArbiter at Phase 5.5 cannot gate Phase 1 publication |
| C6 | DM writes STM at dm_phase.py:185 before WillpowerGate | STM bypass — NPCs remember unspoken speech |

### 6.2. Unconfirmed Places

| # | Item | Status | Why unconfirmed |
|---|------|--------|-----------------|
| U1 | `intent_id` generation mechanism | NOT FOUND | Where is intent_id created? UUID? Counter? Hash? |
| U2 | `scene_state["npc_intents"]` format | PARTIALLY | Described as "RAM-canonical, full selection" but exact dict structure not captured |
| U3 | `working_memory_tick.py:130` perception filtering | NOT FOUND | Does it filter by perception radius before writing STM? |
| U4 | `publish_player_speech` call site | NOT FOUND | Where is this function actually called from? |
| U5 | `publish_classified_player_event` call site | NOT FOUND | Where is this function actually called from? |
| U6 | IntentDTO full field list | PARTIALLY | Found at intent.py:57 but full body not captured in pasted content |
| U7 | How `action_rejected` was supposed to be set | NOT FOUND | The field is read but never written — was it planned and never implemented, or removed? |
| U8 | Whether `_phase_1_input_merge` is a named function | NOT FOUND | The ADR-O-424 references it but the function definition wasn't captured |

---

## §7. Recommendations for Master

### 7.1. Prerequisites Before Implementation

Before the bypass fix can be implemented, these must be resolved:

1. **Create `scene_state["intent_lifecycle"]`** — or decide to use ctx-based evaluation passing instead
2. **Decide BodyArbiter placement** — Phase 1 (after WillpowerGate) or Phase 5.5 (requires deferring publication)
3. **Separate WillpowerGate evaluation from effect application** — or accept that psych effects apply at evaluation time
4. **Find or create `intent_id` generation** — stable, replay-safe
5. **Verify `publish_player_speech` and `publish_classified_player_event` call sites** — R7 found the definitions but not the callers

### 7.2. Recommended Sequence

**Step 0 (archaeology):** Find the call sites of `publish_player_speech` and `publish_classified_player_event`. Find `intent_id` generation. These are gaps in R7/R9 that must be closed.

**Step 1 (design):** Decide BodyArbiter placement (Phase 1 vs Phase 5.5). Decide evaluation passing mechanism (ctx vs lifecycle store).

**Step 2 (design):** Define `scene_state["intent_lifecycle"]` format — or decide to use a simpler mechanism.

**Step 3 (implement):** The actual bypass fix, after the above are resolved.

### 7.3. The Core Insight

R8 correctly identified the boundary (intent → arbitration → authorized action → world event). But R9 shows the existing code does not have the infrastructure to enforce it:

- No canonical lifecycle store
- No persistent evaluation result for BodyArbiter to read
- No Phase 5.5 in the schedule
- Publication happens before the proposed gate

The bypass is not just a missing check — it's a missing **causal chain**. The chain from "WillpowerGate evaluates" to "publication checks authorization" has no links in the current code. The links must be built before the check can be added.

**Production: HOLD.** R9 is read-only audit. Implementation requires Master's design decisions on §7.1.
