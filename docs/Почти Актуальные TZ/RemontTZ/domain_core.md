# ENIGMA — Core Tick Pipeline Deep Analysis Report

**Scope**: Core tick pipeline (TickOrchestrator → NpcTickPipeline → StateApplicator → TickMutation)
**Project root**: `/home/z/my-project/analysis/Enigma-V.0.5.3.6.7_-_-_-/`
**Codebase version**: V.0.5.3.6.7

---

## Executive Summary

The core tick pipeline has **18 distinct bugs**, of which **4 are Critical** (silently breaking the simulation every tick) and **6 are High** (each responsible for one of the known log symptoms). The codebase shows clear evidence of an in-progress refactoring (S98→S100, ADR-O-208/305/310) where many code paths were partially migrated but the **bridges between old and new contracts were never finished** — most importantly the bridge between GameLoop's `_ctx.hub_event` and TickOrchestrator's `state.hub_event` (BUG-CORE-003) which makes player actions invisible to DecisionHub.

The contract `CAUSAL_CONTRACT` is violated in 4 places:
1. Dead NPCs not excluded before Phase 1 (only in Phase 5)
2. `l1_drift_events` returned by NpcTickPipeline is always empty (contract broken)
3. KernelRNG not used in `ResolutionEngine` and `TaskScheduler`
4. `try/except: pass` swallows critical L1 identity projection failure

---

## BUG CATALOG

### BUG-CORE-001 — Massive dead unreachable code in `execute()` after early `return`

| Field | Value |
|---|---|
| **File:line** | `backend/app/services/tick_orchestrator.py:460-594` |
| **Severity** | Critical |
| **Symptom** | ADR-O-201 (Dual Rail Shadow Observer), AdaptiveTickLoader, equivalence_validator, event_compiler, drift summary — **all never execute**. The CFRM `_deobjectify_event` bridge is never attached. Final `TickResultDTO` build at lines 585-594 never runs. |
| **Root cause** | Line 411-458: the new multi-location loop ends with `return _final_result` on line 458. The legacy single-location body that was supposed to be replaced (lines 460-594) was left in place AFTER the return. About 135 lines of dead code. |
| **Suggested fix** | Delete lines 460-594 entirely. If any logic from the dead block is still needed (e.g. the CFRM `_deobjectify_event` attach or AdaptiveTickLoader setup), re-implement it inside the active loop body (lines 411-458) before `_run_core_phases(ctx, tick_fully=_tick_fully)` is called. |

---

### BUG-CORE-002 — Silent failure in `_compute_effective_drives` — L1 Identity always `None`

| Field | Value |
|---|---|
| **File:line** | `backend/app/services/tick_orchestrator.py:1260-1265` |
| **Severity** | Critical |
| **Symptom** | L1 identity traits NEVER reach `DriveResolver.resolve_drives()`. All NPC drives projections are computed from L0 only. Crystallized beliefs and personality drift are silently discarded. |
| **Root cause** | Inside `_compute_effective_drives(self, npc_list, tick_number)`, the code does: <br>`_traits = self.memory_manager.get_identity_traits(ctx.campaign_id, _nid)`<br>But: (a) `self.memory_manager` doesn't exist — only `self._memory_manager` (initialized in `__init__` at line 73); (b) `ctx` is NOT a parameter of this method. Both `AttributeError` and `NameError` are silently swallowed by `except Exception: pass`. |
| **Suggested fix** | (1) Add `campaign_id: str` parameter to `_compute_effective_drives`. (2) Use `self._get_memory_manager()` instead of `self.memory_manager`. (3) Remove the `except Exception: pass` — replace with explicit logging that surfaces the failure. Concretely:<br>```python
def _compute_effective_drives(self, npc_list, tick_number, campaign_id):
    ...
    try:
        _mm = self._get_memory_manager()
        _traits = _mm.get_identity_traits(campaign_id, _nid)
        if _traits:
            _identity_l1 = NPCIdentityL1(npc_id=_nid, active_traits=_traits)
    except Exception as e:
        logger.error(f"[L3_PROJECTION] identity traits load failed for {_nid}: {e}")``` |

---

### BUG-CORE-003 — Broken hub_event bridge — player actions invisible to NPC pipeline

| Field | Value |
|---|---|
| **File:line** | `backend/app/services/pipeline_runner.py:39-43` + `backend/app/services/game_loop/npc_orchestration.py:149-160` |
| **Severity** | Critical |
| **Symptom** | Known log: `[DM]: Ничего не произошло.` — player attacks, dialogues, threats all silently dropped. NPCs respond with `Intent.idle score=0.000 event=unknown` (confirmed in `sleep_test2.log`). |
| **Root cause** | `build_tick_state` (pipeline_runner.py:39-43) extracts `dm_ctx` from intervention payload by looking for the literal key `"dm_ctx"`:<br>```python
for interv in ctx.interventions:
    if interv.source == "player" and "dm_ctx" in interv.payload:
        _dm_ctx = interv.payload["dm_ctx"]
        break```<br>But `npc_orchestration.py:149-160` builds the InterventionEvent with keys `text`, `player_name`, `semantic_action`, `target_id`, `target_reference`, `tick` — **no `dm_ctx` key**. So `_dm_ctx` is always `None`, then `state.hub_event=None`, `state.player_target_id=None`, `state.action_type="idle"`. Inside `NpcTickPipeline.run` (npc_tick_pipeline.py:136), `_is_player_turn = state.hub_event is not None` is `False`, so the pipeline runs in idle-mode processing `state.all_npcs_raw` instead of `state.nearby_npcs`. The DM-classified `hub_event` that GameLoop built in `dm_phase.py:282` and injected into `_ctx.hub_event` is NEVER carried through to TickState. |
