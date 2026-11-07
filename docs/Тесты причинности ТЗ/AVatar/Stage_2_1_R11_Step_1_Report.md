# Stage 2.1 R11 — Step 1: Revised Implementation Plan + ADR-PRE-FLIGHT

**Mode:** READ-ONLY (archaeology complete; no production changes)
**Date:** 2026-11-07
**Author:** Architect (Stage 2.1 R11 successor)
**Recipient:** Master
**Predecessor:** Stage 2.1 R1–R10 handover (2026-11-03)

---

## §0. Executive Summary

Step 0 archaeology (zones [1]-[27]) closed all open gaps from R10 and discovered **six critical divergences** from the handover document. The handover's plan §6 cannot be executed as written — it requires revision based on factual code state. This document delivers the revised plan per Master's four verdicts (2026-11-07).

**Key findings:**

1. `publish_player_speech` — **fully dead code** (0 call sites in entire project).
2. `action_rejected` gate **already exists** structurally in both publication points — but is dead (never set to True). Step 5 is a **gate replacement**, not gate addition.
3. `intent_id` with `uuid4` lives on **`MovementIntent`** (NPC path), not on `IntentDTO` (Player path). Handover §2.4 was doc-drifted.
4. **WillpowerGate is NOT invoked on Player path** (only NPC idle path). Handover §2.7 placement ("after WillpowerGate") is inapplicable.
5. `domain/intent_identity.py` — **already git-tracked** (commit 6192bff1). Handover §3 "NOT git-tracked" is stale.
6. **SOCIAL_ACTION → ACTOR_ATTACKS → CombatSubscriber** is a live ungated bypass creating **double ImpactEngine** for Player attacks — the true R7 bypass that handover R7-R10 missed entirely.

---

## §A. Updated Causal Schema — Player Path

### A.1. Verified call flow (Step 0 archaeology, zones [1]-[27])

```
Player raw_input (text input from frontend)
    │
    ▼
┌─────────────────────────────────────────────────────────────────────┐
│ TurnPipeline.execute (turn_pipeline.py)                             │
│   └─ _execute_dm_and_intent_resolution (turn_pipeline.py:327-475+)  │
│                                                                     │
│   1. avatar_service.load_state (line 339)                           │
│      → player_data_dict                                             │
│                                                                     │
│   2. run_dm_phase (line 341) ←── DM PHASE                           │
│      ├─ DM classifies action → shared_context.action_type           │
│      ├─ DM reads STM (get_stm_prompt_block) for LLM context          │
│      ├─ DM writes Player speech to STM (dm_phase.py:185)            │
│      │   ⚠ BYPASS #1: before ANY authorization check                 │
│      │   Condition: action_type in ("dialogue", "player_interacts")  │
│      │   Effect: NPCs remember unspoken speech                      │
│      ├─ DM writes L1Chronicle (dm_phase.py:200)                    │
│      │   ⚠ BYPASS #1b: TraitDriftEvent "dialogue" before auth       │
│      └─ returns dm_result (is_valid, scene_context, error)           │
│                                                                     │
│   3. intent_compressor.compress (line 379)                          │
│      → IntentSemanticField (action, target, proposition, etc.)       │
│                                                                     │
│   4. SOCIAL_ACTION publish (lines 385-419)                          │
│      ⚠ BYPASS #2: NO authorization check                            │
│      Condition: action_val in ("ATTACK","THREATEN","DIALOGUE",       │
│                                "STEAL","GIVE")                      │
│      Payload: {action, actor, target, speech_act, proposition,      │
│                physical_force, emotional_charge, social_pressure,   │
│                tick}                                                │
│      NOTE: payload has NO "text" field                              │
│      → EventBus.publish(SOCIAL_ACTION)                              │
│        ├─→ SocialActionSubscriber.on_social_action                  │
│        │   ├─→ COMMUNICATION_CLAIM (if proposition)                 │
│        │   │   ⚠ BYPASS #3: claim enters EpistemicStore ungated     │
│        │   │   → ClaimEventSubscriber → BeliefRevisionEngine        │
│        │   │     → EpistemicStore (belief revision)                 │
│        │   ├─→ NPC_SPOKE (if DIALOGUE and text)                     │
│        │   │   ✅ DEAD: text always "" (payload has no "text" field)│
│        │   └─→ ACTOR_ATTACKS (if ATTACK)                            │
│        │       ⚠ BYPASS #4: damage materializes ungated             │
│        │       → CombatSubscriber → ImpactEngine → DAMAGE           │
│        │       ⚠ DOUBLE with INPUT_MERGE→PLAYER_ATTACKED (see §B)   │
│        ├─→ ObservabilityTap (passive, no effect)                     │
│        └─→ idle_event_projection (EXCLUDED from v1 dictionary)      │
│                                                                     │
│   5. resolve_player_intent (line 421)                                │
│      ├─ resolve_target_with_candidates → target_id                  │
│      ├─ _resolve_actor_reference → actor_id                          │
│      └─→ IntentResolution (original_intent: IntentDTO)              │
│          IntentDTO fields: action, target, parameters, text,         │
│                            campaign_id (NO intent_id)               │
│                                                                     │
│   6. WV-2/3 World Validation (lines 431-475)                        │
│      ├─ WV-3: tool_reference vs player_body_topology                │
│      ├─ WV-2: distance vs effective_reach_m                          │
│      └─→ shared_context.physics_validation (list of notes)          │
│          NOTE: does NOT set action_rejected                         │
│          (WV result disconnected from publication gate)              │
│                                                                     │
│   7. return (dm_result, _resolution) → back to execute               │
└─────────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────────┐
│ TurnPipeline.execute (continued, turn_pipeline.py:783+)            │
│                                                                     │
│   8. CLASSIFIED PUBLISH (lines 787-793)                             │
│      Gate: if dm_result.is_valid                                    │
│            AND not getattr(shared_context, "action_rejected", F)    │
│            ⚠ action_rejected NEVER set to True → gate always passes │
│      → publish_classified_player_event(shared_context, ...)          │
│        ├─ Fast-Path lexical override (attack/move verbs)             │
│        ├─ _evt_map: action_type → EventType                         │
│        ├─ UE-GATE: intent_readiness != RESOLVED → degrade to SPOKE  │
│        ├─ G3C: if PLAYER_ATTACKED → defer to INPUT_MERGE (return)    │
│        └─ else: publish PLAYER_SPOKE / PLAYER_THREATENS /            │
│                 PLAYER_INSULTS / THEFT / etc.                       │
│                                                                     │
│   9. run_npc_orchestration (line 802)                                │
│      → NPC decisions, communication_intents, movement_intents        │
│                                                                     │
│   10. return TickPlayerResultDTO                                     │
└─────────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────────┐
│ TickOrchestrator.execute (tick_orchestrator.py, Phases 0-10)        │
│                                                                     │
│   Phase 1: run_phase_1_input (line 2006)                             │
│      ⚠ WillpowerGate runs here — NPC IDLE PATH ONLY                  │
│      Player path does NOT invoke WillpowerGate                       │
│      (handover §2.7 "BodyArbiter after WillpowerGate" inapplicable)  │
│                                                                     │
│   INPUT_MERGE (lines 1694-1726)                                     │
│      if _sem_action == "ATTACK":                                     │
│        if action_rejected (DEAD — always False): suppress            │
│        else: publish PLAYER_ATTACKED (deterministic event_id)        │
│          → CombatSubscriber → ImpactEngine → DAMAGE                  │
│          ⚠ DOUBLE with SOCIAL_ACTION→ACTOR_ATTACKS (see §B)          │
│                                                                     │
│   Phase 3: Memory (MemoryManager.apply for phase_2_events)           │
│   Phase 5: Decision (NpcTickPipeline.run — pure reducer)             │
│   Phase 8: Layered Reduction (combat → ImpactEngine → StateApplicator)│
│   Phase 10: Persistence (atomic_commit)                              │
└─────────────────────────────────────────────────────────────────────┘
```

