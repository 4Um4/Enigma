# E0 — Autonomous Social Impulse Analysis

**Document:** `docs/architecture/E0_AUTONOMOUS_SOCIAL_IMPULSE_ANALYSIS.md`
**Base:** Enigma-V.0.5.4.5.6-3 + E0-PILOT-10 fix (redirect double-count)
**Status:** READ-ONLY architectural research. No code changes.
**Owner:** Master Tai (technical) / Kami (game design)

---

## A. VERIFIED INVENTORY

### A.1 Motivation — NeedEngine + Drives

**VERIFIED** — `backend/app/services/economy/need_engine.py`:

```python
class DriveType(Enum):
    SOCIAL_URGE = "social_urge"  # Нужно общение

NeedType.SOCIAL: DriveType.SOCIAL_URGE,
NeedType.INFORMATION: DriveType.SOCIAL_URGE,  # слухи → общение
```

- **Input:** `EconomicProfile.base_needs` (NeedType.SOCIAL with urgency)
- **Output:** `List[NeedDrive]` with `DriveType.SOCIAL_URGE` when `need.is_urgent` (urgency > 0.6)
- **Called in:** LifeEngine Phase 0 (`life_engine.py`)
- **Production:** YES — NeedEngine.tick() runs every tick

### A.2 LifeEngine — Social Need → Activity

**VERIFIED** — `backend/app/services/npc/life_engine.py:90`:

```python
_NEED_TO_ACTIVITY = {
    "hunger": "eating",
    "shelter_urge": "sleeping",
    "social_urge": "socializing",   # ← social need → ACTIVITY, not INTENT
    "fatigue": "sleeping",
}
```

- Social urge maps to **activity "socializing"** → NPC moves to `NodeRole.BAR`
- **Does NOT produce Intent.TALK** — only moves NPC to a location
- **GAP:** No mechanism converts "standing at BAR" to "talk to someone at BAR"

### A.3 DecisionHub — Scoring + Proactive Bonus

**VERIFIED** — `decision_hub.py:1666-1697`:

```python
# _context_relevance return:
if event.event_type == EventType.WORLD_TICK:
    if intent in PROACTIVE_INTENTS:
        base += 0.4  # proactive bonus — APPLIES TO TALK
        # LifeDirection boost:
        _direction_intents = {
            "family_builder": ["seek_ally", "help", "call_for_help"],
            "knowledge_seeker": ["request_service", "seek_ally"],
            "ruler": ["spread_rumor", "call_for_help", "change_role"],
            # ... TALK IS NOT IN ANY DIRECTION
        }
        if intent in _expected_intents:
            base += _desire * 1.5 + _significance * 0.5
    else:
        base -= 0.3  # реактивные без стимула

return min(base, 2.0)
```

**VERIFIED** — `decision_hub.py:1545`:
```python
# _drive_relevance return:
return round(drive_weight * context_relevance, 4)
```

- +0.4 IS in context_relevance → IS in drive_score → IS in components["drive"] → IS in final score
- **E0-PILOT-8 verdict BONUS_NOT_RETURNED was WRONG** — +0.4 IS returned
- TALK gets +0.4 but **NOT LifeDirection boost** (not in any direction list)
- SEEK_ALLY gets +0.4 AND LifeDirection boost (if life_project is family_builder/knowledge_seeker)

### A.4 need_modifiers — The Bridge (EXISTS but SOURCE DORMANT)

**VERIFIED** — `npc_tick_pipeline.py:~L1000-1020`:

```python
_need_levels = RelationshipStateStore.get_need_levels(scene_state, npc_id)
_need_modifiers = {}

_intimacy = _need_levels.get("intimacy")
if _intimacy and _intimacy.current_intensity > 0.0:
    _need_modifiers["seek_ally"] = _int * 0.5
    _need_modifiers["talk"] = _int * 0.3      # ← TALK modifier EXISTS
    _need_modifiers["approach"] = _int * 0.2

_sexual = _need_levels.get("sexual")
if _sexual and _sexual.current_intensity > 0.0:
    _need_modifiers["approach"] = _sexual * 0.4
```

- **Bridge exists:** need_modifiers["talk"] → passed to `DecisionHub.compute(need_modifiers=...)` → `apply_modifiers(scores, need_modifiers)` → adds to TALK score
- **Source dormant:** `RelationshipStateStore.get_need_levels()` returns intimacy/sexual — behind RE-flags (RELATIONSHIP_EVENTS_ENABLED, RELATIONSHIP_DYNAMICS_ENABLED — OFF by default)
- **In production:** `_need_levels` empty → `_need_modifiers = None` → TALK gets NO modifier
- **No SOCIAL_URGE → need_modifiers path:** NeedEngine's SOCIAL_URGE drive does NOT feed into need_modifiers