| **Suggested fix** | Two options:<br>**Option A (minimal):** In `pipeline_runner.build_tick_state`, also accept `ctx.hub_event` directly. Add at the start:<br>```python
_hub_event = getattr(ctx, "hub_event", None)
_player_target_id = getattr(ctx, "player_target_id", None)
_action_type = getattr(ctx, "action_type", "idle") or "idle"
_raw_input = getattr(ctx, "raw_input", "") or ""
```<br>and pass these into `create_tick_state` instead of always relying on `_dm_ctx`.<br>**Option B (architectural):** Have `npc_orchestration.py` actually wrap the resolution in a `dm_ctx` object and put it in `intervention.payload["dm_ctx"]`. This restores the original design. Option B is preferred per the existing `dm_ctx` legacy bridge at orchestrator.py:374-381. |

---

### BUG-CORE-004 — LifeEngine `__init__` misplaced assignments: spatial_service/persistence/claim_bus reset every tick

| Field | Value |
|---|---|
| **File:line** | `backend/app/services/npc/life_engine.py:246-258` |
| **Severity** | Critical |
| **Symptom** | SpatialService, PersistencePort, and DRFBus are silently reset to `None` after every Phase 5 (Decision). Subsequent ticks see empty `_spatial_service` until Phase 0 of next tick re-injects it. ADR-128 SQLite read-back is silently disabled after first tick. |
| **Root cause** | Look at the indentation: lines 250-258 (`self._spatial_service = None`, `self._persistence = None`, `self._claim_bus = None`) are placed INSIDE the `update_idle_pressure` method body (lines 246-248), NOT inside `__init__`. They should be in `__init__`. So every call to `update_idle_pressure(updates)` (which happens at end of Phase 5 via `tick_orchestrator.py:1391`) wipes these instance attributes. |
| **Suggested fix** | Move lines 250-258 into `__init__` (right after `self._movement_engine = MovementEngine()` at line 240). The corrected `__init__` should end with:<br>```python
self._movement_engine = MovementEngine()
self._spatial_service: Optional[Any] = None
self._persistence: Optional[Any] = None
self._claim_bus: Optional["DRFBus"] = None
```<br>And `update_idle_pressure` should ONLY contain `self._idle_pressure.update(updates)`. |

---

### BUG-CORE-005 — Non-sleeping NPCs never emit movement_intents

| Field | Value |
|---|---|
| **File:line** | `backend/app/services/npc/npc_tick_pipeline.py:545-606` |
| **Severity** | Critical |
| **Symptom** | NPCs with `Intent.APPROACH`/`FLEE`/`SEEK_ALLY`/etc. (anything except attack) and not currently sleeping — their movement intents are silently dropped. `movement_intents` list is always empty for normal reactive NPC behaviour. Confirmed by sleep test logs: NPCs at `loc=city_gate` when expected in tent/bed. |
| **Root cause** | The if/elif structure only handles two branches:<br>```python
if _intent_value in _MOVE_INTENTS and _current_routine.get("current") == "sleeping":
    # SLEEP_GUARD — blocks movement for sleeping NPCs
    ...
    if _movement: movement_intents.append(_movement)
elif _intent_value == "attack":
    # ATTACK branch — builds CommunicationIntent
    ...
# NO ELSE: non-sleeping, non-attack movement intents (approach, flee, etc.) lost
```<br>Furthermore, inside the sleep branch (line 550), `_intent_value = "idle"` is set BEFORE calling `_resolve_reactive_movement(intent=_intent_value, ...)` (line 556) — so the resolver receives "idle" and returns None. |
| **Suggested fix** | Restructure the dispatch:<br>```python
if _intent_value == "attack":
    # build CommunicationIntent for attack
    ...
else:
    # ALL movement-capable intents (approach, flee, seek_ally, ...) INCLUDING idle sleeping
    if _current_routine.get("current") == "sleeping" and _intent_value in _MOVE_INTENTS:
        logger.info(f"[SLEEP_GUARD] npc={npc_id} blocking reactive movement={_intent_value}")
        _intent_value = "idle"
        decision = dataclasses.replace(decision, decision=dataclasses.replace(decision.decision, intent=Intent.IDLE))

    if _intent_value in _MOVE_INTENTS:
        _movement = _resolve_reactive_movement(
            npc_id=npc_id, intent=_intent_value, intent_target=decision.intent_target or "player",
            scene_state=dict(state.scene_state), location_id=state.scene_state.get("location_id", ""),
            spatial_service=state.spatial_service, spatial_query=state.spatial_query, drf_ctx=_npc_drf_ctx,
        )
        if not _movement and state.spatial_service:
            _target_node = _resolve_proactive_target(
                intent_value=_intent_value, npc_id=npc_id, intent_target=decision.intent_target,
                scene_state=dict(state.scene_state), spatial_service=state.spatial_service,
                location_id=state.scene_state.get("location_id", ""),
            )
            if _target_node:
                from app.domain.movement import MacroMovementGoal
                _movement = MacroMovementGoal(
                    actor_id=npc_id, target_node_id=_target_node,
                    reason=f"proactive_{_intent_value}", body_capabilities=state_l2.body_capabilities,
                )
        if _movement:
            movement_intents.append(_movement)
``` |

