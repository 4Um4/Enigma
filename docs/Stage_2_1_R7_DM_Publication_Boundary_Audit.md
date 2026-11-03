# Stage 2.1-R7 — DM Publication Boundary Audit

**Mode:** READ-ONLY
**Date:** 2026-11-03
**Verdict:** CONFIRMED BYPASS — DM path can publish PLAYER_ATTACKED and PLAYER_SPOKE regardless of WillpowerGate outcome.

---

## 1. Full Call Sequence: RAW Player Input → `publish_classified_player_event`

### Path A — WillpowerGate (phases/input.py)

```
Player raw_input
    ↓
resolve_player_intent (phase_1_input.py:276)
    → IntentDTO (action, target, parameters)
    → ctx.player_intent
    ↓
run_phase_1_input (phases/input.py:58)
    ↓
resolve_intent_pressure(intent) → IntentPressureProfile  [L104-105]
scan_affective_resonance(intent, ...) → resonance          [L119]
distort_pressure(pressure, resonance, psyche) → distorted   [L120]
compute_willpower(distorted, psyche) → will_response         [L123]
    ↓
if will_response.state in (COMPLY, RELUCTANT, CONDITIONED):  [L147-153]
    publish_player_intent(ctx, intent)
        → EventDTO(PLAYER_ATTACKS or PLAYER_INTERACTS)     [L25-55]
else (RESIST / DELAY / MISINTERPRET / NEGOTIATE / etc.):    [L206]
    NO publish_player_intent
    delta_buffer.append(WillConflictPayload)                [L215-228]
    shared_context.will_conflict_data = {...}               [L234-247]
    get_event_bus().publish(WILL_CONFLICT)                  [L253-262]
    emotion/stress deltas applied                           [L264-291]
    affective conditioning applied                           [L293-304]
```

**Key:** When WillpowerGate blocks, Path A does NOT publish PLAYER_ATTACKS/PLAYER_INTERACTS. It publishes WILL_CONFLICT instead. But it does NOT set `shared_context.action_rejected = True` — see §4.

### Path B — DM classification (phase_1_input.py)

```
Player raw_input
    ↓
DM processing (dm_phase.py)
    → shared_context.action_type = "attack" / "dialogue" / "player_threatens" / etc.
    ↓
publish_classified_player_event (phase_1_input.py:510)
    ↓
_evt_map maps action_type → EventType:
    "attack"        → PLAYER_ATTACKED
    "player_attacks"→ PLAYER_ATTACKED
    "dialogue"      → PLAYER_SPOKE
    "player_interacts" → PLAYER_SPOKE
    "player_threatens" → PLAYER_THREATENS
    ... etc.
    ↓
Fast-Path lexical override (S122 FIX, L536-549):
    if raw_input.lower() contains any of ["удар","бей","атак","вреж","убей","калеч"]:
        _raw_type = "attack" (FORCE OVERRIDE)
        shared_context.action_type = "attack"
    ↓
_resolved_type = _evt_map.get(_raw_type.lower(), PLAYER_SPOKE)
    ↓
[continues into _phase_1_input_merge — see §3]
```

### Path B continues — _phase_1_input_merge (tick_orchestrator.py)

Per ADR-O-424: `_phase_1_input_merge` is the "single fail-closed gate before branching."

The code at phase_1_input.py:591-668 (function name not captured in available reports, but attributed to the input-merge pipeline) contains:

```
ADR-091 IntentCompressor override (L591-607):
    DM_Router type may be overridden by IntentCompressor output

_evt_map second mapping (L610):
    _resolved_type = _evt_map.get(_raw_type.lower(), PLAYER_SPOKE)

UE-GATE — readiness check (L620-629):
    _readiness = getattr(_params, "intent_readiness", None)
    if _readiness and _readiness != "RESOLVED" and _resolved_type != PLAYER_SPOKE:
        logger.warning("[UE-GATE] intent_readiness={_readiness}: '{_raw_type}' деградирует до PLAYER_SPOKE")
        _resolved_type = EventType.PLAYER_SPOKE

G3-C FIX — cardinality (L656-664):
    if _resolved_type == EventType.PLAYER_ATTACKED:
        logger.info("[G3C] PLAYER_ATTACKED publication deferred to INPUT_MERGE combat pipe")
        [publication deferred — not published here]

Event creation (L668):
    _game_evt = EventDTO.create(...)
```

