# backend/tests/sandbox/r2_adjacency_ab_experiment.py
"""
R2-ADJACENCY-AB-EXPERIMENT probe — A/B comparison with controlled GraphCompiler.

Гипотеза Мастера:
  adjacency.east = "city_gate" в tavern.json может запускать генерацию
  восточных boundary nodes и попытку соединить Tavern с City Gate через
  восточную границу, физически перекрытую wall_5.

Эксперимент:
  A — исходная карта (с adjacency.east = "city_gate")
  B — экспериментальная карта (только adjacency.south = "market_square")

  Оба варианта компилируются через compile_graph, сравниваются:
    - количество boundary nodes
    - IDs и координаты узлов
    - boundary_map содержимое
    - графовые рёбра (connections)
    - результат SpatialValidator (логи / удалённые рёбра)
    - межлокационные переходы (entry_node_hint)

  Дополнительно:
    - проверить маршрут Tavern → Market Square → City Gate
    - проверить FLEE target selection (get_furthest в обоих вариантах)
    - проверить, какие именно "лишние" узлы исчезают в варианте B

Ограничения:
  - НЕ изменять авторский tavern.json
  - Работать на временной копии в памяти
  - НЕ добавлять exit_south, door_2, другие объекты
  - НЕ перемещать door_0, door_1, стены, комнаты
  - НЕ менять node_16
  - НЕ удалять assertion
"""
from __future__ import annotations
import os, sys, json, traceback, copy, tempfile, shutil, logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import io

_THIS = Path(__file__).resolve()
_BACKEND = _THIS.parent.parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

# Add frontend/map_editor to sys.path so we can import graph_compiler
_FRONTEND_ME = _BACKEND.parent / "frontend" / "map_editor"
if str(_FRONTEND_ME) not in sys.path:
    sys.path.insert(0, str(_FRONTEND_ME))

try:
    from app.core.config import settings, BASE_DIR
except Exception as e:
    print(f"[FATAL] Cannot import app.core.config: {e}")
    sys.exit(2)

PROJECT_ROOT = _BACKEND.parent
MAP_FILE = PROJECT_ROOT / "saves/Open_road/locations/tavern.json"

OUT_FILE_DIR = Path("/home/z/my-project/download")
if not OUT_FILE_DIR.exists() or not OUT_FILE_DIR.is_dir():
    OUT_FILE_DIR = _BACKEND / "tests" / "sandbox"
    try:
        OUT_FILE_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        OUT_FILE_DIR = Path(os.getcwd())
OUT_FILE = OUT_FILE_DIR / "r2_adjacency_ab_experiment.txt"


class TeeStream:
    def __init__(self, *streams):
        self.streams = streams

    def write(self, data):
        for s in self.streams:
            try:
                s.write(data)
            except Exception:
                pass

    def flush(self):
        for s in self.streams:
            try:
                s.flush()
            except Exception:
                pass


_stdout_buf = io.StringIO()
_orig_stdout = sys.stdout
sys.stdout = TeeStream(_orig_stdout, _stdout_buf)

# Capture logger output (graph_compiler uses logging)
_log_capture = io.StringIO()
_log_handler = logging.StreamHandler(_log_capture)
_log_handler.setLevel(logging.DEBUG)
_log_handler.setFormatter(logging.Formatter("%(name)s [%(levelname)s] %(message)s"))
# Attach to root logger
_logging_root = logging.getLogger()
_logging_root.addHandler(_log_handler)
_logging_root.setLevel(logging.DEBUG)


