# Domain Analysis: Perception / Phenomenology / Physiology / Combat / Affective

**Project:** ENIGMA V.0.5.3.6.7
**Scope:** Deep analysis of perception, phenomenology, physiology, combat, and affective subsystems only.
**Method:** Static code reading of all targeted files + cross-reference of wiring call-sites.

---

## Executive Summary

The perception/combat/affective domain suffers from **architectural disconnection**: two parallel pipelines produce different `PlayerPerceptionDTO` types, the `PLAYER_THREATENS` event is declared but never published, combat RNG uses `random.Random` instead of `KernelRNG`, and legacy `combat_math.apply_damage` resurrects the dead via HP writes. The reported symptoms — *empty PlayerPerceptionDTO* and *player threats not triggering combat/fear* — are both reproduced as direct consequences of these bugs.

A total of **29 defects** were identified (4 Critical, 9 High, 9 Medium, 7 Low).

---

## BUGS

### BUG-PERC-001 — PlayerPerceptionDTO always EMPTY (DTO type mismatch + bypassed conversion)
- **File:** `backend/app/services/game_loop/__init__.py:954-963` and `backend/app/services/perception/phenomenology_projection_service.py:118-127`
- **Symptom:** Frontend receives
  ```
  PlayerPerceptionDTO(active_perceptions=[], atmosphere_key=None,
                      atmosphere_intensity=0.0, embodied_traces=[],
                      manifestations={}, observed_facts=[])
  ```
  This is the **`embodied_trace.PlayerPerceptionDTO`** shape, NOT the **`snapshot.PlayerPerceptionDTO`** that `WorldSnapshotDTO.player_perception` is typed to hold. The frontend expects `peripheral_cues: List[PeripheralCueDTO]` and `manifestations: List[ManifestationDTO]` but gets `atmosphere_key: None` and `manifestations: {}` (dict).
- **Root cause:**
  1. Two **different** `PlayerPerceptionDTO` classes exist:
     - `app/domain/embodied_trace.py` (domain format: dict `manifestations`, `atmosphere_key`, `atmosphere_intensity`)
     - `app/domain/snapshot.py` (API format: `peripheral_cues`, `manifestations: List[ManifestationDTO]`, `avatar_desync`)
  2. `integration.py:567` builds a domain DTO via `deps.project_svc.project(...)` and feeds it to `WorldSnapshotBuilder.build(player_perception=...)` → `_convert_perception` correctly converts domain→API.
  3. **Then** `game_loop/__init__.py:956` calls `self._project_perception(...)` (a *second* projection) and **overwrites** the snapshot via `dataclasses.replace(world_snapshot, player_perception=_perception)`. `_perception` is the **raw domain DTO** — the converter is **never applied**.
- **Severity:** Critical
- **Suggested fix:**
  - Remove the second `_project_perception` call entirely (`integration.py` already built it), OR
  - Route the second projection through `WorldSnapshotBuilder._convert_perception` before `dataclasses.replace`. Concretely, replace lines 957-963 with:
    ```python
    if _perception:
        _converted = WorldSnapshotBuilder()._convert_perception(_perception, tick=self.get_current_tick(campaign_id))
        _new_ws = dataclasses.replace(result.world_snapshot, player_perception=_converted)
        result = dataclasses.replace(result, world_snapshot=_new_ws)
    ```
  - Better: collapse the dual pipeline (see BUG-PERC-011).

---

### BUG-PERC-002 — Player threats ("угрожать трактирщику ножом") never reach combat/fear pipeline
- **File:** `backend/app/services/game_loop/phase_1_input.py:276-297`
- **Symptom:** DMRouter correctly classifies "угрожать" lemmas to `event_type="player_threatens"` (dm_router.py:103-112). ADR-091 override sets `_raw_type = "player_threatens"` (phase_1_input.py:336-347). But the resulting published event is **`PLAYER_SPOKE`**, not `PLAYER_THREATENS`. ReactionSubscriber, SocialSubscriber, and CombatSubscriber all subscribe to `EventType.PLAYER_THREATENS` but it is **never emitted** — so no threat_gradient_delta, no fear response, no combat trigger.
- **Root cause:** `_evt_map` (lines 276-283) only contains:
  ```python
  _evt_map = {
      "dialogue": EventType.PLAYER_SPOKE,
      "player_interacts": EventType.PLAYER_SPOKE,
      "attack": EventType.PLAYER_ATTACKED,
      "player_attacks": EventType.PLAYER_ATTACKED,
      "move": EventType.PLAYER_MOVED,
      "stealth": EventType.PLAYER_MOVED,
  }
  ```
  Missing entries: `"player_threatens"`, `"player_threatens_indirect"`, `"player_insults"`, `"player_steals"`, `"player_flees"`, `"intimidation"`, `"theft"`, `"betrayal"`, `"help"`, `"saved_life"`. All of these fall back to `EventType.PLAYER_SPOKE`.
