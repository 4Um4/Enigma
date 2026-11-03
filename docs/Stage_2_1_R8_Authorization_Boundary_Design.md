# Stage 2.1-R8 — Authorization Boundary Design

**Mode:** READ-ONLY / DESIGN
**Date:** 2026-11-03
**Foundation:** R7 confirmed bypass. Master approved: single authorization boundary, BodyArbiter as owner, control ALL materialization paths, separate intent from completed action. `action_rejected` rejected as basis. `action_authorized` rejected as second SSOT.

---

## §0. Design Principle

> Authorization is the RESULT of arbitrating a specific intention of a specific consciousness relative to a specific body. It is NOT a global boolean permission for all Player actions in a tick.

Permission to speak ≠ permission to attack. Permission to walk ≠ permission to drink. The authorization lives on the intention, not on a shared_context flag.

**Single source of truth:** the intent's lifecycle state. No second boolean.

---

## §1. Authorization Ownership

### 1.1. Current State

| Component | File:Line | Role | Problem |
|-----------|-----------|------|---------|
| `IntentDTO` | domain/intent.py:57 | Carries action, target, parameters | No lifecycle state field |
| `ControlSource` | domain/control_source.py:15 | PLAYER_INPUT / NPC_DECISION / SCRIPTED_SYSTEM | Distinguishes source, not authorization |
| `WillpowerGate` | phases/input.py:58-304 | Computes `will_response` (WillState) | Result NOT attached to IntentDTO |
| `will_conflict_data` | phases/input.py:188,234 | Written to shared_context | NOT consumed by any gate |
| `action_rejected` | tick_orchestrator.py:1698 | Read by WV gate | NEVER SET — dead field |
| `IntentDTO` consumers | Multiple | Read action/target/parameters | No authorization check possible — field doesn't exist |

**Gap:** The WillpowerGate result (`will_response.state`) is computed but never attached to the intent it concerns. It floats in `shared_context.will_conflict_data` as an output for the UI, not as an authorization signal on the intent.

### 1.2. Target Design

**Introduce `IntentionLifecycleState` on the intent (per ADR-O-435-R5.4):**

```
ACTIVE       → intention formed, awaiting arbitration
SUSPENDED    → arbitration in progress (transient)
SATISFIED    → action completed, intent fulfilled
ABANDONED    → consciousness withdrew the intent
SUPERSEDED   → replaced by a competing intention (Avatar counter-intent)
VOIDED       → BodyArbiter rejected; action will NOT materialize
```

**BodyArbiter transitions the state:**

```
IntentDTO created (Phase 1)
    → state = ACTIVE
    ↓
BodyArbiter (Phase 5.5)
    reads will_response.state (from WillpowerGate, Phase 1)
    reads Avatar counter-intent (if any)
    ↓
    if WillState in (COMPLY, RELUCTANT, CONDITIONED) and no Avatar counter:
        → state remains ACTIVE → proceeds to execution
    elif Avatar counter-intent supersedes:
        → state = SUPERSEDED → Avatar's intent proceeds
    else (RESIST/DELAY/MISINTERPRET/NEGOTIATE):
        → state = VOIDED → action will NOT materialize
```

**No boolean field.** The lifecycle state IS the authorization. Publication paths check `intent.state == ACTIVE` (or equivalent). No `action_authorized`, no `action_rejected`.

### 1.3. Why Not a Boolean SSOT

Master rejected `action_authorized` as SSOT because:

1. **Per-intention, not per-tick.** A boolean in shared_context applies to the whole tick. Permission to speak doesn't imply permission to attack. The lifecycle state is on the specific IntentDTO.

2. **Second source of truth.** If `action_authorized` exists alongside `intent_lifecycle`, they can diverge. The lifecycle state is the ONLY authority.

3. **Composability.** Multiple intentions can coexist (Player wants to attack, Avatar wants to speak). Each has its own lifecycle state. A boolean cannot express this.

