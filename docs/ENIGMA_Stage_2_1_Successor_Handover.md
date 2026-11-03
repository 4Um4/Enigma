# ENIGMA Stage 2.1 — Successor Handover

**Document type:** Project handover / architectural memory transfer
**Date:** 2026-11-03
**Author:** Architect (Stage 2.1 R1–R10)
**Recipient:** Successor architect/developer in a new ChatGPT window

---

## §1. Project Context

### 1.1. What is ENIGMA?

ENIGMA is a narrative simulation game where a Player controls a shared body (Avatar) in a world populated by autonomous NPCs. The core innovation: **two independent consciousnesses share one body**.

- **Player** — the human player's consciousness, expressed through text input.
- **Avatar** — the character's own consciousness, with its own psyche, trauma, willpower, and identity.
- **Body** — the physical body they share. Only one consciousness can control it at a time for any given action.

### 1.2. Canonical principle

> "Player может управлять телом Avatar. Но управление телом не означает владение сознанием Avatar."
>
> "The Player can control the Avatar's body. But controlling the body does not mean owning the Avatar's consciousness."

### 1.3. Causal architecture

```
CONSCIOUSNESS → INTENTION → ARBITRATION → AUTHORIZED ACTION → WORLD EVENT → PERCEPTION → MEMORY
```

- **Intention** — a consciousness wants to do something through the body.
- **Arbitration** — BodyArbiter decides whether this consciousness may use the shared body for this action.
- **Authorized action** — only if arbitration passes does the action materialize.
- **World event** — the materialized action becomes an EventBus event.
- **Perception** — NPCs perceive the event (filtered by distance/consciousness).
- **Memory** — NPCs and Avatar remember what actually happened.

**The principle "попытка ≠ событие" (attempt ≠ event)** governs every channel: an intention that was blocked must never become a world event or a memory.

### 1.4. Two modes of Avatar resistance

1. **Ordinary resistance** — Avatar resists a specific action (refuses to speak, hesitates to attack). The intent is blocked, but the Avatar doesn't seize control of the body.
2. **Full control struggle** — Avatar actively fights for control of the body, potentially replacing Player's intent with Avatar's own intent (counter-intent / supersession).

These are **different game mechanics**. `WillState.RESIST` does not automatically mean full control seizure. The system must distinguish:
- Refusal of a specific action
- Delay
- Resistance without body seizure
- Full control struggle
- Authorized action

### 1.5. Roles

| Role | What it does | What it must NOT do |
|------|-------------|---------------------|
| Player | Forms intentions via text input | Must not bypass Avatar's will |
| Avatar | Has psyche, evaluates pressure, may resist | Must not become a second Player |
| Body | Shared execution substrate | Must not act without authorization |
| BodyArbiter | Decides if a specific intent may use the body | Must not be bypassed by any publication path |
| WillpowerGate | Evaluates Avatar's resistance (Cumulative Strain Model) | Must NOT make the final authorization decision — only evaluates |
| EventBus | Delivers events to subscribers | Must only carry events of actually-completed actions |
| STM / Memory | Records what was spoken and heard | Must only record speech that was actually spoken and actually heard |

---

## §2. All Approved Architectural Decisions

### 2.1. Identity Contract (ADR-O-435-R5.4, APPROVED)

**4 fields:** `intent_owner` / `actor_id` / `body_id` / `control_source`

```python
# backend/app/domain/intent_identity.py (EXISTS but NOT git-tracked)
class IntentIdentity:
    intent_owner: str          # player name/id OR character_id
    actor_id: str              # who executes in the world
    body_id: str               # the body
    control_source: ControlSource  # PLAYER_INPUT | NPC_DECISION | AVATAR_INITIATIVE
```

- `for_player_input(player_name, character_id)` — owner=player, actor=body=character
- `for_avatar_initiative(character_id)` — owner=actor=body=character
- `for_npc(npc_id)` — owner=actor=body=npc

**Rejected:** 5-field version with `public_attribution` (R5.3 proposed, R5.4 corrected to 4).
**Constraint:** No new string-based identity comparisons. All identity checks go through `ControlSource` and `IntentIdentity`.

### 2.2. Intent Lifecycle (ADR-O-435-R5.4, APPROVED)

**6 states:** `ACTIVE` / `SUSPENDED` / `SATISFIED` / `ABANDONED` / `SUPERSEDED` / `VOIDED`

**CRITICAL (Master R9 correction):** `ACTIVE` does NOT mean "authorized to execute." ACTIVE means "the intention exists and awaits execution/arbitration." A separate `arbitration_result` field (on the lifecycle record, not the DTO) carries the authorization decision.

- `ACTIVE` → intent exists, may or may not be authorized
- `SATISFIED` → goal achieved; re-publishing would create duplicate
- `VOIDED` → BodyArbiter rejected; action must NOT materialize
- `SUPERSEDED` → replaced by competing intent (Avatar counter-intent — deferred)
- `ABANDONED` → consciousness withdrew
- `SUSPENDED` → arbitration in progress (transient)

**Rejected:** R8's proposal to equate `ACTIVE` with permission. R8's proposal to add `lifecycle_state` field to IntentDTO.