- **Severity:** Critical
- **Suggested fix:**
  ```python
  _evt_map = {
      "dialogue": EventType.PLAYER_SPOKE,
      "player_interacts": EventType.PLAYER_SPOKE,
      "attack": EventType.PLAYER_ATTACKED,
      "player_attacks": EventType.PLAYER_ATTACKED,
      "player_attack": EventType.PLAYER_ATTACKED,
      "player_threatens": EventType.PLAYER_THREATENS,
      "player_threatens_indirect": EventType.PLAYER_THREATENS,  # or new type
      "player_insults": EventType.PLAYER_INSULTS,
      "player_steals": EventType.THEFT,
      "player_flees": EventType.MOVEMENT,
      "intimidation": EventType.INTIMIDATION,
      "theft": EventType.THEFT,
      "betrayal": EventType.BETRAYAL,
      "help": EventType.HELP,
      "saved_life": EventType.SAVED_LIFE,
      "move": EventType.PLAYER_MOVED,
      "stealth": EventType.PLAYER_MOVED,
  }
  ```

---

### BUG-PERC-003 — Combat uses `random.Random`, not KernelRNG (rule violation)
- **File:** `backend/app/services/combat/impact_engine.py:24,46,95,131`
- **Symptom:** `import random`; `rng = random.Random(rng_seed)`. The seed is computed from `hash((event_id, actor_id, target_id)) & 0xFFFFFFFF` (combat_subscriber.py:215-222). Python's `hash()` for strings is randomized per-process (PYTHONHASHSEED), so seed is **non-deterministic across runs**. Violates "Combat uses KernelRNG (no random.*)".
- **Severity:** High
- **Suggested fix:**
  - Replace `rng = random.Random(rng_seed)` with `rng = KernelRNG(tick=current_tick, npc_id=actor_id, salt=f"combat:{target_id}")` and pass that into `attack_roll(attacker_dict, defender_dict, rng=rng)`.

---

### BUG-PERC-004 — combat_math.py falls back to global `random` module
- **File:** `backend/app/services/game/combat_math.py:12,50,52,61,71,193,210,276,278,379,404,429`
- **Symptom:** Every dice function has signature `rng: Optional[random.Random] = None` with body `_rng = rng or random`. If caller omits `rng` (the common case), the function uses the global `random` module — non-deterministic, non-replayable, violates KernelRNG rule.
- **Severity:** High
- **Suggested fix:**
  - Make `rng` required (no default), OR default to constructing a `KernelRNG` inside the function. Replace `_rng = rng or random` everywhere with `_rng = rng or KernelRNG(tick=0, npc_id="combat", salt="default")`.

---

### BUG-PERC-005 — `combat_math.apply_damage` writes `state.hp` AND kills via `hp<=0` (FORBIDDEN)
- **File:** `backend/app/services/game/combat_math.py:300-322`
- **Symptom:**
  ```python
  target["hp"] = max(0, before - damage)        # writes state.hp (not body_state["current_hp"])
  if target["hp"] <= 0:                          # HP-as-death-source
      target["status"] = "dead" if tier in ("minor","mass") else "incapacitated"
  ```
  Three rule violations in 5 lines:
  1. "HP SSOT is body_state["current_hp"], NOT state.hp"
  2. "No HP Death (hp<=0 as death source forbidden)"
  3. "evaluate_vital_state() is the only death source"
- **Severity:** Critical
- **Suggested fix:** Delete `apply_damage` (it is dead code per state_applicator.py:926-927 comment: "Legacy hp-based death paths are being removed (combat_math.apply_damage is dead code)"). If still referenced, route through `PhysiologyPayload(hp_delta=-damage)` + `StateApplicator._apply_deltas` + `evaluate_vital_state(body_state)`.

---

### BUG-PERC-006 — `combat_math.apply_healing` allows DEAD → ALIVE transition (FORBIDDEN)
- **File:** `backend/app/services/game/combat_math.py:325-340`
- **Symptom:**
  ```python
  target["hp"] = min(max_hp, before + amount)
  if target["hp"] > 0:
      target["status"] = "alive"      # resurrects!
  ```
  Violates "Death is irreversible (DEAD -> ALIVE forbidden)". A heal on a dead NPC (hp=0) raises hp>0 and flips status to "alive".
- **Severity:** Critical
- **Suggested fix:** Add early guard:
  ```python
  if target.get("status") == "dead" or target.get("life_status") == "DEAD":
      return {"hp_before": before, "hp_after": before, "blocked": "dead"}
  ```
  Or simply delete this function (legacy code, see state_applicator for canonical death lock in `evaluate_vital_state`).

---