**The UE-GATE checks `intent_readiness` — NOT WillpowerGate.** `intent_readiness` measures reference resolution confidence (did the resolver find the target?), not willpower authorization. A fully-resolved attack (target found, readiness=RESOLVED) that WillpowerGate blocks passes the UE-GATE.

---

## 2. Publication Phase Relative to WillpowerGate and Phase 5.5

### Phase ordering (tick_orchestrator.py)

| Phase | What happens | WillpowerGate state |
|-------|-------------|---------------------|
| Pre-tick (DM) | DM classifies raw_input → `shared_context.action_type` | Not yet checked |
| Phase 1 | `run_phase_1_input` → WillpowerGate → `publish_player_intent` (if not blocked) | **CHECKED HERE** |
| _phase_1_input_merge | UE-GATE (readiness) + G3C deferral + event publication | WillpowerGate result NOT checked |
| Phase 2 | event_bus_primary — spatial events | — |
| Phase 3 | memory | — |
| Phase 4 | pre_decision (TopicExtractor) | — |
| Phase 5 | DecisionHub (NPC decisions) | — |
| **tick_orchestrator:1690-1718** | INPUT_MERGE combat pipe — publishes deferred PLAYER_ATTACKED | WV gate checks `action_rejected` (always False — see §4) |
| Phase 8 | drain_secondary — CombatSubscriber processes PLAYER_ATTACKED | — |

**Critical timing:** The WV gate at tick_orchestrator:1698 runs AFTER WillpowerGate (Phase 1) but BEFORE CombatSubscriber processing (Phase 8). It was designed to suppress PLAYER_ATTACKED publication when WillpowerGate blocked. But see §4.

---

## 3. Can DM Path Publish PLAYER_ATTACKED When WillpowerGate Blocked?

### The INPUT_MERGE combat pipe (tick_orchestrator.py:1690-1718)

```python
# L1696: # (action_rejected) не издаёт PLAYER_ATTACKED — свидетели не получают
# L1698:
if getattr(getattr(ctx, "shared_context", None), "action_rejected", False):
    # L1701:
    logger.info(f"[WV] PLAYER_ATTACKED suppressed (action_rejected: "
    # L1702:
                f"{getattr(ctx.shared_context, 'rejection_reason', '')})")
    # [skip publication — PLAYER_ATTACKED NOT published]
else:
    # [fall through — publish PLAYER_ATTACKED]
    # L1718:
    ... type=EventType.PLAYER_ATTACKED.value, ...
```

**This is the gate that was SUPPOSED to enforce "попытка ≠ событие" for combat.** If `action_rejected=True`, PLAYER_ATTACKED is suppressed. If `action_rejected=False` (the default), PLAYER_ATTACKED is published.

### §4 below proves `action_rejected` is NEVER SET to True.

Therefore: **the `else` branch always executes → PLAYER_ATTACKED is always published → CombatSubscriber always receives it → ImpactEngine always processes it → damage always occurs.**

---

## 4. Can DM Path Publish PLAYER_SPOKE When Player Speech Not Authorized?

### `publish_classified_player_event` maps dialogue → PLAYER_SPOKE directly

```python
# phase_1_input.py:517-519
_evt_map = {
    "dialogue": EventType.PLAYER_SPOKE,
    "player_interacts": EventType.PLAYER_SPOKE,
    ...
}
```

If DM classifies input as "dialogue" or "player_interacts", PLAYER_SPOKE is published. **No WillpowerGate check exists in this path.**

### The UE-GATE does NOT block PLAYER_SPOKE — it DEGRADES to it

```python
# phase_1_input.py:623-629
if _readiness and _readiness != "RESOLVED" and _resolved_type != EventType.PLAYER_SPOKE:
    _resolved_type = EventType.PLAYER_SPOKE  # degrade to speech
```

Non-resolved intents become PLAYER_SPOKE. This means PLAYER_SPOKE is ALWAYS published — it's the fail-safe fallback. The principle "попытка ≠ событие" applies only to COMBAT (PLAYER_ATTACKED), not to speech.