### 2.3. `scene_state["intent_lifecycle"]` — Canonical Store (Master R9, APPROVED)

**Status: DOES NOT EXIST YET — must be created.**

- One record per intention, keyed by stable `intent_id`
- Record contains: intent_id, owner, body_id, action, lifecycle_state, arbitration_result, created_tick, transitioned_tick
- Writer: BodyArbiter ONLY (for state transitions)
- Reader: publication paths (check `arbitration_result` before publishing)
- Must survive `atomic_commit` / load round-trip (Phase 10 persistence)
- Must be replay-deterministic — **NO `uuid.uuid4()` for keys**

**Rejected:** `action_authorized` as second SSOT boolean. `action_rejected` as basis (dead code). IntentDTO carrying lifecycle state.

### 2.4. Stable Identifiers

| Entity | ID mechanism | Replay-safe? | Status |
|--------|-------------|-------------|--------|
| Player | player_name (string) | ✅ Yes | EXISTS |
| Avatar / Body | character_id = CharacterSheet.name | ✅ Yes | EXISTS |
| Intent | `uuid.uuid4()` | ❌ NO — random | EXISTS but must be replaced |
| Event | `next_event_identity(scene_state, type, source) → (tick, ordinal)` | ✅ Yes | EXISTS (event_identity.py) |

**REQUIRED:** Create `next_intent_identity(scene_state, owner, action)` — mirror of `next_event_identity`, using `scene_state["intent_ordinals"]` (persistent monotonic counter). Replace `uuid.uuid4()` for intent_id generation in production paths.

### 2.5. WillpowerGate Role (Master R9, refined)

**WillpowerGate evaluates. BodyArbiter decides.**

- WillpowerGate: `compute_willpower(distorted_pressure, psyche) → WillResponseDTO`
- Computes: state (COMPLY/RELUCTANT/CONDITIONED/RESIST/DELAY/MISINTERPRET/NEGOTIATE/etc.), resistance, fear_delta, stress_delta, identity_damage, counter_offer, embodied_vector
- Does NOT decide final authorization
- Does NOT set lifecycle state

**Psychological effects** currently applied by WillpowerGate in Phase 1:
- EmotionPayload (fear, stress) — applied immediately
- IdentityPayload (identity damage) — applied immediately
- WillConflictPayload — written to delta_buffer
- Affective conditioning — applied immediately

**Master's decision (R9 §4):** Do NOT mechanically move all effects after BodyArbiter. Separate:
1. Internal conflict effects (stress from resistance itself) — may remain at evaluation time
2. Consequence effects (stress from actual action) — must apply after action materializes
3. No double-application of existing EmotionPayload, IdentityPayload, conditioning

### 2.6. BodyArbiter Role (Master R9, APPROVED)

**Placement: Phase 1, after WillpowerGate evaluation.** (NOT Phase 5.5 — R9 proved all Player publication happens in Phase 1, so Phase 5.5 would be too late.)

**Responsibilities:**
1. Read `ctx.will_response` (WillResponseDTO, passed via tick context)
2. Read Avatar counter-intent (DEFERRED — not in scope yet)
3. Make arbitration decision for this specific intent
4. Set `arbitration_result` on `scene_state["intent_lifecycle"][intent_id]`
5. Transition lifecycle state

**Does NOT:**
- Apply psychological effects (separate concern)
- Publish events (publication paths check lifecycle, not BodyArbiter itself)
- Create a second SSOT

### 2.7. Phase Placement (Master R9, APPROVED)

**Phase 5.5 / 5.6: NOT introduced.** BodyArbiter is embedded in Phase 1.

```
Phase 1 (Input Merge):
  1. NPIC Normalize → Intervention Routing
  2. resolve_player_intent → IntentDTO
  3. WillpowerGate → WillResponseDTO (evaluation only)
  4. BodyArbiter → arbitration_result on intent_lifecycle  [NEW]
  5. Publication (only if arbitration_result == AUTHORIZED)
  6. Psychological effects (separated: internal conflict vs consequence)
```

**Rejected:** Phase 5.5/5.6 insertion (would require deferring all Phase 1 publications — unjustified disruption).

### 2.8. Publication Boundary (R7-R10, APPROVED)

All sites that publish "completed action" events must check `arbitration_result`:

| Site | File:Line | Events | Gate status |
|------|-----------|--------|-------------|
| `publish_player_intent` | phases/input.py:25 | PLAYER_ATTACKS, PLAYER_INTERACTS | ✅ WillpowerGate (keep) |
| `publish_player_speech` | phase_1_input.py:471 | PLAYER_SPOKE | ❌ Add gate |
| `publish_classified_player_event` | phase_1_input.py:510 | PLAYER_ATTACKED, PLAYER_SPOKE, etc. | ❌ Add gate |
| INPUT_MERGE combat pipe | tick_orchestrator.py:1690-1718 | PLAYER_ATTACKED | ❌ Replace dead `action_rejected` with lifecycle check |

**Fast-Path lexical override (S122 FIX):** KEEP classification, GATE publication. Fast-Path may set `action_type = "attack"` for DM processing, but publication must still check `arbitration_result`.