### 1.4. Existing Assets to Reuse

| Asset | Location | Reuse |
|-------|----------|-------|
| `ControlSource` enum | domain/control_source.py | Already distinguishes PLAYER_INPUT vs NPC_DECISION |
| `WillState` enum | models/npc_state.py:133 | WillpowerGate output — BodyArbiter reads this |
| `will_response` | phases/input.py:123 | Computed by WillpowerGate — BodyArbiter consumes |
| `IntentDTO` | domain/intent.py:57 | Add `lifecycle_state` field |
| `WILL_CONFLICT` event | phases/input.py:253 | Already published on resistance — keep as perception signal |

### 1.5. Dependencies

- `IntentDTO` must gain a `lifecycle_state` field (default `ACTIVE` for backward compatibility)
- BodyArbiter (new component, Phase 5.5) reads `will_response` from Phase 1
- No new EventBus, no new store — the state lives on the intent

### 1.6. Tests

| Test | What it verifies |
|------|-----------------|
| Intent with state=VOIDED is not published | Publication paths check state |
| Intent with state=ACTIVE is published | Authorized path works |
| Multiple intents with different states | Per-intention authorization |
| Legacy intent (no state field) defaults to ACTIVE | Old saves don't break |
| BodyArbiter sets SUPERSEDED when Avatar counter-intent exists | Supersession works |

---

## §2. Publication Boundary

### 2.1. All Sites That Materialize Player Actions

| # | Site | File:Line | Events Published | Currently Gated? | Target Gate |
|---|------|-----------|-----------------|-----------------|-------------|
| 1 | `publish_player_intent` | phases/input.py:25 | PLAYER_ATTACKS, PLAYER_INTERACTS | ✅ WillpowerGate (calls only if COMPLY/RELUCTANT/CONDITIONED) | ✅ Keep — already checks will_response |
| 2 | `publish_player_speech` | phase_1_input.py:471 | PLAYER_SPOKE | ❌ NO gate | Add: check intent.state == ACTIVE |
| 3 | `publish_classified_player_event` | phase_1_input.py:510 | PLAYER_ATTACKED, PLAYER_SPOKE, PLAYER_THREATENS, PLAYER_INSULTS, THEFT, INTIMIDATION, BETRAYAL, HELP, SAVED_LIFE, PLAYER_MOVED | ❌ NO gate (Fast-Path override bypasses even DM classification) | Add: check intent.state == ACTIVE before publishing any "completed action" type |
| 4 | INPUT_MERGE combat pipe | tick_orchestrator.py:1690-1718 | PLAYER_ATTACKED (deferred from G3C) | ❌ Dead WV gate (`action_rejected` never set) | Replace dead `action_rejected` check with `intent.state == ACTIVE` check |
| 5 | UE-GATE degradation | phase_1_input.py:620-629 | (modifies _resolved_type, not direct publish) | ✅ Checks intent_readiness (reference resolution) | Keep — but it's a DIFFERENT gate (uncertainty, not authorization) |

### 2.2. Current Behavior (Per Site)

**Site 1 — `publish_player_intent`:**
```python
# phases/input.py:147-153
if will_response.state in (WillState.COMPLY, WillState.RELUCTANT, WillState.CONDITIONED):
    publish_player_intent(ctx, intent)  # ← GATED by WillpowerGate
```
Already correct. WillpowerGate blocks → not called.

**Site 2 — `publish_player_speech`:**
```python
# phase_1_input.py:471-503
def publish_player_speech(player_name, action_text, classified_type, ...):
    if not action_text: return
    get_event_bus().publish(EventDTO.create(event_type=PLAYER_SPOKE, ...))
    # ← NO authorization check
```
Publishes PLAYER_SPOKE regardless of WillpowerGate.