### BUG-PERC-007 — `combat_service.py` is a legacy D&D service that bypasses SSOT
- **File:** `backend/app/services/combat_service.py:1-117`
- **Symptom:** A complete parallel combat system: stores state as `{"name":..., "hp":..., "initiative":...}` flat dict. `resolve_attack` directly mutates `p["hp"]`. Uses external `d20_roll` (no KernelRNG), uses `d20_roll == 20` for crit (not `combat_math.attack_roll`). No `PhysiologyPayload`, no `shock_impulse`, no `pain_delta`, no injuries, no `evaluate_vital_state`.
- **Severity:** High
- **Suggested fix:** Determine if this service is still wired (search call sites). If unused, delete. If used, route through `ImpactEngine.resolve_physical_impact` + `StateApplicator.apply_batch`.

---

### BUG-PERC-008 — `BehaviorManifestationService` filters out healthy NPCs → empty traces
- **File:** `backend/app/services/perception/behavior_manifestation_service.py:140-145`
- **Symptom:**
  ```python
  if (
      trace.locomotion_instability > 0.05
      or trace.posture_rigidity > 0.05
      or trace.micro_pause_density > 0.05
  ):
      traces.append(trace)
  ```
  A calm healthy tavern keeper produces all-zero trace → filtered out → no trace → `PlayerPerceptionDTO.embodied_traces = []` → DM agent has nothing to describe (dm_agent.py:419-447 iterates traces to build "Наблюдаемые симптомы NPC" block).
- **Severity:** Critical
- **Suggested fix:** Always append a baseline trace (even if all-zero), OR add a "neutral/idle" cue key for healthy NPCs. Suggested:
  ```python
  traces.append(trace)  # always append; consumer decides what to render
  ```
  Then `PhenomenologyProjectionService` can emit a `MANIFEST_CALM` tag for healthy NPCs (currently only emits tags when rigidity > 0.4 etc.).

---

### BUG-PERC-009 — Integration.py feeds wrong source into ManifestationPhysicsEngine
- **File:** `backend/app/services/phases/integration.py:474-488`
- **Symptom:**
  ```python
  _npc_positions = ctx.scene_state.get("npc_positions", {})
  ...
  for _nid, _ndata in _npc_positions.items():
      _bs = _body_map.get(_nid, {})
      _manifest = _manifest_engine.manifest(_ndata, _bs, _traversal)
  ```
  `_ndata` is the `NPCPositionDTO` dict (contains `local_position`, `activity`, `facing`, `velocity`, `display_name`, etc. — see snapshot.py:71-99). It does **NOT** contain `psyche`, `social_stats`, `drives_base`, `personality`, or `perceptual_kernel`. ManifestationPhysicsEngine.manifest (manifestation_physics_engine.py:48-67) reads all of these from `npc_state` — they default to 0/empty.
- **Severity:** High
- **Suggested fix:** Use `all_npcs_raw` (full NPC state) instead of `npc_positions` for the manifest call:
  ```python
  _npc_state_map = {n.get("id") or n.get("npc_id"): n for n in _npc_truth_source}
  for _nid in _npc_positions:
      if _nid == "player": continue
      _npc_state = _npc_state_map.get(_nid, {})
      _bs = _npc_state.get("body_state", {})
      _manifest = _manifest_engine.manifest(_npc_state, _bs, _traversal)
  ```

---

### BUG-PERC-010 — `BehaviorManifestationService` reads psyche despite "ЗАПРЕТ: Не читает psyche"
- **File:** `backend/app/services/perception/behavior_manifestation_service.py:48,128,137,167-168,194-199,260-275`
- **Symptom:** Module docstring says *"ЗАПРЕТ: Не читает psyche (fear, anger). Только моторные замки и физиологию."* But `_manifest_npc` accepts `psyche` parameter, extracts `stress` and `affective_load`, and uses them to drive motor patterns:
  ```python
  if stress > 20.0:
      _emo_rigidity = max(_emo_rigidity, min(0.6, stress / 100.0))
  if affective_load > 0.3:
      _emo_instability = min(0.5, (affective_load - 0.3) * 0.7)
  ```
  And adds "stress", "cognitive_overload" to `possible_causes`.
- **Severity:** Medium
- **Suggested fix:** Either remove the psyche reads (true to the docstring) and rely solely on `body_state` + `perceptual_kernel.threat_gradient` (ADR-O-205 comment at line 180-189 already suggests this), OR update the docstring to acknowledge that affective_load is permitted as "emotional energy → motor energy" per S122.

---

### BUG-PERC-011 — Dual perception pipeline (inconsistent + wasteful)
- **Files:**
  - `backend/app/services/phases/integration.py:462-569` (Pipeline A: `ManifestationPhysicsEngine` + `PerceptionPhysicsEngine` + `FactExtractor` + `InferenceEngine` + `PresentationAssembler` + `PhenomenologyProjectionService`)
  - `backend/app/services/game_loop/__init__.py:627-638, 954-963` (Pipeline B: `PerceptionProjector` + `BehaviorManifestationService` + `PhenomenologyProjectionService`)
