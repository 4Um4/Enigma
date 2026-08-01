# ENIGMA — Spatial / Movement / Traversal Domain Analysis

**Codebase:** `/home/z/my-project/analysis/Enigma-V.0.5.3.6.7_-_-_-/`
**Scope:** `backend/app/services/spatial/*`, `backend/app/services/scene_state_manager.py`, `backend/app/services/scene_change.py`, `backend/app/services/motion/*`, `backend/app/services/phases/{movement_bridge,traversal,motion}.py`, `backend/app/domain/{movement,movement_contract,motion_core,spatial_target,traversal,traversal_schema}.py`

---

## Executive Summary

The spatial domain is **internally inconsistent** with its own stated architecture rules.
The biggest functional breakages are:

1. **Cross-loc materialize destroys the original bed target** — NPC ends up stuck at a boundary node (`exit_west` / `exit_east`) instead of at `tent_*/guard_bed*`. This is the direct cause of Bug #1 and Bug #2 from the logs.
2. **`find_path` searches for `start_node` in the TARGET's zone, not the NPC's zone** — latent landmine; works today only because the cross-loc intercept rewrites the target to a same-zone boundary node first.
3. **`player_spatial` is still read as the source of truth for the player** inside `_enrich_local_positions` — direct violation of the "player_spatial is DEAD" rule.
4. **No `transition_traversal()` FSM is invoked from `SceneStateManager`** — the FSM exists in `traversal_schema.py` but the SSM only writes raw `status="MOVING"` via `build_traversal_dict`; `transition_traversal` is dead code.
5. **(0.0, 0.0) sentinel leaks** in `_enrich_local_positions`, `event_compiler`, `spatial_observatory_service._extract_pos`.
6. **`cluster_relation` is broken** — unused `neighbors` variable + a check that always returns `"adjacent"`.
7. **Debug `print()` calls left in `find_path`** in production code.

Below is the per-bug ledger.

---

## BUG-SPATIAL-001 — Cross-loc materialize loses the original bed target

- **File:line** — `backend/app/services/spatial/movement_engine.py:323` (rewrite) and `:269-289` (materialize lookup)
- **Symptom** — NPCs end up at `loc=city_gate, node=exit_west` (or `exit_east` in target loc) when their schedule said `tent_*/guard_bed*`. The original bed intent is silently replaced by a boundary node.
- **Root cause** — The cross-loc intercept **mutates** `intent.target_node_id` in place:

  ```python
  # movement_engine.py:322-324
  intent.target_node_id = boundary_node.node_id.split(":")[-1]   # was "guard_bed", now "exit_west"
  intent.location_id = current_loc
  target_loc = current_loc
  ```

  Then, once the NPC reaches the boundary, the materialize block tries to look up the bed in the **new** location using the *already-rewritten* `intent.target_node_id`:

  ```python
  # movement_engine.py:269-272
  _target_node_id_short = intent.target_node_id.split(":")[-1]   # "exit_west", NOT "guard_bed"!
  target_node_obj = target_svc.get_node(_target_node_id_short) or \
                    target_svc.get_node(f"{target_loc}:{_target_node_id_short}")
  ```

  That lookup either returns the *opposite* boundary in the target loc, or falls back to `entry_node_hint` (also a boundary node). The actual bed (`guard_bed`) is never queried because the original target string was overwritten on the previous tick.
- **Severity** — **Critical**. Directly reproduces Bug #1 / Bug #2 from the logs.
- **Suggested fix**
  1. Do **not** mutate `intent.target_node_id`. Keep a separate field `intent._boundary_node_id` (or local variable `pending_target_node_id`) for the boundary step.
  2. At materialize time, look up the **original** target in `target_svc`:
     ```python
     original_target = intent.target_node_id  # never overwritten
     target_node_obj = target_svc.get_node(original_target) or \
                       target_svc.get_node(f"{target_loc}:{original_target}")
     ```
  3. If the original target genuinely does not exist in the target loc, raise `SimulationIntegrityError` (already present at line 284) — do **not** silently fall back to `entry_node_hint` (a boundary node), because that produces a "stuck at exit" NPC.

---

## BUG-SPATIAL-002 — `find_path` finds `start_node` in the TARGET's zone

- **File:line** — `backend/app/services/spatial/spatial_service.py:526`
- **Symptom** — When `find_path` is ever invoked with a `target_node` whose `zone_id` differs from the NPC's actual zone, the returned path begins at the nearest node in the *target* zone to the NPC's xy — usually a boundary node. The NPC's true start node is dropped, the path is wrong, and `path_nodes[0]` does not correspond to where the NPC actually is.
- **Root cause**

  ```python
  # spatial_service.py:525-526
  # Находим стартовый узел (ближайший к start_xy в той же зоне)
  start_node = self.get_nearest(target_node.zone_id, start_xy, urgency)
  ```

  The comment says "in the same zone" but the code uses `target_node.zone_id`, assuming the NPC is already in the target's zone. `get_nearest` then filters candidates by `n.zone_id == zone_id` (`spatial_service.py:692`), so any cross-zone call silently returns a wrong-zone start node.
- **Severity** — **High**. Currently masked because the cross-loc intercept rewrites the target to a same-zone boundary node before `find_path` is called. Any future code path that calls `find_path` directly (e.g., `event_compiler._find_path`, `spatial_observatory_service._calculate_path`) without the intercept will hit this bug.
- **Suggested fix**
  - Either accept `start_zone` as an explicit parameter:
    ```python
    def find_path(self, start_xy, target_node, urgency=Urgency.NORMAL, start_zone: Optional[str] = None):
        zone = start_zone or target_node.zone_id
        start_node = self.get_nearest(zone, start_xy, urgency)
    ```
  - Or drop the zone filter and use a global nearest-node lookup. The zone filter is not a correctness requirement for A*; it is a (broken) performance hint.

---

## BUG-SPATIAL-003 — `print()` debug statements left in `find_path`