---

### BUG-CORE-006 — GameLoop `_project_perception` overwrites Phase 9 perception, losing `observed_facts`

| Field | Value |
|---|---|
| **File:line** | `backend/app/services/perception/perception_projector.py:34-56` + `backend/app/services/game_loop/__init__.py:956-963, 1054-1060, 1236-1242` |
| **Severity** | High |
| **Symptom** | Known log: `Empty PlayerPerceptionDTO (manifestations={}, observed_facts=[], active_perceptions=[])`. Phase 9 already builds a correct `PlayerPerceptionDTO` with `observed_facts=_facts_for_dm` (`integration.py:567`), but GameLoop's `_project_perception` is called AFTER and OVERWRITES the world_snapshot's player_perception with a fresh projection that does NOT pass `observed_facts`. |
| **Root cause** | `PerceptionProjector.project(scene_state, all_npcs_raw, tick)` calls `self._project_svc.project(_traces, scene_state, tick=tick)` — missing the `observed_facts=` argument that `PhenomenologyProjectionService.project()` accepts as an optional 4th parameter. The GameLoop then `dataclasses.replace(result.world_snapshot, player_perception=_perception)` overwriting the Phase 9 version. |
| **Suggested fix** | Three changes:<br>(1) In `PerceptionProjector.project()`, accept and forward `observed_facts`:<br>```python
def project(self, scene_state, all_npcs_raw, tick, observed_facts=None):
    ...
    return self._project_svc.project(_traces, scene_state, tick=tick, observed_facts=observed_facts)
```<br>(2) In GameLoop `idle_tick` (line 956-963): **remove** the override entirely — Phase 9 already built the correct perception. The `result.world_snapshot.player_perception` is the authoritative version.<br>(3) In `run_turn` (line 1236-1242) where `_builder.build(_scene, ..., player_perception=_pp, ...)` is called: pass `observed_facts=getattr(state, "observed_facts", [])` through to the builder, or skip the rebuild entirely and reuse `_tick_result.world_snapshot`. |

---

### BUG-CORE-007 — Phase 8 social_input_projector crashes on `SimpleNamespace` shared_context

| Field | Value |
|---|---|
| **File:line** | `backend/app/services/phases/reduction.py:178-181` + `backend/app/services/events/social_input_projector.py:93, 111` |
| **Severity** | High |
| **Symptom** | Log: `[PHASE8_CRASH] handler=social_input error=AttributeError: 'types.SimpleNamespace' object has no attribute 'scene_state'. Events lost this tick.` Social listener detection broken every tick. |
| **Root cause** | `reduction.py` line 178-181 creates a fallback `SimpleNamespace()` for `ctx.shared_context` when it's None, but does NOT set a `scene_state` attribute on it. Then `social_input_projector.py` line 93 and 111 unconditionally access `ctx.shared_context.scene_state or {}` which raises `AttributeError` because `SimpleNamespace` has no `scene_state`. The error is caught at `reduction.py:214-222` and silently logged. |
| **Suggested fix** | Two complementary fixes:<br>(1) In `reduction.py:179-181`, also set `scene_state`:<br>```python
ctx.shared_context = SimpleNamespace()
ctx.shared_context.scene_state = ctx.scene_state  # carry the source of truth
```<br>(2) In `social_input_projector.py:93, 111`, use defensive `getattr`:<br>```python
scene_state=getattr(ctx.shared_context, "scene_state", None) or ctx.tick_ctx.scene_state or {},
``` |

---

### BUG-CORE-008 — GameLoop writes to singular `_tick_scene`, SceneStateManager uses plural `_tick_scenes`

| Field | Value |
|---|---|
| **File:line** | `backend/app/services/game_loop/__init__.py:1642` |
| **Severity** | High |
| **Symptom** | Log: `AttributeError: 'SceneStateManager' object has no attribute '_tick_scene'. Did you mean: '_tick_scenes'?`. When `lock_for_tick` returns `None` (scene not pre-locked), GameLoop tries to manually initialize the scene by setting `self.scene_manager._tick_scene = scene_state` — but SceneStateManager only has `_tick_scenes: Dict[str, dict]` (plural). The assignment creates an isolated attribute that nothing else reads. |
| **Root cause** | Refactoring ADR-SCENE-LOCK changed SceneStateManager to use a dict-keyed-by-location (`_tick_scenes`), but `game_loop/__init__.py:1642` still uses the legacy singular `_tick_scene`. The follow-up lines 1643-1644 also set `_tick_locked` and `_tick_campaign_id` but never insert into `_tick_scenes`. |
| **Suggested fix** | Replace lines 1642-1644 with proper lock acquisition: <br>```python
scene_state = init_scene_state(self, campaign_id, _loc_id, shared_context, campaign_state, player_position=player_position)
# ADR-SCENE-LOCK: insert into _tick_scenes dict, not _tick_scene singular
self.scene_manager._tick_scenes[_loc_id] = scene_state
self.scene_manager._tick_locked = True
self.scene_manager._tick_campaign_id = campaign_id
```<br>Better: call `self.scene_manager.lock_for_tick(campaign_id, _loc_id, force=True)` to ensure single source of truth. |