### A.2. Materialization points (where action becomes world event)

| # | Point | File:Line | Gate | Status |
|---|-------|-----------|------|--------|
| M1 | STM write (add_dialogue_turn) | dm_phase.py:185 | NONE | ⚠ BYPASS |
| M2 | L1Chronicle write (TraitDriftEvent) | dm_phase.py:200 | NONE | ⚠ BYPASS |
| M3 | SOCIAL_ACTION publish | turn_pipeline.py:412 | NONE | ⚠ BYPASS |
| M4 | COMMUNICATION_CLAIM projection | social_action_subscriber.py:34 | NONE (derives from M3) | ⚠ BYPASS |
| M5 | ACTOR_ATTACKS projection | social_action_subscriber.py:68 | NONE (derives from M3) | ⚠ BYPASS + DOUBLE |
| M6 | publish_classified_player_event | turn_pipeline.py:788 | dead `action_rejected` | ⚠ DEAD GATE |
| M7 | PLAYER_ATTACKED (INPUT_MERGE) | tick_orchestrator.py:1716 | dead `action_rejected` | ⚠ DEAD GATE + DOUBLE |
| M8 | publish_player_intent (PLAYER_ATTACKS/INTERACTS) | phases/input.py:25 | WillpowerGate | ✅ WORKING (NPC path only) |

### A.3. Revised BodyArbiter placement (per Master verdict 2)

Master verdict 2: "BodyArbiter размещается в Player pipeline до первой материализации действия."

First materialization = M1 (STM write in dm_phase.py:185). BodyArbiter must execute **before** dm_phase — or dm_phase must be restructured so STM write happens after BodyArbiter.

**Problem:** At dm_phase time, IntentDTO does not exist yet (resolve_player_intent runs later). BodyArbiter needs an intent to evaluate, but intent is formed after DM.

**Proposed ordering (revised):**

```
1. avatar_service.load_state
2. intent_compressor.compress → IntentSemanticField
3. [NEW] next_intent_identity(scene_state, owner, action) → intent_id
4. [NEW] Create scene_state["intent_lifecycle"][intent_id] record (ACTIVE)
5. [NEW] BodyArbiter.arbitrate(intent_id, semantic_field, scene_state) → arbitration_result
   Write to scene_state["intent_lifecycle"][intent_id]
   Initial: always AUTHORIZED (no evaluation source yet — Master verdict 2: TBD)
6. run_dm_phase (MOVED: after BodyArbiter)
   ├─ DM classifies, reads STM, prepares response
   └─ [MOVED] STM write: ONLY if arbitration_result == AUTHORIZED
7. [GATED] SOCIAL_ACTION publish — ONLY if AUTHORIZED
8. resolve_player_intent → IntentResolution (attach intent_id)
9. WV-2/3 (unchanged — independent per Master verdict 4)
10. [GATED] publish_classified_player_event — check arbitration_result
11. [GATED] INPUT_MERGE PLAYER_ATTACKED — check arbitration_result
```

**Critical constraint:** DM phase currently runs BEFORE compress. Moving BodyArbiter before DM requires either:
- (a) Moving compress before DM (changes DM prompt construction — DM uses semantic_field? Need to verify)
- (b) BodyArbiter evaluates on raw_input + action_type (before compress), not on IntentSemanticField
- (c) Splitting dm_phase: classification first, STM write after BodyArbiter

Option (c) is least disruptive. This is an open question for §E.

---

## §B. Full SOCIAL_ACTION Map

### B.1. Producer