### 2.9. Memory / STM Boundary (R9-R10, APPROVED)

**`add_dialogue_turn` at dm_phase.py:185 writes Player speech to STM BEFORE WillpowerGate.** This is a bypass — NPCs remember unspoken speech.

**Required:** Move `add_dialogue_turn` call from dm_phase (pre-tick) to AFTER BodyArbiter authorization.

DM MAY:
- Classify raw_input → action_type
- Read STM (`get_stm_prompt_block`) for LLM context
- Prepare response

DM MAY NOT:
- Write to STM (`add_dialogue_turn`) before authorization
- Publish PLAYER_SPOKE before authorization

### 2.10. NPC Execution Paths — Unchanged (R8 §4, APPROVED)

| Component | Action | Change needed? |
|-----------|--------|---------------|
| CombatSubscriber | PLAYER_ATTACKED → ImpactEngine → damage | ❌ No — gated by publication |
| ImpactEngine | Resolves attack → damage | ❌ No |
| StateApplicator | Applies StateDeltas | ❌ No |
| WindupWriteGate | NPC intents → ActionWindup | ❌ No — NPC path, different consciousness |
| CommitmentArbiter | NPC commitment gate | ❌ No — NPC path |
| ReactionSubscriber | NPC stress/emotion | ❌ No — gated by publication |
| ClaimEventSubscriber | PLAYER_SPOKE → belief | ❌ No — gated by publication |

**Principle:** Fix the publisher, not the subscriber.

### 2.11. Replay and Determinism (ADR-O-404, APPROVED)

- `next_event_identity` — Single Writer for event identity, uses `scene_state["event_ordinals"]`
- `intent_id` must follow the same pattern — deterministic ordinal counter, NOT UUID4
- `atomic_commit` persists all scene_state including ordinals and lifecycle
- Replay must reproduce identical event_ids and intent_ids

### 2.12. Deferred Items

| Item | Status | Reason |
|------|--------|--------|
| Avatar counter-intent (SUPERSEDED) | DEFERRED | R8 must fix Player bypass first; Avatar agency is separate track |
| Phase 5.5/5.6 | NOT INTRODUCED | BodyArbiter in Phase 1 is sufficient |
| Full control struggle mechanic | DEFERRED | Requires AvatarInitiativeEngine — not yet designed |
| Sleep/death/body-switching (Stage 6) | OUT OF MVP | Per R5.6 correction |

---

## §3. Current Implementation State

| Component | State | What exists | What's missing | Next step |
|-----------|-------|------------|----------------|-----------|
| IntentDTO | ✅ Production | domain/intent.py:57 — action, target, parameters | No lifecycle field (by design) | None |
| IntentIdentity | ⚠️ On disk, NOT git-tracked | domain/intent_identity.py — 4 fields, factory methods | Not committed; not integrated into production paths | Git add; wire into IntentDTO creation |
| ControlSource | ✅ Production | domain/control_source.py — PLAYER_INPUT/NPC_DECISION/SCRIPTED_SYSTEM | AVATAR_INITIATIVE enum value (reserved, unused) | None |
| WillpowerGate | ✅ Production | phases/input.py:58-304 — compute_willpower, will_response | Evaluates AND applies effects (must separate) | Separate evaluation from effect-application |
| will_response passing | ❌ Missing | Local variable in run_phase_1_input | Not persisted on ctx; fragmented to will_conflict_data dict | Store on ctx as structured WillResponseDTO |
| scene_state["intent_lifecycle"] | ❌ Missing | Nothing | Entire structure must be created | Design + implement |
| intent_id generation | ⚠️ UUID4 (random) | `uuid.uuid4()` default_factory | NOT replay-safe | Replace with next_intent_identity ordinal counter |
| BodyArbiter | ❌ Missing | Nothing | Entire component must be created | Design + implement in Phase 1 |
| Publication gates | ⚠️ Partial | publish_player_intent gated by WillpowerGate | publish_player_speech, publish_classified_player_event, INPUT_MERGE — NOT gated | Add arbitration_result check |
| action_rejected / rejection_reason | ❌ Dead code | tick_orchestrator.py:1698 reads, never written | Remove after lifecycle gate proven | Remove in cleanup step |
| STM write (dm_phase) | ❌ Bypass | dm_phase.py:185 writes before authorization | Move to after BodyArbiter | Relocate add_dialogue_turn |
| Fast-Path lexical override | ✅ Exists | phase_1_input.py:536-549 | Classification OK, publication NOT gated | Gate publication, keep classification |
| UE-GATE (readiness) | ✅ Production | phase_1_input.py:620-629 | Checks intent_readiness (uncertainty) — different concern | Keep as-is |
| G3C deferral | ✅ Production | phase_1_input.py:656-664 | Defers PLAYER_ATTACKED to INPUT_MERGE | Keep; gate INPUT_MERGE |
| CombatSubscriber | ✅ Production | combat_subscriber.py | No change needed | None |
| WindupWriteGate | ✅ Production | post_decision.py:33 | NPC path — no change | None |
| StateApplicator | ✅ Production | state_applicator.py | No change needed | None |
| EventBus | ✅ Production | event_bus.py | No change needed | None |
| next_event_identity | ✅ Production | event_identity.py:13 | Deterministic, replay-safe | Use as template for next_intent_identity |
| scene_state persistence | ✅ Production | atomic_commit via SQLitePersistenceAdapter | intent_lifecycle must be added to persisted keys | Add intent_lifecycle to scene_state |