### Consequence

If WillpowerGate blocks a Player's speech (avatar refuses to speak), the DM path still publishes PLAYER_SPOKE. NPCs hear words the Avatar's body never uttered. This violates the distinction between "intent to speak" and "actually spoken speech."

---

## 5. Subscribers That Turn These Events Into Consequences

### PLAYER_ATTACKED subscribers

| Subscriber | File:Line | Effect |
|-----------|-----------|--------|
| **CombatSubscriber** | combat_subscriber.py:43 | PLAYER_ATTACKED → ImpactEngine → PhysiologyPayload(shock_impulse) → StateApplicator → **physical damage** |
| **ReactionSubscriber** | reaction_subscriber.py:55 | PLAYER_ATTACKED → NPC stress/emotion deltas → reaction event generation |
| **ObservationSubscriber** | game_loop.py:649 | PLAYER_ATTACKED → `_obs_sub.on_world_event` → NPC perception ("ты видишь как {actor} атакует") |
| **SocialSubscriber** | social_subscriber.py:38 | PLAYER_ATTACKED → social relationship changes (trust/fear) |
| **RulesSubscriber** | rules_subscriber.py:84 | PLAYER_ATTACKED → rules processing |

### PLAYER_SPOKE subscribers

| Subscriber | File:Line | Effect |
|-----------|-----------|--------|
| **ClaimEventSubscriber** | claim_event_subscriber.py:89-90 | PLAYER_SPOKE → ClaimEvent → belief revision for hearing NPCs |
| **PlayerSpeechActSubscriber** | game_loop.py:576 | PLAYER_SPOKE → speech act processing (ACCUSE/THREATEN/ASSERT etc.) |
| **DialogueMemorySubscriber** | game_loop.py:560 | PLAYER_SPOKE → EventMemory in narrative_cache |
| **NpcDialogueSubscriber** | game_loop.py:627 | PLAYER_SPOKE → NPC dialogue session update |
| **SocialSubscriber** | social_subscriber.py:37 | PLAYER_SPOKE → social relationship changes |
| **ObservationSubscriber** | perception_filter.py:220 | PLAYER_SPOKE → NPC perception ("{actor} обращается к кому-то") |

**Both PLAYER_ATTACKED and PLAYER_SPOKE have DIRECT paths to physical and social consequences via subscribers.** If these events are published by the DM path when WillpowerGate blocked, the consequences materialize regardless of the Avatar's refusal.

---

## 6. Existing Mechanism to Pass Authorization Result to DM Path

### `shared_context.will_conflict_data` — WRITTEN but NOT READ for suppression

| Where | Action |
|-------|--------|
| phases/input.py:188 | **WRITE** (COMPLY/RELUCTANT path with identity damage) |
| phases/input.py:234 | **WRITE** (RESIST path) |
| game_loop.py:393 (UI builder) | **READ** — but only for API/UI response display |
| _phase_1_input_merge | **NOT READ** |
| tick_orchestrator:1698 | **NOT READ** (reads `action_rejected`, not `will_conflict_data`) |
| publish_classified_player_event | **NOT READ** |

**`will_conflict_data` exists as a signal — it carries the WillpowerGate result — but no gate in the DM path consumes it.** It's an output field for the player UI, not an authorization signal for the publication boundary.

### `shared_context.action_rejected` — READ but NEVER WRITTEN

| Where | Action |
|-------|--------|
| tick_orchestrator.py:1698 | **READ** (`if getattr(..., "action_rejected", False)`) |
| **Anywhere** | **NEVER WRITTEN** — no assignment found in entire codebase |

**`action_rejected` is a dead field.** The WV gate that reads it is dead code. The default `False` means the gate never triggers.

### `shared_context.rejection_reason` — READ but NEVER WRITTEN

Same as `action_rejected` — read at tick_orchestrator:1702, never assigned anywhere.

### Conclusion on existing mechanism

**There IS a signal (`will_conflict_data`) that carries the WillpowerGate result, but it's NOT wired to the DM publication path.** The mechanism that WAS intended to enforce the boundary (`action_rejected`) is dead — it was never connected to WillpowerGate's output.