- **File:line** — `backend/app/services/spatial/spatial_service.py:528, 531, 534, 600`
- **Symptom** — Production stdout is polluted with `[FIND_PATH_DIAG]` lines on every pathfinding call. In a server context these go to the request stream / log shipper and corrupt structured logs.
- **Root cause** — Direct `print()` calls were added for debugging and never converted to `logger.debug(...)`.
- **Severity** — **Low** (operational hygiene).
- **Suggested fix** — Replace all four `print(f"[FIND_PATH_DIAG] ...")` calls with `logger.debug(...)`.

---

## BUG-SPATIAL-004 — `player_spatial` is still read as the source of truth

- **File:line** — `backend/app/services/scene_state_manager.py:1019-1030` (initialization), `:1681-1696` (`_enrich_local_positions`)
- **Symptom** — The architecture rule states "player_spatial is DEAD; truth is in `npc_positions['player']`". But `_enrich_local_positions` does the opposite:

  ```python
  # scene_state_manager.py:1677-1696
  # ADR-048 FIX: Синхронизация позиционной истины игрока.
  # Фронтенд пишет в player_spatial, бэкенд читает npc_positions.
  if npc_id == "player":
      _ps = scene_state.get("player_spatial", {})
      _plp = _ps.get("local_position", {})
      if isinstance(_plp, dict) and isinstance(_plp.get("x"), (int, float)):
          entry["local_position"] = _plp
          ...
          entry["position"] = _p_node_id
      continue  # Игрок не нуждается в enrichment из editor_coords
  ```

  And the scene is still initialised with a `player_spatial` block at line 1019.
- **Root cause** — The "player_spatial is DEAD" rule was only partially applied: writes were disabled (`update_player_target` lines 569-570 are commented out) but reads from `player_spatial` are still active as the authoritative source for the player's `local_position`. The result is **double truth**: `npc_positions["player"]` exists, but its `local_position` is overwritten from `player_spatial` on every load.
- **Severity** — **High**. If `player_spatial` is stale or empty (e.g., on a fresh save), the player's `local_position` becomes empty / `(0,0)` and `find_path` for NPCs approaching the player fails.
- **Suggested fix**
  1. Stop reading `player_spatial` in `_enrich_local_positions`. Let the player flow through the same `editor_coords` / `svc.get_node(current_node)` path as every other NPC.
  2. Remove the `"player_spatial": {...}` block from scene initialization (line 1019).
  3. Remove the `player_spatial` parameter from `update_player_target` (line 539) entirely.

---

## BUG-SPATIAL-005 — `transition_traversal()` FSM is dead code

- **File:line** — `backend/app/domain/traversal_schema.py:55-78` (FSM), `backend/app/services/scene_state_manager.py:1210-1234` (writes status directly)
- **Symptom** — The architecture rule says "Status mutation bypassing `transition_traversal()` FSM" is forbidden. But:
  - `build_traversal_dict` (`traversal_schema.py:171-190`) hard-codes `"status": "MOVING"`.
  - `SSM.apply_change` calls `build_traversal_dict` and stores the result directly into `scene_state["active_traversals"][npc_id]` (line 1232) — **no `transition_traversal` call**.
  - `TraversalExecutionSystem.advance` (line 86) writes `trav["status"] = "COMPLETED"` directly, bypassing the FSM.
  - A grep for `transition_traversal` across `backend/` finds **zero call sites** (only the definition itself).
- **Root cause** — The FSM was added but never wired in.
- **Severity** — **High**. The invariant "PENDING → MOVING → {COMPLETED, CANCELLED}" is unenforced. Any caller can write any status, including illegal transitions (e.g., `COMPLETED → MOVING` "zombie revival").
- **Suggested fix**
  1. In `build_traversal_dict`, start at `"PENDING"` and then call `transition_traversal(d, "MOVING")`.
  2. In `TraversalExecutionSystem.advance`, replace `trav["status"] = "COMPLETED"` with `transition_traversal(trav, "COMPLETED")`.
  3. In `SSM.apply_change`, when receiving `cause="traversal_complete"`, call `transition_traversal(active_travs[npc_id], "COMPLETED")` instead of relying on the ExecutionSystem to flip the status separately.

---

## BUG-SPATIAL-006 — `(0.0, 0.0)` sentinel leaks

The architecture rule says: "local_position (0.0, 0.0) is FORBIDDEN unless explicitly valid". The following sites violate this:

### BUG-SPATIAL-006a — SSM template NPC fallback
- **File:line** — `backend/app/services/scene_state_manager.py:977`
- **Code**
  ```python
  pos_entry.setdefault("local_position", {"x": 0.0, "y": 0.0})
  ```
- **Symptom** — An NPC present in the template's `npc_defaults` but missing from the editor JSON gets `local_position = (0, 0)`. Subsequent `euclidean_distance` treats this as "no data" only when the *other* entity is also at (0,0) (see BUG-SPATIAL-007).
- **Severity** — **High**.
- **Suggested fix** — Refuse to create the NPC entry; log an error and skip. NPCs without editor coordinates are a data-integrity bug, not a fallback case.

### BUG-SPATIAL-006b — SSM apply_change `from_xy`
- **File:line** — `backend/app/services/scene_state_manager.py:1186-1190`
- **Code**
  ```python
  from_xy = entry.get("local_position", {"x": 0.0, "y": 0.0})
  if not isinstance(from_xy, dict):
      from_xy = {"x": 0.0, "y": 0.0}
  ```
- **Symptom** — `from_xy` is captured (apparently for an audit log) but never used after line 1190. The (0,0) default is dead, but the code is misleading.
- **Severity** — **Low** (dead code).
- **Suggested fix** — Either delete the unused `from_xy` block, or actually use it (e.g., log the movement delta for telemetry).

### BUG-SPATIAL-006c — event_compiler `_resolve_source_xy` fallback
- **File:line** — `backend/app/services/event_compiler.py:311-312, 749-750`
- **Code**
  ```python
  # S-142.1: Честный source_xy из snapshot. Нельзя подставлять (0.0, 0.0) — это ложный факт.
  _src_xy = (0.0, 0.0)            # <-- comment forbids it, code does it
  ...
  # E7: Fallback (0, 0) — устраняется в Gen 3 (perceive_world)
  return (0.0, 0.0)
  ```