---

### BUG-CORE-009 — `phase_2_world_tick.py` destructures proactive NPC tuple incorrectly

| Field | Value |
|---|---|
| **File:line** | `backend/app/services/game_loop/phase_2_world_tick.py (BUG-CORE-009 устранён: файл теперь заглушка Stage 0 Task 0.10)` |
| **Severity** | Medium |
| **Symptom** | NeedEngine.tick receives `current_activity=""` for every NPC because the variable `_wt_npc_raw` is actually an `NPCState` object (not the raw dict). Recovery and need decay calculations run against the wrong activity, causing spurious hunger/fatigue during sleep and rest. |
| **Root cause** | `_proactive_npc_data` is built at line 41-52 as a list of `(_pid, _p_l2, _p_l0)` tuples (where `_p_l2 = load_l2_state_from_runtime_dict(_n)` is an NPCState object). But the consumer at line 149 destructures as `for _pid, _wt_npc_raw, _ in _proactive_npc_data:` — so `_wt_npc_raw = _p_l2` (the NPCState). Then `isinstance(_wt_npc_raw, dict)` is False, and the elif branch `hasattr(_wt_npc_raw, "routine")` accesses `_p_l2.routine` which is likely a string/enum, not a dict. Result: `_wt_current_activity = ""`. |
| **Suggested fix** | Either rebuild the tuple to include the raw dict, or look up the raw dict from `tick_ctx.all_npcs_raw` inside the loop. Cleaner fix:<br>```python
for _pid, _p_l2, _p_l0 in _proactive_npc_data:
    _wt_npc_raw = next(
        (_n for _n in tick_ctx.all_npcs_raw
         if (_n.get("id") or _n.get("npc_id")) == _pid),
        None,
    )
    if not _wt_npc_raw:
        continue
    _wt_current_activity = _wt_npc_raw.get("routine", {}).get("current", "")
    _wt_ne.tick(_wt_ep, current_activity=_wt_current_activity)
``` |

---

### BUG-CORE-010 — Dialogue queue spam — `pending_tasks` re-enqueued every tick

| Field | Value |
|---|---|
| **File:line** | `backend/app/services/game_loop/task_scheduler.py:92-138` |
| **Severity** | High |
| **Symptom** | Known log: `Dialogue queue spammed with ambient tasks (priority=5) — 10+ tasks queued in single tick`. The `DialogueQueue._heap` grows unboundedly across ticks. |
| **Root cause** | `execute_pending(scene_state, campaign_id)`:<br>(1) Iterates ALL `pending_tasks` and enqueues each to `self._dialogue_queue` (lines 98-119).<br>(2) Dequeues ONLY ONE task via `dequeue_next()` (line 121).<br>(3) Removes ONLY the dequeued task from `pending_tasks` (lines 129-131).<br>The OTHER 9+ tasks REMAIN in BOTH `pending_tasks` AND in the dialogue_queue heap. Next tick, those 9 tasks get re-enqueued to the queue (now 9+1+new = 10+ items), and again only one is processed. The heap accumulates duplicates indefinitely. |
| **Suggested fix** | Either:<br>**Option A (preferred):** Clear `pending_tasks` after enqueueing — they're now in DialogueQueue's responsibility:<br>```python
for task_dict in pending:
    if task_dict.get("kind") == "dialogue":
        ...self._dialogue_queue.enqueue(...)
# All tasks moved to queue; clear source list
scene_state["pending_tasks"] = []
```<br>**Option B:** Add deduplication in `DialogueQueue.enqueue` — skip if same `task_id` is already in heap. Also add a TTL/eviction policy for tasks sitting in the heap too long. |

---

### BUG-CORE-011 — `random.choice` used instead of KernelRNG in TaskScheduler

| Field | Value |
|---|---|
| **File:line** | `backend/app/services/game_loop/task_scheduler.py:171, 199` |
| **Severity** | Medium (KernelRNG contract violation) |
| **Symptom** | Non-deterministic NPC target selection. Replays produce different social graphs. |
| **Root cause** | `import random` at line 171 and `random.choice(_candidates)` at line 199 — both bypass KernelRNG. The `CAUSAL_CONTRACT` requires all kernel randomness to flow through `KernelRNG(tick, npc_id, salt)`. |
| **Suggested fix** | Replace with:<br>```python
from app.services.npc.kernel_rng import KernelRNG
...
_tick = scene_state.get("tick", 0)
_rng = KernelRNG(tick=_tick, npc_id=task.owner_id, salt="task_target_resolve")
_resolved_target = _rng.choice(_candidates) if _candidates else "soliloquy"
``` |

---

### BUG-CORE-012 — `ResolutionEngine` uses `random.Random(seed)` instead of KernelRNG