---

## §4. Technical Map

### 4.1. Key Files

| File | Purpose | Key lines |
|------|---------|-----------|
| `backend/app/domain/intent.py` | IntentDTO definition | L57: class IntentDTO |
| `backend/app/domain/intent_identity.py` | IntentIdentity (4 fields) | L19: class IntentIdentity (NOT git-tracked) |
| `backend/app/domain/control_source.py` | ControlSource enum | L15: class ControlSource |
| `backend/app/domain/action_windup.py` | ActionWindup, WindupStatus | L14: WindupStatus, L40: held_intent_id |
| `backend/app/models/will.py` | WillResponseDTO, WillState, WillConflictPayload | L61: WillResponseDTO, L94: original_intent |
| `backend/app/services/will.py` | compute_willpower, resolve_intent_pressure | L135: compute_willpower |
| `backend/app/services/phases/input.py` | WillpowerGate (run_phase_1_input), publish_player_intent | L25: publish_player_intent, L58: run_phase_1_input |
| `backend/app/services/game_loop/phase_1_input.py` | publish_player_speech, publish_classified_player_event, resolve_player_intent, Fast-Path | L276: resolve_player_intent, L471: publish_player_speech, L510: publish_classified_player_event, L536-549: Fast-Path, L620-629: UE-GATE, L656-664: G3C |
| `backend/app/services/game_loop/turn_pipeline.py` | Turn orchestration | L32: imports resolve_player_intent, L405: calls resolve_player_intent |
| `backend/app/services/game_loop/dm_phase.py` | DM phase — classification, STM read/write | L72: get_stm_prompt_block, L185: add_dialogue_turn (BYPASS), L224: action_type |
| `backend/app/services/tick_orchestrator.py` | Tick phase orchestration (Phases 1-10) | L1690-1718: INPUT_MERGE combat pipe (dead action_rejected gate) |
| `backend/app/services/events/event_identity.py` | next_event_identity (Single Writer) | L13: next_event_identity |
| `backend/app/services/events/event_bus.py` | EventBus publish/subscribe | L41: subscribe, L58: identity provider |
| `backend/app/services/events/event_types.py` | EventType enum | L43: PLAYER_ATTACKED, L46: PLAYER_SPOKE, L87-88: PLAYER_INTERACTS/PLAYER_ATTACKS |
| `backend/app/services/combat/combat_subscriber.py` | CombatSubscriber | L38-55: _COMBAT_EVENT_TYPES (PLAYER_ATTACKS + PLAYER_ATTACKED) |
| `backend/app/services/events/reaction_subscriber.py` | ReactionSubscriber | L53-56: subscribed events |
| `backend/app/services/events/claim_event_subscriber.py` | ClaimEventSubscriber | L89: on_player_spoke |
| `backend/app/services/memory/memory_manager.py` | STM management | L106: add_dialogue_turn, L209: get_stm_prompt_block |
| `backend/app/services/memory/working_memory_tick.py` | Phase 3 STM writes | L130: add_dialogue_turn (event-driven) |
| `backend/app/services/phases/post_decision.py` | WindupWriteGate (Phase 6) | L33: WindupWriteGate |
| `backend/app/services/npc/state_applicator.py` | StateApplicator (Phase 8) | L275: WillConflictPayload intercept |
| `backend/app/services/scene_state/scene_factory.py` | scene_state initialization | L252: next_event_identity, L255: event_ordinals default |

**WARNING:** Line numbers are from R-round audits (2026-10-26 to 2026-11-03). They may have changed. Always read the actual current source before modifying.

### 4.2. Publication Call Sites (OPEN GAP)

The call sites of `publish_player_speech` and `publish_classified_player_event` were NOT found in any R-round search output. The definitions exist at known locations, but who calls them is unconfirmed.

**Likely callers** (based on architecture):
- `turn_pipeline.py` — orchestrates turn flow, imports resolve_player_intent
- `game_loop.py` — main game loop
- `dm_phase.py` — DM phase processing

**FIRST ACTION for successor:** grep for `publish_player_speech(` and `publish_classified_player_event(` in the actual codebase to find all call sites.

### 4.3. Known Authorization Bypasses

| Bypass | Location | Mechanism |
|--------|----------|-----------|
| DM publishes PLAYER_ATTACKED regardless of WillpowerGate | publish_classified_player_event (phase_1_input.py:510) + INPUT_MERGE (tick_orchestrator.py:1718) | No authorization check; dead action_rejected gate |
| DM publishes PLAYER_SPOKE regardless of WillpowerGate | publish_player_speech (phase_1_input.py:471) | No authorization check |
| Fast-Path force-classifies attack | phase_1_input.py:536-549 | Lexical override bypasses even DM classification |
| DM writes STM before WillpowerGate | dm_phase.py:185 | add_dialogue_turn called pre-tick, before authorization |
| CombatSubscriber receives unauthorized events | combat_subscriber.py:43 | Subscribes to PLAYER_ATTACKED which is published without gate |