```
File: backend/app/services/game_loop/turn_pipeline.py
Lines: 385-419 (inside _execute_dm_and_intent_resolution)
Condition: _action_val in ("ATTACK", "THREATEN", "DIALOGUE", "STEAL", "GIVE")
Timing: AFTER compress, BEFORE resolve_player_intent, BEFORE WV, BEFORE any auth
Payload: {
    "action": _action_val,
    "actor": _semantic_field.actor or "player",
    "target": _semantic_field.target or shared_context.player_target_id or "",
    "speech_act": _semantic_field.speech_act.value or "assert",
    "proposition": _prop or None,
    "physical_force": _semantic_field.physical_force,
    "emotional_charge": _semantic_field.emotional_charge,
    "social_pressure": _semantic_field.social_pressure,
    "tick": shared_context.current_tick
}
NOTE: NO "text" field in payload
visibility: "public", radius: 10.0
```

### B.2. Subscriber

```
File: backend/app/services/events/social_action_subscriber.py
Registration: game_loop.py:636 (_bus.subscribe(EventType.SOCIAL_ACTION, _social_sub.on_social_action))
```

### B.3. Projections (derivative events)

| # | Projection | Condition | Event Type | Subscribers | Effect | Classification |
|---|-----------|-----------|------------|-------------|--------|----------------|
| P1 | COMMUNICATION_CLAIM | `if prop:` (proposition exists) | COMMUNICATION_CLAIM | ClaimEventSubscriber (game_loop.py:619) → BeliefRevisionEngine → EpistemicStore | Epistemic: claim enters belief system | **ASSERTS FACT** — must be gated |
| P2 | NPC_SPOKE | `if action == "DIALOGUE" and text:` | NPC_SPOKE | (would be: DialogueMemorySubscriber, ClaimEventSubscriber, NpcDialogueSubscriber, NpcSpeechActSubscriber) | Memory + epistemic | **DEAD** — `text` always `""` (payload has no text field). No action needed. If text is added later, must be gated. |
| P3 | ACTOR_ATTACKS | `if action == "ATTACK":` | ACTOR_ATTACKS | CombatSubscriber (_COMBAT_EVENT_TYPES includes ACTOR_ATTACKS) → ImpactEngine → StateApplicator | Physical: damage to target | **ASSERTS FACT** — must be gated OR projection removed |

### B.4. Double ImpactEngine problem (CRITICAL)

For Player ATTACK action, CombatSubscriber receives **two separate events**:

```
PATH A (UNGATED):
  turn_pipeline.py:412 → SOCIAL_ACTION (no auth check)
    → SocialActionSubscriber → ACTOR_ATTACKS (projection)
      → CombatSubscriber._on_event
        → ImpactEngine.resolve_physical_impact
          → DAMAGE #1

PATH B (dead gate):
  turn_pipeline.py:788 → publish_classified_player_event
    → G3C: PLAYER_ATTACKED deferred to INPUT_MERGE (return, no publish)
  tick_orchestrator.py:1716 → PLAYER_ATTACKED (gated by dead action_rejected)
    → CombatSubscriber._on_event
      → ImpactEngine.resolve_physical_impact
        → DAMAGE #2
```

G3C comment (phase_1_input.py:656-661): "иначе дубль: двойной ImpactEngine/VITAL_EVAL/SOCIAL_EMA — подтверждено логом injuries 1→2". G3C fixed double between `publish_classified_player_event` and INPUT_MERGE, but **did not address** the third publication path via SOCIAL_ACTION → ACTOR_ATTACKS.

### B.5. Other SOCIAL_ACTION listeners

| Listener | File | Effect |
|----------|------|--------|
| ObservabilityTap | calibration/observability_tap.py:33 | Passive observation only. No causal effect. |
| idle_event_projection | idle_event_projection.py:144 | EXCLUDED from v1 projection dictionary. Not projected to player. |

### B.6. Resolution per Master verdict 3

Verdict 3: "SOCIAL_ACTION сохраняется, но все его производные события, утверждающие факт совершённого действия, должны находиться за границей авторизации. Устранить возможность двойной публикации."

Two options for each fact-asserting projection:

**COMMUNICATION_CLAIM (P1):**
- Option A: Gate the SOCIAL_ACTION publish itself (before projection) — then all projections are gated at source
- Option B: Gate inside SocialActionSubscriber — check arbitration_result before projecting COMMUNICATION_CLAIM
- **Recommended: Option A** — gate at source (single gate point, not per-projection)

**ACTOR_ATTACKS (P3):**
- Option A: Gate at source (SOCIAL_ACTION publish gated) — same as P1
- Option B: Remove ACTOR_ATTACKS projection from SocialActionSubscriber entirely — INPUT_MERGE → PLAYER_ATTACKED is the canonical path for Player attacks
- **Recommended: Option B** — ACTOR_ATTACKS is for NPC→NPC/NPC→Player attacks (event_types.py:80: "Универсальная атака"). Player attacks should only go through PLAYER_ATTACKED. Removing the projection eliminates the double publication permanently.

**NPC_SPOKE (P2):** DEAD — no action needed.

---

## §C. Implementation Plan — Small Commits

Each commit is independently deployable, testable, and revertible. Order matters (dependencies noted).

### Commit 1: Stable Intent Identity infrastructure

**Goal:** Create deterministic intent_id generator + lifecycle store, without wiring into any production path.

**Files:**
- `backend/app/services/events/event_identity.py` (or new `intent_identity.py`) — add `next_intent_identity(scene_state, owner, action) → (tick, ordinal)`
- `backend/app/services/scene_state/scene_factory.py` — add defaults: `scene_state["intent_ordinals"] = {}`, `scene_state["intent_lifecycle"] = {}`

**Behavior change:** None (no production path uses them yet).