**Site 3 — `publish_classified_player_event`:**
```python
# phase_1_input.py:510-560
def publish_classified_player_event(shared_context, location, campaign_id, raw_input):
    _raw_type = shared_context.action_type or "dialogue"
    # Fast-Path: if raw_input contains "удар/бей/атак/вреж/убей/калеч" → force "attack"
    _resolved_type = _evt_map.get(_raw_type.lower(), PLAYER_SPOKE)
    # ← NO authorization check — publishes PLAYER_ATTACKED / PLAYER_SPOKE / etc.
```
The Fast-Path lexical override (S122 FIX) is especially dangerous — it force-classifies as attack based on raw text, bypassing even DM classification.

**Site 4 — INPUT_MERGE combat pipe:**
```python
# tick_orchestrator.py:1696-1718
# (action_rejected) не издаёт PLAYER_ATTACKED — свидетели не получают
if getattr(shared_context, "action_rejected", False):  # ← ALWAYS False (dead)
    logger.info("[WV] PLAYER_ATTACKED suppressed ...")
else:
    # Falls through → publishes PLAYER_ATTACKED at L1718
    ... type=EventType.PLAYER_ATTACKED.value, ...
```
The WV gate was designed to suppress PLAYER_ATTACKED when WillpowerGate blocks. But `action_rejected` is never set. The gate is dead code. PLAYER_ATTACKED is always published.

### 2.3. Target Behavior

**All sites 2-4 must check the intent's lifecycle state before publishing "completed action" events.**

```python
# GUARD PATTERN (applied to sites 2, 3, 4):
def _is_authorized_for_publication(ctx, intent) -> bool:
    """Check if the intent is authorized to materialize as a world event."""
    if intent is None:
        return True  # Legacy/no-intent path — fail-open for backward compat
    state = getattr(intent, "lifecycle_state", "ACTIVE")  # default ACTIVE for legacy
    return state in ("ACTIVE", "SATISFIED")

# Site 2: publish_player_speech
def publish_player_speech(...):
    if not _is_authorized_for_publicition(ctx, ctx.player_intent):
        return  # Avatar refused to speak — no PLAYER_SPOKE
    get_event_bus().publish(...)

# Site 3: publish_classified_player_event
def publish_classified_player_event(...):
    if not _is_authorized_for_publication(ctx, ctx.player_intent):
        # Intent was VOIDED — don't publish completed-action event
        # WILL_CONFLICT already published by WillpowerGate
        return
    ...

# Site 4: INPUT_MERGE combat pipe
# Replace dead action_rejected check:
if not _is_authorized_for_publication(ctx, ctx.player_intent):
    logger.info("[BODY_ARBITER] PLAYER_ATTACKED suppressed (intent VOIDED)")
    return  # Don't publish PLAYER_ATTACKED
```

### 2.4. What Stays Unchanged

| Component | Why it stays |
|-----------|-------------|
| `publish_player_intent` (Site 1) | Already gated by WillpowerGate — no change needed |
| UE-GATE (Site 5) | Checks `intent_readiness` (reference resolution) — different concern, keep as-is |
| Fast-Path lexical override | Keep the classification, but gate the PUBLICATION. The Fast-Path can still set `action_type = "attack"` for DM processing, but publication is blocked if intent is VOIDED |
| `WILL_CONFLICT` event | Keep — it's the authorized "resistance" signal, not a completed action |

### 2.5. Tests

| Test | Scenario | Expected |
|------|----------|----------|
| `test_attack_blocked_no_player_attacked` | Player attacks, WillpowerGate RESIST → intent VOIDED | PLAYER_ATTACKED NOT published; CombatSubscriber receives nothing; no damage |
| `test_speech_blocked_no_player_spoke` | Player speaks, WillpowerGate RESIST → intent VOIDED | PLAYER_SPOKE NOT published; ClaimEventSubscriber receives nothing |
| `test_attack_authorized_player_attacked` | Player attacks, WillpowerGate COMPLY → intent ACTIVE | PLAYER_ATTACKED published; CombatSubscriber processes; damage occurs |
| `test_fast_path_does_not_bypass_gate` | Raw input "удар", WillpowerGate RESIST | Fast-Path sets action_type="attack" but PLAYER_ATTACKED NOT published |
| `test_will_conflict_always_published` | Any WillpowerGate block | WILL_CONFLICT published (resistance signal) |