| Field | Value |
|---|---|
| **File:line** | `backend/app/services/npc/resolution_engine.py:127, 145` |
| **Severity** | Medium (KernelRNG contract violation) |
| **Symptom** | Resolution outcomes are non-deterministic across runs. |
| **Root cause** | `self._rng = random.Random(seed)` — when `seed=None` (default), uses wall-clock entropy. The class also reads `state.drives_runtime` (line 153-154) which violates L3-P2 (drives_runtime cache is supposed to be dead; only `effective_drives_map` should be used). |
| **Suggested fix** | Replace `random.Random(seed)` with `KernelRNG(tick=tick, npc_id=state.npc_id, salt="resolution_engine")`. Pass `effective_drives` from caller instead of reading `state.drives_runtime`. |

---

### BUG-CORE-013 — `l1_drift_events` always empty in TickMutation

| Field | Value |
|---|---|
| **File:line** | `backend/app/services/npc/npc_tick_pipeline.py:150, 642` |
| **Severity** | Medium (contract violation) |
| **Symptom** | `pipeline_runner.py:102-104` tries to commit `mutation.l1_drift_events` to `l1_chronicle` every tick — but the list is ALWAYS empty. TIFL drift events computed in `compute_continuous_drift` (break_progress_engine.py:246) are never propagated through the pipeline. |
| **Root cause** | Line 150 initializes `l1_drift_events: List[Any] = []`. The loop body (lines 153-636) never appends to it. Line 642 returns it as part of `TickMutation(l1_drift_events=l1_drift_events, ...)`. The actual L1 events are emitted by `BreakProgressEngine` (via `decision.py:179, 182, 194`) and by `compute_continuous_drift` (in `phases/integration.py:212-223`), but the latter goes DIRECTLY to `l1_chronicle.commit_tick_buffer` — bypassing the TickMutation contract. |
| **Suggested fix** | In `npc_tick_pipeline.py`, collect drift events from `BreakProgressEngine.calculate()` result (which already returns delta info) and append `TraitDriftEvent` instances to `l1_drift_events` inside the per-NPC loop. Then `pipeline_runner.build_npc_contexts_from_intents` will correctly commit them. |

---

### BUG-CORE-014 — Dead NPCs NOT excluded before Phase 1 (contract violation)

| Field | Value |
|---|---|
| **File:line** | `backend/app/services/tick_orchestrator.py:600-624` |
| **Severity** | Medium (CAUSAL_CONTRACT violation) |
| **Symptom** | Dead NPCs (life_status="DEAD") are processed through Phases 0-4 (NPIC normalize, input merge, willpower gate, event bus, memory, topic extraction). Their body states may be mutated, they may publish events, they may consume MemoryManager capacity. |
| **Root cause** | The CAUSAL_CONTRACT states "Dead NPCs must be excluded before Phase 1". But the filter only happens in `_phase_5_decision` at line 1307-1311: <br>```python
_alive_npcs = [n for n in (ctx.all_npcs_raw or ctx.npc_states) if n.get("body_state", {}).get("life_status") != "DEAD"]<br>```<br>This filter is applied AFTER Phases 0-4 have already iterated `ctx.all_npcs_raw` / `ctx.npc_states`. |
| **Suggested fix** | Add an early filter at the top of `_run_core_phases` before `_phase_0_simulation`:<br>```python
def _run_core_phases(self, ctx, tick_fully=True):
    # ADR-123: Death Lock — exclude dead NPCs BEFORE any phase
    ctx.all_npcs_raw = [
        n for n in (ctx.all_npcs_raw or [])
        if n.get("body_state", {}).get("life_status") != "DEAD"
    ]
    if hasattr(ctx, "npc_states") and ctx.npc_states:
        ctx.npc_states = [
            n for n in ctx.npc_states
            if n.get("body_state", {}).get("life_status") != "DEAD"
        ]
    self._snapshot_positions_before(ctx)
    self._phase_0_simulation(ctx)
    ...
``` |

---

### BUG-CORE-015 — DRF scoring overlay checks `npc_id` but accesses `actor_id`

| Field | Value |
|---|---|
| **File:line** | `backend/app/services/tick_orchestrator.py:1609-1611` |
| **Severity** | Low |
| **Symptom** | DRF scoring overlay silently misroutes pressures to the wrong NPC (or no NPC). |
| **Root cause** | Line 1609: `if not hasattr(_intent, "npc_id"):` — checks for attribute `npc_id`. Line 1611: `_npc_id = _intent.actor_id` — reads attribute `actor_id`. `CommunicationIntent` has `speaker`, not `actor_id` or `npc_id` (see `decision_hub.py:359-367`). So either:<br>(a) `hasattr(_intent, "npc_id")` is False → `continue` (skipped silently)<br>(b) `_intent.actor_id` raises `AttributeError` (caught where? — there's no try/except here, so it'd crash the tick) |
| **Suggested fix** | Replace with: <br>```python
for _intent in intents:
    _npc_id = getattr(_intent, "speaker", None) or getattr(_intent, "npc_id", None) or getattr(_intent, "actor_id", None)
    if not _npc_id:
        continue
    ...
``` |

---

### BUG-CORE-016 — `LifeEngine.tick_decisions` is dead code (never called in production)