**Tests before:** IPT baseline (must be green).
**Tests after:**
- `test_intent_id_deterministic_under_replay` — same tick replayed twice → same intent_id
- `test_intent_lifecycle_default_empty` — new scene_state has empty dict
- `test_old_save_loads_without_intent_lifecycle` — old save without keys → treated as empty (fail-open)

**Regression:** IPT, save/load round-trip tests.
**Acceptance:** next_intent_identity returns deterministic (tick, ordinal); scene_state persists intent_ordinals and intent_lifecycle.
**Rollback:** Remove the function and defaults.
**Dependency:** None.

---

### Commit 2: Assign intent_id on Player path (no gate yet)

**Goal:** Player path assigns deterministic intent_id and creates lifecycle record.

**Files:**
- `backend/app/services/game_loop/turn_pipeline.py` — in `_execute_dm_and_intent_resolution`, after `intent_compressor.compress` (line 379), call `next_intent_identity`; store on `shared_context.player_intent_id`; create `scene_state["intent_lifecycle"][intent_id]` record (ACTIVE, arbitration_result=PENDING).

**Behavior change:** New empty lifecycle record per Player action. No gate changes. No publication changes.

**Tests before:** Commit 1 tests green.
**Tests after:**
- `test_player_intent_id_assigned` — after compress, shared_context has intent_id
- `test_lifecycle_record_created` — scene_state["intent_lifecycle"][intent_id] exists with ACTIVE state
- `test_intent_id_deterministic_in_replay` — same inputs → same intent_id

**Regression:** IPT, UE suite, will vertical tests.
**Acceptance:** Every Player action creates a lifecycle record with deterministic intent_id.
**Rollback:** Remove the assignment.
**Dependency:** Commit 1.

---

### Commit 3: BodyArbiter structural placement (always AUTHORIZED)

**Goal:** BodyArbiter runs on Player path, writes arbitration_result. Initial logic: always AUTHORIZED (no evaluation source — Master verdict 2: TBD).

**Files:**
- `backend/app/services/body_arbiter.py` (NEW) — `arbitrate(ctx, intent_id, scene_state) → ArbitrationResult`
- `backend/app/domain/arbitration.py` (NEW) — `ArbitrationResult` enum: AUTHORIZED / REJECTED
- `backend/app/services/game_loop/turn_pipeline.py` — call BodyArbiter after intent_id assignment (Commit 2), write `arbitration_result` to lifecycle record

**Behavior change:** `scene_state["intent_lifecycle"][intent_id]["arbitration_result"]` = AUTHORIZED. No publication change (gates not yet wired). Functionally a no-op.

**Tests before:** Commit 2 tests green.
**Tests after:**
- `test_body_arbiter_sets_authorized` — after BodyArbiter, lifecycle has AUTHORIZED
- `test_body_arbiter_no_psych_effects` — BodyArbiter does not write any psych deltas (§D check)

**Regression:** IPT, UE suite.
**Acceptance:** arbitration_result is set in lifecycle after BodyArbiter runs.
**Rollback:** Remove BodyArbiter call.
**Dependency:** Commits 1, 2.

---

### Commit 4: Gate SOCIAL_ACTION publish

**Goal:** SOCIAL_ACTION publication checks arbitration_result.

**Files:**
- `backend/app/services/game_loop/turn_pipeline.py` — add guard before line 412: `if _is_authorized(scene_state, intent_id):` publish SOCIAL_ACTION

**Behavior change:** When BodyArbiter returns REJECTED, SOCIAL_ACTION is not published. Currently BodyArbiter always AUTHORIZED → no behavior change yet. Infrastructure for future fix.

**Tests before:** Commit 3 tests green.
**Tests after:**
- `test_social_action_blocked_when_rejected` — mock BodyArbiter REJECTED → SOCIAL_ACTION not published
- `test_social_action_published_when_authorized` — AUTHORIZED → SOCIAL_ACTION published (baseline preserved)

**Regression:** UE suite, combat suite (SOCIAL_ACTION → ACTOR_ATTACKS path).
**Acceptance:** Gate is in place; behavior unchanged when AUTHORIZED.
**Rollback:** Remove guard.
**Dependency:** Commit 3.

---

### Commit 5: Remove ACTOR_ATTACKS projection from SocialActionSubscriber

**Goal:** Eliminate double ImpactEngine for Player attacks. Per §B.6: ACTOR_ATTACKS projection from SOCIAL_ACTION is removed; INPUT_MERGE → PLAYER_ATTACKED is the canonical Player attack path.