### A.5 SocialTargetResolver

**VERIFIED** — `backend/app/services/npc/social_target_resolver.py`:

```python
class SocialTargetResolver:
    @staticmethod
    def resolve(state, spatial_query, all_npc_ids, relationship_store, campaign_id):
        # Filter: trust < SOCIAL_TRUST_HOSTILE_THRESHOLD (-30) → excluded
        # Prefer: trust > SOCIAL_TRUST_HIGH_THRESHOLD
        # Proximity: <= _SPEAK_RADIUS (5.0m)
        # LoS: spatial_query.visibility check
        # Returns: closest non-hostile NPC within 5m with LoS, or None
```

- **Input:** NPC state, spatial_query, all_npc_ids, relationship_store
- **Output:** target NPC ID or None
- **Called in:** `DecisionHub._resolve_intent_target` (~L1930)
- **Production:** YES
- **When None:** no valid social target → social intents may be filtered

### A.6 CognitionContextResolver

**VERIFIED** — `backend/app/services/npc/cognition_context.py`:

```python
class CognitionContextResolver:
    def resolve_block(self, npc_id, partner_id="player") -> str:
        # Reads STM claims + open_questions from DialogueSession
        # Reads EpistemicStore beliefs (confidence >= 0.25)
        # Returns formatted cognition block for LLM prompt
```

- **B5-F1.1 finding:** EpistemicStore has beliefs (conf=0.649) but cognition context returns empty
- **Likely cause:** `_epistemic_store` not wired at construction (None) OR different instance
- **Not directly relevant to TALK scoring** — affects LLM prompt, not DecisionHub scores

### A.7 Memory — narrative_cache

**VERIFIED** — `backend/app/services/memory/memory_manager.py`:

- `narrative_cache`: list of EventMemory sorted by importance
- `get_dialogue_session(campaign_id, npc_id, partner_id)`: returns STM for pair
- `load_narrative_from_sqlite()`: restores narrative_cache from SQLite
- **GAP:** No mechanism connects high-importance memory → TALK impulse
- **Limitation:** Most chronicle events have `target_id=""` → recall-by-target fails

### A.8 Commitment + Switching Cost

**VERIFIED** — `decision_hub.py:816-826`:

```python
# Commitment bonus to current intent:
scores[current] += commitment * COMMITMENT_BONUS_K  # K=0.10

# Switching cost to all others:
cost = SWITCHING_COST_BASE + age_cost + emotion_cost + identity_cost
# BASE=0.05, AGE_K=0.08, EMOTION_K=0.06, IDENTITY_K=0.04
for k in scores:
    if k != current:
        scores[k] -= cost
```

- **Intended mechanic:** intent inertia — NPC sticks with current intent
- **Effect on TALK:** once NPC picks SEEK_ALLY/CHANGE_ROLE, switching cost (~0.05-0.14) penalizes TALK
- **TALK drive advantage (~0.08) < switching cost (~0.14)** → TALK cannot overcome inertia

---

## B. CURRENT PRODUCTION FLOW

### How internal state reaches (or fails to reach) TALK

```
NeedEngine generates SOCIAL_URGE (urgency > 0.6)
  ↓
LifeEngine maps social_urge → "socializing" activity
  ↓
NPC moves to BAR node (NodeRole.BAR)
  ↓
??? ← GAP: no mechanism converts "at BAR" to "want to talk"
  ↓
DecisionHub.compute() called with WORLD_TICK event
  ↓
_score_all: TALK scored with:
  - drive: significance × context_relevance (includes +0.4 proactive)
  - emotion: ~0 (affective_load ≈ 0 in playerless)
  - relationship: 0 (trust/fear toward "player" = 0 in playerless)
  - risk: 0 (fear=0 in playerless)
  - need_modifiers: None (intimacy source dormant)
  - redirect: ~0 (affective_load < 0.01 → early return)
  ↓
Post-hoc: commitment bonus to current intent + switching cost to TALK
  ↓
TALK loses to SEEK_ALLY / CHANGE_ROLE
  ↓
No DialogueRequest → No LLM → No NPC_SPOKE
```

### Where the chain breaks