---

## 7. Test Scenario: Player Attacks → WillpowerGate Rejects → Can Damage Occur?

### Trace

```
1. Player types: "Ударь стражника"
   ↓
2. DM classifies: action_type = "attack" (or Fast-Path override triggers on "удар")
   shared_context.action_type = "attack"
   ↓
3. Phase 1 — run_phase_1_input:
   compute_willpower → WillState.RESIST (avatar refuses)
   → publish_player_intent NOT called (no PLAYER_ATTACKS)
   → WILL_CONFLICT published
   → shared_context.will_conflict_data = {state: "resist", ...}
   → shared_context.action_rejected NOT SET (remains False/absent)
   ↓
4. _phase_1_input_merge:
   _resolved_type = PLAYER_ATTACKED (from _evt_map["attack"])
   UE-GATE: intent_readiness = "RESOLVED" (target found) → no degradation
   G3-C: PLAYER_ATTACKED deferred to INPUT_MERGE combat pipe
   ↓
5. tick_orchestrator:1698 — INPUT_MERGE combat pipe:
   if getattr(shared_context, "action_rejected", False):  → False (never set)
   → else branch: publish PLAYER_ATTACKED  [L1718]
   ↓
6. CombatSubscriber receives PLAYER_ATTACKED (immediate callback)
   → _pending_events accumulates
   ↓
7. Phase 8 — drain_secondary:
   CombatSubscriber.drain_events → handle
   → ImpactEngine → PhysiologyPayload(shock_impulse)
   → StateApplicator → Guard takes damage
   ↓
8. Guard is wounded. Avatar's refusal was overridden.
```

### Verdict: **CONFIRMED BYPASS**

Player attempts attack → WillpowerGate rejects → DM path still publishes PLAYER_ATTACKED → CombatSubscriber causes damage.

The Avatar's refusal has NO effect on whether the attack materializes in the world. The only thing WillpowerGate prevents is the PLAYER_ATTACKS event (Path A). The PLAYER_ATTACKED event (Path B) is published regardless.

---

## 8. Architectural Diagnosis

### Root Cause

The system has TWO independent publication paths that can turn the same Player intent into a world event:

| Path | Gate | Events |
|------|------|--------|
| A (WillpowerGate) | `compute_willpower` → WillState check | PLAYER_ATTACKS, PLAYER_INTERACTS |
| B (DM/INPUT_MERGE) | UE-GATE (readiness only) | PLAYER_ATTACKED, PLAYER_SPOKE, PLAYER_THREATENS, ... |

**Path B does NOT check WillpowerGate's result.** The intended bridge (`action_rejected`) was never connected to WillpowerGate's output. The existing signal (`will_conflict_data`) is written but not consumed for suppression.

### The "попытка ≠ событие" Principle

The codebase asserts this principle (ЗАВЕЩАНИЕ_АРХИТЕКТОРОВ.md:307):
> "Серия жива, пока жив гейт: попытка ≠ событие, на всех каналах."

The UE-GATE enforces it for **uncertainty** (non-RESOLVED → degrade to PLAYER_SPOKE). But it does NOT enforce it for **willpower authorization** (WillpowerGate block → still publish PLAYER_ATTACKED). The principle is half-implemented.

### The Fast-Path lexical override compounds the problem

The S122 FIX Fast-Path (phase_1_input.py:536-549) force-overrides `action_type = "attack"` based SOLELY on raw text containing combat verbs. This happens BEFORE any gate check. Even if WillpowerGate blocked the attack, the Fast-Path ensures the DM path classifies it as an attack → PLAYER_ATTACKED.

---

## 9. Recommendation for BodyArbiter Implementation

### The boundary must cover BOTH paths

Per Master's principle: "Если одно и то же действие может попасть в мир через два разных пути, оба пути должны соблюдать одну границу авторизации."

### Proposed single authorization boundary

**One gate, before ALL publication paths, checking WillpowerGate result:**