---

## §3. Memory Boundary

### 3.1. Current State — DM Writes to STM Before Authorization

```
Player raw_input: "Я говорю стражнику: сдайся"
    ↓
dm_phase.py:72  → shared_context.npc_stm_block_targeted = get_stm_prompt_block(...)
                  (DM READS STM for LLM context — OK, this is input processing)
    ↓
dm_phase.py:185 → deps.memory_manager.add_dialogue_turn(
                      campaign_id, npc_id="guard", speaker="player",
                      text="сдайся", target_id="guard", ...
                  )
                  (DM WRITES Player speech to STM — PROBLEM: this fixates
                   "player said 'сдайся'" as a memory fact BEFORE WillpowerGate)
    ↓
Phase 1: WillpowerGate → RESIST (avatar refuses to speak)
    ↓
PLAYER_SPOKE not published (after R8 §2 fix)
    ↓
BUT STM already contains: {speaker: "player", text: "сдайся"}
    ↓
NPCs can recall words the body never uttered — via memory, not EventBus
```

### 3.2. All STM Write Sites

| # | Site | File:Line | What it writes | Currently gated? |
|---|------|-----------|---------------|-----------------|
| 1 | DM phase | dm_phase.py:185 | Player dialogue turn to NPC's STM | ❌ Before WillpowerGate |
| 2 | Working memory tick | working_memory_tick.py:130 | Dialogue turn to STM (Phase 3) | ⚠ After Phase 1, but processes events from bus |
| 3 | NPC dialogue subscriber | npc_dialogue_subscriber.py:520 | NPC speech turn to listener's STM | ✅ NPC speech — different authorization (NPC decided) |
| 4 | `add_dialogue_turn` definition | memory_manager.py:106 | The function itself | N/A — needs caller gating |

### 3.3. Target Design — Separate Input Processing from Fact Fixation

**DM may:**
- Classify raw_input → `shared_context.action_type` (analysis)
- Read STM for LLM context → `get_stm_prompt_block()` (reading is safe)
- Prepare DM response (analysis)
- Build IntentDTO (formation)

**DM may NOT:**
- Write to STM (`add_dialogue_turn`) — this fixates "player spoke X" as a memory fact
- Publish PLAYER_SPOKE — this fixates "player spoke X" as a world event (§2)
- Any other action that records the attempt as a completed action

### 3.4. Migration of `add_dialogue_turn` Call

**Current:** `dm_phase.py:185` (pre-tick, before WillpowerGate)

**Target:** Move to AFTER BodyArbiter authorization (Phase 5.5+)

```
Phase 5.5: BodyArbiter
    → intent.state = ACTIVE (authorized) or VOIDED (rejected)
    ↓
Phase 5.6 (NEW — authorized speech fixation):
    if intent.state == ACTIVE and intent.action in ("dialogue", "player_interacts"):
        deps.memory_manager.add_dialogue_turn(
            campaign_id, npc_id=target, speaker="player",
            text=intent.parameters.semantic_action, ...
        )
    elif intent.state == VOIDED:
        # Don't write to STM — body didn't speak
        pass
```

### 3.5. Working Memory Tick (Site 2)

`working_memory_tick.py:130` writes to STM during Phase 3 (memory). It processes events from the EventBus. If PLAYER_SPOKE is not published (per §2), this site won't write Player speech to STM — because it won't receive the event.

**No change needed** — this site is gated indirectly by the publication boundary (§2).

### 3.6. NPC Dialogue Subscriber (Site 3)