- **Symptom** — When an NPC has no `local_position` in the snapshot and no resolvable node, `event_compiler` constructs a `SpatialResolution` with `source_xy=(0.0, 0.0)`. This propagates to `ThickSceneChange` and into shadow validation, where it can mask real movement failures (any "did the NPC move?" check against (0,0) becomes trivially true).
- **Severity** — **High**.
- **Suggested fix** — Raise `SimulationIntegrityError` if source_xy cannot be resolved. The comment already says (0,0) is a "false fact" — enforce it.

### BUG-SPATIAL-006d — spatial_observatory_service `_extract_pos`
- **File:line** — `backend/app/services/spatial/spatial_observatory_service.py:228, 233, 238, 239`
- **Code**
  ```python
  if not isinstance(data, dict):
      return (0.0, 0.0)
  ...
  if x is None or y is None: return (0.0, 0.0)
  ...
  except (TypeError, ValueError): return (0.0, 0.0)
  return (0.0, 0.0)
  ```
- **Symptom** — Observatory projections silently fall back to (0,0) for malformed agent data. Observatory is supposed to be a *diagnostic* tool; hiding malformed input defeats its purpose.
- **Severity** — **Medium**.
- **Suggested fix** — Return `None` and surface a diagnostic DTO with code `MALFORMED_AGENT_POS`.

---

## BUG-SPATIAL-007 — `euclidean_distance` only treats (0,0) as missing if BOTH ends are (0,0)

- **File:line** — `backend/app/services/spatial/spatial_runtime.py:71-83`
- **Code**
  ```python
  ax, ay = _local(a)
  bx, by = _local(b)
  # если обе позиции (0,0) по умолчанию — считаем что данных нет
  if ax == 0.0 and ay == 0.0 and bx == 0.0 and by == 0.0:
      return 999.0
  return round(math.hypot(ax - bx, ay - by), 2)
  ```
- **Symptom** — If only one entity is at the (0,0) sentinel (e.g., an NPC with a corrupt `local_position`), the function returns the real Euclidean distance between (0,0) and the other entity's actual position. This is then consumed by perception/attention/social engines as if it were a real distance, producing false "NPC is X meters away" facts.
- **Root cause** — The sentinel check is too narrow. It was probably written defensively for the case where both entities had no position, but the (0,0) sentinel can leak from a single entity (BUG-SPATIAL-006a/b/c).
- **Severity** — **High**.
- **Suggested fix**
  ```python
  if (ax == 0.0 and ay == 0.0) or (bx == 0.0 and by == 0.0):
      return 999.0
  ```
  Or, better, make `_local` return `None` when `local_position` is missing entirely, and propagate `None` through `euclidean_distance`.

---

## BUG-SPATIAL-008 — `cluster_relation` always returns "adjacent"

- **File:line** — `backend/app/services/spatial/spatial_query_service.py:81-98`
- **Code**
  ```python
  def cluster_relation(self, entity_a, entity_b):
      ...
      if cl_a == cl_b:
          return "same"
      neighbors = self._cluster_occupancy.cluster_to_entities.get(cl_a, set())  # UNUSED
      return (
          "adjacent"
          if cl_b in self._cluster_occupancy.cluster_to_entities   # WRONG CHECK
          else "distant"
      )
  ```
- **Symptom** — `cluster_to_entities` is a dict mapping `cluster_id → set[entity_id]`. The check `cl_b in self._cluster_occupancy.cluster_to_entities` tests whether `cl_b` is a *key* in that dict — i.e., whether cluster B exists at all. Since we just resolved `cl_b` from `get_cluster(entity_b)`, it always exists. Therefore `cluster_relation` returns `"adjacent"` for **any** two entities in different clusters, never `"distant"`.
- **Root cause** — The variable `neighbors` was meant to be the set of neighbor cluster IDs of `cl_a`, and the check was supposed to be `cl_b in neighbors`. But `cluster_to_entities` is the wrong data structure (it maps cluster → entities, not cluster → neighbor clusters), and the `neighbors` variable was never used.
- **Severity** — **Medium**. Affects any consumer that branches on `cluster_relation` (e.g., perception range scaling, social decay).
- **Suggested fix** — Either:
  - Add a `cluster_to_neighbors: dict[str, set[str]]` field to `ClusterOccupancy` and check `cl_b in cluster_to_neighbors.get(cl_a, set())`.
  - Or, if neighbor data isn't available, delete the "adjacent" branch and only return `"same"` / `"distant"`.

---

## BUG-SPATIAL-009 — `SpatialRegistry.find_artifact` has a missing `return None`

- **File:line** — `backend/app/services/spatial/spatial_registry.py:122-140`
- **Code**
  ```python
  @classmethod
  def find_artifact(cls, campaign_id: str) -> Optional[Path]:
      ...
      candidate = (project_root / "frontend" / "map_editor" / "campaigns" / campaign_id / "compiled" / "spatial_registry.json")
      if candidate.exists():
          return candidate
      # ← implicit return None
  ```
- **Symptom** — Function works correctly (Python returns `None` implicitly) but the code is unclear. More importantly, the function only checks one path; there is no fallback for campaigns stored in `data/campaigns/` (which is where `SceneStateManager` looks for templates).
- **Severity** — **Low**.
- **Suggested fix** — Add an explicit `return None` and a second candidate path aligned with `SceneStateManager._state_file`.

---

## BUG-SPATIAL-010 — `SpatialService.__init__` assigns `self._spatial_obstacles` twice

- **File:line** — `backend/app/services/spatial/spatial_service.py:132` and `:134`
- **Code**
  ```python
  self._spatial_obstacles = spatial_obstacles or []  # ADR-O-324   (line 132)
  self._affordance_objects = affordance_objects or []  # ADR-O-330  (line 133)
  self._spatial_obstacles = spatial_obstacles or []  # ADR-O-324    (line 134) ← duplicate
  ```