| Step | Status | Why |
|---|---|---|
| Social need generated | ✅ WORKS | NeedEngine produces SOCIAL_URGE |
| Social need → activity | ✅ WORKS | LifeEngine moves NPC to BAR |
| Activity → TALK impulse | ❌ BROKEN | No mechanism connects "socializing" to TALK intent |
| need_modifiers → TALK score | ⚠️ DORMANT | Bridge exists but source (intimacy) behind RE-flags |
| TALK in candidates | ⚠️ PARTIAL | Available by _is_intent_available but sometimes filtered (UNVERIFIED why) |
| TALK wins scoring | ❌ LOSES | Commitment/switching cost + no LifeDirection boost |
| TALK → DialogueExecutor | ❌ NOT REACHED | TALK never wins |

---

## C. MISSING LINKS

### C.1 SOCIAL_URGE → TALK intent (CRITICAL GAP)

**The #1 missing link.** NeedEngine generates SOCIAL_URGE, but it maps to ACTIVITY ("socializing"), not to INTENT (TALK). NPC moves to BAR but doesn't decide to talk.

**What exists:**
- NeedEngine: SOCIAL_URGE drive produced
- need_modifiers: bridge to DecisionHub scores (but only for intimacy/sexual, not SOCIAL_URGE)

**What's missing:**
- Connection: SOCIAL_URGE drive → need_modifiers["talk"]
- Currently: need_modifiers only from RelationshipStateStore (dormant RE needs)
- NeedEngine's SOCIAL_URGE output is consumed by LifeEngine (for movement) but NOT by npc_tick_pipeline (for need_modifiers)

### C.2 TALK not in LifeDirection (SCORING DISADVANTAGE)

TALK gets +0.4 proactive bonus but is NOT in any `_direction_intents` list. SEEK_ALLY IS in "family_builder" and "knowledge_seeker" → gets extra `_desire * 1.5 + _significance * 0.5`.

**Effect:** Even with equal drive_weight, SEEK_ALLY outscores TALK by ~0.3-0.4 from LifeDirection alone.

### C.3 need_modifiers source dormant (DORMANT BRIDGE)

The bridge `need_modifiers["talk"] = intimacy * 0.3` EXISTS in npc_tick_pipeline but the source (RelationshipStateStore need levels) is behind RE-flags (OFF in production).

### C.4 CognitionContextResolver wiring (B5-F1.1)