| Field | Value |
|---|---|
| **File:line** | `backend/app/services/npc/life_engine.py:632-1132` |
| **Severity** | Low (dead code, ~500 lines) |
| **Symptom** | `tick_decisions` is a duplicate of `NpcTickPipeline.run` functionality. It's only referenced by tests (`tests/sandbox/test_causal_bridge_integration.py:307`) and `tests/test_tick_orchestrator_full_loop.py:103`. The production code path uses `NpcTickPipeline.run` via `pipeline_runner.run_pipeline`. |
| **Root cause** | The method was the legacy Phase 5 entry point. After ADR-TZ09 (Pure Reducer Pattern), the orchestrator switched to `NpcTickPipeline.run`, but `tick_decisions` was never deleted. |
| **Suggested fix** | Delete `tick_decisions` (lines 632-1132) and its tests. Update the README at `phases/README.md:84` to remove the reference to `tick_decisions`. |

---

### BUG-CORE-017 — Duplicate dead `npcs = self._npc_cache.get(campaign_id)` block after `return`

| Field | Value |
|---|---|
| **File:line** | `backend/app/services/npc/life_engine.py:683-694` |
| **Severity** | Low (dead code) |
| **Symptom** | Inside `tick_decisions` (which is itself dead code per BUG-CORE-016), after the first `return ([], [], [])` at lines 679-683 (when `npcs` cache is empty), there's a duplicate block at lines 684-694 doing the exact same check. Unreachable. |
| **Root cause** | Copy-paste artifact during refactoring. |
| **Suggested fix** | Delete lines 683-694. The first check at lines 673-683 is sufficient. |

---

### BUG-CORE-018 — `_phase_2_event_bus_primary` mutates `ctx.scene_state["npc_positions"]` directly

| Field | Value |
|---|---|
| **File:line** | `backend/app/services/tick_orchestrator.py:262-341` (`_rebuild_cluster_occupancy`) |
| **Severity** | Medium (CAUSAL_CONTRACT: Phase8Result → delta_buffer → StateApplicator.apply_batch() is the ONLY mutation path) |
| **Symptom** | `_rebuild_cluster_occupancy` writes recovered NPC positions directly into `ctx.scene_state["npc_positions"]` (lines 307-321):<br>```python
npc_positions[_npc_id] = {
    "position": _pos,
    "local_position": _local_pos or {"x": 0.0, "y": 0.0},
    "name": _npc.get("name", _npc_id),
}
```<br>Bypasses StateApplicator. Same issue at lines 335-341 for player position. |
| **Root cause** | Cluster occupancy rebuild merges missing NPCs back into `npc_positions`, but it does so via direct dict mutation instead of routing through `delta_buffer` + `StateApplicator.apply_batch`. |
| **Suggested fix** | Emit a `StateDeltas(domain=DeltaDomain.SPATIAL, payload=...)` for each recovered NPC and route through `ctx.delta_buffer`. StateApplicator will then apply them in Phase 10. |

---

## Known log bugs — Root cause mapping

| Known bug | Mapped to | Confidence |
|---|---|---|
| **Bug 1**: `AttributeError: 'str' object has no attribute 'target_id' at decision.py:206 in evaluate_behavior_and_identity` | Could NOT reproduce exactly. The actual line 206 of `phases/decision.py` is `if _player_data:`. The closest fragility is at lines 204-211: if `relationship_store.get_all_for_source()` ever returns `Dict[str, str]` instead of `Dict[str, Dict[str, float]]`, then `_player_data.get("trust")` would fail with `'str' object has no attribute 'get'` (not `target_id`). The user's bug description appears to be paraphrased or referring to an older revision. **Recommendation**: add a type-check on `_player_data` before calling `.get()`. | Medium — exact error not reproducible, but related fragility confirmed |
| **Bug 2**: `DM: Ничего не произошло` — player actions don't propagate | **BUG-CORE-003** — broken `dm_ctx` bridging means `state.hub_event=None` for the entire NPC pipeline. DecisionHub runs in idle mode, NPCs see `EventType.WORLD_TICK` instead of the player action. | High |
| **Bug 3**: Empty `PlayerPerceptionDTO` | **BUG-CORE-006** — GameLoop's `_project_perception` overwrites Phase 9 perception without forwarding `observed_facts`. `manifestations={}` may also be empty if no NPC has elevated body markers (separate but related). | High |
| **Bug 4**: Sleep test failures — NPCs at `loc=city_gate` instead of tent/bed | **BUG-CORE-005** — non-sleeping NPCs never get their movement intents emitted. Combined with **BUG-CORE-004** (spatial_service wiped every tick), MovementEngine falls back to `CROSS_LOC_INTERCEPT` rerouting to `city_gate` (confirmed in `sleep_test2.log` line 252-257). | High |
| **Bug 5**: Dialogue queue spam (priority=5, 10+ tasks/tick) | **BUG-CORE-010** — `execute_pending` re-enqueues pending_tasks every tick without clearing, only dequeues one, leaves the rest in both `pending_tasks` AND the queue. | High |

---

## Architectural contract violations