- **Symptom** — No functional impact (idempotent assignment). But the duplicate suggests a merge artifact and can hide a real bug if someone later changes one of the two lines.
- **Severity** — **Low**.
- **Suggested fix** — Delete line 134.

---

## BUG-SPATIAL-011 — `motion_pipeline.py` uses `Optional[Dict[str, dict]]` without importing it

- **File:line** — `backend/app/services/motion/motion_pipeline.py:11, 38, 88, 122`
- **Code**
  ```python
  from typing import TYPE_CHECKING, Tuple     # ← no Optional, no Dict
  ...
  def apply(
      drive: DriveVector,
      pos: Tuple[float, float],
      topology: "WorldTopologyProvider",
      region: str,
      npc_positions: Optional[Dict[str, dict]] = None,   # ← undeclared names
      current_npc_id: Optional[str] = None,
  ) -> DriveVector:
  ```
- **Symptom** — Today this works because `from __future__ import annotations` (line 8) makes annotations strings, so they're never evaluated. But any caller that does `typing.get_type_hints(CollisionAvoidance.apply)` (e.g., a future serializer or runtime contract checker) will hit `NameError: name 'Optional' is not defined`.
- **Severity** — **Low** (latent).
- **Suggested fix** — Change import to `from typing import TYPE_CHECKING, Any, Dict, Optional, Tuple`.

---

## BUG-SPATIAL-012 — `is_reachable` lies about disconnected nodes

- **File:line** — `backend/app/services/spatial/spatial_service.py:728-732`
- **Code**
  ```python
  def is_reachable(self, node: NodeRef, urgency: Urgency = Urgency.NORMAL) -> bool:
      """Проверяет достижимость узла с учётом overlay."""
      if node.node_id in self._overlay.blocked_nodes:
          return urgency == Urgency.URGENT
      return node.node_id in self._graph
  ```
- **Symptom** — Returns `True` for any node present in the graph, regardless of whether A* can actually reach it from the NPC's current position. The name "reachable" implies connectivity; the implementation only checks membership.
- **Severity** — **Medium**. Any consumer that uses `is_reachable` to pre-filter targets will not catch disconnected nodes (e.g., orphan rooms created by `_validate_navigation_geometry` edge removal).
- **Suggested fix** — Rename to `is_present_in_graph` (and add a real `is_reachable_from(start_node, target_node)` that calls A*), or actually call A* inside `is_reachable`.

---

## BUG-SPATIAL-013 — `euclidean_distance` returns `999.0` instead of a sentinel

- **File:line** — `backend/app/services/spatial/spatial_runtime.py:82`
- **Symptom** — Magic number `999.0` is used as "no data". Consumers (e.g., `player_target_pipeline.build_spatial_data_for_dm`) explicitly filter `if _dist is None: continue` because they know 999.0 is a sentinel, but other consumers (perception, social engine) may treat 999.0 as a real "very far" distance.
- **Severity** — **Low**.
- **Suggested fix** — Return `Optional[float]` and let callers handle `None` explicitly. Or define a module-level constant `DISTANCE_UNKNOWN = -1.0` that fails any `<` comparison.

---

## BUG-SPATIAL-014 — `update_npc_position` is dead code that bypasses the TraversalState contract

- **File:line** — `backend/app/services/scene_state_manager.py:1853-1883`
- **Code** — The method directly writes `entry["position"] = position` and `entry["local_position"] = {"x": node.x, "y": node.y}` without creating a `TraversalState`, without going through `apply_change`, and without `transition_traversal`.
- **Symptom** — A grep for `update_npc_position` across `backend/` finds **zero call sites**. The method is dead, but its existence is a footgun: any future caller would bypass the entire movement contract (no SceneChange, no TraversalProposal, no FSM transition).
- **Severity** — **Low** (today), **High** (latent).
- **Suggested fix** — Delete the method. If external callers ever need this, route them through `apply_change` with `cause="external_position_update"`.

---

## BUG-SPATIAL-015 — `resolve_affordance` returns nearest nav node in the WRONG zone

- **File:line** — `backend/app/services/spatial/spatial_service.py:327-377`
- **Code**
  ```python
  # find closest object with affordance (e.g., bed) — works globally
  ...
  # but then return nearest NAV node in origin_zone:
  zone = origin_zone or self._location_id
  return self.get_nearest(zone, (best_obj["x"], best_obj["y"]))
  ```
- **Symptom** — If the closest bed object is in `tent_1` but `origin_zone="tavern"`, `get_nearest("tavern", (bed_x, bed_y))` returns the nearest *tavern* node to the bed's coordinates — usually the boundary node `tavern:exit_east`. The NPC is then routed to that boundary node instead of to the bed.
- **Root cause** — The zone filter assumes the affordance object is in the same zone as the NPC. For sleep schedules where the bed is in another chunk, this is wrong.
- **Severity** — **High**. Combined with `LifeEngine._resolve_position` calling `resolve_affordance` for `NodeRole.BED` (`life_engine.py:2447-2453`), this is a second path that routes NPCs to boundary nodes instead of beds.
- **Suggested fix** — Drop the zone filter in `resolve_affordance`'s final `get_nearest` call, or accept `target_zone` as a parameter and pass the bed object's actual zone (which the compiler knows from the editor JSON).

---

## BUG-SPATIAL-016 — `find_path` does not check `target_node` existence explicitly

- **File:line** — `backend/app/services/spatial/spatial_service.py:510-535`
- **Code**
  ```python
  def find_path(self, start_xy, target_node, urgency=Urgency.NORMAL):
      if target_node is None:
          return []
      target_id = target_node.node_id
      start_node = self.get_nearest(target_node.zone_id, start_xy, urgency)
      ...
  ```