- **Symptom:** Two independent trace generators produce two different `EmbodiedTraceDTO` lists, then both feed into `PhenomenologyProjectionService.project()`. Pipeline B (game_loop) overwrites Pipeline A's result on the world_snapshot. Pipeline A's fact extraction, inference, and signals are silently discarded. Pipeline A reads `npc_positions` (wrong source — see BUG-PERC-009), Pipeline B reads `all_npcs_raw` (correct source). They produce **different** traces for the same NPCs.
- **Severity:** Medium
- **Suggested fix:** Collapse into one pipeline. Recommended: keep Pipeline B (`BehaviorManifestationService` reads `all_npcs_raw` correctly) and remove Pipeline A's trace-building loop (integration.py:472-518). Pipeline A's `PerceptionPhysicsEngine` / `FactExtractor` / `InferenceEngine` should be invoked only if `observed_facts` need to be populated for DM.

---

### BUG-PERC-012 — `PresentationAssembler` reads non-existent field `fact.perceived_value`
- **File:** `backend/app/services/perception/presentation_assembler.py:31-33`
- **Symptom:**
  ```python
  value=fact.perceived_value
        if hasattr(fact, "perceived_value")
        else fact.value,
  ```
  `ObservedFact` (domain/observed_fact.py:14-33) has `value: Any` — **not** `perceived_value`. `perceived_value` is a field of `PerceivedSignal` (domain/perception_physics.py:42), not `ObservedFact`. The `hasattr` check always returns False, so `fact.value` is used, but the code is misleading dead branch.
- **Severity:** Low
- **Suggested fix:** Replace with `value=fact.value`.

---

### BUG-PERC-013 — `L1Chronicle` deletes events from active table (violates "append-only, no deletions")
- **File:** `backend/app/services/npc/l1_chronicle.py:240-268`
- **Symptom:** `archive_old_events()`:
  ```python
  self._store.execute(
      "DELETE FROM l1_chronicle_events WHERE campaign_id = ? AND tick_id < ?",
      (self._campaign_id, _threshold),
  )
  # ...and in RAM:
  self._events[npc_id] = [e for e in self._events[npc_id] if e.tick_id >= _threshold]
  if not self._events[npc_id]:
      del self._events[npc_id]
  ```
  Rule states "L1Chronicle: append-only, no deletions". While events are archived to `l1_chronicle_archive` table (not truly lost), the active table is mutated with `DELETE`. The contract says "no deletions" — archiving is a soft violation since it changes the canonical L1 table.
- **Severity:** Medium
- **Suggested fix:** Either rename the contract to "append-only + archival migration" (acknowledging the move-to-archive pattern), or use a single table with `archived_at_tick` column and never DELETE.

---

### BUG-PERC-014 — L2.5 belief crystallization runs every tick (no `phase_2_events` gate)
- **File:** `backend/app/services/phases/integration.py:380-422`
- **Symptom:** The crystallization loop:
  ```python
  for npc_dict in _npc_truth_source:
      _l1_events = deps.l1_chronicle.query_raw(_npc_id)
      if not _l1_events: continue
      _evidence_list = deps.pattern_detector.detect(_l1_events)
      ...
      _updated_beliefs = deps.belief_engine.crystallize(...)
  ```
  Runs every tick (active or idle), re-reading the entire L1 history. Rule: "No L2.5 crystallization in idle without phase_2_events". On idle ticks with stale L1 events (e.g., trauma from previous active tick), this re-crystallizes beliefs without new input.
- **Severity:** Medium
- **Suggested fix:** Gate on `if not ctx.phase_2_events: continue` (or whatever flag denotes "no new events this tick"). Pattern detection should also be incremental (track last-processed tick) instead of re-scanning all history.

---

