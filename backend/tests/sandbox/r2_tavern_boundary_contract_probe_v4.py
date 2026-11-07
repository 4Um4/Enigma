# backend/tests/sandbox/r2_tavern_boundary_contract_probe_v4.py
"""
R2-TAVERN-BOUNDARY-CONTRACT probe v4 — READ-ONLY.

Исследование исходников и контрактов, связанных с boundary nodes.

Цели:
  1. Прочитать graph_compiler.py (L440-500 edge validation, L850-870 _validate_connectivity,
     L950-1000 _create_boundary_nodes).
  2. Прочитать spatial_service.py (L710-780) get_furthest.
  3. Прочитать spatial_target_resolver.py (L120-160) FLEE resolution.
  4. Прочитать tests/sandbox/micro/test_boundary_nodes.py.
  5. Дамп door_0, door_1, wall_0, wall_7 из tavern.json.

Эксперименты (изолированные, read-only):
  A. Существует ли приоритет авторского exit_south над синтезируемым?
  B. Сохраняется ли adjacency tavern↔market_square при авторском boundary node?
  C. Как правильно связать дверь с wall_0 согласно контракту?
  D. Какие узлы возвращает get_furthest()? Проверяется ли достижимость через A*?

Запрещено: менять production-код, карту, тесты.
"""
from __future__ import annotations
import os, sys, json, traceback, copy
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_THIS = Path(__file__).resolve()
_BACKEND = _THIS.parent.parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

try:
    from app.core.config import settings, BASE_DIR
except Exception as e:
    print(f"[FATAL] Cannot import app.core.config: {e}")
    sys.exit(2)

PROJECT_ROOT = _BACKEND.parent
MAP_FILE = PROJECT_ROOT / "saves/Open_road/locations/tavern.json"