```
Player raw_input
    ↓
DM classification → shared_context.action_type
IntentDTO resolution → ctx.player_intent
    ↓
WillpowerGate → will_response
    ↓
BodyArbiter (NEW — single authorization boundary):
    reads will_response.state
    sets shared_context.action_authorized = (state in COMPLY/RELUCTANT/CONDITIONED)
    ↓
ALL publication paths check shared_context.action_authorized:
    Path A (publish_player_intent): already gated by WillpowerGate ✓
    Path B (_phase_1_input_merge / INPUT_MERGE): MUST check action_authorized
        if not action_authorized and _resolved_type in (PLAYER_ATTACKED, ...):
            suppress / degrade to PLAYER_SPOKE or WILL_CONFLICT
```

### Wire `will_conflict_data` → `action_authorized`

The signal already exists (`will_conflict_data`). The field that was supposed to enforce (`action_rejected`) is dead. The fix is to either:

**Option 1 (minimal):** Set `shared_context.action_rejected = True` in the WillpowerGate RESIST branch, and verify the WV gate at tick_orchestrator:1698 catches all PLAYER_ATTACKED publication paths.

**Option 2 (correct):** Replace the dead `action_rejected` field with `action_authorized` (positive authorization, default False), set by BodyArbiter, checked by ALL publication paths before publishing any event that turns intent into world action.

### Distinguish intent perception from action observation

Per Master's principle: "мир может знать о намерении, если оно действительно стало доступно его восприятию. Но знать о намерении — не значит наблюдать уже совершённое действие."

| Event type | Semantics | Should be publishable when WillpowerGate blocks? |
|-----------|-----------|--------------------------------------------------|
| PLAYER_ATTACKED | "Body committed attack" | ❌ NO — body refused |
| PLAYER_SPOKE | "Body uttered words" | ❌ NO — body refused to speak |
| WILL_CONFLICT | "Avatar resisted Player's intent" | ✅ YES — this IS the authorized signal |
| PLAYER_INTENT_PERCEIVED (new?) | "NPC perceived Player's intent" | ✅ YES — intent can be perceived without action |

The current system conflates intent with action. PLAYER_SPOKE is used both for "Player wanted to speak" and "Body spoke." PLAYER_ATTACKED is used both for "Player wanted to attack" and "Body attacked." BodyArbiter must separate these.

---

## 10. Summary Table

| Question | Answer |
|----------|--------|
| 1. Full call sequence RAW → publish_classified_player_event? | DM → shared_context.action_type → publish_classified_player_event → _phase_1_input_merge → INPUT_MERGE combat pipe (§1) |
| 2. Publication phase relative to WillpowerGate? | DM path publishes in _phase_1_input_merge + tick_orchestrator:1690-1718, AFTER WillpowerGate but WITHOUT checking its result (§2) |
| 3. Can DM publish PLAYER_ATTACKED if WillpowerGate blocked? | **YES** — `action_rejected` never set, WV gate is dead code (§3, §4) |
| 4. Can DM publish PLAYER_SPOKE if speech not authorized? | **YES** — no WillpowerGate check in DM path; PLAYER_SPOKE is always published (§4) |
| 5. Subscribers that cause consequences? | CombatSubscriber (damage), ReactionSubscriber, ObservationSubscriber, SocialSubscriber, ClaimEventSubscriber, PlayerSpeechActSubscriber, DialogueMemorySubscriber (§5) |
| 6. Existing mechanism to pass auth result to DM? | `will_conflict_data` exists but NOT read for suppression; `action_rejected` is dead (§6) |

---

## VERDICT: CONFIRMED BYPASS

**The DM publication path can publish PLAYER_ATTACKED and PLAYER_SPOKE regardless of WillpowerGate outcome.** CombatSubscriber will cause physical damage. ClaimEventSubscriber will cause belief revision. The Avatar's refusal is overridden.

**The bypass is not a bug in one function — it's a structural gap.** Two independent paths turn the same intent into world events, and only one path (WillpowerGate) is gated. The intended bridge (`action_rejected`) was never connected.

**BodyArbiter MUST enforce a single authorization boundary before ALL publication paths.** The existing `will_conflict_data` signal can be wired to the DM path, or the dead `action_rejected` field can be revived and properly set.

**Production: HOLD.** No code changes — this is a read-only audit.