**Files:**
- `backend/app/services/events/social_action_subscriber.py` — remove lines 66-78 (projection #3: ACTOR_ATTACKS)

**Behavior change:** Player ATTACK action no longer triggers ACTOR_ATTACKS via SOCIAL_ACTION. Only PLAYER_ATTACKED (from INPUT_MERGE) triggers CombatSubscriber for Player attacks. NPC→NPC/NPC→Player attacks via ACTOR_ATTACKS are unaffected (they come from IntentEventAdapter, not from SocialActionSubscriber).

**Tests before:** Commit 4 tests green.
**Tests after:**
- `test_player_attack_single_impact_engine` — ATTACK action → exactly one ImpactEngine invocation (via PLAYER_ATTACKED)
- `test_npc_attack_actor_attacks_unchanged` — NPC ATTACK → ACTOR_ATTACKS still published via IntentEventAdapter
- `test_no_actor_attacks_from_social_action` — SOCIAL_ACTION with action=ATTACK → no ACTOR_ATTACKS projection

**Regression:** Combat suite (test_combat_subscriber, test_combat_pipeline_e2e), IPT.
**Acceptance:** Player attacks cause exactly one damage application, not two.
**Rollback:** Re-add the projection.
**Dependency:** Commit 4 (gate SOCIAL_ACTION, so REJECTED attacks don't publish at all).

---

### Commit 6: Gate publish_classified_player_event

**Goal:** Replace dead `action_rejected` gate with `arbitration_result` check.

**Files:**
- `backend/app/services/game_loop/turn_pipeline.py` — line 787: replace `not getattr(shared_context, "action_rejected", False)` with `_is_authorized(scene_state, intent_id)`

**Behavior change:** When BodyArbiter returns REJECTED, classified events (PLAYER_SPOKE, PLAYER_THREATENS, etc.) are not published. WV `physics_validation` remains independent (Master verdict 4) — it can still record notes, but does not gate publication.

**Tests before:** Commit 5 tests green.
**Tests after:**
- `test_classified_blocked_when_rejected` — REJECTED → no PLAYER_SPOKE/THREATENS/etc.
- `test_classified_published_when_authorized` — AUTHORIZED → events published (baseline)
- `test_wv_physics_validation_independent` — WV notes recorded regardless of arbitration_result
- `test_fast_path_does_not_bypass_gate` — Fast-Path classifies but publication blocked if REJECTED

**Regression:** UE suite, combat suite, dialogue tests.
**Acceptance:** R7 bypass scenario: REJECTED → no classified event published.
**Rollback:** Revert to `action_rejected` gate.
**Dependency:** Commit 3.

---

### Commit 7: Gate INPUT_MERGE PLAYER_ATTACKED

**Goal:** Replace dead `action_rejected` gate in INPUT_MERGE with `arbitration_result` check.

**Files:**
- `backend/app/services/tick_orchestrator.py` — lines 1698-1703: replace `action_rejected` check with `_is_authorized(scene_state, intent_id)`

**Behavior change:** When BodyArbiter returns REJECTED, PLAYER_ATTACKED is not published from INPUT_MERGE. No damage from blocked attacks.

**Tests before:** Commit 6 tests green.
**Tests after:**
- `test_player_attacked_blocked_when_rejected` — REJECTED → no PLAYER_ATTACKED, no damage
- `test_player_attacked_published_when_authorized` — AUTHORIZED → PLAYER_ATTACKED published (baseline)
- `test_combat_subscriber_receives_only_authorized` — CombatSubscriber receives no events for REJECTED intents

**Regression:** Combat suite (test_combat_subscriber, test_combat_pipeline_e2e, test_physiology_flow), IPT.
**Acceptance:** Blocked attack → no damage, no NPC perception of attack.
**Rollback:** Revert to `action_rejected` gate.
**Dependency:** Commit 6.

---

### Commit 8: Fix STM bypass

**Goal:** Move `add_dialogue_turn` from dm_phase (before auth) to after BodyArbiter (after auth).

**Files:**
- `backend/app/services/game_loop/dm_phase.py` — remove `add_dialogue_turn` call (line 185) and L1Chronicle write (line 200)
- `backend/app/services/game_loop/turn_pipeline.py` — add `add_dialogue_turn` + L1Chronicle write AFTER BodyArbiter (Commit 3 placement), guarded by `arbitration_result == AUTHORIZED`

**Behavior change:** Blocked speech does not enter STM. NPCs don't remember unspoken words. L1Chronicle doesn't record unspoken dialogue.

**Tests before:** Commit 7 tests green.
**Tests after:**
- `test_blocked_speech_not_in_stm` — REJECTED → STM clean
- `test_authorized_speech_in_stm` — AUTHORIZED → STM has speech (baseline)
- `test_blocked_speech_not_in_l1` — REJECTED → no TraitDriftEvent
- `test_dm_reads_stm_before_auth` — DM can still read STM for context (get_stm_prompt_block unchanged)

**Regression:** Dialogue thread continuity tests, cognition context tests, gc_dialogue_test, test_love (L1Chronicle).
**Acceptance:** STM does not contain Player speech when BodyArbiter blocked speech.
**Rollback:** Move add_dialogue_turn back to dm_phase.
**Dependency:** Commit 3 (BodyArbiter placement).

---

### Commit 9: Remove dead code (action_rejected / rejection_reason / publish_player_speech)

**Goal:** Clean up dead code after all gates proven to use arbitration_result.

**Files:**
- `backend/app/services/tick_orchestrator.py` — remove dead `action_rejected` check (line 1698) and `rejection_reason` read (line 1702)
- `backend/app/services/game_loop/phase_1_input.py` — remove `publish_player_speech` function (lines 471-503, fully dead)
- Grep for any remaining `action_rejected` / `rejection_reason` / `publish_player_speech` references and remove

**Behavior change:** None (all gates already use arbitration_result from Commits 6-7).

**Tests before:** Commits 6, 7, 8 green.
**Tests after:**
- `test_no_action_rejected_references` — grep returns 0 matches
- `test_no_publish_player_speech_references` — grep returns 0 matches

**Regression:** Full IPT + pytest suite.
**Acceptance:** No references to action_rejected/rejection_reason/publish_player_speech in codebase.
**Rollback:** N/A (dead code removal).
**Dependency:** Commits 6, 7, 8.

---

### Commit 10: Integration test — real game scenario

**Goal:** Prove the bypass fix works end-to-end.

**Test scenario (per handover §6 Step 9 + Master verdicts):**

```
1. Avatar сопротивляется речи Player
   → Player tries to speak, BodyArbiter REJECTED
   → PLAYER_SPOKE NOT published
   → STM does NOT contain the speech
   → L1Chronicle does NOT contain the dialogue event
   → NPCs do NOT hear or remember unspoken words

2. Player пытается атаковать, Avatar отказывает
   → Player tries to attack, BodyArbiter REJECTED
   → PLAYER_ATTACKED NOT published (INPUT_MERGE gated)
   → ACTOR_ATTACKS NOT published (projection removed in Commit 5)
   → SOCIAL_ACTION NOT published (gated in Commit 4)
   → CombatSubscriber receives nothing
   → No damage occurs
   → NPCs do NOT perceive an attack that didn't happen

3. мир не получает ложных событий
   → The world receives NO false events from blocked intentions
   → EpistemicStore has no claims from blocked COMMUNICATION_CLAIM
   → STM has no records from blocked speech
   → L1Chronicle has no events from blocked actions
```

**NOTE:** This test requires BodyArbiter to actually REJECTED. Until Commit 11 (evaluation source) is wired, BodyArbiter always AUTHORIZES → test passes trivially. The real bypass fix is only proven when BodyArbiter can reject.

**Tests before:** All previous commits green.
**Tests after:** Integration test GREEN.
**Acceptance:** NPCs don't hear unspoken words, don't take damage from uncommitted attacks, don't form memories of events that didn't happen.
**Rollback:** N/A (test-only).
**Dependency:** Commits 4-9. **BLOCKED on Commit 11 for real validation.**

---

### Commit 11 (TBD): Wire Avatar resistance evaluation into BodyArbiter

**Goal:** BodyArbiter can actually REJECTED based on Avatar resistance.

**Status:** BLOCKED — per Master verdict 2: "Источник оценки сопротивления Avatar необходимо исследовать отдельно."

**Open research (see §E):**
- (a) Read Avatar NPCState.psyche (willpower, breakpoint, loyalty) directly
- (b) Create lightweight evaluation specific to Player path
- (c) Other approach (Master's verdict TBD)

**This commit cannot be planned until the evaluation source is decided.**

---

## §D. ADR-PRE-FLIGHT CHECKLIST

### D.1. ADR classification

- **Type:** STANDARD (not ONTO — no new domain primitive; wiring + gate replacement)
- **Affected domains:** intent lifecycle, authorization, publication, STM, combat, epistemic
- **Downstream consumers:** CombatSubscriber, ClaimEventSubscriber, SocialActionSubscriber, DialogueMemorySubscriber, ReactionSubscriber, ObservationSubscriber, SocialSubscriber, RulesSubscriber, NpcDialogueSubscriber, NpcSpeechActSubscriber, PlayerSpeechActSubscriber, idle_event_projection

### D.2. Resource budget

| Resource | Impact |
|----------|--------|
| RAM | +1 dict per intent (intent_lifecycle record, ~10 fields); +1 counter dict (intent_ordinals, 1 entry per owner/action per tick) |
| VRAM | None |
| Tick latency | +1 dict lookup per gate (3 gates: SOCIAL_ACTION, classified, INPUT_MERGE) — negligible |
| Persistence | intent_lifecycle + intent_ordinals persisted via atomic_commit (additive keys, fail-open for old saves) |

### D.3. Rollback plan

Each commit is independently revertible:
- Commits 1-3: infrastructure (no behavior change)
- Commits 4-5: gates (revert to dead action_rejected / re-add projection)
- Commits 6-7: gate replacement (revert to action_rejected)
- Commit 8: STM move (revert to dm_phase placement)
- Commit 9: dead code removal (re-add if needed)
- Full rollback: revert commits 9→1 in order

### D.4. Checks

#### D.4.1. ID stability & replay
- ✅ `next_intent_identity` uses persistent ordinal counter (`scene_state["intent_ordinals"]`), mirrors `next_event_identity` (ADR-O-404)
- ✅ Deterministic: same (tick, owner, action) → same intent_id across replays
- ✅ No `uuid4` for intent_id (MovementIntent uuid4 on NPC path is separate, out of scope)
- ✅ Old saves: `intent_ordinals` absent → treated as `{}` (fail-open)

#### D.4.2. Old saves preservation
- ✅ `intent_lifecycle` and `intent_ordinals` are additive keys in scene_state
- ✅ Old saves without these keys load without error (default to `{}`)
- ✅ `IntentDTO` does not get `intent_id` field (verdict 1: "backend-generated"; stored on shared_context, not on DTO crossing FE→BE boundary)
- ✅ No migration required (additive keys, not schema change)

#### D.4.3. No second SSOT
- ✅ `scene_state["intent_lifecycle"]` is the ONLY source of `arbitration_result`
- ✅ `action_rejected` removed (was dead, never written)
- ✅ `physics_validation` (WV result) remains independent (Master verdict 4) — does not gate publication, only records notes
- ✅ No `action_authorized` boolean (handover §2.3 rejected this)

#### D.4.4. No double psych effects
- ✅ BodyArbiter does NOT apply psych effects (only sets `arbitration_result`)
- ✅ WillpowerGate on NPC path (Phase 1, tick_orchestrator:2006) unchanged — still applies psych effects for NPC intents
- ✅ No second WillpowerGate invocation on Player path (Master verdict 2)
- ⚠ Open: separation of internal-conflict vs consequence effects (handover §6 Step 7, DEFERRED) — not in scope of Commits 1-10

#### D.4.5. No BodyArbiter bypass
- ✅ ALL Player publication paths check `arbitration_result`:
  - SOCIAL_ACTION (Commit 4)
  - publish_classified_player_event (Commit 6)
  - INPUT_MERGE PLAYER_ATTACKED (Commit 7)
- ✅ STM write gated (Commit 8)
- ✅ L1Chronicle write gated (Commit 8)
- ✅ ACTOR_ATTACKS projection removed (Commit 5) — eliminates double path
- ✅ COMMUNICATION_CLAIM projection gated at source (SOCIAL_ACTION gate in Commit 4)
- ⚠ Open: verify no OTHER publication paths exist (need comprehensive grep after Commit 9)

#### D.4.6. No NPC pipeline regression
- ✅ BodyArbiter is Player-path only
- ✅ NPC path (WillpowerGate in `run_phase_1_input`, tick_orchestrator:2006) unchanged
- ✅ MovementIntent `intent_id` (uuid4, NPC path) unchanged — out of scope
- ✅ `IntentIdentity` (domain/intent_identity.py) unchanged — already git-tracked
- ✅ `publish_player_intent` (phases/input.py:25, NPC path gated by WillpowerGate) unchanged
- ⚠ Open: verify NPC ACTOR_ATTACKS path (IntentEventAdapter) is not affected by SocialActionSubscriber change (Commit 5) — different producer, should be safe

#### D.4.7. Existing paths preserved
- ✅ Combat: AUTHORIZED attacks → PLAYER_ATTACKED from INPUT_MERGE (single path, no double)
- ✅ Dialogue: AUTHORIZED speech → PLAYER_SPOKE from publish_classified_player_event → STM write
- ✅ Movement: unchanged (not Player-action-derived in this scope)
- ✅ Interaction: AUTHORIZED interactions → PLAYER_INTERACTS from publish_classified_player_event
- ⚠ Tests that assume PLAYER_ATTACKED is always published must be updated to set arbitration_result=AUTHORIZED explicitly (NOT mass-set ACTIVE — each test must reflect a real scenario)

#### D.4.8. Speech recording correctness
- ✅ Authorized speech: enters STM (Commit 8, guarded by AUTHORIZED)
- ✅ Blocked speech: does NOT enter STM
- ✅ DM reads STM before auth (get_stm_prompt_block unchanged) — DM has context
- ✅ NPC perception: ClaimEventSubscriber receives COMMUNICATION_CLAIM only if SOCIAL_ACTION published (Commit 4 gate)
- ✅ EpistemicStore: no claims from blocked speech
- ⚠ Open: NPC_SPOKE projection from SocialActionSubscriber is DEAD (text always "") — if text is added to SOCIAL_ACTION payload later, must be gated

### D.5. Regression test matrix

| Suite | Commits affected | Must pass |
|-------|-----------------|-----------|
| IPT | All | 54/0/0 (baseline preserved) |
| UE suite | 2, 3, 4, 6 | 56+7xf |
| Combat suite | 5, 6, 7 | 24+1s |
| Dialogue tests | 8 | All green |
| Save/load | 1, 2 | Round-trip intact |
| IPT-INV-REPLAY-DETERMINISM | 1, 2 | GREEN (intent_id deterministic) |

---

## §E. Unresolved Questions

These are NOT filled with assumptions. Each is marked with what the code does NOT prove.

### E.1. BodyArbiter evaluation source (BLOCKING — Master verdict 2)

**Question:** How does BodyArbiter evaluate Avatar resistance on Player path?

**What code proves:**
- WillpowerGate (`run_phase_1_input`) is NOT invoked on Player path (only NPC idle path, tick_orchestrator:2006)
- `ctx.will_response` does not exist on Player path
- Avatar NPCState exists in `scene_state` (NPC psyche with willpower, breakpoint, loyalty — confirmed by NPC path architecture)

**What code does NOT prove:**
- Whether BodyArbiter should read Avatar psyche directly
- Whether a lightweight evaluation should be created
- What inputs BodyArbiter needs (raw_input? action_type? semantic_field? target_id?)
- How BodyArbiter distinguishes refusal/delay/resistance/struggle (handover §6 Step 4 granularity)

**Status:** BLOCKED on Master's verdict. Commits 1-9 are structural (BodyArbiter always AUTHORIZED). Commit 10 (integration test) cannot prove the real bypass fix until Commit 11 is wired.

### E.2. DM phase ordering (Commits 3, 8)

**Question:** Can BodyArbiter run before DM phase, or must DM phase be split?

**What code proves:**
- DM phase (`run_dm_phase`, turn_pipeline.py:341) runs BEFORE compress (line 379)
- DM phase writes STM (dm_phase.py:185) and L1Chronicle (dm_phase.py:200) — both are materialization
- BodyArbiter needs intent to evaluate — but IntentSemanticField is created by compress (after DM)
- DM uses STM reads (get_stm_prompt_block) for LLM context — reads are OK before auth

**What code does NOT prove:**
- Whether DM classification needs to happen before BodyArbiter (DM sets action_type, which BodyArbiter might need)
- Whether compress can run before DM (DM prompt may depend on compress output — need to verify DM phase internals)
- Whether splitting dm_phase (classification first, STM write after BodyArbiter) is safe

**Status:** Open. Commit 3 placement assumes BodyArbiter can run after compress but before DM STM write. Need to verify DM phase structure. Option (c) from §A.3 may be required.

### E.3. intent_id field on IntentDTO (Master verdict 1 interpretation)

**Question:** Does "backend-generated deterministic intent_id" mean add a field to IntentDTO, or store on shared_context?

**What code proves:**
- IntentDTO (domain/intent.py:56-70) has 5 fields: action, target, parameters, text, campaign_id
- IntentDTO crosses FE→BE boundary (docstring: "Парсер (intent_parser) выдаёт это")
- Master verdict 1: "Не генерировать авторитетный ID на frontend"

**What code does NOT prove:**
- Whether intent_id should be added to IntentDTO (backend sets it after FE sends DTO)
- Or whether intent_id stays on shared_context only (not on DTO)
- Or whether intent_id is a composite key (tick, ordinal) without a field

**Interpretation:** Verdict 1 says "backend-generated" — this means FE does not send intent_id. Backend assigns it. The field can be added to IntentDTO (set by backend after receipt) OR stored on shared_context. Both satisfy "backend-generated". Plan uses shared_context (Commit 2) — least disruptive, no DTO change. Open to Master's clarification.

### E.4. SOCIAL_ACTION payload "text" field (Commit 4)

**Question:** Should SOCIAL_ACTION payload include "text" for NPC_SPOKE projection?

**What code proves:**
- SOCIAL_ACTION payload (turn_pipeline.py:400-410) has NO "text" field
- SocialActionSubscriber NPC_SPOKE projection (line 50) checks `action == "DIALOGUE" and text` — text always "" → DEAD
- NPC_SPOKE for Player is published via publish_classified_player_event (PLAYER_SPOKE), not via SOCIAL_ACTION

**What code does NOT prove:**
- Whether the NPC_SPOKE projection was intended to be live (and text field was forgotten)
- Or whether it's intentionally dead (NPC_SPOKE only via classified publish)

**Status:** DEAD projection. No action in Commits 1-10. If text is added later, must be gated by arbitration_result (same gate as SOCIAL_ACTION publish — Commit 4 covers this).

### E.5. intent_lifecycle cleanup

**Question:** When are SATISFIED/ABANDONED/VOIDED records removed from scene_state["intent_lifecycle"]?

**What code proves:**
- Nothing (scene_state["intent_lifecycle"] does not exist yet — Commit 1 creates it)

**What code does NOT prove:**
- Whether records should persist indefinitely (scene_state grows unbounded)
- Whether records should be cleaned up after SATISFIED
- Whether records should survive save/load

**Status:** Open. Not blocking for Commits 1-10 (records are small, ~10 fields each). Address in a future step if scene_state growth becomes an issue.

### E.6. Multiple intents per tick

**Question:** Can Player form multiple intents in one tick? If so, how does BodyArbiter handle them?

**What code proves:**
- `actions[0].action` (turn_pipeline.py:792) suggests only first action is processed
- `resolve_player_intent` returns single IntentResolution

**What code does NOT prove:**
- Whether multi-action input is possible
- Whether BodyArbiter should evaluate each intent separately

**Status:** Open. Current code processes single action per turn. Not blocking.

### E.7. publish_player_speech removal (Commit 9)

**Question:** Is `publish_player_speech` (phase_1_input.py:471-503) safe to remove?

**What code proves:**
- 0 call sites in `backend/app/` (Step 0 finding 1)
- 0 call sites in `backend/tests/`, `backend/scripts/`, `scripts/` (Step 0 finding 11)

**What code does NOT prove:**
- Whether it was recently deprecated and might be referenced in docs/ADRs
- Whether frontend expects it (unlikely — frontend doesn't import backend)

**Status:** Safe to remove in Commit 9. Grep docs/ for references before removal.

### E.8. L1Chronicle TraitDriftEvent bypass (Commit 8)

**Question:** Is dm_phase.py:200 (TraitDriftEvent "dialogue" write) also a bypass?

**What code proves:**
- dm_phase.py:200 writes TraitDriftEvent to L1Chronicle alongside STM write
- Both happen before any auth check
- L1Chronicle is append-only (cannot be removed — ADR-O-208)

**What code does NOT prove:**
- Whether TraitDriftEvent for blocked speech should be prevented (yes — same logic as STM)
- Whether moving it with STM write (Commit 8) is sufficient

**Status:** Commit 8 moves both STM write and L1Chronicle write. Both gated by AUTHORIZED.

### E.9. SOCIAL_ACTION for THREATEN/STEAL/GIVE

**Question:** Do THREATEN/STEAL/GIVE actions also need gate analysis?

**What code proves:**
- SOCIAL_ACTION publishes for ATTACK, THREATEN, DIALOGUE, STEAL, GIVE (turn_pipeline.py:387)
- SocialActionSubscriber: COMMUNICATION_CLAIM projection fires for any action with proposition (including THREATEN/STEAL/GIVE if they have propositions)
- ACTOR_ATTACKS projection fires only for ATTACK

**What code does NOT prove:**
- Whether THREATEN/STEAL/GIVE have other publication paths (publish_classified_player_event → PLAYER_THREATENS, THEFT, etc.)
- Whether gating SOCIAL_ACTION (Commit 4) is sufficient for all derivatives

**Status:** Commit 4 gates SOCIAL_ACTION at source — all projections (COMMUNICATION_CLAIM, NPC_SPOKE, ACTOR_ATTACKS) are gated. THREATEN/STEAL/GIVE covered by the same gate. No separate analysis needed.

### E.10. ObservabilityTap on SOCIAL_ACTION

**Question:** Does ObservabilityTap (calibration/observability_tap.py:33) need gating?

**What code proves:**
- ObservabilityTap is passive (ADR-O-361: "наблюдение не создает причинность")
- It records events for calibration lab, does not mutate world state

**What code does NOT prove:**
- Whether recording a REJECTED SOCIAL_ACTION in ObservabilityTap is semantically correct (it observes the publish, which didn't happen if gated)

**Status:** If SOCIAL_ACTION is gated (not published), ObservabilityTap never receives it — no issue. If SOCIAL_ACTION is published but projections are gated internally (alternative approach), ObservabilityTap sees the event. Current plan gates at source (Commit 4) — ObservabilityTap only sees AUTHORIZED SOCIAL_ACTION. Acceptable.

---

## §F. Provenance

This report is based on:
- Step 0 archaeology zones [1]-[27] (PowerShell read-only commands, executed 2026-11-07)
- Stage 2.1 R1-R10 handover document (2026-11-03)
- Master's four verdicts (2026-11-07)
- ADR atlas (docs/ADR (Architecture Decision Records).md, v8.0)
- CAUSAL CONTRACT v3.0
- Architectural Charter (АРХИТЕКТУРНЫЙ УСТАВ ENIGMA)
- ЗАВЕЩАНИЕ_АРХИТЕКТОРОВ (letters S348-S380)

All findings tagged with evidence origin:
- **VERIFIED BY SOURCE** — directly confirmed by source code in Step 0 archaeology
- **DESIGN DECISION** — approved by Master (4 verdicts, 2026-11-07)
- **OPEN QUESTION** — requires successor investigation (§E)

---

*Production: HOLD. READ-ONLY. All findings in this report are factual, based on code archaeology. No assumptions fill the open questions in §E. After Master's approval of the first commit, production work begins.*