- **Symptom** — `find_path` only checks `target_node is None`. It does not verify that `target_node.node_id` is actually in `self._graph`. If a caller passes a `NodeRef` from a different loc's graph (which happens if `target_node` is cached across loc switches), the A* loop iterates connections but never finds `target_id`, falls through to the "no path" warning, and returns `[]`. The caller then sees `A_STAR_FAILED` when the real cause was `TARGET_NODE_NOT_IN_GRAPH`.
- **Severity** — **Medium** (diagnostic clarity).
- **Suggested fix**
  ```python
  if target_node is None or target_node.node_id not in self._graph:
      logger.warning(f"[FIND_PATH] target {target_id} not in graph (loc={self._location_id})")
      return []
  ```

---

## BUG-SPATIAL-017 — `try_reserve_node` allows double-occupancy under URGENT

- **File:line** — `backend/app/services/spatial/spatial_overlay.py:72-104`
- **Code**
  ```python
  if urgency == "urgent":
      # URGENT: снижаем штраф, но не выкидываем другого NPC
      # Возвращаем True, но с предупреждением
      logger.debug(...)
      return True
  ```
- **Symptom** — Under `urgency="urgent"`, `try_reserve_node` returns `True` even if the node is held by another NPC. The caller then proceeds as if the reservation succeeded, but `overlay.reserved_nodes` is **not** updated — the original holder is still recorded. This creates a "phantom reservation": the URGENT NPC thinks it owns the node, the overlay says the other NPC owns it, and the next URGENT caller also gets `True`.
- **Severity** — **Medium**.
- **Suggested fix** — Either:
  - Actually evict the previous holder: `overlay.reserved_nodes[node_id] = npc_id` and log the eviction.
  - Or return `False` and force the caller to find an alternative node.

---

## BUG-SPATIAL-018 — `apply_changes` zombie-cleanup uses `TRAVERSAL_TRANSITIONS` semantics that conflict with `build_traversal_dict`

- **File:line** — `backend/app/services/scene_state_manager.py:1347-1362`
- **Code**
  ```python
  _zombie_ids = [
      nid for nid, t in list(_active_traversals.items())
      if not TRAVERSAL_TRANSITIONS.get(t.get("status", ""), set())
  ]
  for _zid in _zombie_ids:
      del _active_traversals[_zid]
  ```
- **Symptom** — `TRAVERSAL_TRANSITIONS` maps terminal statuses (`COMPLETED`, `CANCELLED`) to `set()`. The zombie-cleanup deletes any traversal whose status has no outgoing transitions. But:
  - `build_traversal_dict` creates traversals with `status="MOVING"` directly, skipping `PENDING`. So a freshly created traversal is already in a "live" state — fine.
  - `TraversalExecutionSystem.advance` flips `MOVING → COMPLETED` directly. The zombie-cleanup then deletes it on the next `apply_changes` call. **But `apply_changes` is called BEFORE `advance` in the tick order** (`advance` is Phase 0.5, `apply_changes` is via MovementBridge in Phase 5). So a traversal that just completed in `advance` survives one extra tick, during which `npc_positions[npc_id].position` is still the old node.
- **Severity** — **Medium** (one-tick-stale traversal state).
- **Suggested fix** — Run zombie-cleanup AFTER `TraversalExecutionSystem.advance`, or have `advance` itself call `transition_traversal(trav, "COMPLETED")` and let the SSM observe.

---

## BUG-SPATIAL-019 — `event_compiler` ghost interpolation is linear start→end, not multi-waypoint

- **File:line** — `backend/app/services/event_compiler.py:712-728`
- **Code**
  ```python
  interp_x = wp[0][0] + (wp[-1][0] - wp[0][0]) * prog
  interp_y = wp[0][1] + (wp[-1][1] - wp[0][1]) * prog
  ```
- **Symptom** — The shadow compiler interpolates the NPC's position as a straight line from `wp[0]` to `wp[-1]`, ignoring intermediate waypoints. The authoritative `TraversalExecutionSystem._interpolate_path` (`traversal_execution_system.py:147-201`) does proper segment-by-segment interpolation. The two diverge whenever the path bends (e.g., around a wall), causing the shadow vs. legacy validator to flag false-positive drift.
- **Severity** — **Medium**.
- **Suggested fix** — Replace the two-line interpolation with a call to `TraversalExecutionSystem._interpolate_path(wp, prog, segment_modes, segment_arc_heights)`.

---

## BUG-SPATIAL-020 — `MovementEngine._spatial_intent_gate` is dead code (called from `process_intents` only)

