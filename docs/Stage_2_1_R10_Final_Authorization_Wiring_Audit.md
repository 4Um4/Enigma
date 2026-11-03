# Stage 2.1-R10 — Final Authorization Wiring Audit

**Mode:** READ-ONLY
**Date:** 2026-11-03
**Purpose:** Close five factual gaps from R9 before implementation.

---

## §1. Publication Callers

### Finding: Call sites of `publish_player_speech` and `publish_classified_player_event` NOT FOUND

Despite searching all available pasted content (25+ files from R-rounds R0 through R9), the actual **call sites** of these two functions were never captured. Previous searches found:
- Definitions: `phase_1_input.py:471` (`publish_player_speech`), `phase_1_input.py:510` (`publish_classified_player_event`)
- Test imports of `resolve_player_intent` from `phase_1_input`
- `turn_pipeline.py:32` imports `resolve_player_intent`, calls it at `turn_pipeline.py:405`

**But no search result contains a line calling `publish_player_speech(...)` or `publish_classified_player_event(...)` outside of the definition itself.**

### What we know about the call path

From ЗАВЕЩАНИЕ_АРХИТЕКТОРОВ.md:303:
> "B1-проекция: шорт-лист из 5 файлов — agents/dm_agent.py, models/schemas.py, services/game_loop/dm_phase.py, game_loop.py, phase_1_input.py."

The predecessor (S358) identified these 5 files as the Player intent projection surface. The publish functions are defined in `phase_1_input.py` and likely called from `turn_pipeline.py` or `game_loop.py` — but the exact call site was not captured.

### Evidence origin: REPORTED BY ARCHITECT (inference from R7/R9 code traces)
The functions exist, take `shared_context` and `raw_input`, and their effects (PLAYER_ATTACKED/PLAYER_SPOKE on the bus) are confirmed by subscriber registrations. The callers must exist but were not captured in any pasted search output.

### Gap status: OPEN — successor must grep for callers in the actual codebase.

---

## §2. Intent Identity

### Finding: `intent_id = uuid.uuid4()` — random, NOT replay-deterministic

```python
# Found in Pasted Content_1793535698026.txt:565 (line 57 of the file containing this field)
intent_id: str = field(default_factory=lambda: str(uuid.uuid4()))  # P1-09: Уникальный ID для трекинга
```

### Event identity is SEPARATE and deterministic

```python
# backend/app/services/events/event_identity.py:13
def next_event_identity(scene_state, event_type, source) -> Tuple[int, int]:
    """Выделяет (event_tick, ordinal) для нового события.
    Единственная точка инкремента счётчиков identity (Single Writer)."""
    # Uses scene_state["event_ordinals"] — persistent monotonic counter
```

- `event_id` = `(event_type, source, tick, ordinal)` — deterministic, replay-safe
- `intent_id` = `uuid.uuid4()` — random, NOT replay-safe

### Replay implication

| ID type | Generation | Replay-safe? | Risk |
|---------|-----------|-------------|------|
| `intent_id` | `uuid.uuid4()` (random) | ❌ NO | Two replays of the same tick generate different intent_ids. If intent_id is used as a key in `scene_state["intent_lifecycle"]`, replay cannot match the original. |
| `event_id` | `next_event_identity(scene_state, ...)` (ordinal counter) | ✅ YES | scene_state["event_ordinals"] is persisted and restored. |

### Recommendation

`scene_state["intent_lifecycle"]` must NOT use `uuid.uuid4()` for keys. Either:
- Use a deterministic `next_intent_identity(scene_state, owner, action)` — mirror of `next_event_identity` with `scene_state["intent_ordinals"]`
- Or use a composite key: `(owner, action, tick, ordinal)`

### Evidence origin: VERIFIED BY SOURCE (uuid4 line found in pasted code), VERIFIED BY SOURCE (next_event_identity in event_identity.py:13)

---

## §3. Lifecycle Persistence

### scene_state serialization mechanism

| Component | File | Role |
|-----------|------|------|
| `SceneStateManager` | scene_state/ | `commit_tick_result()` → atomic commit |
| `SQLitePersistenceAdapter` | state/sqlite_persistence_adapter.py | `atomic_commit()` — INSERT OR REPLACE |
| `scene_factory.py` | scene_state/scene_factory.py:252 | Initializes scene_state defaults on load (e.g., `"event_ordinals": {}`) |
| Phase 10 | tick_orchestrator | `SceneStateManager.commit_tick_result()` → SQLitePersistenceAdapter |

### Minimal `intent_lifecycle` format

Based on the existing `event_ordinals` and `commitment_ordinals` patterns:

```python
scene_state["intent_lifecycle"] = {
    "<intent_id>": {
        "intent_id": "<intent_id>",        # stable, deterministic
        "owner": "player" | "<character_id>",
        "body_id": "<character_id>",
        "action": "attack" | "dialogue" | ...,
        "lifecycle_state": "ACTIVE" | "VOIDED" | "SATISFIED" | ...,
        "arbitration_result": "AUTHORIZED" | "REJECTED" | "PENDING",
        "created_tick": 42,
        "transitioned_tick": 42,
        # NOT stored: WillResponseDTO (tick-scoped, on ctx)
    },
    ...
}
```