`npc_dialogue_subscriber.py:520` writes NPC speech to STM. This is NPC-authored speech — the NPC decided to speak via DecisionHub. The authorization is the NPC's own decision process (CommitmentArbiter, WindupWriteGate).

**No change needed** — different consciousness, different authorization path.

### 3.7. Tests

| Test | Scenario | Expected |
|------|----------|----------|
| `test_blocked_speech_not_in_stm` | Player speaks, WillpowerGate RESIST | STM does NOT contain player's words |
| `test_authorized_speech_in_stm` | Player speaks, WillpowerGate COMPLY | STM contains player's words |
| `test_dm_can_read_stm_before_auth` | DM reads STM for context | Reading works regardless of authorization |
| `test_dm_cannot_write_stm_before_auth` | DM phase runs | `add_dialogue_turn` NOT called in dm_phase |
| `test_working_memory_no_player_speech_when_blocked` | PLAYER_SPOKE not published | working_memory_tick doesn't write player speech |

---

## §4. Execution Boundary

### 4.1. Principle: Gate at Publication, Not at Subscription

CombatSubscriber, WindupWriteGate, and StateApplicator are DOWNSTREAM consumers. They process events that have already been published. If the publication boundary (§2) ensures only authorized events reach the bus, these consumers need NO modification.

### 4.2. Consumer Audit

| Consumer | File | What it does | Needs change? | Why |
|----------|------|-------------|--------------|-----|
| **CombatSubscriber** | combat_subscriber.py | PLAYER_ATTACKED → ImpactEngine → PhysiologyPayload → damage | ❌ NO | If PLAYER_ATTACKED not published (§2), subscriber never receives it |
| **ImpactEngine** | combat/impact_engine.py | Resolves attack → damage | ❌ NO | Called by CombatSubscriber only if event received |
| **StateApplicator** | state_applicator.py | Applies StateDeltas to NPCState | ❌ NO | Receives deltas from CombatSubscriber, not from Player directly |
| **WindupWriteGate** | phases/post_decision.py:33 | NPC communication intents → ActionWindup / QueuedTask | ❌ NO | Processes NPC intents (ctx.communication_intents), not Player intents |
| **ReactionSubscriber** | reaction_subscriber.py | PLAYER_ATTACKED → NPC stress/emotion | ❌ NO | If PLAYER_ATTACKED not published, subscriber never receives it |
| **ClaimEventSubscriber** | claim_event_subscriber.py | PLAYER_SPOKE → ClaimEvent → belief | ❌ NO | If PLAYER_SPOKE not published, subscriber never receives it |
| **PlayerSpeechActSubscriber** | player_speech_act_subscriber.py | PLAYER_SPOKE → speech act processing | ❌ NO | Same — gated by publication |
| **ObservationSubscriber** | observation_subscriber.py | PLAYER_ATTACKED → NPC perception | ❌ NO | Same — gated by publication |
| **SocialSubscriber** | social_subscriber.py | Multiple Player events → social deltas | ❌ NO | Same — gated by publication |
| **DialogueMemorySubscriber** | dialogue_memory_subscriber.py | PLAYER_SPOKE → EventMemory | ❌ NO | Same — gated by publication |

### 4.3. Why No Rewrite Is Needed

The bypass found in R7 is NOT a bug in CombatSubscriber or ImpactEngine. They correctly process events they receive. The bug is that they RECEIVE events that should never have been published.

**Fix the publisher, not the subscriber.** If `publish_classified_player_event` and the INPUT_MERGE combat pipe check the intent's lifecycle state (§2), no unauthorized PLAYER_ATTACKED reaches the bus. CombatSubscriber processes only authorized attacks. The execution pipeline is unchanged.

### 4.4. WindupWriteGate — Already Correct for NPC Path