---

## §5. Audit Summary R1–R10

| Audit | What it investigated | What was proven | What remains open |
|-------|---------------------|-----------------|-------------------|
| **R1-R2** | Existing intent/body infrastructure | IntentDTO, ControlSource, NPCState intent fields exist | IntentIdentity not git-tracked |
| **R3** | WillpowerGate + intent lifecycle | WillpowerGate computes WillResponseDTO; applies psych effects in Phase 1 | Separation of evaluation and effects not implemented |
| **R4** | Execution boundary (CombatSubscriber, WindupWriteGate) | Subscribers are downstream consumers; NPC path via WindupWriteGate separate | — |
| **R5** | Identity persistence, npc_intents, execution exclusivity, orchestration | scene_state["npc_intents"] exists (NPC only); tick phases 1-10 confirmed | No Phase 5.5 exists |
| **R6** | EventBus causality, Player deferral | EventBus immediate callback; STM = previous tick; NPC reactions are next-tick | — |
| **R6-Correction** | Player event chains, NPC awareness, attack scenario | Three publish functions (intent, speech, classified); CombatSubscriber subscribes to both PLAYER_ATTACKS and PLAYER_ATTACKED | — |
| **R7** | DM publication boundary | **CONFIRMED BYPASS:** DM path publishes PLAYER_ATTACKED regardless of WillpowerGate; action_rejected is dead code | Call sites of publish_player_speech/classified not found |
| **R8** | Authorization boundary design | Proposed lifecycle_state on IntentDTO; Phase 5.5/5.6; ACTIVE=permission | **REJECTED by Master:** ACTIVE≠permission; Phase 5.5 too late; WillpowerGate≠BodyArbiter |
| **R9** | Authorization lifecycle consistency | scene_state["intent_lifecycle"] doesn't exist; will_response is local variable; Phase 5.5 doesn't exist; all publication in Phase 1; DM writes STM before auth | intent_id generation; working_memory_tick perception filtering |
| **R10** | Final authorization wiring | intent_id = uuid4 (NOT replay-safe); all psych effects written by WillpowerGate only (no double-application currently); event identity is deterministic via next_event_identity | Call sites of publish functions; working_memory_tick body; scene_state exact serialization format for intent_lifecycle |

### Evidence origin legend

- **VERIFIED BY SOURCE** — directly confirmed by source code in pasted content
- **REPORTED BY ARCHITECT** — inference from previous architect's report, not re-verified
- **DESIGN DECISION** — approved architectural decision (Master verdict)
- **OPEN QUESTION** — unresolved, requires successor investigation

---

## §6. Coding Plan for Successor

### Sequence: small isolated changes, each independently testable

#### Step 0: Archaeology (READ-ONLY)

**Goal:** Close the two remaining open gaps from R10.

**Actions:**
1. grep for `publish_player_speech(` and `publish_classified_player_event(` call sites in the actual codebase
2. Read `working_memory_tick.py:120-140` to confirm whether it filters by perception radius
3. Read the actual `IntentDTO` definition at `domain/intent.py:57` to confirm all fields
4. Read `turn_pipeline.py` around lines 400-410 to understand the turn flow

**Files to study:** `phase_1_input.py`, `turn_pipeline.py`, `game_loop.py`, `working_memory_tick.py`, `domain/intent.py`

**Tests before:** None (read-only)
**Tests after:** None
**Acceptance:** Call sites documented; working_memory_tick behavior confirmed.
**Rollback:** N/A (read-only)

---

#### Step 1: Stable Intent Identity

**Goal:** Replace `uuid.uuid4()` with deterministic ordinal counter.

**Files to study:** `events/event_identity.py` (template), `domain/intent.py` (intent_id field)

**Changes:**
1. Create `next_intent_identity(scene_state, owner, action) → (tick, ordinal)` in a new or existing module
2. Add `scene_state["intent_ordinals"] = {}` default to `scene_factory.py`
3. Replace `intent_id` generation in IntentDTO/CommunicationIntent to use the new function

**Behavior change:** Intent IDs become deterministic across replay.

**Must not break:** Existing tests that check intent_id presence (they check existence, not value). Event identity unchanged.

**Tests before:** Run existing intent-related tests to establish baseline.
**Tests after:** `test_intent_id_deterministic_under_replay` — same tick replayed twice produces same intent_id.
**Regression:** IPT suite, UE suite.
**Acceptance:** Two replays of same tick produce identical intent_ids.
**Rollback:** Revert to uuid4.

**DEPENDENCY:** Must be done before Step 2 (lifecycle store needs stable keys).

---

#### Step 2: Create `scene_state["intent_lifecycle"]`

**Goal:** Canonical lifecycle store, persisted, replay-safe.

**Files to study:** `scene_factory.py` (defaults), `scene_state/` (persistence), `event_identity.py` (ordinal pattern)