### Key constraints
- Must survive `atomic_commit` → load round-trip
- Must be replay-deterministic (no UUID4 keys)
- Writer: BodyArbiter ONLY (for state transitions)
- Reader: publication paths (check `arbitration_result` before publishing)
- Default for legacy saves: if key absent, treat as `AUTHORIZED` (fail-open for backward compat)

### Evidence origin: VERIFIED BY SOURCE (atomic_commit in phase schedule, scene_factory defaults), DESIGN DECISION (minimal format proposed)

---

## §4. STM Perception Filtering

### Finding: `working_memory_tick.py` — perception filtering UNCONFIRMED

The file's purpose is described as:
> "записывает в STM через memory_manager.add_dialogue_turn" (working_memory_tick.py:40)

The call at line 130:
```python
memory_manager.add_dialogue_turn(...)
```

**The function body around line 130 was NOT captured in any pasted content.** I cannot confirm whether it:
- Filters by perception radius (`action_perception_radius`)
- Checks NPC alive/conscious status
- Writes to ALL NPCs regardless of distance
- Only writes to NPCs who subscribed to PLAYER_SPOKE

### What we know

- `action_perception_radius` exists and returns distance per action type (constants.py)
- `ObservationSubscriber` (`observation_subscriber.py`) filters by perception radius for world events
- `ClaimEventSubscriber` (`claim_event_subscriber.py:89-90`) processes PLAYER_SPOKE → ClaimEvent "для слышащих" (for hearing NPCs) — implies perception filtering exists somewhere
- `perception_filter.py:219-277` has PLAYER_ATTACKED and PLAYER_SPOKE entries with distance strings

### Inference

The perception filtering likely happens in the subscriber layer (ClaimEventSubscriber, ObservationSubscriber) — NOT in working_memory_tick itself. If working_memory_tick writes STM for ALL NPCs, it would be a separate bug (NPCs remembering unperceived speech).

### Evidence origin: PARTIALLY VERIFIED (subscribers have perception filtering, working_memory_tick body NOT captured)
### Gap status: OPEN — successor must read working_memory_tick.py:120-140 to confirm.

---

## §5. Psychological Effects — Writers and Consumers

### All writers are in WillpowerGate (Phase 1)

| Payload | Writer | File:Line | Phase | Condition |
|---------|--------|-----------|-------|-----------|
| `WillConflictPayload` | WillpowerGate (COMPLY+damage) | phases/input.py:176 | Phase 1 | `will_response.state != COMPLY or identity_damage > 0` |
| `WillConflictPayload` | WillpowerGate (RESIST) | phases/input.py:220 | Phase 1 | `else` (RESIST/DELAY/etc.) |
| `EmotionPayload` (fear) | WillpowerGate | phases/input.py:265-275 | Phase 1 | `will_response.fear_delta > 0` |
| `EmotionPayload` (stress) | WillpowerGate | phases/input.py:278-291 | Phase 1 | `will_response.stress_delta > 0` |
| `IdentityPayload` | WillpowerGate | phases/input.py:156-166 | Phase 1 | `will_response.identity_damage > 0` (COMPLY path) |
| `affective conditioning` | WillpowerGate | phases/input.py:301 | Phase 1 | `identity_damage > 0 or resonance.trigger_strength > 0.1` |

### Consumers

| Payload | Consumer | File:Line | What it does |
|---------|----------|-----------|-------------|
| `WillConflictPayload` | StateApplicator | state_applicator.py:275-279 | Intercepted before v1 collapse — preserved as structural signal |
| `EmotionPayload` | StateApplicator | state_applicator.py | Applied to NPC stress/emotion state |
| `IdentityPayload` | StateApplicator | state_applicator.py | Applied to identity integrity |
| `affective_imprints` | player_dict | phases/input.py:304 | `player_dict["affective_imprints"] = [asdict(imp) for imp in updated_imprints]` — directly mutates player_dict |

### Double-application risk

**Currently: NO double-application.** All psych effects are written exactly once, in Phase 1, by WillpowerGate. There is no second writer.

**After BodyArbiter addition: RISK.** If BodyArbiter also applies psych effects (e.g., stress from the arbitration decision itself), AND the existing WillpowerGate code still applies effects, double-application occurs.

### Master's concern confirmed

Master identified two distinct causal impacts:
1. Internal conflict stress (from resistance itself)
2. Consequence stress (from the actual action being performed)

Currently these are conflated — both applied in Phase 1 by WillpowerGate. The separation Master requires means:
- Phase 1 (WillpowerGate): compute evaluation, apply ONLY internal conflict effects (stress from resistance)
- Phase 1 (BodyArbiter, after WillpowerGate): make arbitration decision, set lifecycle state
- After publication: apply consequence effects (stress from actual action — if authorized)

### Evidence origin: VERIFIED BY SOURCE (all writers found in phases/input.py)

---

## §6. Full Player Action Path Trace

### All paths from input text to EventBus