WindupWriteGate (post_decision.py:33) processes `ctx.communication_intents` — these are NPC intents from DecisionHub. It creates ActionWindup for NPC attacks/steals, QueuedTask for NPC dialogue.

This is the NPC authorization path — NPCs go through DecisionHub → WindupWriteGate → ActionWindup → execution. Player goes through a different path (WillpowerGate → publish → CombatSubscriber).

**No change needed to WindupWriteGate.** It's a different consciousness's execution boundary.

### 4.5. The Phase 5.5 Timing Compromise

Master noted: if INPUT_MERGE executes before Phase 5.5, BodyArbiter can't set a permission that INPUT_MERGE should have already checked.

**Resolution:** For actions requiring arbitration, final materialization must happen AFTER BodyArbiter.

| Phase | What happens | Change |
|-------|-------------|--------|
| Pre-tick (DM) | DM classifies, reads STM, prepares response | Remove `add_dialogue_turn` (§3) |
| Phase 1 | WillpowerGate computes will_response | Keep — but don't publish yet |
| Phase 2-4 | Event processing, memory, topic extraction | No Player action events yet |
| Phase 5 | NPC DecisionHub | NPC decides without seeing current Player action (conscious compromise) |
| **Phase 5.5** | **BodyArbiter** — reads will_response, sets intent.lifecycle_state | **NEW** |
| **Phase 5.6** | **Authorized publication** — publishes PLAYER_ATTACKED/PLAYER_SPOKE only if intent ACTIVE | **NEW (replaces INPUT_MERGE for Player actions)** |
| Phase 6 | WindupWriteGate (NPC path) | Unchanged |
| Phase 8 | CombatSubscriber drains, processes | Unchanged — receives only authorized events |

**Conscious compromise:** NPC DecisionHub (Phase 5) cannot react to current-tick Player action because it's not yet published. NPC reaction happens next tick. This is already the case for combat (R6-Correction §3 confirmed). R8 extends it to all Player actions.

### 4.6. Tests

| Test | What it verifies |
|------|-----------------|
| `test_combat_subscriber_no_change` | CombatSubscriber still processes authorized PLAYER_ATTACKED |
| `test_impact_engine_no_change` | ImpactEngine still resolves authorized attacks |
| `test_windup_write_gate_no_change` | NPC path still creates ActionWindup for NPC attacks |
| `test_npc_decision_hub_no_current_tick_player_action` | NPC decides without seeing current Player action |
| `test_npc_reacts_next_tick` | NPC reacts to Player action in next tick (Phase 5) |

---

## §5. Migration Sequence

### 5.1. Principles

1. **Each step is independently deployable and testable.**
2. **Legacy intents default to ACTIVE** — old saves don't break.
3. **No big-bang rewrite.** Each step adds a gate, doesn't remove existing logic.
4. **Dead code (`action_rejected`) removed last** — after the new gate is proven.

### 5.2. Five Steps

#### Step 1: Intent Lifecycle State (additive, no behavior change)

**Files:**
- `backend/app/domain/intent.py` — add `lifecycle_state: str = "ACTIVE"` to IntentDTO
- `backend/app/models/will.py` — add lifecycle state constants (or enum)

**Changes:**
- Add `lifecycle_state` field to IntentDTO, default `"ACTIVE"`
- No logic change — just the field exists

**Behavior:** Identical to current. All intents are ACTIVE by default.

**Tests:**
- `test_intent_has_lifecycle_state` — field exists, defaults to ACTIVE
- All existing tests pass unchanged

**Risk:** Zero — additive field with default.

#### Step 2: BodyArbiter Sets Lifecycle State (additive gate)

**Files:**
- `backend/app/services/body_arbiter.py` — NEW component
- `backend/app/services/tick_orchestrator.py` — call BodyArbiter at Phase 5.5
- `backend/app/services/phases/input.py` — WillpowerGate still computes will_response, but ALSO sets `intent.lifecycle_state` based on will_response