- **File:line** — `backend/app/services/spatial/movement_engine.py:71-118`
- **Symptom** — `_spatial_intent_gate` is defined and called inside `process_intents` (line 179), but its only effect is to **skip** intents where `current_pos == target_pos`. This is the same check that `_resolve_macro_relocation` does at line 658 (`if current_pos and current_pos == intent.target_node_id: return []`). So the gate is a duplicate no-op filter that adds log noise without changing behavior.
- **Severity** — **Low** (code clarity).
- **Suggested fix** — Either delete the gate (rely on the resolver's check) or make the resolver's check delegate to the gate.

---

## BUG-SPATIAL-021 — `movement_engine.py` declares `logger` twice

- **File:line** — `backend/app/services/spatial/movement_engine.py:9` and `:37`
- **Code**
  ```python
  import logging
  logger = logging.getLogger(__name__)    # line 9

  import math
  from typing import Any, Dict, List, Optional
  ...
  from app.services.spatial.local_traversal_planner import LocalTraversalPlanner

  logger = logging.getLogger(__name__)    # line 37 (duplicate)
  ```
- **Symptom** — No functional impact (same module name → same logger). Suggests a botched merge.
- **Severity** — **Low**.
- **Suggested fix** — Delete the second `logger = ...` line.

---

## BUG-SPATIAL-022 — `spatial_target_resolver.py` swallows `ValueError` with `pass`

- **File:line** — `backend/app/services/spatial/spatial_target_resolver.py:77-78`
- **Code**
  ```python
  try:
      role_enum = NodeRole(target_id)
      node = self._spatial_service.resolve_node(role=role_enum, origin_zone=location_id)
  except ValueError:
      pass  # Строка не соответствует ни одной роли NodeRole
  ```
- **Symptom** — The `pass` is technically correct (testing whether `target_id` is a valid `NodeRole` enum value), but the pattern matches the "try/except: pass" anti-pattern the audit looks for. More importantly, if `resolve_node` itself raises `ValueError` for an unrelated reason (e.g., bad `origin_zone` type), the exception is silently swallowed.
- **Severity** — **Low**.
- **Suggested fix** — Test the enum membership explicitly:
  ```python
  if target_id in {r.value for r in NodeRole}:
      role_enum = NodeRole(target_id)
      node = self._spatial_service.resolve_node(role=role_enum, origin_zone=location_id)
  ```

---

## BUG-SPATIAL-023 — `tick_orchestrator.py` silently swallows `SpatialRegistry` load errors

- **File:line** — `backend/app/services/tick_orchestrator.py:527-533` and `:1260-1265`
- **Code**
  ```python
  try:
      from app.services.spatial.spatial_registry import SpatialRegistry
      _reg = SpatialRegistry.get_or_load(campaign_id)
      if _reg:
          _connected = [e.location_b for e in _reg.get_neighbors(active_location_id)]
  except Exception:
      pass
  ```
  And:
  ```python
  try:
      _traits = self.memory_manager.get_identity_traits(ctx.campaign_id, _nid)
      ...
  except Exception:
      pass
  ```
- **Symptom** — Bare `except Exception: pass` with no logging. If `SpatialRegistry.get_or_load` fails (e.g., corrupt JSON, permission error), the orchestrator silently falls back to "no neighbors" — which then disables full ticking for connected locations (`_tick_fully` defaults to False). The world freezes with no error message.
- **Severity** — **Medium**.
- **Suggested fix** — At minimum `logger.warning(f"[SPATIAL_REGISTRY] load failed: {e}")`. Better: let the exception propagate to the tick-level catch-all so it shows up in `TICK_CRASH`.

---

## BUG-SPATIAL-024 — `movement_engine` cross-loc intercept silently drops intent when no boundary found

- **File:line** — `backend/app/services/spatial/movement_engine.py:326-338`
- **Code**
  ```python
  else:
      logger.warning(
          f"[CROSS_LOC_INTERCEPT] No boundary node in {current_loc} to {target_loc} for {intent.actor_id}"
      )
      # ADR-O-314: Нет boundary node — кросс-локационный роутинг невозможен.
      # Дропаем интент, чтобы предотвратить невалидный SceneChange (SHADOW_COMPILER FAILED).
      continue
  ...
  else:
      logger.warning(
          f"[CROSS_LOC_INTERCEPT] No SpatialService for current_loc={current_loc}"
      )
      # Нет SpatialService — нет валидации маршрута. Дропаем интент.
      continue
  ```
- **Symptom** — When the boundary graph is incomplete (e.g., `tent_1` is not registered as a neighbor of `city_gate` in the editor JSON's `adjacency` map), the NPC's sleep intent is dropped every tick. The NPC stays awake at their current node, never reaches the bed, and no error propagates to the player.
- **Severity** — **Medium**.
- **Suggested fix** — Raise `SimulationIntegrityError` with `invariant_id="INV-CROSS-LOC-NO-BOUNDARY"` so the map author can fix the adjacency. Silent drops hide map configuration bugs.

---

## BUG-SPATIAL-025 — `_enrich_local_positions` uses `get_nearest(zone=location_id)` for player, ignoring player's actual chunk

- **File:line** — `backend/app/services/scene_state_manager.py:1685-1696`
- **Code**
  ```python
  _p_node_ref = svc.get_nearest(
      zone_id=location_id, origin_xy=(_px, _py)
  )
  if _p_node_ref:
      _p_node_id = getattr(_p_node_ref, "node_id", str(_p_node_ref))
      if _p_node_id.startswith(f"{location_id}:"):
          _p_node_id = _p_node_id.split(":")[-1]
      entry["position"] = _p_node_id
  ```
- **Symptom** — `svc` is built for `scene_state.location_id`. If the player is actually in a different chunk (e.g., walked through a boundary into `tent_1` but `scene_state.location_id` is still `city_gate`), `get_nearest(zone="city_gate", xy=(player_xy_in_tent_1))` returns the nearest *city_gate* node to the player's tent_1 coordinates — usually `city_gate:exit_east`. The player's `position` is then set to `exit_east`, which is wrong.
- **Root cause** — Same family as BUG-SPATIAL-002 and BUG-SPATIAL-015: zone-filtered nearest-node lookup assumes the entity is in the filtered zone.
- **Severity** — **Medium**.
- **Suggested fix** — Use `get_nearest_safe_node` (which doesn't filter by zone, only excludes isolated nodes) or pass the player's actual `location_id` from `entry["location_id"]` instead of `scene_state.location_id`.

---

## BUG-SPATIAL-026 — `TraversalExecutionSystem.advance` does not call `transition_traversal`

- **File:line** — `backend/app/services/spatial/traversal_execution_system.py:86-87`
- **Code**
  ```python
  trav["status"] = "COMPLETED"
  completed_npcs.append(npc_id)
  ```
- **Symptom** — Direct status mutation, bypassing the FSM in `traversal_schema.py`. Combined with BUG-SPATIAL-005, this means **no code anywhere** calls `transition_traversal`.
- **Severity** — **High** (architectural invariant violation).
- **Suggested fix** — `from app.domain.traversal_schema import transition_traversal; transition_traversal(trav, "COMPLETED")`.

---

## BUG-SPATIAL-027 — `phases/traversal.py` materialize emits `local_position` snap without `traversal_proposal`

- **File:line** — `backend/app/services/phases/traversal.py:104-117`
- **Code**
  ```python
  if not _is_boundary and len(wp) >= 2:
      completion_changes.append(
          SceneChange(
              type=ChangeType.NPC_POSITION,
              target=npc_id,
              field="local_position",
              value={"x": wp[-1][0], "y": wp[-1][1]},
              cause="traversal_complete",
              tick=current_tick,
          )
      )
  ```
- **Symptom** — The change has `cause="traversal_complete"` and `field="local_position"`. In `SSM.apply_change`, this hits the `elif change.field in ("local_position", ...)` branch (line 1249-1255) and writes the value directly. Good. But the rule "On traversal_complete: snap local_position, don't create new TraversalState" is enforced only by the `cause` string check at line 1211. If anyone typos `cause="traversal_completed"` or `cause="traversal_complete:schedule"`, the check `getattr(change, "cause", "") != "traversal_complete"` evaluates True, and a new TraversalState is created from the (missing) proposal — which then logs `MISSING_TRAVERSAL_PROPOSAL` but does NOT crash.
- **Severity** — **Medium** (brittle string match).
- **Suggested fix** — Use an explicit flag on `SceneChange` (e.g., `is_traversal_complete: bool = False`) instead of substring matching on `cause`.

---

## BUG-SPATIAL-028 — `_resolve_macro_relocation` returns `[]` on missing target_node_obj instead of raising

- **File:line** — `backend/app/services/spatial/movement_engine.py:670-673`
- **Code**
  ```python
  target_node_obj = svc.get_node(intent.target_node_id) or svc.get_node(f"{intent.location_id}:{intent.target_node_id}")
  source_node_obj = svc.get_node(current_pos)
  if not target_node_obj:
       return []
  ```
- **Symptom** — When `target_node_obj` is missing, the function silently returns an empty list. The MovementTrace is not populated with `MovementFailure.TARGET_NODE_NOT_FOUND`, so the diagnostic pipeline (S-141) cannot distinguish this from "NPC already at target" (which also returns `[]` at line 665). The architecture rule says A* must distinguish `ALREADY_AT_TARGET` vs `A_STAR_FAILED`; here we have a third case (`TARGET_NODE_NOT_FOUND`) that is collapsed into silence.
- **Severity** — **Medium** (diagnostic loss).
- **Suggested fix**
  ```python
  if not target_node_obj:
      _trace.failure = MovementFailure.TARGET_NODE_NOT_FOUND
      _trace.path_status = PathStatus.NO_PATH
      logger.warning(f"[MOVEMENT_TRACE] npc={intent.actor_id} failure=M003 target={intent.target_node_id}")
      return []
  ```

---

## BUG-SPATIAL-029 — `SpatialOverlay.build_overlay_from_scene` uses `position` field, but `position` may be canonical OR short form

- **File:line** — `backend/app/services/spatial/spatial_overlay.py:43-57`
- **Code**
  ```python
  for npc_id, entry in npc_positions.items():
      pos = entry.get("position", "")
      if pos and entry.get("visible", True):
          overlay.reserved_nodes[pos] = npc_id
  ...
  for npc_id, entry in npc_positions.items():
      pos = entry.get("position", "")
      if pos:
          node_npc_count[pos] = node_npc_count.get(pos, 0) + 1
  ```
- **Symptom** — `reserved_nodes` is keyed by whatever string is in `entry["position"]`. As shown in BUG-SPATIAL-004, the player's position is normalized to short form (`exit_west`) while NPC positions are canonical (`city_gate:exit_west`). The graph's `node_id` is always canonical. So `resolve_node`'s reservation check `self._overlay.reserved_nodes.get(n.node_id)` (canonical) will miss the player's reservation (short form). NPCs can be routed to the player's node because the overlay says it's free.
- **Severity** — **Medium**.
- **Suggested fix** — Normalize all positions to canonical form when building the overlay. Either:
  ```python
  canon = self._spatial_service.normalize_id(pos) if self._spatial_service else pos
  overlay.reserved_nodes[canon] = npc_id
  ```
  Or, better, fix BUG-SPATIAL-004 so positions are always canonical everywhere.

---

## BUG-SPATIAL-030 — `find_path` cache key omits `start_xy`, only uses `start_node.node_id`

- **File:line** — `backend/app/services/spatial/spatial_service.py:537-546`
- **Code**
  ```python
  cache_key = (
      start_node.node_id,
      target_id,
      self._overlay.compute_hash(),
      urgency,
  )
  ```
- **Symptom** — Two calls with the same `start_node.node_id` but different `start_xy` (e.g., NPC moved within the same node's vicinity) hit the same cache entry. The cached path begins at `start_node`, not at `start_xy`, so the NPC's actual position is ignored on cache hit. This is fine for graph-level routing but wrong for `LocalTraversalPlanner`, which expects the path to start at the NPC's actual xy.
- **Severity** — **Low** (the path returned is graph-correct; the local planner handles the micro-offset).
- **Suggested fix** — Document that `find_path` returns graph-node paths only, not xy-accurate paths. Or include `start_xy` (rounded to 0.5m) in the cache key.

---

## TODO / FIXME Audit (Spatial Domain)

From `rg "TODO|FIXME|XXX"`:

| File | Line | Note |
|------|------|------|
| `spatial/player_target_pipeline.py` | 13-16 | 4 TODOs about future extensions (low priority) |
| `spatial/world_topology_provider.py` | 110, 155, 181 | "Долг" markers for `ZoneAffordanceProfile` extraction |
| `spatial/spatial_runtime.py` | 21-23 | 3 TODOs about caching and LOS optimization |
| `spatial/movement_engine.py` | 189 | "ADR-XXXX" placeholder — invariant has no ADR number assigned |
| `motion/motion_pipeline.py` | 26, 247 | TODO for Spatial Hash; TODO for affordance collision check (currently a no-op!) |
| `scene_state_manager.py` | 519, 1347, 1517 | TODO-A1 for JSON mirror removal; "ADR-XXX" placeholders |
| `phases/traversal.py` | 119, 126 | "ADR-XXX" placeholders for traversal lifecycle |

The `motion/motion_pipeline.py:247` TODO is particularly concerning:
```python
# TODO: Проверка коллизий с affordance (can_pass == 0.0 -> стена)
# Пока оставляем как есть, коллизии будут в WorldTopologyProvider.
```
`MotionIntegrator.integrate` does `position += velocity * dt` with **no collision check**. The ETKE-IK continuous motion phase can walk NPCs through walls. The TODO has been there long enough to ship in v0.5.3.6.7.

---

## `try/except: pass` and Silent-Swallow Audit (Spatial Domain)

| File:line | Pattern | Severity |
|-----------|---------|----------|
| `spatial/spatial_target_resolver.py:77-78` | `except ValueError: pass` (testing NodeRole membership) | Low |
| `spatial/spatial_registry.py:127-128` | `except (IndexError, ValueError): project_root = Path(".")` (defensive) | Low |
| `tick_orchestrator.py:532-533` | `except Exception: pass` around `SpatialRegistry.get_or_load` | Medium (BUG-SPATIAL-023) |
| `tick_orchestrator.py:1264-1265` | `except Exception: pass` around `memory_manager.get_identity_traits` | Medium |
| `scene_state_manager.py:1667-1670` | `except Exception as e: logger.error(...)` (logged, but build failure is silent — svc stays None) | Medium |
| `graph_compiler.py:784, 800, 815` | `except Exception as e: logger.error(...)` around JSON parsing (logged, returns None) | Low |
| `movement_engine.py:1244-1247` | `except Exception as exc: logger.error("[APPLY_CRASH]...")` — swallows the exception, apply_change returns False, NPC doesn't move, no upstream signal | High |

The `movement_engine.py:1244-1247` case is the most dangerous: if `build_traversal_dict` or `scene_state.setdefault("active_traversals", {})[change.target] = _traversal_dict` raises (e.g., KeyError, TypeError), the exception is logged but the SceneChange is reported as "applied=False". The MovementEngine sees `applied_count < len(changes)` but does not retry or raise. The NPC's traversal is silently lost.

---

## Architecture Rule Compliance Summary

| Rule | Status | Evidence |
|------|--------|----------|
| SpatialFactory.build_for_campaign() is the ONLY graph builder | ✅ Compliant | `spatial_factory.py` is the single entry; `spatial_service.py:48` `build_for_location` is called only from factory and observatory (which is intentionally separate) |
| SpatialQueryService is the ONLY reader of positions | ⚠️ Partial | `npc_orchestration.py:96-97` falls back to `player_spatial` despite the rule; `life_engine.py:850-863` reads `player_spatial` as fallback |
| player_spatial is DEAD | ❌ Violated | BUG-SPATIAL-004 |
| TraversalState lives in scene_state["active_traversals"] | ✅ Compliant | No competing store found |
| SceneStateManager manages TraversalState lifecycle via transition_traversal() FSM | ❌ Violated | BUG-SPATIAL-005, BUG-SPATIAL-026 — FSM is dead code |
| Cannot overwrite status="MOVING" in apply_changes | ⚠️ Partial | `apply_change` checks `!= "MOVING"` at line 1214-1216, but the check is on the *existing* status, not the *incoming* one. A second `build_traversal_dict` call would overwrite a MOVING traversal with a new MOVING traversal (different target), losing the in-progress movement. |
| On traversal_complete: snap local_position, don't create new TraversalState | ⚠️ Partial | Enforced by `cause` string match (BUG-SPATIAL-027) — brittle |
| Boundary nodes are interfaces, NOT living spaces | ❌ Violated | BUG-SPATIAL-001 — NPCs terminate at boundary nodes after materialize fallback |
| Spatial Coherence Validation SC-1 through SC-8 | ❌ Missing | No `SC-*` validation code exists; only a comment at `scene_state_manager.py:921` references "SC-1" |
| A* must distinguish ALREADY_AT_TARGET vs A_STAR_FAILED | ✅ Compliant | `find_path` returns `[start_node]` (len 1) vs `[]` (len 0); `_resolve_macro_relocation` distinguishes them at lines 699-709 |
| Single-node path [start_node] is SUCCESS, not failure | ✅ Compliant | `find_path:530-532` returns `[start_node]` |
| local_position (0.0, 0.0) is FORBIDDEN unless explicitly valid | ❌ Violated | BUG-SPATIAL-006a/b/c/d |

---

## Recommended Fix Order (by impact)

1. **BUG-SPATIAL-001** (Critical) — Fix cross-loc materialize to use original target, not rewritten boundary ID. This unblocks the sleep test.
2. **BUG-SPATIAL-005 + BUG-SPATIAL-026** (High) — Wire `transition_traversal()` FSM into `build_traversal_dict` and `TraversalExecutionSystem.advance`.
3. **BUG-SPATIAL-004** (High) — Remove `player_spatial` reads; route player through same enrichment as NPCs.
4. **BUG-SPATIAL-015** (High) — Fix `resolve_affordance` to not zone-filter the final `get_nearest` call.
5. **BUG-SPATIAL-006a + BUG-SPATIAL-007** (High) — Eliminate (0,0) sentinel in SSM template fallback; tighten `euclidean_distance` sentinel check.
6. **BUG-SPATIAL-002** (High, latent) — Make `find_path` accept `start_zone` explicitly.
7. **BUG-SPATIAL-016 + BUG-SPATIAL-028** (Medium) — Add explicit `target_node` existence check; populate `MovementTrace` on `TARGET_NODE_NOT_FOUND`.
8. **BUG-SPATIAL-008** (Medium) — Fix `cluster_relation` to use real neighbor data.
9. **BUG-SPATIAL-024** (Medium) — Raise on missing boundary node instead of silent drop.
10. **BUG-SPATIAL-029** (Medium) — Normalize position strings in overlay reservation.
11. **BUG-SPATIAL-019** (Medium) — Use multi-waypoint interpolation in event_compiler shadow.
12. **BUG-SPATIAL-003, 010, 011, 021, 022** (Low) — Code hygiene: logger duplicates, print→logger, missing imports, dead code.

---

## Files Touched in This Analysis

All 31 files from the task description were read in full. Key file:line references above are exact as of commit `Enigma-V.0.5.3.6.7_-_-_-`.