EpistemicStore has beliefs but CognitionContextResolver returns empty cognition block. This affects LLM prompt quality (NPC can't reference beliefs in speech) but does NOT affect DecisionHub scoring.

### C.5 Memory → social impulse (NO MECHANISM)

No mechanism connects significant memory ("I was attacked by X") to social impulse ("I want to tell Y about X"). narrative_cache stores memories but doesn't generate TALK impulses.

---

## D. CAUSAL EXAMPLES

### Example A: Social need → TALK

```
NeedEngine: SOCIAL_URGE urgency > 0.6
  → [GAP: need_modifiers["talk"] not generated from SOCIAL_URGE]
  → [If bridge activated: need_modifiers["talk"] += social_urge * weight]
  → DecisionHub: TALK score += social_urge * weight
  → [If score > switching cost: TALK wins]
  → SocialTargetResolver: finds closest non-hostile NPC within 5m
  → DialogueExecutor → LLM → NPC_SPOKE
```

**Status:** SOCIAL_URGE generated (✅), bridge dormant (⚠️), scoring disadvantaged (❌ no LifeDirection), commitment blocks (❌)

### Example B: Memory → share information → SPREAD_RUMOR

```
narrative_cache: high-importance EventMemory (e.g., "saw theft by X")
  → [GAP: no mechanism connects memory to SPREAD_RUMOR impulse]
  → [If bridge: scan narrative_cache for shareable memories → need_modifiers["spread_rumor"]]
  → DecisionHub: SPREAD_RUMOR score += memory_importance * weight
  → SPREAD_RUMOR is in LifeDirection "ruler" → gets boost
  → SocialTargetResolver: finds listener
  → DialogueExecutor → LLM → NPC_SPOKE
```

**Status:** Memory stored (✅), no impulse bridge (❌), SPREAD_RUMOR has LifeDirection boost (✅)

### Example C: Belief contradiction → TALK to verify

```
EpistemicStore: NPC believes "X is dangerous" (conf=0.7)
  → [GAP: no mechanism connects belief to TALK impulse]
  → [If bridge: CognitionContextResolver finds contradiction → need_modifiers["talk"]]
  → DecisionHub: TALK score += belief_confidence * weight
  → SocialTargetResolver: finds NPC who might know about X
  → DialogueExecutor → LLM → NPC_SPOKE
```

**Status:** Beliefs stored (✅), CognitionContextResolver wiring broken (❌ B5-F1.1), no impulse bridge (❌)

---

## E. ARCHITECTURE OPTIONS

### Option 1: Connect SOCIAL_URGE to need_modifiers (MINIMAL)

**What:** Use existing NeedEngine output to generate need_modifiers["talk"]

**How:**
- In `npc_tick_pipeline.py`, after NeedEngine produces drives:
- If `DriveType.SOCIAL_URGE` present with strength > threshold:
- Set `_need_modifiers["talk"] = social_urge_strength * weight`

**Components used:**
- NeedEngine (existing, production) — generates SOCIAL_URGE
- need_modifiers bridge (existing, wired to DecisionHub.apply_modifiers)
- DecisionHub scoring (existing) — TALK score += modifier
- SocialTargetResolver (existing) — finds conversation partner

**Files to change:**
- `npc_tick_pipeline.py` — add SOCIAL_URGE → need_modifiers connection (~5 lines)
- No new files, no new systems

**New data needed:** None — SOCIAL_URGE already generated by NeedEngine

**Risks:**
- SOCIAL_URGE is economic (NeedType.SOCIAL), not emotional — might not be the right source for "want to talk"
- Weight calibration needed (too high → TALK always wins; too low → no effect)
- Commitment/switching cost still blocks TALK after first intent selection

**Performance:** Negligible — one dict assignment per NPC per tick

**Compatibility:** Full — uses existing apply_modifiers path, no new SSOT

### Option 2: Add TALK to LifeDirection intents

**What:** Add "talk" to relevant `_direction_intents` entries

**How:**
- In `decision_hub.py:1675`, add "talk" to direction lists:
  - "family_builder": ["seek_ally", "help", "call_for_help", "talk"]
  - "knowledge_seeker": ["request_service", "seek_ally", "talk"]

**Components used:**
- _context_relevance LifeDirection boost (existing)
- _drive_relevance (existing)
- No new bridge needed

**Files to change:**
- `decision_hub.py` — add "talk" to 1-2 direction lists (~2 lines)

**Risks:**
- TALK becomes direction-specific (only family_builder/knowledge_seeker NPCs get boost)
- Might make TALK win too often for those directions
- Doesn't solve the SOCIAL_URGE → TALK gap (NPC still needs a reason to talk)

**Performance:** Negligible

**Compatibility:** Full — uses existing context_relevance mechanism

### Option 3: Memory-driven social impulse

**What:** Scan narrative_cache for shareable memories → generate need_modifiers

**How:**
- In `npc_tick_pipeline.py`, before DecisionHub:
- Scan `state.narrative_cache` for high-importance memories with target_id
- If found: `_need_modifiers["talk"] += memory.importance * weight`
- Optionally: set `pending_response_target` to memory's target_id

**Components used:**
- narrative_cache (existing, production)
- need_modifiers bridge (existing)
- SocialTargetResolver (existing — can target specific NPC from memory)

**Files to change:**
- `npc_tick_pipeline.py` — add memory scan → need_modifiers (~15 lines)

**Risks:**
- Most chronicle memories have `target_id=""` → recall-by-target fails
- Might generate impulses for irrelevant memories
- Needs filtering (not all memories are "shareable")

**Performance:** O(narrative_cache size) per NPC per tick — typically <20 items, negligible

**Compatibility:** Full — uses existing need_modifiers path

---

## F. RECOMMENDATION

**Option 1: Connect SOCIAL_URGE to need_modifiers**

**Justification:**
1. **Most minimal change** — ~5 lines in npc_tick_pipeline.py
2. **Uses existing infrastructure** — NeedEngine already generates SOCIAL_URGE, need_modifiers bridge already wired to DecisionHub
3. **No new systems** — respects "не создавать вторую систему потребностей"
4. **No new SSOT** — NeedEngine is the existing source for social needs
5. **Production-compatible** — apply_modifiers already processes need_modifiers
6. **Reversible** — if weight is wrong, adjust one constant

**Limitation:** SOCIAL_URGE alone may not be enough to overcome commitment/switching cost. May need to combine with Option 2 (add TALK to LifeDirection) for full effect.

**Recommended combination:** Option 1 (activate bridge) + Option 2 (add TALK to "family_builder" direction). Together they provide both the impulse source and the scoring boost.

**But:** This is a GAME DESIGN DECISION. The architect recommends the technical path; the game designer decides:
- Should social need drive TALK?
- What weight (0.1? 0.3? 0.5)?
- Should TALK be in LifeDirection?
- Which directions?

---

## G. IMPLEMENTATION PLAN

### Task 1: Activate SOCIAL_URGE → need_modifiers bridge

**File:** `npc_tick_pipeline.py`
**Change:** After NeedEngine produces drives, check for SOCIAL_URGE:
```python
# After _need_modifiers from RelationshipStateStore:
_social_drive = next((d for d in drives if d.drive_type == DriveType.SOCIAL_URGE), None)
if _social_drive and _social_drive.strength > 0.3:
    if _need_modifiers is None:
        _need_modifiers = {}
    _need_modifiers["talk"] = (
        _need_modifiers.get("talk", 0.0) + _social_drive.strength * 0.3
    )
```
**Size:** ~8 lines
**Risk:** Low — adds to existing need_modifiers dict
**Test:** Verify need_modifiers["talk"] > 0 when SOCIAL_URGE is urgent

### Task 2: Add TALK to LifeDirection (optional, game design decision)

**File:** `decision_hub.py:1675`
**Change:** Add "talk" to relevant direction lists:
```python
"family_builder": ["seek_ally", "help", "call_for_help", "talk"],
"knowledge_seeker": ["request_service", "seek_ally", "talk"],
```
**Size:** ~2 lines
**Risk:** Medium — TALK gets LifeDirection boost, might win too often
**Test:** Verify TALK context_relevance increases for family_builder NPCs

### Task 3: Verify with E0-PILOT-5 re-run

**Action:** Re-run 10-tick Lusya↔Orm experiment with activated bridge
**Expected:** TALK score increases by social_urge × 0.3; if combined with Task 2, TALK may win on some ticks
**Success criterion:** TALK won ≥ 1/10 ticks → DialogueRequest created → LLM called → NPC_SPOKE

### Task 4: Calibration (game designer)

**Action:** Adjust weight (0.3 → calibrated value) based on gameplay
**Owner:** Kami (game design)
**Input:** E0-PILOT-5 re-run results + playtesting

---

## H. UNVERIFIED

| Question | Why | What's needed |
|---|---|---|
| Why TALK absent from candidates on tick 1-3 | Filtering not fully traced — _is_intent_available returns True for TALK | Read _get_possible_intents or compute() filtering section |
| _get_commitment runtime value | Not captured | Runtime capture of commitment variable |
| Exact switching_cost runtime values | Not captured | Runtime capture of cost variable |
| SOCIAL_URGE actual urgency in playerless | NeedEngine.tick produces drives but not captured | Runtime capture of drives list |
| CognitionContextResolver wiring (B5-F1.1) | _epistemic_store might be None at construction | Read game_loop_builder or _register_epistemic_core |
| LifeDirection state.runtime value | life_project_state and life_project not captured | Runtime capture |
| How "socializing" activity satisfies social need | _ACTIVITY_TO_NEED might map "socializing" → NeedType.SOCIAL | Read _ACTIVITY_TO_NEED in life_engine.py |

---

## ANSWER TO THE MAIN QUESTION

**How can NPC ENIGMA autonomously form desire to talk with another NPC?**

**The mechanism EXISTS but is DISCONNECTED:**

1. NeedEngine generates SOCIAL_URGE — NPC feels social need (✅)
2. LifeEngine moves NPC to BAR — NPC goes where socializing happens (✅)
3. need_modifiers["talk"] bridge — TALK score can be boosted by need (✅ but source dormant)
4. DecisionHub scores TALK — +0.4 proactive bonus (✅ but no LifeDirection boost)
5. SocialTargetResolver finds partner — non-hostile NPC within 5m (✅)
6. DialogueExecutor → LLM → NPC_SPOKE — production path (✅)

**The disconnection is at step 2→3:** SOCIAL_URGE drives LifeEngine movement but does NOT feed into need_modifiers. The bridge (need_modifiers["talk"]) only reads from RelationshipStateStore (intimacy/sexual — dormant).

**To connect:** Add ~8 lines in `npc_tick_pipeline.py` to map SOCIAL_URGE drive → need_modifiers["talk"]. This uses exclusively existing infrastructure — no new systems, no new SSOT, no new queues.

**But this is a game design decision** — the architect provides the technical path; the game designer decides whether social need should drive TALK, and at what weight.

**STOP. Analysis complete. No code changes. No additional documents.**