**Changes:**
- WillpowerGate: after computing `will_response`, set `intent.lifecycle_state`:
  - COMPLY/RELUCTANT/CONDITIONED → `ACTIVE` (stays active)
  - RESIST/DELAY/MISINTERPRET/NEGOTIATE/etc. → `VOIDED`
- BodyArbiter at Phase 5.5: reads `intent.lifecycle_state`, may transition to SUPERSEDED if Avatar counter-intent exists
- No publication change yet — just setting the state

**Behavior:** Identical to current. The state is set but nobody reads it yet.

**Tests:**
- `test_willpower_gate_sets_voided_on_resist` — WillpowerGate RESIST → intent.lifecycle_state == VOIDED
- `test_willpower_gate_sets_active_on_comply` — WillpowerGate COMPLY → intent.lifecycle_state == ACTIVE
- `test_body_arbiter_supersedes_on_avatar_counter` — Avatar counter-intent → SUPERSEDED
- All existing tests pass unchanged (state is set but not checked)

**Risk:** Low — state is written but not yet consumed.

#### Step 3: Gate Publication Sites (the core fix)

**Files:**
- `backend/app/services/game_loop/phase_1_input.py` — `publish_player_speech`, `publish_classified_player_event`
- `backend/app/services/tick_orchestrator.py` — INPUT_MERGE combat pipe (L1690-1718)

**Changes:**
- Add `_is_authorized_for_publication(intent)` guard to `publish_player_speech`
- Add same guard to `publish_classified_player_event`
- Replace dead `action_rejected` check with `intent.lifecycle_state == ACTIVE` check in INPUT_MERGE combat pipe

**Behavior:** When WillpowerGate blocks (intent VOIDED):
- `publish_player_speech` → returns early, no PLAYER_SPOKE
- `publish_classified_player_event` → returns early, no PLAYER_ATTACKED/PLAYER_SPOKE/etc.
- INPUT_MERGE combat pipe → suppresses PLAYER_ATTACKED

WILL_CONFLICT still published (by WillpowerGate, not affected by this gate).

**Tests:**
- `test_attack_blocked_no_player_attacked` — R7 bypass scenario → no damage
- `test_speech_blocked_no_player_spoke` — speech block → no PLAYER_SPOKE
- `test_fast_path_does_not_bypass_gate` — Fast-Path override still classifies, but publication blocked
- `test_authorized_actions_still_work` — COMPLY → events published normally
- All existing combat tests still pass for authorized attacks
- `test_ue_d4_kernel_red` — UE-GATE tests still pass (different gate, unchanged)

**Risk:** Medium — this is the core behavior change. Existing tests that assume PLAYER_ATTACKED is always published may fail. These tests need updating to reflect the new contract: "PLAYER_ATTACKED only published when authorized."

#### Step 4: Move STM Write to After Authorization

**Files:**
- `backend/app/services/game_loop/dm_phase.py` — remove `add_dialogue_turn` call at L185
- `backend/app/services/tick_orchestrator.py` or new phase — add `add_dialogue_turn` call after Phase 5.5, only if intent ACTIVE

**Changes:**
- DM phase: remove `deps.memory_manager.add_dialogue_turn(...)` at L185
- DM phase keeps: `get_stm_prompt_block()` (reading STM is OK), classification, response preparation
- New: after BodyArbiter (Phase 5.6), if intent.lifecycle_state == ACTIVE and action is dialogue/interacts, call `add_dialogue_turn`

**Behavior:** Player speech only enters STM when Avatar actually speaks. Blocked speech doesn't pollute memory.

**Tests:**
- `test_blocked_speech_not_in_stm` — WillpowerGate RESIST → STM clean
- `test_authorized_speech_in_stm` — COMPLY → STM has the speech
- `test_dm_reads_stm_before_auth` — DM can still read STM for context
- Existing dialogue tests updated: STM write happens later, not in dm_phase