| Contract | Violation | Location |
|---|---|---|
| TickOrchestrator = single entry point | Mostly OK, but `LifeEngine.tick_decisions` (BUG-CORE-016) duplicates the pipeline | `life_engine.py:632` |
| Core pipeline PURE function (TickState → TickMutation) | **NpcTickPipeline.run** instantiates `StateApplicator` internally (npc_tick_pipeline.py:611) and calls `applicator.apply()` — this writes to `state.relationship_store` (SSOT) which is a side-effect, breaking purity | `npc_tick_pipeline.py:609-636` |
| KernelRNG mandatory (no `random.*`) | `ResolutionEngine` uses `random.Random(seed)` (BUG-CORE-012); `TaskScheduler` uses `random.choice` (BUG-CORE-011) | `resolution_engine.py:127`, `task_scheduler.py:199` |
| WillpowerGate ONE invocation per tick | ✅ Verified — only one call site at `phases/input.py:120` via `_apply_willpower_gate` → `run_phase_1_input`. Comment at `input.py:99-100` warns against re-calling `resolve_intent_pressure` but the fallback at line 103 (`pressure = ctx.player_pressure or resolve_intent_pressure(intent)`) WILL re-call if `ctx.player_pressure` is None — should be guarded. | `phases/input.py:103` |
| L3 (EffectiveDrives) MUST be ephemeral | ✅ Verified in `_compute_effective_drives` (line 1278: `l3_stable = l3_raw`), no caching to drives_runtime. BUT BUG-CORE-002 silently disables L1 → L3 projection. | `tick_orchestrator.py:1278` |
| No LLM calls inside TickOrchestrator/DecisionHub | ✅ Verified — no LLM imports in either file. `IntentCompressor` (LLM slow-path) is correctly invoked in `game_loop/__init__.py:1698` outside the core. | — |
| No retro-simulation (only `reconcile_state`) | ✅ Verified — `macro_simulate` at `life_engine.py:283-364` is dead code (immediately returns `self.tick(...)` because `idle_seconds = 0.0`). `reconcile_state` at line 433 is the only valid path. | `life_engine.py:300-306` |
| `Phase8Result → delta_buffer → StateApplicator.apply_batch()` is the ONLY mutation path | **VIOLATED** by BUG-CORE-018 (direct `npc_positions` mutation in `_rebuild_cluster_occupancy`) and by `npc_tick_pipeline.py:611` (StateApplicator.apply called inside pure reducer) | multiple |
| InterventionEvent is the only input (no dm_ctx or player branches) | Mostly OK — `execute()` accepts `dm_ctx` as backward-compat (line 351-353) and bridges it. But BUG-CORE-003 shows the bridge is broken for the new intervention flow. | `tick_orchestrator.py:351-381` |
| Dead NPCs excluded before Phase 1 | **VIOLATED** — BUG-CORE-014 — only filtered in Phase 5 | `tick_orchestrator.py:1307-1311` |

---

## Silent failures (try/except: pass and similar)

| File:line | Pattern | Impact |
|---|---|---|
| `tick_orchestrator.py:1264-1265` | `try: ... _traits = self.memory_manager.get_identity_traits(ctx.campaign_id, _nid) ... except Exception: pass` | BUG-CORE-002 — silently disables L1 identity projection forever |
| `tick_orchestrator.py:532-533` | `try: ... _connected = [e.location_b for e in _reg.get_neighbors(...)] except Exception: pass` | Silent — AdaptiveTickLoader never gets neighbor list (dead code anyway per BUG-CORE-001) |
| `npc_tick_pipeline.py:188-191, 286-289, 314-317, 584-585, 635-636` | Multiple `try: ... except Exception as _e: logger.warning(...)` | Memory event creation, belief integration, proactive movement — all silently skip per-NPC |
| `reduction.py:204-210, 214-222` | Phase8Context construction and handler.handle() exceptions swallowed | BUG-CORE-007 — social_input crash hidden |
| `pipeline_runner.py:144-145, 175-176` | Memory apply failures for individual NPCs swallowed | Memory propagation may silently drop events |
| `npc_orchestration.py:194-195` | `_loc_spatial_svc = SpatialFactory.build_for_campaign(...); except Exception: pass` | Silent spatial service build failure for non-active locations |

---

## TODO/FIXME markers in scope

| File:line | TODO content |
|---|---|
| `phases/input.py:115` | "TODO: Передать PsychologicalPressure и PerceivedPhenomenon от CFRM P2, когда LocalCausalSolver будет генерировать их для хода игрока" — ADR-O-209 unfinished |
| `phases/decision.py: TODO(S28)` at `domain/decision_context.py:25` | "TODO(S28): Заменить строковые ключи на enum IntentType при рефакторинге" — stringly-typed constraints still in use |
| `legacy_delta_adapter.py:9-13` | TODO: по мере миграции legacy-кода на v2 постепенно удалять этот класс — adapter still actively used in `npc_tick_pipeline.py:761` |
| `game_loop/tick_context.py:16` | "TODO: при экстракции фаз из монолитного _run_pipeline — наполнить TickOutput результатами" — TickOutput dataclass is empty `pass` |
| `game_loop/dm_phase.py:166-167` | "TODO: LLM-classify" — dialogue intent and tone hardcoded to "dialogue" / "" |

---

## Recommendations — priority order