def _print_section(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def _dump_json(obj: Any, max_chars: int = 0) -> str:
    try:
        s = json.dumps(obj, ensure_ascii=False, indent=2, default=str)
        if max_chars and len(s) > max_chars:
            return s[:max_chars] + f"\n... (truncated, total {len(s)} chars)"
        return s
    except Exception:
        return str(obj)


def _try_import_graph_compiler():
    """Try importing graph_compiler from frontend/map_editor."""
    try:
        from app.services.spatial.graph_compiler import compile_graph  # type: ignore
        return compile_graph, "app.services.spatial.graph_compiler"
    except Exception:
        pass
    # Try frontend path
    try:
        # Force reload of sys.path
        import importlib
        # Try direct import from frontend/map_editor
        sys.path.insert(0, str(_FRONTEND_ME))
        from graph_compiler import compile_graph  # type: ignore
        return compile_graph, "graph_compiler (frontend/map_editor)"
    except Exception as e:
        print(f"[import error] {e}")
        return None, None


def _compile_map(compile_fn, map_data: dict, location_id: str = "tavern") -> dict:
    """Compile a map and return the result dict with all components."""
    result = {
        "success": False,
        "error": None,
        "graph": {},
        "connections": {},
        "alias_map": {},
        "boundary_map": {},
        "rooms_geometry": [],
        "walls": [],
        "obstacles": [],
        "affordance_objects": [],
        "boundary_nodes": [],
        "all_node_ids": [],
    }
    try:
        # Clear log capture for this run
        _log_capture.truncate(0)
        _log_capture.seek(0)

        compile_result = compile_fn(map_data, location_id=location_id)
        if compile_result is None:
            result["error"] = "compile_graph returned None"
            return result

        # Unpack the result tuple
        # Expected: (graph, connections, alias_map, boundary_map, rooms_geometry, walls, obstacles, affordance_objects)
        if isinstance(compile_result, tuple) and len(compile_result) >= 7:
            (graph, connections, alias_map, boundary_map,
             rooms_geometry, walls, obstacles, *rest) = compile_result
            affordance_objects = rest[0] if rest else []
            result["graph"] = graph if isinstance(graph, dict) else {}
            result["connections"] = connections if isinstance(connections, dict) else {}
            result["alias_map"] = alias_map if isinstance(alias_map, dict) else {}
            result["boundary_map"] = boundary_map if isinstance(boundary_map, dict) else {}
            result["rooms_geometry"] = rooms_geometry if isinstance(rooms_geometry, list) else []
            result["walls"] = walls if isinstance(walls, list) else []
            result["obstacles"] = obstacles if isinstance(obstacles, list) else []
            result["affordance_objects"] = affordance_objects if isinstance(affordance_objects, list) else []
            result["success"] = True

            # Extract boundary nodes (role == BOUNDARY)
            try:
                from app.models.spatial_contracts import NodeRole  # type: ignore
                boundary_role = NodeRole.BOUNDARY
            except Exception:
                # Try frontend path
                try:
                    from models.spatial_contracts import NodeRole  # type: ignore
                    boundary_role = NodeRole.BOUNDARY
                except Exception:
                    boundary_role = None

            for nid, nref in result["graph"].items():
                role = getattr(nref, "role", None)
                if role is not None and boundary_role is not None and role == boundary_role:
                    result["boundary_nodes"].append({
                        "node_id": nid,
                        "x": getattr(nref, "x", None),
                        "y": getattr(nref, "y", None),
                        "role": str(role),
                        "tags": getattr(nref, "tags", []),
                    })
            result["all_node_ids"] = sorted(result["graph"].keys())
        else:
            result["error"] = f"unexpected compile_result type: {type(compile_result).__name__}"
    except Exception as e:
        result["error"] = f"{type(e).__name__}: {e}"
        traceback.print_exc()
    # Capture logs
    result["logs"] = _log_capture.getvalue()
    return result


def _summarize_compilation(label: str, result: dict) -> None:
    """Print summary of compilation result."""
    print(f"\n--- {label} ---")
    if not result["success"]:
        print(f"  ERROR: {result['error']}")
        return
    print(f"  Total nodes in graph: {len(result['graph'])}")
    print(f"  Boundary nodes: {len(result['boundary_nodes'])}")
    print(f"  boundary_map entries: {len(result['boundary_map'])}")
    print(f"  walls: {len(result['walls'])}")
    print(f"  connections: {sum(len(v) for v in result['connections'].values()) // 2} edges")

    print(f"\n  All node IDs:")
    for nid in result["all_node_ids"]:
        nref = result["graph"].get(nid)
        x = getattr(nref, "x", "?") if nref else "?"
        y = getattr(nref, "y", "?") if nref else "?"
        role = getattr(nref, "role", "?") if nref else "?"
        is_boundary = "← BOUNDARY" if role and "BOUNDARY" in str(role) else ""
        print(f"    {nid:<40} ({x}, {y})  role={role} {is_boundary}")

    print(f"\n  boundary_map (full):")
    print(_dump_json(result["boundary_map"]))

    print(f"\n  connections (first 20):")
    shown = 0
    for src, targets in sorted(result["connections"].items()):
        for tgt in sorted(targets):
            print(f"    {src} ↔ {tgt}")
            shown += 1
            if shown >= 20:
                break
        if shown >= 20:
            break
    if shown >= 20:
        print(f"    ... (more edges)")

    print(f"\n  logs (last 3000 chars):")
    logs = result.get("logs", "")
    if logs:
        print("    " + logs[-3000:].replace("\n", "\n    "))
    else:
        print("    (no logs captured)")


def _compare_results(a: dict, b: dict) -> dict:
    """Compare A and B compilation results."""
    diff = {
        "node_id_only_in_A": [],
        "node_id_only_in_B": [],
        "boundary_only_in_A": [],
        "boundary_only_in_B": [],
        "edges_only_in_A": [],
        "edges_only_in_B": [],
        "boundary_map_only_in_A": [],
        "boundary_map_only_in_B": [],
    }
    a_ids = set(a["all_node_ids"])
    b_ids = set(b["all_node_ids"])
    diff["node_id_only_in_A"] = sorted(a_ids - b_ids)
    diff["node_id_only_in_B"] = sorted(b_ids - a_ids)

    a_boundary_ids = {bn["node_id"] for bn in a["boundary_nodes"]}
    b_boundary_ids = {bn["node_id"] for bn in b["boundary_nodes"]}
    diff["boundary_only_in_A"] = sorted(a_boundary_ids - b_boundary_ids)
    diff["boundary_only_in_B"] = sorted(b_boundary_ids - a_boundary_ids)

    # Edges (normalize to frozenset of frozensets)
    def _edges_set(r: dict) -> set:
        out = set()
        for src, targets in r["connections"].items():
            for tgt in targets:
                out.add(frozenset([src, tgt]))
        return out
    a_edges = _edges_set(a)
    b_edges = _edges_set(b)
    diff["edges_only_in_A"] = sorted([tuple(sorted(e)) for e in (a_edges - b_edges)])
    diff["edges_only_in_B"] = sorted([tuple(sorted(e)) for e in (b_edges - a_edges)])

    diff["boundary_map_only_in_A"] = sorted(set(a["boundary_map"].keys()) - set(b["boundary_map"].keys()))
    diff["boundary_map_only_in_B"] = sorted(set(b["boundary_map"].keys()) - set(a["boundary_map"].keys()))

    return diff


def main() -> int:
    print("=" * 78)
    print("R2-ADJACENCY-AB-EXPERIMENT — controlled A/B comparison")
    print(f"Map file: {MAP_FILE}")
    print("=" * 78)

    if not MAP_FILE.exists():
        print(f"[FATAL] Map file not found: {MAP_FILE}")
        return 1

    # === STEP 1: Load original map ===
    _print_section("STEP 1: Load original tavern.json (VARIANT A — original)")
    original_data = json.loads(MAP_FILE.read_text(encoding="utf-8", errors="replace"))
    print(f"Original adjacency: {original_data.get('adjacency')}")
    print(f"Original nodes count: {len(original_data.get('nodes', {}))}")
    print(f"Original walls count: {len(original_data.get('walls', []))}")
    print(f"Original objects count: {len(original_data.get('objects', []))}")

    # === STEP 2: Create VARIANT B (remove adjacency.east) ===
    _print_section("STEP 2: Create VARIANT B (remove adjacency.east)")
    variant_b_data = copy.deepcopy(original_data)
    original_adjacency = variant_b_data.get("adjacency", {})
    print(f"Before: {original_adjacency}")
    # Remove east
    if "east" in original_adjacency:
        del original_adjacency["east"]
    variant_b_data["adjacency"] = original_adjacency
    print(f"After: {variant_b_data.get('adjacency')}")

    # === STEP 3: Import compile_graph ===
    _print_section("STEP 3: Import compile_graph")
    compile_fn, source = _try_import_graph_compiler()
    if compile_fn is None:
        print("[FATAL] Cannot import compile_graph")
        return 1
    print(f"Imported from: {source}")
    print(f"Function: {compile_fn}")

    # === STEP 4: Compile VARIANT A ===
    _print_section("STEP 4: Compile VARIANT A (original — with adjacency.east)")
    result_a = _compile_map(compile_fn, original_data, "tavern")
    _summarize_compilation("VARIANT A (original)", result_a)

    # === STEP 5: Compile VARIANT B ===
    _print_section("STEP 5: Compile VARIANT B (without adjacency.east)")
    result_b = _compile_map(compile_fn, variant_b_data, "tavern")
    _summarize_compilation("VARIANT B (no east)", result_b)

    # === STEP 6: Compare A vs B ===
    _print_section("STEP 6: COMPARE A vs B")
    diff = _compare_results(result_a, result_b)
    print(f"\nNode IDs only in A (exist when east is present): {len(diff['node_id_only_in_A'])}")
    for nid in diff["node_id_only_in_A"]:
        nref = result_a["graph"].get(nid)
        x = getattr(nref, "x", "?") if nref else "?"
        y = getattr(nref, "y", "?") if nref else "?"
        role = getattr(nref, "role", "?") if nref else "?"
        print(f"  {nid}  ({x}, {y})  role={role}")
    print(f"\nNode IDs only in B (exist when east is removed): {len(diff['node_id_only_in_B'])}")
    for nid in diff["node_id_only_in_B"]:
        nref = result_b["graph"].get(nid)
        x = getattr(nref, "x", "?") if nref else "?"
        y = getattr(nref, "y", "?") if nref else "?"
        role = getattr(nref, "role", "?") if nref else "?"
        print(f"  {nid}  ({x}, {y})  role={role}")

    print(f"\nBoundary nodes only in A: {len(diff['boundary_only_in_A'])}")
    for bn in diff["boundary_only_in_A"]:
        print(f"  {bn}")
    print(f"Boundary nodes only in B: {len(diff['boundary_only_in_B'])}")
    for bn in diff["boundary_only_in_B"]:
        print(f"  {bn}")

    print(f"\nEdges only in A: {len(diff['edges_only_in_A'])}")
    for e in diff["edges_only_in_A"]:
        print(f"  {e[0]} ↔ {e[1]}")
    print(f"Edges only in B: {len(diff['edges_only_in_B'])}")
    for e in diff["edges_only_in_B"]:
        print(f"  {e[0]} ↔ {e[1]}")

    print(f"\nboundary_map entries only in A: {len(diff['boundary_map_only_in_A'])}")
    for k in diff["boundary_map_only_in_A"]:
        print(f"  {k}: {result_a['boundary_map'][k]}")
    print(f"boundary_map entries only in B: {len(diff['boundary_map_only_in_B'])}")
    for k in diff["boundary_map_only_in_B"]:
        print(f"  {k}: {result_b['boundary_map'][k]}")

    # === STEP 7: Investigate specific node "tavern:exit_east" ===
    _print_section("STEP 7: Investigate 'tavern:exit_east' in both variants")
    for label, result in [("A", result_a), ("B", result_b)]:
        print(f"\n--- {label}: tavern:exit_east ---")
        nref = result["graph"].get("tavern:exit_east")
        if nref:
            print(f"  EXISTS in graph")
            print(f"  x={getattr(nref, 'x', '?')}, y={getattr(nref, 'y', '?')}")
            print(f"  role={getattr(nref, 'role', '?')}")
            print(f"  tags={getattr(nref, 'tags', '?')}")
            # Check if it's in authored nodes or synthetic
            authored = "tavern:exit_east" in original_data.get("nodes", {})
            print(f"  Authored in JSON: {authored}")
            # Connections
            conns = result["connections"].get("tavern:exit_east", set())
            print(f"  Connections: {sorted(conns)}")
            # boundary_map entry
            bm = result["boundary_map"].get("tavern:exit_east")
            if bm:
                print(f"  boundary_map entry: {bm}")
            else:
                print(f"  boundary_map entry: NONE")
        else:
            print(f"  NOT in graph")

    # === STEP 8: Check FLEE target selection (get_furthest) ===
    _print_section("STEP 8: FLEE target selection — which node would get_furthest return?")
    print(f"\nThreat position: fireplace at (10.5, 3.0)")
    threat_xy = (10.5, 3.0)
    for label, result in [("A", result_a), ("B", result_b)]:
        print(f"\n--- {label}: candidates for get_furthest ---")
        best = None
        best_dist = -1.0
        for nid, nref in result["graph"].items():
            x = getattr(nref, "x", 0)
            y = getattr(nref, "y", 0)
            try:
                fx, fy = float(x), float(y)
                d = ((fx - threat_xy[0]) ** 2 + (fy - threat_xy[1]) ** 2) ** 0.5
                if d > best_dist:
                    best_dist = d
                    best = nid
            except (TypeError, ValueError):
                continue
        print(f"  FURTHEST node: {best} (distance={best_dist:.3f})")
        nref = result["graph"].get(best)
        if nref:
            print(f"    coords: ({getattr(nref, 'x', '?')}, {getattr(nref, 'y', '?')})")
            print(f"    role: {getattr(nref, 'role', '?')}")

    # === STEP 9: Trace route Tavern → Market Square → City Gate ===
    _print_section("STEP 9: Trace route Tavern → Market Square → City Gate")
    print(f"\nOriginal adjacency: {original_data.get('adjacency')}")
    print(f"\n--- Tavern's boundary_map (VARIANT A) ---")
    for bid, binfo in result_a["boundary_map"].items():
        print(f"  {bid}:")
        print(f"    neighbor_chunk: {binfo.get('neighbor_chunk')}")
        print(f"    entry_direction: {binfo.get('entry_direction')}")
        print(f"    entry_node_hint: {binfo.get('entry_node_hint')}")
        print(f"    direction: {binfo.get('direction')}")
        print(f"    coords: ({binfo.get('x')}, {binfo.get('y')})")

    print(f"\n--- Tavern's boundary_map (VARIANT B) ---")
    for bid, binfo in result_b["boundary_map"].items():
        print(f"  {bid}:")
        print(f"    neighbor_chunk: {binfo.get('neighbor_chunk')}")
        print(f"    entry_direction: {binfo.get('entry_direction')}")
        print(f"    entry_node_hint: {binfo.get('entry_node_hint')}")
        print(f"    direction: {binfo.get('direction')}")
        print(f"    coords: ({binfo.get('x')}, {binfo.get('y')})")

    # Try to load market_square.json to check its adjacency
    market_square_file = PROJECT_ROOT / "saves/Open_road/locations/market_square.json"
    print(f"\n--- Checking market_square.json for adjacency ---")
    if market_square_file.exists():
        ms_data = json.loads(market_square_file.read_text(encoding="utf-8", errors="replace"))
        print(f"market_square adjacency: {ms_data.get('adjacency')}")
        print(f"market_square nodes (with exit_*): ")
        for name in ms_data.get("nodes", {}):
            if "exit" in name.lower():
                print(f"  {name}")
    else:
        print(f"[market_square.json not found: {market_square_file}]")

    city_gate_file = PROJECT_ROOT / "saves/Open_road/locations/city_gate.json"
    print(f"\n--- Checking city_gate.json for adjacency ---")
    if city_gate_file.exists():
        cg_data = json.loads(city_gate_file.read_text(encoding="utf-8", errors="replace"))
        print(f"city_gate adjacency: {cg_data.get('adjacency')}")
        print(f"city_gate nodes (with exit_*): ")
        for name in cg_data.get("nodes", {}):
            if "exit" in name.lower():
                print(f"  {name}")
    else:
        print(f"[city_gate.json not found: {city_gate_file}]")

    # === STEP 10: VERDICT ===
    _print_section("STEP 10: VERDICT")
    print(f"""
HYPOTHESIS: adjacency.east = "city_gate" creates phantom eastern boundary nodes
            that interfere with FLEE target selection.

EVIDENCE:
  - VARIANT A (with east): {len(result_a['boundary_nodes'])} boundary nodes
    IDs: {[bn['node_id'] for bn in result_a['boundary_nodes']]}

  - VARIANT B (no east): {len(result_b['boundary_nodes'])} boundary nodes
    IDs: {[bn['node_id'] for bn in result_b['boundary_nodes']]}

  - Boundary nodes only in A (created by east adjacency):
    {diff['boundary_only_in_A']}

  - Boundary nodes only in B:
    {diff['boundary_only_in_B']}

  - FLEE target (furthest from fireplace (10.5, 3.0)):
    A: {('see Step 8 for details')}
    B: {('see Step 8 for details')}

CONCLUSION (based on evidence above):
  {'CONFIRMED: adjacency.east creates phantom boundary node tavern:exit_east' if diff['boundary_only_in_A'] else 'NOT CONFIRMED: no extra boundary nodes from east adjacency'}

  ROUTE ANALYSIS:
  Tavern → Market Square: through south boundary (entry_node_hint in boundary_map)
  Market Square → City Gate: depends on market_square.json adjacency

  If hypothesis is confirmed:
    Minimal diff: remove "east": "city_gate" from tavern.json adjacency
    Effect: tavern:exit_east will not be synthesized (it's already authored in nodes)
           OR tavern:exit_east IS authored and remains — check Step 7

  WAIT FOR MASTER'S DECISION before any production change.
""")

    # Write to file
    try:
        OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(OUT_FILE, "w", encoding="utf-8") as f:
            f.write(_stdout_buf.getvalue())
        size = OUT_FILE.stat().st_size
        print(f"\n>>> Output written to: {OUT_FILE}")
        print(f">>> File size: {size} bytes ({size / 1024:.1f} KB)")
    except Exception as e:
        print(f"\n[ERROR writing output file: {e}]")
        traceback.print_exc()

    return 0


if __name__ == "__main__":
    try:
        rc = main()
    except Exception as e:
        print(f"\n[FATAL] {type(e).__name__}: {e}")
        traceback.print_exc()
        rc = 1
    finally:
        sys.stdout = _orig_stdout
    sys.exit(rc)