**Risk:** Medium — tests that check STM immediately after dm_phase will need timing adjustment.

#### Step 5: Remove Dead Code

**Files:**
- `backend/app/services/tick_orchestrator.py` — remove `action_rejected` / `rejection_reason` reads at L1698, L1702
- Any other references to `action_rejected` / `rejection_reason`

**Changes:**
- Remove the dead WV gate block (replaced by lifecycle_state check in Step 3)
- Remove `action_rejected` / `rejection_reason` from shared_context if present

**Behavior:** Cleanup only — no functional change (the gate was already dead).

**Tests:**
- All tests from Steps 1-4 still pass
- `test_no_action_rejected_references` — grep confirms no remaining references

**Risk:** Zero — removing dead code.

### 5.3. Rollback Plan

Each step is independently revertible:
- Step 1: remove the field → back to current
- Step 2: remove BodyArbiter call → state not set, defaults to ACTIVE → fail-open
- Step 3: remove the guards → back to current (bypass restored, but explicitly known)
- Step 4: move `add_dialogue_turn` back to dm_phase → STM writes early again
- Step 5: N/A (cleanup)

If Step 3 reveals unexpected breakage, revert Steps 3-4, keep Steps 1-2 (state is set but not consumed), investigate, re-deploy.

### 5.4. Compatibility with Existing Saves

| Concern | Resolution |
|---------|-----------|
| Old saves have IntentDTO without `lifecycle_state` | Default `"ACTIVE"` — old intents treated as authorized |
| Old saves have `action_rejected` in shared_context | Ignored — Step 5 removes the read, but even before that, the new gate uses lifecycle_state |
| Old NPC behavior depends on PLAYER_SPOKE always published | Step 3 changes this — NPC tests need updating. NPC behavior change: NPC no longer hears blocked speech. This is the INTENDED fix. |
| Old combat tests assume PLAYER_ATTACKED always published | Step 3 changes this — tests need updating to mock intent.lifecycle_state = ACTIVE |

---

## §6. Summary

| Task | Current | Target | Key Change |
|------|---------|--------|------------|
| 1. Authorization ownership | will_response floats in shared_context | IntentDTO.lifecycle_state | BodyArbiter sets state, no boolean SSOT |
| 2. Publication boundary | Only publish_player_intent gated | All 4 publication sites gated | Add lifecycle_state check to sites 2-4 |
| 3. Memory boundary | DM writes STM before WillpowerGate | STM write after BodyArbiter | Move add_dialogue_turn from dm_phase to Phase 5.6 |
| 4. Execution boundary | N/A (subscribers process what they receive) | No change to subscribers | Gate at publication, not subscription |
| 5. Migration | N/A | 5 steps, each independently deployable | Legacy intents default ACTIVE |

**Production: HOLD.** This is a design document. Implementation requires Master's GO.

---

## §7. Open Questions for Master

| # | Question |
|---|----------|
| 1 | IntentionLifecycleState — implement as enum on IntentDTO, or as a separate lifecycle tracker? (Recommendation: enum on IntentDTO, simplest, no second store) |
| 2 | Phase 5.6 (authorized publication) — new phase, or fold into existing Phase 5.5 BodyArbiter? (Recommendation: separate phase, clearer separation of arbitration from publication) |
| 3 | Avatar counter-intent (SUPERSEDED) — is this in scope for R8 implementation, or deferred to AvatarInitiativeEngine? (Recommendation: defer — R8 focuses on the bypass fix, not Avatar agency) |
| 4 | Step 3 test updates — many existing tests assume PLAYER_ATTACKED is always published. Approve updating these tests to explicitly set lifecycle_state = ACTIVE? |
| 5 | Fast-Path lexical override (S122 FIX) — keep the classification but gate publication, or remove the Fast-Path entirely? (Recommendation: keep classification, gate publication — Fast-Path serves DM processing, not publication) |