```
Player raw_input (text)
    │
    ├─→ [PATH DM] dm_phase.py
    │   ├─ L72: get_stm_prompt_block() — READS STM for LLM context
    │   ├─ L185: add_dialogue_turn() — WRITES STM (BYPASS: before authorization)
    │   ├─ L224: action_type=shared_context.action_type — classifies
    │   └─ L263: event_type=EventType(...) — prepares event
    │
    ├─→ [PATH RESOLVE] turn_pipeline.py:405
    │   └─ resolve_player_intent() → IntentDTO → ctx.player_intent
    │
    ├─→ [PATH WILLPOWERGATE] phases/input.py:58
    │   ├─ resolve_intent_pressure(intent) → pressure
    │   ├─ scan_affective_resonance(intent, ...) → resonance
    │   ├─ distort_pressure(pressure, resonance, psyche) → distorted
    │   ├─ compute_willpower(distorted, psyche) → will_response
    │   │
    │   ├─ if COMPLY/RELUCTANT/CONDITIONED:
    │   │   ├─ publish_player_intent(ctx, intent) ──→ PLAYER_ATTACKS / PLAYER_INTERACTS [GATED ✓]
    │   │   ├─ apply IdentityPayload (if damage)
    │   │   ├─ apply WillConflictPayload (if not COMPLY or damage)
    │   │   └─ write will_conflict_data to shared_context
    │   │
    │   └─ else (RESIST/DELAY/etc.):
    │       ├─ NO publish_player_intent [BLOCKED ✓]
    │       ├─ apply WillConflictPayload
    │       ├─ apply EmotionPayload (fear, stress)
    │       ├─ write will_conflict_data to shared_context
    │       ├─ publish WILL_CONFLICT event
    │       └─ apply affective conditioning
    │
    ├─→ [PATH CLASSIFIED] phase_1_input.py:510 — publish_classified_player_event
    │   ├─ Fast-Path lexical override (if "удар/бей/атак..." → force "attack")
    │   ├─ _evt_map: action_type → EventType
    │   ├─ G3C: if PLAYER_ATTACKED → defer to INPUT_MERGE
    │   └─ else: publish directly [NOT GATED ✗]
    │
    ├─→ [PATH SPEECH] phase_1_input.py:471 — publish_player_speech
    │   └─ publish PLAYER_SPOKE [NOT GATED ✗]
    │
    ├─→ [PATH INPUT_MERGE] tick_orchestrator.py:1690-1718
    │   ├─ if action_rejected (DEAD — never True): suppress
    │   └─ else: publish PLAYER_ATTACKED [NOT GATED ✗ — dead gate]
    │
    └─→ [EVENTBUS] get_event_bus().publish(EventDTO)
        │
        ├─→ CombatSubscriber (PLAYER_ATTACKS, PLAYER_ATTACKED) → ImpactEngine → damage
        ├─→ ReactionSubscriber (PLAYER_ATTACKS, PLAYER_ATTACKED, PLAYER_THREATENS) → NPC stress
        ├─→ ClaimEventSubscriber (PLAYER_SPOKE) → ClaimEvent → belief revision
        ├─→ PlayerSpeechActSubscriber (PLAYER_SPOKE) → speech act processing
        ├─→ DialogueMemorySubscriber (PLAYER_SPOKE) → EventMemory
        ├─→ ObservationSubscriber (PLAYER_ATTACKED) → NPC perception
        ├─→ SocialSubscriber (multiple) → social deltas
        └─→ RulesSubscriber (multiple) → rules processing
```

### Summary of gates

| Path | Gate | Status |
|------|------|--------|
| publish_player_intent | WillpowerGate (COMPLY/RELUCTANT/CONDITIONED) | ✅ Working |
| publish_player_speech | NONE | ❌ Bypass |
| publish_classified_player_event | NONE (Fast-Path overrides even DM) | ❌ Bypass |
| INPUT_MERGE combat pipe | action_rejected (DEAD) | ❌ Dead gate |
| dm_phase add_dialogue_turn | NONE | ❌ STM bypass |

### Evidence origin: VERIFIED BY SOURCE (code traces from R7/R9/R10)

---

## §7. Summary

| Gap | Status | Key finding |
|-----|--------|-------------|
| 1. Publication callers | OPEN | Call sites not captured in pasted content. Successor must grep actual codebase. |
| 2. Intent identity | VERIFIED | `uuid.uuid4()` — random, NOT replay-safe. Must use deterministic ordinal counter like `next_event_identity`. |
| 3. Lifecycle persistence | VERIFIED | atomic_commit via SQLitePersistenceAdapter. Minimal format: dict keyed by deterministic intent_id, persisted in scene_state. |
| 4. STM perception | PARTIALLY OPEN | working_memory_tick body not captured. Subscriber layer has perception filtering. working_memory_tick may or may not filter. |
| 5. Psych effects | VERIFIED | All writers in WillpowerGate (Phase 1). No double-application currently. Risk exists if BodyArbiter also applies effects. |

**Production: HOLD.** R10 complete. Ready for R11 handover document.