**Changes:**
1. Add `scene_state["intent_lifecycle"] = {}` default to `scene_factory.py`
2. Define lifecycle record format: `{intent_id, owner, body_id, action, lifecycle_state, arbitration_result, created_tick, transitioned_tick}`
3. Add serialization (to_dict/from_dict or JSON-native dict)
4. Ensure `atomic_commit` persists it (it persists all scene_state keys — verify)

**Behavior change:** New empty key in scene_state. No functional change yet.

**Must not break:** Old saves without `intent_lifecycle` key → treated as empty dict (fail-open).

**Tests before:** Save/load round-trip tests.
**Tests after:** `test_intent_lifecycle_persists_through_save_load`
**Regression:** Save/load tests, IPT.
**Acceptance:** scene_state["intent_lifecycle"] survives save/load.
**Rollback:** Remove the key.

**DEPENDENCY:** Depends on Step 1 (stable intent_id as key).

---

#### Step 3: Pass WillResponseDTO via tick context

**Goal:** BodyArbiter can read the full structured evaluation, not just fragmented dict.

**Files to study:** `phases/input.py` (WillpowerGate), tick context definition

**Changes:**
1. Add `ctx.will_response: Optional[WillResponseDTO]` to tick context
2. In `run_phase_1_input`, after `compute_willpower`, store `ctx.will_response = will_response`
3. Do NOT remove existing `will_conflict_data` writing (UI consumers depend on it)

**Behavior change:** `ctx.will_response` available for later sub-steps in Phase 1. No functional change yet.

**Must not break:** will_conflict_data still written (UI/API consumers).

**Tests before:** WillpowerGate tests, UI response tests.
**Tests after:** `test_ctx_carries_will_response`
**Regression:** UE suite, will vertical tests.
**Acceptance:** `ctx.will_response` is the structured WillResponseDTO after Phase 1 WillpowerGate runs.
**Rollback:** Remove ctx.will_response assignment.

**DEPENDENCY:** None (can be done independently).

---

#### Step 4: BodyArbiter in Phase 1

**Goal:** BodyArbiter reads will_response, sets arbitration_result on intent_lifecycle.

**Files to study:** `phases/input.py` (Phase 1 flow), `scene_state["intent_lifecycle"]` (Step 2)

**Changes:**
1. Create `backend/app/services/body_arbiter.py` — `arbitrate(ctx, intent, will_response) → ArbitrationResult`
2. Call BodyArbiter after WillpowerGate evaluation, before publication
3. BodyArbiter writes to `scene_state["intent_lifecycle"][intent_id]`:
   - `lifecycle_state`: ACTIVE (if authorized) or VOIDED (if rejected)
   - `arbitration_result`: AUTHORIZED or REJECTED
4. BodyArbiter decision logic (initial — Avatar counter-intent DEFERRED):
   - If `will_response.state in (COMPLY, RELUCTANT, CONDITIONED)` → AUTHORIZED
   - Else → REJECTED
   - **NOTE:** This is the initial simplification. Master requires finer granularity (refusal vs delay vs resistance without seizure vs full struggle). But for bypass fix, this is sufficient. Refinement is a later step.

**Behavior change:** intent_lifecycle records now have arbitration_result set. No publication change yet (nobody reads it).

**Must not break:** WillpowerGate still applies psych effects (separation of effects is Step 7). Existing publish_player_intent still gated by WillpowerGate (redundant with BodyArbiter for now — acceptable).

**Tests before:** Phase 1 tests.
**Tests after:** `test_body_arbiter_sets_authorized_on_comply`, `test_body_arbiter_sets_voided_on_resist`
**Regression:** UE suite, will vertical, IPT.
**Acceptance:** intent_lifecycle has arbitration_result after Phase 1.
**Rollback:** Remove BodyArbiter call.

**DEPENDENCY:** Depends on Steps 1, 2, 3.

---

#### Step 5: Gate Publication Sites

**Goal:** All publication paths check arbitration_result before publishing.

**Files to study:** `phase_1_input.py` (publish functions), `tick_orchestrator.py` (INPUT_MERGE)

**Changes:**
1. Add guard function: `_is_authorized(ctx, intent_id) → bool` — reads `scene_state["intent_lifecycle"][intent_id]["arbitration_result"]`
2. Add guard to `publish_player_speech` — return early if not authorized
3. Add guard to `publish_classified_player_event` — return early if not authorized
4. Replace dead `action_rejected` check in INPUT_MERGE with `_is_authorized` check
5. Fast-Path: keep classification, but publication gated

**Behavior change:** THE BYPASS FIX. When BodyArbiter rejects, PLAYER_ATTACKED/PLAYER_SPOKE are NOT published. CombatSubscriber receives nothing. No damage from blocked attacks.

**Must not break:** Authorized actions must still work. publish_player_intent already gated by WillpowerGate — redundant but not harmful.

**Tests before:** Combat tests (establish baseline), dialogue tests.
**Tests after:**
- `test_attack_blocked_no_player_attacked` — R7 bypass scenario → no damage
- `test_speech_blocked_no_player_spoke` — speech block → no PLAYER_SPOKE
- `test_fast_path_does_not_bypass_gate` — Fast-Path classifies but publication blocked
- `test_authorized_actions_still_work` — COMPLY → events published