def _print_section(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def _read_lines(path: Path, start: int, end: int) -> List[str]:
    """Read lines [start, end] (1-indexed, inclusive)."""
    if not path.exists():
        return [f"[file not found: {path}]"]
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").split("\n")
        return [f"L{i+1:4d}: {lines[i]}" for i in range(start - 1, min(end, len(lines)))]
    except Exception as e:
        return [f"[read error: {e}]"]


def _dump_json_section(data: Any, max_chars: int = 0) -> str:
    try:
        s = json.dumps(data, ensure_ascii=False, indent=2, default=str)
        if max_chars and len(s) > max_chars:
            return s[:max_chars] + f"\n... (truncated, total {len(s)} chars)"
        return s
    except Exception:
        return str(data)


# ============================================================================
# STEP 1: graph_compiler.py source — edge validation
# ============================================================================
def step1_graph_compiler_edge_validation() -> None:
    _print_section("STEP 1: graph_compiler.py — edge validation (L440-510)")
    p = _BACKEND / "app/services/spatial/graph_compiler.py"
    for line in _read_lines(p, 440, 510):
        print(line)


# ============================================================================
# STEP 2: graph_compiler.py — _validate_connectivity
# ============================================================================
def step2_graph_compiler_validate_connectivity() -> None:
    _print_section("STEP 2: graph_compiler.py — _validate_connectivity (L850-870)")
    p = _BACKEND / "app/services/spatial/graph_compiler.py"
    for line in _read_lines(p, 850, 870):
        print(line)


# ============================================================================
# STEP 3: graph_compiler.py — _create_boundary_nodes
# ============================================================================
def step3_graph_compiler_create_boundary_nodes() -> None:
    _print_section("STEP 3: graph_compiler.py — _create_boundary_nodes (L950-1010)")
    p = _BACKEND / "app/services/spatial/graph_compiler.py"
    for line in _read_lines(p, 950, 1010):
        print(line)

    # Also search for the function definition
    _print_section("STEP 3b: locate _create_boundary_nodes definition")
    if p.exists():
        src = p.read_text(encoding="utf-8", errors="replace")
        for i, line in enumerate(src.split("\n"), 1):
            if "_create_boundary_nodes" in line or "create_boundary" in line:
                print(f"  L{i}: {line.rstrip()}")


# ============================================================================
# STEP 4: spatial_service.py — get_furthest
# ============================================================================
def step4_spatial_service_get_furthest() -> None:
    _print_section("STEP 4: spatial_service.py — get_furthest (L710-790)")
    p = _BACKEND / "app/services/spatial/spatial_service.py"
    for line in _read_lines(p, 710, 790):
        print(line)

    # Also search for the function signature
    _print_section("STEP 4b: locate get_furthest definition")
    if p.exists():
        src = p.read_text(encoding="utf-8", errors="replace")
        for i, line in enumerate(src.split("\n"), 1):
            if "def get_furthest" in line:
                print(f"  L{i}: {line.rstrip()}")
                # show 5 lines after
                lines_list = src.split("\n")
                for j in range(i, min(i + 5, len(lines_list))):
                    print(f"  L{j+1}: {lines_list[j].rstrip()}")
                break


# ============================================================================
# STEP 5: spatial_target_resolver.py — FLEE target resolution
# ============================================================================
def step5_spatial_target_resolver_flee() -> None:
    _print_section("STEP 5: spatial_target_resolver.py — FLEE target resolution (L120-170)")
    p = _BACKEND / "app/services/spatial/spatial_target_resolver.py"
    for line in _read_lines(p, 120, 170):
        print(line)


# ============================================================================
# STEP 6: tests/sandbox/micro/test_boundary_nodes.py
# ============================================================================
def step6_test_boundary_nodes() -> None:
    _print_section("STEP 6: tests/sandbox/micro/test_boundary_nodes.py — existing boundary contract tests")
    p = _BACKEND / "tests/sandbox/micro/test_boundary_nodes.py"
    if not p.exists():
        print(f"[file not found: {p}]")
        # search elsewhere
        for cand in _BACKEND.rglob("test_boundary_nodes.py"):
            print(f"  found at: {cand}")
            p = cand
            break
    if p.exists():
        try:
            src = p.read_text(encoding="utf-8", errors="replace")
            print(f"\n--- full file ({len(src)} chars) ---")
            print(src)
        except Exception as e:
            print(f"  [read error: {e}]")


# ============================================================================
# STEP 7: door_0, door_1, wall_0, wall_7 definitions in tavern.json
# ============================================================================
def step7_door_wall_defs() -> None:
    _print_section("STEP 7: door_0, door_1, wall_0, wall_7 full definitions in tavern.json")
    if not MAP_FILE.exists():
        print(f"[file not found: {MAP_FILE}]")
        return
    data = json.loads(MAP_FILE.read_text(encoding="utf-8", errors="replace"))

    walls = data.get("walls", [])
    objects = data.get("objects", [])

    print("\n--- Target walls ---")
    target_wall_ids = {"wall_0", "wall_7", "wall_5"}
    for w in walls:
        if isinstance(w, dict) and w.get("id") in target_wall_ids:
            print(_dump_json_section(w))

    print("\n--- Target doors ---")
    target_door_ids = {"door_0", "door_1"}
    for o in objects:
        if isinstance(o, dict) and o.get("id") in target_door_ids:
            print(_dump_json_section(o))


# ============================================================================
# STEP 8 (Experiment A): Does authored exit_south take priority over synthesized?
# ============================================================================
def step8_experiment_a_authored_priority() -> None:
    _print_section("STEP 8 (Experiment A): Authored exit_south priority over synthesized")
    print("""
QUESTION: If map author defines 'exit_south' explicitly in nodes dict,
          does GraphCompiler skip synthesizing a placeholder boundary node?

METHOD: Read graph_compiler.py around _create_boundary_nodes (Step 3 already done).
        Look for branching logic: 'if node_id in graph: skip', or 'graph.setdefault(...)'.

EXPECTED OUTCOMES:
  - If code uses `if exit_id not in graph:` or `setdefault(...)` → authored has priority.
  - If code unconditionally adds → synthesized OVERWRITES authored (bad).
  - If code raises or warns on conflict → contract requires explicit choice.
""")
    # Inspect graph_compiler.py around _create_boundary_nodes for branching logic
    p = _BACKEND / "app/services/spatial/graph_compiler.py"
    if not p.exists():
        print("[file not found]")
        return
    src = p.read_text(encoding="utf-8", errors="replace")
    lines = src.split("\n")

    # Find _create_boundary_nodes function body and show 80 lines after definition
    func_start = None
    for i, line in enumerate(lines):
        if "def _create_boundary_nodes" in line or "def create_boundary_nodes" in line:
            func_start = i
            print(f"\nFound function definition at L{func_start + 1}:")
            print(f"  {line.rstrip()}")
            break

    if func_start is not None:
        print(f"\n--- function body (next 80 lines) ---")
        for j in range(func_start, min(func_start + 80, len(lines))):
            print(f"  L{j+1}: {lines[j].rstrip()}")
            # Stop at next top-level def
            if j > func_start + 3 and lines[j].startswith("def ") and not lines[j].startswith("def _create_boundary"):
                break

        # Check for branching patterns
        print("\n--- branching logic analysis ---")
        body_lines = lines[func_start:func_start + 80]
        branching_keywords = ["if ", "elif ", "else:", "in self._graph", "in graph",
                              "setdefault", "already exists", "skip", "continue",
                              "raise ", "warn"]
        for k, line in enumerate(body_lines):
            for kw in branching_keywords:
                if kw in line:
                    print(f"  L{func_start + k + 1} [{kw}]: {line.rstrip()}")
                    break


# ============================================================================
# STEP 9 (Experiment B): Adjacency preservation with authored boundary node
# ============================================================================
def step9_experiment_b_adjacency_preservation() -> None:
    _print_section("STEP 9 (Experiment B): Adjacency preservation with authored boundary node")
    print("""
QUESTION: If we add an authored 'exit_south' node to tavern.json, will the
          adjacency link tavern <-> market_square still be preserved?

METHOD: Inspect how _create_boundary_nodes handles adjacency.south:
        - Does it ALWAYS create a synthetic exit_south node?
        - Or does it use existing exit_south if present?
        - Does it create edges to neighbor location's entry node?

LOOK FOR: After the function definition (Step 8), look for:
  - adjacency iteration: `for direction, neighbor_loc in adjacency.items():`
  - edge creation: `graph.add_edge(exit_X, neighbor_entry_node)` or similar
  - boundary_map population: `boundary_map[direction] = {neighbor: ..., entry_direction: ...}`
""")
    p = _BACKEND / "app/services/spatial/graph_compiler.py"
    if not p.exists():
        return
    src = p.read_text(encoding="utf-8", errors="replace")
    lines = src.split("\n")
    # Find _create_boundary_nodes function
    func_start = None
    for i, line in enumerate(lines):
        if "def _create_boundary_nodes" in line:
            func_start = i
            break
    if func_start is None:
        print("[function not found]")
        return
    # Show 100 lines of body, then search for adjacency-related code
    body = lines[func_start:func_start + 120]
    print("\n--- adjacency/boundary_map references in function ---")
    for k, line in enumerate(body):
        for kw in ["adjacency", "neighbor", "boundary_map", "entry_node", "entry_direction", "exit_", "market_square"]:
            if kw in line:
                print(f"  L{func_start + k + 1} [{kw}]: {line.rstrip()}")
                break


# ============================================================================
# STEP 10 (Experiment C): Door-wall binding contract
# ============================================================================
def step10_experiment_c_door_wall_contract() -> None:
    _print_section("STEP 10 (Experiment C): Door-wall binding contract (from door_0, door_1 examples)")
    print("""
QUESTION: How should door_2 be linked to wall_0 according to existing contract?

OBSERVED PATTERNS:
  door_0:
    - position: {x: 8.18, y: 13.0}
    - wall_id: "wall_2" (explicit)
    - wall_2 geometry: x1=14.0, y1=13.0, x2=0.5, y2=13.0 (horizontal at y=13)
    - door position y=13.0 matches wall y=13.0
    - door position x=8.18 is within wall x-range [0.5, 14.0]
    - door size: {w: 1.33, h: 1.0}

  door_1:
    - position: {x: 14.0, y: 4.5}
    - wall_id: NOT SET (only geometric match)
    - wall_7 geometry: x1=14.0, y1=8.0, x2=14.0, y2=0.5 (vertical at x=14.0)
    - door position x=14.0 matches wall x=14.0
    - door position y=4.5 is within wall y-range [0.5, 8.0]
    - door size: {w: 1.0, h: 1.0}

CONTRACT SCHEMA (deduced):
  A door object MUST have:
    - "id": unique string like "door_N"
    - "name": human-readable label
    - "type": "door"
    - "position": {"x": <wall_x or within wall extent>, "y": <wall_y or within wall extent>}
    - "size": {"w": float, "h": float}
    - "rotation": int (0 = aligned with axis)
    - "passability": {"walk": true, ...}
    - "properties": {
        "open": bool,
        "locked": bool,
        "durability": int,
        "visibility_through": float,
        "target_file": str (e.g. "market_square" or ""),
        "target_portal": str
      }
    - "wall_id": "<wall_id>" (preferred — door_0 has this)

  A wall object that has a door should NOT need modification — door carries the link.
  (Step 5b of probe v1 confirmed: walls with explicit door_id field = 0 — door_id lives in door, not wall)

  OPTIONAL: wall can have "door_id" field, but this is NOT required (no examples in tavern.json).
""")
    if not MAP_FILE.exists():
        return
    data = json.loads(MAP_FILE.read_text(encoding="utf-8", errors="replace"))
    print("\n--- wall_0 (target for door_2) ---")
    for w in data.get("walls", []):
        if isinstance(w, dict) and w.get("id") == "wall_0":
            print(_dump_json_section(w))
            # Compute midpoint and extent
            x1, y1, x2, y2 = w["x1"], w["y1"], w["x2"], w["y2"]
            print(f"\n  wall_0 geometry: x1={x1}, y1={y1}, x2={x2}, y2={y2}")
            print(f"  orientation: {'horizontal' if y1 == y2 else 'vertical' if x1 == x2 else 'diagonal'}")
            print(f"  extent x: [{min(x1, x2)}, {max(x1, x2)}]")
            print(f"  extent y: [{min(y1, y2)}, {max(y1, y2)}]")
            # Recommended door_2 position: midpoint of wall_0
            mx = (x1 + x2) / 2
            my = (y1 + y2) / 2
            print(f"  midpoint: ({mx}, {my})")
            break


# ============================================================================
# STEP 11 (Experiment D): get_furthest behavior and reachability check
# ============================================================================
def step11_experiment_d_get_furthest_reachability() -> None:
    _print_section("STEP 11 (Experiment D): get_furthest behavior + A* reachability check")
    print("""
QUESTION: What nodes can get_furthest() return? Does it filter by reachability?

METHOD: Read spatial_service.py around get_furthest (Step 4 already done).
        Look for:
          - Node iteration logic (which nodes are candidates?)
          - Distance computation (Euclidean? Manhattan?)
          - Any reachability check (A*, BFS, connectivity)
          - Filter on node type/role/tags
""")
    p = _BACKEND / "app/services/spatial/spatial_service.py"
    if not p.exists():
        return
    src = p.read_text(encoding="utf-8", errors="replace")
    lines = src.split("\n")

    # Find get_furthest function
    func_start = None
    for i, line in enumerate(lines):
        if "def get_furthest" in line:
            func_start = i
            break
    if func_start is None:
        print("[get_furthest function not found]")
        return

    print(f"\n--- get_furthest full body (L{func_start + 1} to L{func_start + 70}) ---")
    for j in range(func_start, min(func_start + 70, len(lines))):
        print(f"  L{j+1}: {lines[j].rstrip()}")
        if j > func_start + 3 and lines[j].startswith("def ") and "get_furthest" not in lines[j]:
            break

    # Check for reachability filtering keywords
    print("\n--- reachability filter analysis ---")
    body = lines[func_start:func_start + 70]
    reach_keywords = ["reachable", "reachable_from", "connected", "bfs", "astar", "a_star",
                      "path_to", "has_path", "can_reach", "is_reachable",
                      "filter", "exclude", "skip"]
    found_any = False
    for k, line in enumerate(body):
        for kw in reach_keywords:
            if kw in line.lower():
                print(f"  L{func_start + k + 1} [{kw}]: {line.rstrip()}")
                found_any = True
                break
    if not found_any:
        print("  [NO reachability filtering detected in get_furthest body]")
        print("  >>> get_furthest likely returns ANY node by distance,")
        print("  >>> without checking if A* can actually reach it.")

    # Also check candidate filter
    print("\n--- candidate filter analysis ---")
    filter_keywords = ["role", "boundary", "exit_", "type", "node_id", "for ", "if "]
    for k, line in enumerate(body):
        line_lower = line.lower()
        if any(kw in line_lower for kw in ["role", "boundary", "exit_"]):
            print(f"  L{func_start + k + 1}: {line.rstrip()}")


# ============================================================================
# STEP 12: Isolated read-only experiment — call get_furthest in current scene
# ============================================================================
def step12_isolated_experiment_get_furthest() -> None:
    _print_section("STEP 12: ISOLATED EXPERIMENT — call get_furthest from current scene")
    print("""
GOAL: Invoke SpatialService.get_furthest() on the live tavern scene and dump
      what it actually returns. Verify it returns 'exit_south' with placeholder coords.

METHOD: Build game loop (read-only, no idle_tick), get scene's spatial_service,
        call get_furthest(threat_position=fireplace_coords), print result.

NOTE: This does NOT modify production state — we only query the service.
""")
    try:
        from app.services.game_loop_builder import build_game_loop
        from app.core.config import settings

        # Use temp saves dir to avoid touching production saves
        import tempfile
        saves_dir = Path(tempfile.mkdtemp(prefix="r2_v4_exp_"))
        settings.saves_dir = str(saves_dir)
        settings.environment = "development"

        loop = build_game_loop(data_dir=Path(settings.data_dir))
        scene = loop.scene_manager.get_scene_state("Open_road", "tavern")
        if scene is None:
            scene = loop.scene_manager.initialize_scene("Open_road", "tavern", "12:00")

        # fireplace coords (NPC threat position)
        threat_x, threat_y = 10.5, 3.0

        # Try to get spatial_service from loop
        spatial_service = None
        for attr in ("spatial_service", "_spatial_service", "spatial"):
            if hasattr(loop, attr):
                candidate = getattr(loop, attr)
                if candidate is not None:
                    spatial_service = candidate
                    print(f"  Found spatial_service at loop.{attr}")
                    break

        if spatial_service is None:
            # Try via scene_manager
            sm = loop.scene_manager
            for attr in ("spatial_service", "_spatial_service"):
                if hasattr(sm, attr):
                    spatial_service = getattr(sm, attr)
                    print(f"  Found spatial_service at scene_manager.{attr}")
                    break

        if spatial_service is None:
            # Try to find via get_spatial_service
            for attr_name in ("get_spatial_service", "spatial_service_for", "get_spatial"):
                if hasattr(loop, attr_name):
                    try:
                        spatial_service = getattr(loop, attr_name)("Open_road", "tavern")
                        print(f"  Found spatial_service via loop.{attr_name}()")
                        break
                    except Exception:
                        continue

        if spatial_service is None:
            print("[WARN] Could not find spatial_service via standard attributes.")
            print("       Dumping loop attributes for inspection:")
            for attr in sorted(dir(loop)):
                if not attr.startswith("__"):
                    try:
                        val = getattr(loop, attr)
                        if not callable(val):
                            print(f"  loop.{attr} = {type(val).__name__}")
                    except Exception:
                        continue
            return

        # Inspect get_furthest signature
        import inspect
        try:
            sig = inspect.signature(spatial_service.get_furthest)
            print(f"\nget_furthest signature: {sig}")
        except (ValueError, TypeError) as e:
            print(f"  [cannot get signature: {e}]")

        # Call get_furthest with fireplace coords as threat
        try:
            print(f"\nCalling spatial_service.get_furthest(threat_x={threat_x}, threat_y={threat_y})")
            # Try different parameter names
            result = None
            for kwargs in [
                {"x": threat_x, "y": threat_y},
                {"threat_x": threat_x, "threat_y": threat_y},
                {"origin_x": threat_x, "origin_y": threat_y},
                {"px": threat_x, "py": threat_y},
                {"position_x": threat_x, "position_y": threat_y},
            ]:
                try:
                    result = spatial_service.get_furthest(**kwargs)
                    print(f"  WORKED with kwargs: {kwargs}")
                    break
                except TypeError as te:
                    print(f"  failed with kwargs {list(kwargs.keys())}: {te}")
                    continue

            if result is None:
                # Try positional
                try:
                    result = spatial_service.get_furthest(threat_x, threat_y)
                    print(f"  WORKED with positional args")
                except Exception as e:
                    print(f"  failed with positional: {e}")

            if result is not None:
                print(f"\n  RESULT: {result}")
                print(f"  RESULT type: {type(result).__name__}")
                if hasattr(result, "__dict__"):
                    print(f"  RESULT attrs: {vars(result)}")
                else:
                    print(f"  RESULT value: {result}")
        except Exception as e:
            print(f"  [call failed: {e}]")
            traceback.print_exc()

        # Cleanup
        try:
            ts = loop._get_task_scheduler()
            if hasattr(ts, "_executor_pool"):
                ts._executor_pool.shutdown(wait=False, cancel_futures=True)
        except Exception:
            pass
        del loop
        import gc
        gc.collect()
        import shutil
        shutil.rmtree(saves_dir, ignore_errors=True)
    except Exception as e:
        print(f"[FATAL] {type(e).__name__}: {e}")
        traceback.print_exc()


# ============================================================================
# STEP 13: Final report — minimal diff for variant C
# ============================================================================
def step13_final_report_minimal_diff() -> None:
    _print_section("STEP 13: MINIMAL DIFF FOR VARIANT C (proposed, DO NOT APPLY)")
    print("""
Based on findings above, the minimal diff to tavern.json is:

1. ADD new node "exit_south" to nodes dict:
   (coordinates: midpoint of wall_0 = (7.25, 0.5), but choose round number ~ (7.0, 0.5))
   "exit_south": {
     "x": 7.0,
     "y": 0.5,
     "label": "Выход на рынок",
     "role": "boundary",
     "tags": ["boundary:exit"],
     "connections": ["main_hall_west", "bar_pass_north"]
   }

   Connections chosen to be near wall_0 midpoint, with neighbors that can
   reach fireplace (where threat is). main_hall_west at (6.0, 8.0) is reachable.

2. ADD door_2 to objects[] (binding to wall_0):
   {
     "id": "door_2",
     "name": "Выход на рынок",
     "type": "door",
     "position": {"x": 7.0, "y": 0.5},
     "size": {"w": 1.33, "h": 1.0},
     "rotation": 0,
     "passability": {"walk": true, "jump_over": false, "crawl_under": false, "climb_on": false, "walk_around": true},
     "cover": 0.0,
     "color": "#FFD700",
     "show_name": false,
     "properties": {
       "open": true, "locked": false, "durability": 25,
       "visibility_through": 0.0,
       "target_file": "market_square",
       "target_portal": ""
     },
     "wall_id": "wall_0"
   }

3. UPDATE node "main_hall_west" connections to include exit_south:
   Before: "connections": ["entrance", "main_hall_south", "bar_area", "right_table", "corner_table"]
   After:  "connections": ["entrance", "main_hall_south", "bar_area", "right_table", "corner_table", "exit_south"]

   (Alternatively, connect via bar_pass_north at (2.2, 6.0) — but that's far from wall_0 midpoint.
    Best is to add a new intermediate node near (7, 2) or use main_hall_west directly.)

   RECOMMENDED: Add new intermediate node "south_passage":
     "south_passage": {
       "x": 7.0, "y": 2.0,
       "label": "Южный проход",
       "role": "default",
       "connections": ["main_hall_west", "main_hall", "exit_south"]
     }
   And update main_hall_west connections to include south_passage.

After diff:
  - GraphCompiler sees authored exit_south in nodes dict.
    - If _create_boundary_nodes uses `if exit_id not in graph:` → no overwrite (Step 8 will confirm).
    - If it overwrites → still works, because authored coords are on wall_0 (south), not wall_5.
  - adjacency.south still points to market_square → preserved (Step 9).
  - door_2 on wall_0 follows door_0 contract (Step 10).
  - SpatialTargetResolver.get_furthest still returns exit_south (Step 11 — by distance),
    but now A* CAN reach it through door_2 → FLEE EXECUTED.

EXPECTED POST-DIFF SPATIAL VALIDATOR OUTPUT:
  [SPATIAL_VALIDATION] tavern: edge exit_south <-> south_passage — door_id=door_2 on wall_0 — OK
  (or silent — no edge removal message)

EXPECTED POST-DIFF FLEE PIPELINE:
  DH.EXIT maid_lusya: FLEE
  RESOLVER.EXIT: anchor_node=tavern:exit_south (real coords (7.0, 0.5))
  CA: interrupt incumbent traversal
  ME.process_intents: ENTER intent_type=flee target=tavern:exit_south
  ME._resolve_macro_relocation: path found fireplace → main_hall → south_passage → exit_south (via door_2)
  ME.process_intents: EXIT ml_changes_count=2 FLEE_EXECUTED=true
  TICK_2:END: traversal target=exit_south status=MOVING
""")


# ============================================================================
# Main
# ============================================================================
def main() -> int:
    print("=" * 78)
    print("R2-TAVERN-BOUNDARY-CONTRACT probe v4 — READ-ONLY source + contract archaeology")
    print(f"Map file: {MAP_FILE}")
    print("=" * 78)

    try:
        step1_graph_compiler_edge_validation()
    except Exception as e:
        print(f"[step1 error: {e}]")

    try:
        step2_graph_compiler_validate_connectivity()
    except Exception as e:
        print(f"[step2 error: {e}]")

    try:
        step3_graph_compiler_create_boundary_nodes()
    except Exception as e:
        print(f"[step3 error: {e}]")

    try:
        step4_spatial_service_get_furthest()
    except Exception as e:
        print(f"[step4 error: {e}]")

    try:
        step5_spatial_target_resolver_flee()
    except Exception as e:
        print(f"[step5 error: {e}]")

    try:
        step6_test_boundary_nodes()
    except Exception as e:
        print(f"[step6 error: {e}]")

    try:
        step7_door_wall_defs()
    except Exception as e:
        print(f"[step7 error: {e}]")

    try:
        step8_experiment_a_authored_priority()
    except Exception as e:
        print(f"[step8 error: {e}]")

    try:
        step9_experiment_b_adjacency_preservation()
    except Exception as e:
        print(f"[step9 error: {e}]")

    try:
        step10_experiment_c_door_wall_contract()
    except Exception as e:
        print(f"[step10 error: {e}]")

    try:
        step11_experiment_d_get_furthest_reachability()
    except Exception as e:
        print(f"[step11 error: {e}]")

    try:
        step12_isolated_experiment_get_furthest()
    except Exception as e:
        print(f"[step12 error: {e}]")

    try:
        step13_final_report_minimal_diff()
    except Exception as e:
        print(f"[step13 error: {e}]")

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"\n[FATAL] {type(e).__name__}: {e}")
        traceback.print_exc()
        sys.exit(1)