1. **Critical (P0)**: Fix BUG-CORE-003 (broken `dm_ctx` bridge) — this single fix will restore player action propagation and likely resolve 80% of "Ничего не произошло" cases.
2. **Critical (P0)**: Fix BUG-CORE-004 (LifeEngine `__init__` misplaced assignments) — spatial service / persistence / claim_bus must survive across ticks.
3. **Critical (P0)**: Fix BUG-CORE-005 (missing else branch for movement intents) — required for any NPC navigation to work.
4. **Critical (P0)**: Fix BUG-CORE-001 (dead unreachable code in `execute()`) — restore ADR-O-201 Dual Rail Observer and AdaptiveTickLoader.
5. **High (P1)**: Fix BUG-CORE-006 (PerceptionProjector missing `observed_facts`) — restores perception pipeline.
6. **High (P1)**: Fix BUG-CORE-007 (SimpleNamespace missing `scene_state`) — restores social_input listener detection.
7. **High (P1)**: Fix BUG-CORE-008 (`_tick_scene` vs `_tick_scenes`) — restores scene state commit flow.
8. **High (P1)**: Fix BUG-CORE-010 (dialogue queue spam) — clear `pending_tasks` after enqueue.
9. **High (P1)**: Fix BUG-CORE-002 (L1 identity projection) — remove `try/except: pass`, fix attribute names.
10. **Medium (P2)**: Fix BUG-CORE-009, 011, 012, 013, 014, 015, 018 — contract violations and silent data loss.
11. **Low (P3)**: Clean up BUG-CORE-016, 017 (dead code) — reduce maintenance burden.

---

## Files read completely

- `backend/app/services/tick_orchestrator.py` (1643 lines)
- `backend/app/services/pipeline_runner.py` (261 lines)
- `backend/app/services/npc/npc_tick_pipeline.py` (1133 lines)
- `backend/app/services/npc/life_engine.py` (2662 lines, partial — focus on `__init__`, `tick`, `tick_decisions`, `update_cache`)
- `backend/app/services/npc/decision_hub.py` (1975 lines, partial — focus on `compute`, `_get_rel_value`, `EventContext`)
- `backend/app/services/npc/break_progress_engine.py` (325 lines)
- `backend/app/services/npc/belief_crystallization_engine.py` (134 lines)
- `backend/app/services/npc/pattern_detector.py` (137 lines)
- `backend/app/services/npc/pe_modifier_resolver.py` (46 lines)
- `backend/app/services/npc/legacy_delta_adapter.py` (91 lines)
- `backend/app/services/npc/behavior_modifiers.py` (59 lines)
- `backend/app/services/npc/kernel_rng.py` (83 lines)
- `backend/app/services/npc/state_applicator.py` (1329 lines, partial — focus on `apply_batch`)
- `backend/app/services/npc/resolution_engine.py` (380 lines, partial)
- `backend/app/services/game_loop/__init__.py` (2143 lines, partial — focus on `idle_tick`, `run_turn`, `_run_pipeline`, `_project_perception`, `_load_npcs_with_runtime`)
- `backend/app/services/game_loop/dm_phase.py` (294 lines)
- `backend/app/services/game_loop/npc_orchestration.py` (381 lines)
- `backend/app/services/game_loop/phase_1_input.py` (380 lines)
- `backend/app/services/game_loop/phase_2_world_tick.py` (168 lines)
- `backend/app/services/game_loop/phase_6_avatar.py` (112 lines)
- `backend/app/services/game_loop/tick_context.py` (80 lines)
- `backend/app/services/game_loop/task_scheduler.py` (309 lines)
- `backend/app/services/game_loop/time_advance.py` (106 lines)
- `backend/app/services/game_loop/service_factories.py` (193 lines)
- `backend/app/services/game_loop/scene_init.py` (391 lines)
- `backend/app/services/game_loop/agent_runner.py` (161 lines)
- `backend/app/services/phases/decision.py` (320 lines)
- `backend/app/services/phases/reduction.py` (295 lines)
- `backend/app/services/phases/post_decision.py` (347 lines)
- `backend/app/services/phases/commit_phase.py` (127 lines)
- `backend/app/services/phases/integration.py` (580 lines)
- `backend/app/services/phases/input.py` (301 lines)
- `backend/app/services/phases/memory.py` (125 lines)
- `backend/app/services/phases/simulation.py` (107 lines)
- `backend/app/services/phases/motion.py` (176 lines)
- `backend/app/domain/tick.py` (217 lines)
- `backend/app/domain/intent.py` (48 lines)
- `backend/app/domain/action_windup.py` (41 lines)
- `backend/app/domain/decision_context.py` (90 lines)
- `backend/app/services/perception/perception_projector.py` (60 lines)
- `backend/app/services/perception/phenomenology_projection_service.py` (128 lines)
- `backend/app/services/perception/behavior_manifestation_service.py` (305 lines)
- `backend/app/services/perception/perception_physics_engine.py` (618 lines)
- `backend/app/services/events/social_input_projector.py` (145 lines)
- `backend/app/services/memory/relationship_store.py` (partial — `get_all_for_source`, `get_pair`)
- `backend/app/services/scene_state_manager.py` (grep only — confirmed `_tick_scenes` plural)
- `backend/app/services/execution/dialogue_queue.py` (115 lines)

**Cross-referenced logs**:
- `backend/causal_validation.log` (confirmed "Ничего не произошло" pattern across all test categories)
- `backend/logs/cds_session_20260731_224852.log` (confirmed `[PHASE8_CRASH] social_input AttributeError scene_state`)
- `backend/logs/cds_session_20260731_224226.log` (confirmed `_tick_scene` AttributeError and `PipelineContext.tick` AttributeError)
- `sleep_test2.log` (confirmed CROSS_LOC_INTERCEPT rerouting sleep-bound NPCs to `city_gate`)