**Existing tests to update:** Tests that assume PLAYER_ATTACKED is always published must explicitly set arbitration_result = AUTHORIZED. NOT by mass-setting ACTIVE — each test must reflect a real scenario (intent formed → arbitrated → published).

**Regression:** UE suite (test_ue_d4_kernel_red), combat suite (test_combat_subscriber, test_combat_pipeline_e2e), IPT.
**Acceptance:** R7 bypass scenario produces no damage when WillpowerGate blocks.
**Rollback:** Remove guards.

**DEPENDENCY:** Depends on Step 4.

---

#### Step 6: Fix STM Premature Write

**Goal:** DM does not write Player speech to STM before authorization.

**Files to study:** `dm_phase.py:185`, `memory_manager.py:106`

**Changes:**
1. Remove `add_dialogue_turn` call from `dm_phase.py:185`
2. Add `add_dialogue_turn` call AFTER BodyArbiter (still in Phase 1, after Step 4), only if `arbitration_result == AUTHORIZED` and action is dialogue/interacts
3. DM phase keeps: `get_stm_prompt_block` (reading OK), classification, response preparation

**Behavior change:** Blocked speech does not enter STM. NPCs don't remember unspoken words.

**Must not break:** DM still reads STM for context. Authorized speech still enters STM.

**Tests before:** Dialogue tests, STM tests.
**Tests after:**
- `test_blocked_speech_not_in_stm` — RESIST → STM clean
- `test_authorized_speech_in_stm` — COMPLY → STM has speech
- `test_dm_reads_stm_before_auth` — DM can still read STM

**Regression:** Dialogue thread continuity tests, cognition context tests, gc_dialogue_test.
**Acceptance:** STM does not contain Player speech when WillpowerGate blocked speech.
**Rollback:** Move add_dialogue_turn back to dm_phase.

**DEPENDENCY:** Depends on Step 5.

---

#### Step 7: Separate Psychological Effects (DEFERRED — design required)

**Goal:** Separate internal conflict effects from consequence effects.

**Status:** This step requires additional design work. Master specified the principle (R9 §4) but the exact separation mechanism needs design:
- Which effects are "internal conflict" (apply at evaluation time)?
- Which effects are "consequence" (apply after action materializes)?
- How to avoid double-application?

**DO NOT implement until design is approved by Master.**

---

#### Step 8: Remove Dead Code

**Goal:** Clean up `action_rejected` / `rejection_reason`.

**Files:** `tick_orchestrator.py:1698, 1702`

**Changes:**
1. Remove dead `action_rejected` check (replaced by Step 5)
2. Remove `rejection_reason` read
3. Grep for any remaining references and remove

**Tests after:** `test_no_action_rejected_references`
**Acceptance:** No references to action_rejected/rejection_reason in codebase.
**Rollback:** N/A (dead code removal).

**DEPENDENCY:** Depends on Step 5 (must prove the replacement works first).

---

#### Step 9: Integration Test — Real Game Scenario

**Goal:** Prove the fix works end-to-end.

**Test scenario (per Master R10 §6):**
```
1. Avatar сопротивляется речи Player
   → Player tries to speak, Avatar resists
   → PLAYER_SPOKE NOT published
   → STM does NOT contain the speech
   → NPCs do NOT hear or remember unspoken words

2. Player пытается атаковать, Avatar отказывает
   → Player tries to attack, Avatar refuses
   → PLAYER_ATTACKED NOT published
   → CombatSubscriber receives nothing
   → No damage occurs
   → NPCs do NOT perceive an attack that didn't happen

3. мир не получает ложных событий
   → The world receives NO false events from blocked intentions
```

**Acceptance:** This is not a test for field presence or function calls — it's proof that NPCs don't hear unspoken words, don't take damage from uncommitted attacks, and don't form memories of events that didn't happen.

---

## §7. Unfinished Questions and Risks

### 7.1. Successor must investigate before modifying

| # | Question | Where to look |
|---|----------|--------------|
| 1 | Call sites of `publish_player_speech` and `publish_classified_player_event` | grep in actual codebase |
| 2 | `working_memory_tick.py:130` — does it filter by perception radius? | Read the function body |
| 3 | Exact IntentDTO fields | Read `domain/intent.py:57` full class |
| 4 | How `intent_id` is currently used as key (if at all) | grep for `intent_id` in scene_state access |
| 5 | Whether `turn_pipeline.py` or `game_loop.py` calls the publish functions | Read these files around the resolve_player_intent call |

### 7.2. Unapproved architectural decisions

| # | Decision needed | Context |
|---|----------------|---------|
| 1 | BodyArbiter decision granularity | Master requires distinguishing refusal/delay/resistance/struggle/authorized. Initial implementation can use simple COMPLY→AUTHORIZED / else→REJECTED, but refinement is needed. |
| 2 | Psychological effects separation | Which effects are "internal conflict" vs "consequence"? Master specified the principle but not the exact mapping. |
| 3 | `intent_lifecycle` cleanup | When are SATISFIED/ABANDONED records removed from scene_state? If never, scene_state grows unbounded. |
| 4 | Multiple intents per tick | Can Player form multiple intents in one tick? If so, how does BodyArbiter handle them? |