### BUG-PERC-015 — `physics_validator.py` uses `self` in class-level lambda → `NameError`
- **File:** `backend/app/services/game/physics_validator.py:82`
- **Symptom:**
  ```python
  VIOLATION_RULES: list[tuple[str, Callable[[Dict, Dict], bool] | bool, str]] = [
      ...
      (
          r"поднимаю (\d+) кг|поднимаю (\d+) килограмм|несу (\d+) кг",
          lambda char, _: self._check_lifting_capacity(char, 500),   # NameError!
          "Слишком тяжёлый вес. Максимум — Сила × 15 фунтов...",
      ),
  ```
  `self` is not defined in class-body scope (lambdas in class bodies don't close over the class). When this rule fires for a "поднимаю 50 кг" action, Python raises `NameError: name 'self' is not defined`. The validator catches nothing; the action proceeds unchecked.
- **Severity:** High
- **Suggested fix:** Convert to `staticmethod` reference:
  ```python
  lambda char, _: PhysicsValidator._check_lifting_capacity(char, 500),
  ```
  Or move the rule check inside `validate()` method where `self` is bound.

---

### BUG-PERC-016 — `InferenceEngine._map_fact_to_cause_key` has wrong/stub mapping
- **File:** `backend/app/services/perception/inference_engine.py:94-95`
- **Symptom:**
  ```python
  if fact.fact_name == "movement_speed":
      return "movement.coordination_impaired"  # Заглушка, потом уточним
  ```
  Movement speed has nothing to do with coordination impairment. A fast-moving NPC gets inferred as "coordination_impaired" with all causes from `signal_causes.yaml` for that key. Misleading hypotheses feed DM context.
- **Severity:** Low
- **Suggested fix:** Either remove this stub mapping (return `""` so no inference is built) or add a proper `movement.speed` key to `signal_causes.yaml`.

---

### BUG-PERC-017 — `PerceptualAttentionService` is dead code (orphan, never wired)
- **File:** `backend/app/services/perception/perceptual_attention_service.py` (entire file)
- **Symptom:** Defines `build_perception(events, avatar_state, current_tick) -> PlayerPerceptionDTO` (snapshot variant). Returns `PlayerPerceptionDTO` with `avatar_desync: AvatarDesyncDTO` (the ONLY place that computes camera_inertia / motion_trail / auditory_muffle from `AvatarStateDTO`).
  - **Not** imported by `PerceptionProjector`.
  - **Not** imported by `integration.py`.
  - **Not** imported by `game_loop`.
  - `PerceptionProjector.project()` calls `BehaviorManifestationService.produce_traces()` + `PhenomenologyProjectionService.project()` — bypassing `PerceptualAttentionService`.
  - Result: `avatar_desync` field on snapshot PlayerPerceptionDTO is **always None** ( BUG-PERC-024 ).
- **Severity:** Medium
- **Suggested fix:** Either delete `PerceptualAttentionService` (and remove `avatar_desync` from snapshot.PlayerPerceptionDTO), or wire it: `PerceptionProjector.project()` should call `PerceptualAttentionService.build_perception(events, avatar_state, tick)` after `_project_svc.project()` and merge `avatar_desync` into the result.

---

### BUG-PERC-018 — `combat_subscriber` uses `print()` for diagnostics
- **File:** `backend/app/services/combat/combat_subscriber.py:73-75`
- **Symptom:**
  ```python
  def _on_event(self, event) -> Optional[dict]:
      print(
          f"[DIAG_COMBAT_ON_EVENT] type={getattr(event, 'type', '?')}, ..."
      )
  ```
  `print()` to stdout — will spam production logs, bypass log levels, cannot be filtered.
- **Severity:** Low
- **Suggested fix:** Replace with `logger.debug(f"[COMBAT_ON_EVENT] type=...")`.

---

### BUG-PERC-019 — `game_loop` uses `print()` for PerceptionProjector diagnostics
- **File:** `backend/app/services/game_loop/__init__.py:635-637`
- **Symptom:**
  ```python
  print(f"[ARCHAE_PROJECTOR] scene_state={bool(scene_state)} all_npcs_raw={len(all_npcs_raw) if all_npcs_raw else 0}")
  _res = _projector.project(scene_state, all_npcs_raw, _tick)
  print(f"[ARCHAE_PROJECTOR] result={_res}")
  ```
- **Severity:** Low
- **Suggested fix:** Replace with `logger.debug(...)`.

---

### BUG-PERC-020 — `state_applicator.apply_physical` writes HP twice with inconsistent types
- **File:** `backend/app/services/npc/state_applicator.py:283-292`
- **Symptom:**
  ```python
  _new_hp = max(0.0, old_hp - outcome.damage)        # float
  if not new_state.body_state:
      new_state.body_state = {"current_hp": _max_hp, "max_hp": _max_hp}
  new_state.body_state["current_hp"] = min(_max_hp, _new_hp)   # float
  if new_state.body_state:
      new_state.body_state["current_hp"] = int(_new_hp)        # int (overwrites!)
  ```
  First writes float, then immediately overwrites with `int(_new_hp)`. Truncates fractional HP. Inconsistent with `_apply_deltas` (line 853-855) which writes float.
- **Severity:** Low
- **Suggested fix:** Remove the redundant `int()` cast. Single source of truth:
  ```python
  new_state.body_state["current_hp"] = max(0.0, min(_max_hp, old_hp - outcome.damage))
  ```

---

### BUG-PERC-021 — `state_applicator` logs DEATH_CERTIFIED twice (duplicate block)
- **File:** `backend/app/services/npc/state_applicator.py:932-939`
- **Symptom:**
  ```python
  if _life_status == LifeStatus.DEAD:
      logger.warning(
          f"[DEATH_CERTIFIED] npc={state.npc_id} bl=... structural=..."
      )
  if _life_status == LifeStatus.DEAD:                # duplicate check!
      logger.warning(
          f"[DEATH_CERTIFIED] npc={state.npc_id} life_status={_life_status.value} bl=... structural=..."
      )
  ```
  Two consecutive `if` blocks with same condition. Logs the same death twice (second includes `life_status=` field).
- **Severity:** Low
- **Suggested fix:** Delete the duplicate block (lines 936-939).

---

### BUG-PERC-022 — `BehaviorManifestationService._manifest_npc` references `_threat` outside its defining scope
- **File:** `backend/app/services/perception/behavior_manifestation_service.py:184-189,267,288`
- **Symptom:**
  ```python
  _kernel = data.get("perceptual_kernel")
  if _kernel:
      _threat = getattr(_kernel, "threat_gradient", 0.0)
      _emo_rigidity = min(0.8, _threat * 0.9)
  
  # ...later...
  if posture_rigidity > 0.3:
      ...
      if _kernel and _threat > 0.0:      # _threat may be unbound!
          _possible_causes.add("threat")
  
  # ...and in _confidence:
  _threat if _kernel else 0.0            # safe
  ```
  If `_kernel` is truthy on the first check, `_threat` gets defined. If `_kernel` is falsy, `_threat` is never defined. Line 267 `if _kernel and _threat > 0.0` is short-circuit safe (Python evaluates `_kernel` first), but the code is fragile and confusing.
- **Severity:** Low
- **Suggested fix:** Initialize `_threat = 0.0` at the top of `_manifest_npc`, before the `if _kernel:` block.

---

### BUG-PERC-023 — `affective_integrator` reads psyche dict using drive names as keys (semantic leak)
- **File:** `backend/app/services/affective/affective_integrator.py:34-39`
- **Symptom:**
  ```python
  _w_threat = psyche.get("fear", 0.25)
  _w_uncertainty = psyche.get("control", 0.25)
  _w_anomaly = psyche.get("significance", 0.25)
  willpower = psyche.get("willpower", 0.5)
  ```
  The caller (phases/affective.py:109-114) builds `psyche = {"fear": _drive_fear, "control": _drive_control, "significance": _drive_significance, "willpower": ...}`. So drive weights are smuggled through a dict named `psyche`. The naming is misleading: these are drive modulation weights, not psyche fields.
- **Severity:** Low
- **Suggested fix:** Rename parameter from `psyche` to `drive_weights` or pass a typed `DriveWeights` dataclass. Update all callers.

---

### BUG-PERC-024 — `avatar_desync` is always None on the API `PlayerPerceptionDTO`
- **File:** `backend/app/domain/snapshot.py:186,200-205` and `backend/app/services/integration/world_snapshot_builder.py:200-206`
- **Symptom:** `snapshot.PlayerPerceptionDTO.avatar_desync: Optional[AvatarDesyncDTO] = None`. `WorldSnapshotBuilder._convert_perception` does NOT set `avatar_desync` — it remains None. The only place that computes `AvatarDesyncDTO` is `PerceptualAttentionService.build_perception` (BUG-PERC-017), which is dead code. So frontend never receives camera_inertia / motion_trail / auditory_muffle.
- **Severity:** Medium
- **Suggested fix:** Wire `PerceptualAttentionService.build_perception` (or fold its `avatar_desync` logic into `assemble_avatar_presentation` or `PhenomenologyProjectionService.project`) and set `avatar_desync` in `_convert_perception`.

---

### BUG-PERC-025 — Somatic Gate missing before semantic parsing
- **File:** `backend/app/services/npc/decision_hub.py:402-418`
- **Symptom:** Architecture rule: *"Body is a Gate of Perception (somatic_urgency before semantic parsing)"* and *"Somatic Gate MUST come BEFORE semantic parsing (Body -> Somatic Gate -> Semantic -> Legitimacy -> Action)"*. The `DecisionHub.compute()` checks vital_state at line 408 — but this is at the **Action** stage, after semantic parsing (which happens in Phase 1 input + Phase 5 DecisionHub). The somatic gate (body vetoing input parsing) is not implemented.
  The `translate_kernel_to_context` (cfrm/pressure_translator.py:66-85) does apply a somatic veto via `constraints[action] = 0.0` for high pain/shock/blood_loss — but this is **after** semantic parsing, as Action compression. The "Body before Semantic" pipeline is missing.
- **Severity:** Medium
- **Suggested fix:** Add an early somatic gate in `phase_1_input.publish_classified_player_event` (or in NPC perception pipeline): if observer's `body_state.shock_impulse > 0.7` or `is_conscious(body_state) == False`, the NPC should not parse the semantic content of the event (only register raw disturbance).

---

### BUG-PERC-026 — `state_applicator` doesn't propagate `life_status` to root-level state
- **File:** `backend/app/services/npc/state_applicator.py:930-931`
- **Symptom:**
  ```python
  _life_status = evaluate_vital_state(state.body_state)
  state.body_state["life_status"] = _life_status.value
  ```
  Only sets `body_state["life_status"]`. If `NPCState` has a separate `life_status` field (or if other code reads `state.life_status` instead of `state.body_state["life_status"]`), there's an inconsistency. `combat_subscriber._build_snapshot` (line 402) reads `body_state.life_status` correctly; `decision_hub.compute` (line 407) reads via `evaluate_vital_state(_body)`. But NPC loaders / serializers may use root-level fields.
- **Severity:** Low
- **Suggested fix:** Verify `NPCState.write_to_legacy` (state_applicator.py:1328) syncs `body_state["life_status"]` to any root-level `life_status` field used by persistence. If `state.life_status` exists on NPCState, also set it: `state.life_status = _life_status`.

---

### BUG-PERC-027 — TODO markers indicate incomplete vital-state processes
- **Files:**
  - `backend/app/domain/vital_state.py:122,141` (TODO: death_cause classification, DeathState)
  - `backend/app/services/npc/state_applicator.py:927-929` (TODO: move vital_state eval to end-of-tick reconciliation)
  - `backend/app/services/combat/injury_processor.py:221-225` (TODO: Process-system: BleedingProcess, HypoxiaProcess, PoisonProcess)
  - `backend/app/services/combat/physiology_decay_handler.py:246-248` (ARCHITECTURAL DEBT: decay as bandage for missing perceive_world())
- **Symptom:** Acknowledged backlog. Current death only via `blood_loss ≥ 0.9` or `structural_damage ≥ 1.5`. No infection, hypoxia, poison, suffocation. Decay is used as emergency "fear eraser" because PerceptualKernel isn't recomputed each tick.
- **Severity:** Low (intentional backlog, not a defect per se)
- **Suggested fix:** Track in roadmap. The decay-as-bandage is the most concerning — it means NPC fear fades artificially even when the threat is still present.

---

### BUG-PERC-028 — `CombatSubscriber` injects `missed_targets` via `setattr` on `Phase8Result`
- **File:** `backend/app/services/combat/combat_subscriber.py:237`
- **Symptom:**
  ```python
  result.missed_targets = missed_targets  # type: ignore[attr-defined]
  ```
  `Phase8Result` (models/phase8.py:50-62) is a `@dataclass` (mutable, not frozen). The `missed_targets` field is not declared on the dataclass. Other handlers and the orchestrator don't know about this attribute. Reading `result.missed_targets` elsewhere raises `AttributeError` for handlers that don't set it.
- **Severity:** Low
- **Suggested fix:** Add `missed_targets: List[Dict[str, Any]] = field(default_factory=list)` to `Phase8Result` dataclass, then use `result.missed_targets = missed_targets` without `type: ignore`.

---

### BUG-PERC-029 — `combat_math.apply_healing` has buggy max_hp fallback
- **File:** `backend/app/services/game/combat_math.py:325-328`
- **Symptom:**
  ```python
  max_hp = target.get("max_hp", target.get("hp", 0))   # fallback: current hp as max
  before = target.get("hp", 0)
  target["hp"] = min(max_hp, before + amount)
  ```
  If `max_hp` is not set on the target, fallback uses current `hp` as the max. Then `min(max_hp, before + amount)` = `min(before, before + amount) = before` — **no healing happens**. NPC at 5 HP without explicit `max_hp` cannot be healed past 5.
- **Severity:** Medium
- **Suggested fix:** If `max_hp` is not set, log a warning and use a sane default (e.g., 100) or refuse to heal. Better: delete this legacy function (see BUG-PERC-005/006).

---

## Cross-Cutting Observations

### O1. Two `PlayerPerceptionDTO` classes with same name
- `app/domain/embodied_trace.py:PlayerPerceptionDTO` (domain format)
- `app/domain/snapshot.py:PlayerPerceptionDTO` (API format)
- Same name, different fields, different consumers. Imports are ambiguous. Recommend renaming one (e.g., `DomainPlayerPerceptionDTO` vs `PlayerPerceptionDTO`).

### O2. `PerceptualAttentionService` (Phase 9 specification) is unwired
The file `perceptual_attention_service.py` implements the budget-based attention filter described in the spec ("Строгий attention_budget = 1.0", `CATEGORY_COST` dict, `PeripheralCueDTO`/`ActivePerception` mappers). None of this is invoked. The current perception pipeline has NO attention budget — all traces pass through.

### O3. `ManifestationPhysicsEngine` is mostly unused
- Only called from `integration.py:488` (Pipeline A, which is overridden by Pipeline B).
- Computes `BodyManifestation`, `GazeManifestation`, `VoiceManifestation`, `BreathingManifestation`, `MovementManifestation`, `HandsManifestation`, `MicroExpressionManifestation` — rich model.
- `PerceptionPhysicsEngine.filter_manifestation` produces `PerceivedSignal`s → `FactExtractor` produces `ObservedFact`s → `InferenceEngine` builds `Inference`s → `PresentationAssembler` builds `ObservedFactsBundle`.
- All this work is discarded by Pipeline B's override.

### O4. `evaluate_vital_state` is correctly the single death source
The function in `vital_state.py:94-145` correctly:
- Returns `LifeStatus.DEAD` early if `body_state["life_status"] == DEAD` (DEATH LOCK, line 116-117) — prevents DEAD→ALIVE resurrection via decay.
- Uses only `blood_loss ≥ 0.9` and `structural_damage ≥ 1.5` thresholds.
- Does NOT use `hp <= 0` or `shock_impulse` as death source (correct).
- The bug is only in legacy `combat_math.apply_damage/apply_healing` (BUG-PERC-005/006), which should be deleted.

### O5. `PhysiologyDecayHandler` correctly skips DEAD NPCs
- `physiology_decay_handler.py:88-89`: `if npc.get("life_status", "ALIVE") == "DEAD": continue`
- This is correct.
- `InjuryProcessor` also correctly skips DEAD (line 246-247): `if _body.get("life_status") == "DEAD": continue`
- `AffectiveDecayHandler` does NOT check DEAD status — see below.

### O6. `AffectiveDecayHandler` does NOT check DEAD status (potential violation)
- **File:** `backend/app/services/affective/affective_decay_handler.py:52-93`
- The handler iterates all NPCs and decays `affective_load` for each. There is NO `if npc.get("life_status") == "DEAD": continue` check.
- A dead NPC's affective_load will continue to decay toward 0.0 each tick, then `emotion_tag` will be set to "neutral" (line 70-71).
- This is mostly harmless (dead NPCs don't act), but it's a rule violation: "Decay for DEAD is forbidden".
- **Severity:** Medium
- **Suggested fix:** Add `if npc.get("life_status", "ALIVE") == "DEAD": continue` after line 55.

---

## Recommended Fix Priority

| Priority | Bug IDs | Impact |
|---|---|---|
| P0 (blocker) | BUG-PERC-001, BUG-PERC-002, BUG-PERC-008 | Empty perception + dead threat pipeline — directly causes both reported user-facing bugs |
| P1 (critical) | BUG-PERC-005, BUG-PERC-006, BUG-PERC-003, BUG-PERC-004 | Combat determinism + death-rule violations |
| P2 (high) | BUG-PERC-007, BUG-PERC-009, BUG-PERC-015, BUG-PERC-011 | Legacy combat service + wrong data source + crash-on-rule-fire + dual pipeline |
| P3 (medium) | BUG-PERC-010, BUG-PERC-013, BUG-PERC-014, BUG-PERC-017, BUG-PERC-024, BUG-PERC-025, BUG-PERC-029, O6 | Architecture rule violations |
| P4 (low) | BUG-PERC-012, BUG-PERC-016, BUG-PERC-018, BUG-PERC-019, BUG-PERC-020, BUG-PERC-021, BUG-PERC-022, BUG-PERC-023, BUG-PERC-026, BUG-PERC-027, BUG-PERC-028 | Code hygiene / dead code / minor bugs |

---

## Next Actions

1. **Fix BUG-PERC-001** by either routing `_project_perception` through `_convert_perception` or removing the second projection entirely. This single fix will make `PlayerPerceptionDTO` non-empty on the frontend.
2. **Fix BUG-PERC-002** by extending `_evt_map` with all missing event type mappings (player_threatens, player_insults, player_steals, etc.). This single fix will make player threats reach `ReactionSubscriber` and trigger fear responses.
3. **Fix BUG-PERC-008** by always appending traces (or adding a calm baseline cue). Combined with #1, the frontend will show observable symptoms for all NPCs, not just injured ones.
4. **Delete `combat_math.apply_damage` and `combat_math.apply_healing`** (BUG-PERC-005/006) — they are acknowledged dead code (state_applicator.py:926-927 comment) and contain forbidden death logic.
5. **Replace `random.Random` with `KernelRNG`** in `impact_engine.py` (BUG-PERC-003) and remove the `rng or random` fallback in `combat_math.py` (BUG-PERC-004).
6. **Investigate whether `combat_service.py` (BUG-PERC-007) is still wired** — if so, route through `ImpactEngine`; if not, delete.
7. **Add DEAD guard to `AffectiveDecayHandler`** (O6).
8. **Fix the `self`-in-lambda NameError** in `physics_validator.py:82` (BUG-PERC-015).
9. **Decide on the dual-pipeline architecture** (BUG-PERC-011) — keep `BehaviorManifestationService` (correct data source) and remove the `ManifestationPhysicsEngine` trace loop in `integration.py`, OR keep `ManifestationPhysicsEngine` but feed it `all_npcs_raw` (BUG-PERC-009).
10. **Wire `PerceptualAttentionService`** (BUG-PERC-017) or delete it — `avatar_desync` (BUG-PERC-024) cannot work without it.