### 7.3. Risks

| # | Risk | Mitigation |
|---|------|-----------|
| 1 | Second source of truth | Do NOT create `action_authorized` boolean. Use `scene_state["intent_lifecycle"]` as single source. |
| 2 | BodyArbiter bypass | ALL publication paths must check lifecycle. The Fast-Path and INPUT_MERGE are the known bypasses. Check for others. |
| 3 | Replay non-determinism | Do NOT use `uuid.uuid4()` for intent_id. Use deterministic ordinal counter. |
| 4 | NPC pipeline break | Do NOT modify CombatSubscriber, WindupWriteGate, StateApplicator. Gate at publication, not subscription. |
| 5 | STM pollution | `add_dialogue_turn` must move from dm_phase to after BodyArbiter. working_memory_tick is gated by publication (indirect). |
| 6 | Double psych effect application | WillpowerGate currently applies effects. If BodyArbiter also applies effects, double-application. Step 7 (deferred) addresses this. |
| 7 | Test breakage | Many tests assume PLAYER_ATTACKED is always published. Update tests to reflect real scenarios, not mass-set ACTIVE. |

---

## §8. INSTRUCTIONS FOR SUCCESSOR

1. **You are continuing work, not starting a new project.** This document transfers context. The source code remains the source of truth.

2. **Read the actual current source before every change.** Line numbers in this document are from audits conducted 2026-10-26 to 2026-11-03. They may have changed.

3. **Do not reconstruct code from old reports.** Reports are archaeological snapshots. The live code may have evolved.

4. **Do not create second sources of truth.** `scene_state["intent_lifecycle"]` is the canonical lifecycle store. `ctx.will_response` is the tick-scoped evaluation carrier. No boolean flags.

5. **Do not change game design intent without Master's decision.** The Architect investigates and reports. The Master-Programmer approves technical decisions, architecture, and implementation quality.

6. **Work in small changes with checks before and after.** Each step in §6 is independently deployable and revertible.

7. **Preserve existing dirty files.** Do not destroy others' work. `IntentIdentity` is on disk but not git-tracked — git add it, don't recreate it.

8. **Do not block project development for red baseline.** Fix issues sequentially and locally. Baseline: 7 passed (test_ue_d4_l1_sibling_red) / UE 56+7xf / combat 24+1s / IPT 53-0-0 CRITICAL.

9. **Do not propose paid APIs or tools as mandatory.** The project uses local LLM, open-source tools, and Python.

10. **The Architect investigates and reports. The Master decides.** Do not make architectural decisions without Master's verdict.

11. **"Попытка ≠ событие, на всех каналах."** This is the core invariant. An intention that was blocked must never become a world event, a perception, or a memory — on ANY channel (EventBus, STM, EpistemicStore, EventMemory).

12. **Production is HOLD.** No production changes without Master's explicit GO. All R-rounds were READ-ONLY.

---

## §9. FIRST ACTION FOR SUCCESSOR

**Read the actual source code of `backend/app/services/game_loop/phase_1_input.py` (full file) and `backend/app/services/game_loop/turn_pipeline.py` (full file).**

These two files contain the Player input → publication flow that R7-R10 audited. You need to see the actual current code — not the archaeological snapshots in this document — to understand:

1. Where `publish_player_speech` and `publish_classified_player_event` are called (the OPEN gap from R10)
2. How `resolve_player_intent` feeds into the publication path
3. Where BodyArbiter should be inserted in Phase 1
4. The exact Fast-Path and INPUT_MERGE code

After reading these files, grep for:
```bash
grep -rn "publish_player_speech\|publish_classified_player_event\|publish_player_action" backend/app/ --include="*.py" | grep -v "^.*def "
```

This finds all call sites (excluding definitions). Document them. Then begin Step 0 of the coding plan.

---

## §10. Document Provenance

This handover was compiled from:
- R1-R10 audit reports (in `/home/z/my-project/download/`)
- ADR-O-435-R5.6 (in `/home/z/my-project/upload/`)
- АРХИТЕКТУРНЫЙ_УСТАВ_ENIGMA.md
- ЗАВЕЩАНИЕ_АРХИТЕКТОРОВ.md
- ENIGMA_ROADMAP_v4_12_WPS.md
- ADR (Architecture Decision Records).md
- DTO Registry (Реестр контрактов).md
- 00_CAUSAL_CONTRACT_v3.0.md
- 25+ Pasted Content files (conversation logs from R-rounds)

All evidence is tagged with origin:
- **VERIFIED BY SOURCE** — found in source code pasted content
- **REPORTED BY ARCHITECT** — inference from previous reports
- **DESIGN DECISION** — approved by Master
- **OPEN QUESTION** — requires successor investigation

The document was reviewed for contradictions. Obsolete R8 recommendations (lifecycle_state on IntentDTO, ACTIVE=permission, Phase 5.5/5.6) have been marked as REJECTED and replaced with Master's R9 corrections.

---

*Игра жива. Держать.*
