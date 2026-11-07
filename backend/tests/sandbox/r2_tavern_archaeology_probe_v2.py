# backend/tests/sandbox/r2_tavern_archaeology_probe_v2.py
"""
R2-TAVERN-ARCHAEOLOGY v2 — расширенная read-only разведка.

Что добавлено по сравнению с v1:
  1. Выводит top-level структуру файла (ключи верхнего уровня, размеры секций)
  2. Дампает ВСЕ объекты objects[] полностью (не только door — любые type)
  3. Дедуплицирует doors (в v1 door_0 и door_1 показывались по 3 раза с .properties)
  4. Ищет nodes по ЛЮБОМУ строковому полю, совпадающему с target node IDs
  5. Ищет edges по всем возможным форматам:
       {"from":..., "to":...}, {"source":..., "target":...},
       {"exits":[...]}, {"neighbors":[...]}, {"connections":[...]},
       {"adjacency":{...}}, {"links":[...]}, {"transitions":[...]}
  6. Ищет все строковые упоминания "exit_south", "kitchen_bed_2", "fireplace",
     "kitchen", "kitchen_bed_1" в ЛЮБЫХ полях и на любой глубине
  7. Для каждого найденного node выводит его координаты
  8. Вычисляет геометрическое пересечение ребра exit_south <-> kitchen_bed_2 с wall_5

Read-only. Никаких изменений.
"""
from __future__ import annotations
import os, sys, json, traceback
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Set

_THIS = Path(__file__).resolve()
_BACKEND = _THIS.parent.parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

try:
    from app.core.config import settings, BASE_DIR
except Exception as e:
    print(f"[FATAL] Cannot import app.core.config: {e}")
    sys.exit(2)

TARGET_WALL = {"x1": 19.5, "y1": 0.5, "x2": 19.5, "y2": 8.0}
TARGET_WALL_ID = "wall_5"
TARGET_EDGE = ("tavern:exit_south", "tavern:kitchen_bed_2")

# Node IDs we are interested in (with and without "tavern:" prefix)
TARGET_NODE_IDS = {
    "tavern:exit_south", "tavern:kitchen_bed_2", "tavern:fireplace",
    "tavern:kitchen", "tavern:kitchen_bed_1",
    "tavern:main_hall", "tavern:node_16", "tavern:node_17",
    "exit_south", "kitchen_bed_2", "fireplace",
    "kitchen", "kitchen_bed_1", "main_hall",
    "node_16", "node_17",
}


def _approx_equal(a: float, b: float, tol: float = 1e-6) -> bool:
    try:
        return abs(float(a) - float(b)) < tol
    except (TypeError, ValueError):
        return False


def _match_wall(wall: Dict[str, Any], target: Dict[str, float]) -> bool:
    if not isinstance(wall, dict):
        return False
    return all(_approx_equal(wall.get(k), target.get(k)) for k in ("x1", "y1", "x2", "y2"))


def _print_section(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def _print_dict(obj: Any, indent: int = 2) -> str:
    try:
        return json.dumps(obj, ensure_ascii=False, indent=2, default=str)
    except Exception:
        return str(obj)


def _flatten_search(obj: Any, key_path: str = "") -> List[Tuple[str, Any]]:
    """Recursively flatten dict/list. Returns (path, value) for every node."""
    out: List[Tuple[str, Any]] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{key_path}.{k}" if key_path else k
            out.append((p, v))
            out.extend(_flatten_search(v, p))
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            p = f"{key_path}[{i}]"
            out.append((p, item))
            out.extend(_flatten_search(item, p))
    return out


def _find_string_occurrences(data: Any, targets: Set[str]) -> List[Tuple[str, str]]:
    """Find every place where a target string appears as a value (any depth)."""
    out: List[Tuple[str, str]] = []
    flat = _flatten_search(data)
    for path, val in flat:
        if isinstance(val, str) and val in targets:
            out.append((path, val))
    return out


def _find_nodes_with_id(data: Any, target_ids: Set[str]) -> List[Tuple[str, Dict[str, Any]]]:
    """Find dict objects that have a string field matching a target node ID."""
    out: List[Tuple[str, Dict[str, Any]]] = []
    flat = _flatten_search(data)
    seen_paths = set()
    for path, val in flat:
        if isinstance(val, dict):
            # Check all string values in this dict's top-level fields
            for k, v in val.items():
                if isinstance(v, str) and v in target_ids:
                    # Use the parent path (without the trailing .k)
                    parent_path = path
                    if parent_path not in seen_paths:
                        out.append((parent_path, val))
                        seen_paths.add(parent_path)
                    break
    return out


def _extract_coords(val: Dict[str, Any]) -> Tuple[Optional[float], Optional[float]]:
    """Try various coordinate field names to extract x, y from a dict."""
    if not isinstance(val, dict):
        return None, None
    # Direct x/y
    x = val.get("x") or val.get("pos_x") or val.get("px") or val.get("coord_x")
    y = val.get("y") or val.get("pos_y") or val.get("py") or val.get("coord_y")
    if x is not None and y is not None:
        try:
            return float(x), float(y)
        except (TypeError, ValueError):
            pass
    # Nested position dict
    for pos_key in ("position", "pos", "coords", "coordinates", "location"):
        if pos_key in val and isinstance(val[pos_key], dict):
            pp = val[pos_key]
            xx = pp.get("x") or pp.get("px")
            yy = pp.get("y") or pp.get("py")
            if xx is not None and yy is not None:
                try:
                    return float(xx), float(yy)
                except (TypeError, ValueError):
                    pass
    return None, None


def _find_edges_in_graph(data: Any, target_pair: Tuple[str, str]) -> List[Tuple[str, Any]]:
    """Find graph edges connecting two specific nodes.
    Supports many possible schemas."""
    out: List[Tuple[str, Any]] = []
    flat = _flatten_search(data)
    a, b = target_pair
    # Pairs to match (in any direction)
    pair_set = {a, b}

    for path, val in flat:
        if isinstance(val, dict):
            # Direct edge: {"from":..., "to":...}
            for from_k, to_k in (("from", "to"), ("source", "target"),
                                  ("src", "dst"), ("a", "b"),
                                  ("node_a", "node_b"), ("u", "v"),
                                  ("start", "end"), ("origin", "dest")):
                if from_k in val and to_k in val:
                    f = str(val[from_k]); t = str(val[to_k])
                    if f in pair_set and t in pair_set and f != t:
                        out.append((path, val))
                        break
        elif isinstance(val, list) and len(val) == 2:
            a_str, b_str = str(val[0]), str(val[1])
            if a_str in pair_set and b_str in pair_set and a_str != b_str:
                out.append((path, val))
        elif isinstance(val, str) and ("->" in val or "→" in val):
            # Try parsing "a -> b"
            for sep in (" -> ", "->", " → ", "→"):
                if sep in val:
                    parts = [p.strip() for p in val.split(sep)]
                    if len(parts) == 2 and all(p in pair_set for p in parts) and parts[0] != parts[1]:
                        out.append((path, val))
                        break
    return out


def _find_adjacency_lists_for_node(data: Any, target_node: str) -> List[Tuple[str, Any]]:
    """Find adjacency list entries that reference target_node.
    Examples:
      node_dict = {"id": "...", "exits": ["target_node", ...]}
      node_dict = {"id": "...", "neighbors": [...]}
    """
    out: List[Tuple[str, Any]] = []
    flat = _flatten_search(data)
    for path, val in flat:
        if isinstance(val, dict):
            # Find any list field that contains target_node
            for k, v in val.items():
                if isinstance(v, list) and any(isinstance(x, str) and x == target_node for x in v):
                    # Check that this dict has an id-like field
                    has_id = any(idk in val for idk in ("id", "node_id", "node", "name"))
                    if has_id:
                        out.append((path, val))
                        break
                # Also check if v is a dict like {"target_node": {...}}
                if isinstance(v, dict) and target_node in v:
                    out.append((path, val))
                    break
    return out


def main() -> int:
    print("=" * 78)
    print("R2-TAVERN-ARCHAEOLOGY v2 — extended survey")
    print(f"Target wall: {TARGET_WALL} (id={TARGET_WALL_ID})")
    print(f"Target edge: {TARGET_EDGE}")
    print("=" * 78)

    # Use the known file location from v1
    candidate = Path("C:/DDD/Codex/VSC_Enigma/Enigma/saves/Open_road/locations/tavern.json")
    if not candidate.exists():
        # Fallback: search
        search_roots = []
        try:
            search_roots.append(Path(settings.data_dir))
        except Exception:
            pass
        search_roots.append(Path(BASE_DIR))
        search_roots.append(_BACKEND.parent)
        for root in search_roots:
            if not root.exists():
                continue
            for p in root.rglob("tavern.json"):
                if "locations" in str(p) and "Open_road" in str(p):
                    candidate = p
                    break
            if candidate.exists():
                break

    if not candidate.exists():
        print(f"[FATAL] Cannot find tavern.json")
        return 1

    print(f"\nMap file: {candidate}")
    raw_text = candidate.read_text(encoding="utf-8", errors="replace")
    try:
        data = json.loads(raw_text)
    except Exception as e:
        print(f"[FATAL] Cannot parse JSON: {e}")
        return 1

    # === STEP A: Top-level schema ===
    _print_section("STEP A: TOP-LEVEL SCHEMA of tavern.json")
    if isinstance(data, dict):
        print(f"Top-level keys ({len(data)}):")
        for k, v in data.items():
            if isinstance(v, list):
                print(f"  {k}: list of {len(v)} items")
            elif isinstance(v, dict):
                print(f"  {k}: dict with {len(v)} keys: {list(v.keys())[:10]}")
            else:
                v_str = str(v)
                if len(v_str) > 80:
                    v_str = v_str[:77] + "..."
                print(f"  {k}: {type(v).__name__} = {v_str}")
    else:
        print(f"Top-level type: {type(data).__name__} (not dict)")
        print(_print_dict(data)[:2000])

    # === STEP B: Dump all objects[] entries ===
    _print_section("STEP B: ALL OBJECTS in objects[] (full dump)")
    objects = data.get("objects") if isinstance(data, dict) else None
    if not objects and isinstance(data, dict):
        # try other names
        for k in ("entities", "items", "elements"):
            if k in data and isinstance(data[k], list):
                objects = data[k]
                print(f"  (using key '{k}' instead of 'objects')")
                break
    if objects and isinstance(objects, list):
        print(f"Total objects: {len(objects)}")
        # Group by type
        by_type: Dict[str, List[Tuple[int, Dict[str, Any]]]] = {}
        for i, obj in enumerate(objects):
            if isinstance(obj, dict):
                t = obj.get("type") or obj.get("kind") or "<no type>"
                by_type.setdefault(t, []).append((i, obj))
        print(f"\nObjects grouped by type:")
        for t, items in sorted(by_type.items()):
            print(f"  type={t}: {len(items)} objects")

        print(f"\n--- Full dump of all door-type objects ---")
        for t in ("door", "portal", "passage", "exit", "gateway", "opening"):
            if t in by_type:
                print(f"\n  === type={t} ({len(by_type[t])} objects) ===")
                for idx, obj in by_type[t]:
                    print(f"\n  objects[{idx}]:")
                    print(_print_dict(obj))

        print(f"\n--- Full dump of all node-type objects ---")
        for t in ("node", "exit_node", "waypoint", "anchor", "spawn_point", "landmark"):
            if t in by_type:
                print(f"\n  === type={t} ({len(by_type[t])} objects) ===")
                for idx, obj in by_type[t]:
                    print(f"\n  objects[{idx}]:")
                    print(_print_dict(obj))

        # Also show objects with id matching target node IDs
        print(f"\n--- Objects with id matching target nodes (exit_south, kitchen_bed_2, fireplace, ...) ---")
        for i, obj in enumerate(objects):
            if isinstance(obj, dict):
                obj_id = obj.get("id") or obj.get("node_id") or obj.get("name")
                if isinstance(obj_id, str) and obj_id in TARGET_NODE_IDS:
                    print(f"\n  objects[{i}] (id={obj_id}):")
                    print(_print_dict(obj))

        # Show ALL objects with type=="furniture" or "prop" that might be nodes
        # (some maps use furniture type for spatial anchors)
        print(f"\n--- Objects with type=furniture or type=prop (could contain anchor nodes) ---")
        for t in ("furniture", "prop", "fixture", "static"):
            if t in by_type:
                print(f"\n  === type={t} ({len(by_type[t])} objects) ===")
                for idx, obj in by_type[t]:
                    obj_id = obj.get("id") or obj.get("name") or "<no id>"
                    print(f"\n  objects[{idx}] (id={obj_id}):")
                    print(_print_dict(obj))
    else:
        print("No 'objects' array found at top level.")

    # === STEP C: Walls ===
    _print_section("STEP C: ALL WALLS")
    walls = data.get("walls") if isinstance(data, dict) else None
    if walls and isinstance(walls, list):
        print(f"Total walls: {len(walls)}")
        for i, w in enumerate(walls):
            if isinstance(w, dict):
                is_target = _match_wall(w, TARGET_WALL)
                marker = " <== TARGET" if is_target else ""
                w_id = w.get("id", "?")
                x1, y1, x2, y2 = w.get("x1"), w.get("y1"), w.get("x2"), w.get("y2")
                orient = "vertical" if _approx_equal(x1, x2) else ("horizontal" if _approx_equal(y1, y2) else "diagonal")
                length = ((float(x2)-float(x1))**2 + (float(y2)-float(y1))**2)**0.5
                print(f"  walls[{i}] id={w_id}: x1={x1}, y1={y1}, x2={x2}, y2={y2}, {orient}, len={length:.3f}{marker}")
                # Show ALL extra fields
                extra = {k: v for k, v in w.items() if k not in ("x1", "y1", "x2", "y2", "id", "type", "thickness")}
                if extra:
                    print(f"    EXTRA: {extra}")
    else:
        print("No 'walls' array found.")

    # === STEP D: All door definitions (deduplicated) ===
    _print_section("STEP D: ALL DOOR OBJECTS (deduplicated, full schema)")
    if objects and isinstance(objects, list):
        seen_door_ids = set()
        for i, obj in enumerate(objects):
            if isinstance(obj, dict) and obj.get("type") == "door":
                door_id = obj.get("id", f"<no_id_{i}>")
                if door_id in seen_door_ids:
                    continue
                seen_door_ids.add(door_id)
                print(f"\n--- door at objects[{i}], id={door_id} ---")
                print(_print_dict(obj))
                # Compute which wall this door sits on
                pos = obj.get("position") or obj.get("pos")
                if isinstance(pos, dict) and "x" in pos and "y" in pos:
                    dx, dy = float(pos["x"]), float(pos["y"])
                    print(f"\n  Geometric analysis of door position ({dx}, {dy}):")
                    if walls:
                        for j, w in enumerate(walls):
                            if not isinstance(w, dict):
                                continue
                            try:
                                wx1, wy1 = float(w["x1"]), float(w["y1"])
                                wx2, wy2 = float(w["x2"]), float(w["y2"])
                            except (KeyError, TypeError, ValueError):
                                continue
                            on_wall = False
                            if _approx_equal(wx1, wx2):  # vertical
                                on_wall = _approx_equal(dx, wx1, 0.1) and min(wy1, wy2)-0.01 <= dy <= max(wy1, wy2)+0.01
                            elif _approx_equal(wy1, wy2):  # horizontal
                                on_wall = _approx_equal(dy, wy1, 0.1) and min(wx1, wx2)-0.01 <= dx <= max(wx1, wx2)+0.01
                            if on_wall:
                                print(f"    -> LIES ON walls[{j}] id={w.get('id')}")
                    # Check explicit wall_id
                    wid = obj.get("wall_id")
                    if wid:
                        print(f"    -> explicit wall_id field: {wid}")

    # === STEP E: All string occurrences of target node IDs ===
    _print_section("STEP E: ALL STRING OCCURRENCES of target node IDs")
    print(f"Searching for: {sorted(TARGET_NODE_IDS)}")
    occurrences = _find_string_occurrences(data, TARGET_NODE_IDS)
    print(f"\nTotal occurrences: {len(occurrences)}")
    for path, val in occurrences:
        print(f"  {path} = {val!r}")

    # === STEP F: Find node objects ===
    _print_section("STEP F: NODE OBJECTS (any dict with a string field matching target node ID)")
    nodes = _find_nodes_with_id(data, TARGET_NODE_IDS)
    print(f"Total node objects found: {len(nodes)}")
    for path, val in nodes:
        print(f"\n--- node at {path} ---")
        print(_print_dict(val))
        # Extract coords
        x, y = _extract_coords(val)
        if x is not None and y is not None:
            print(f"  Coordinates: ({x}, {y})")

    # === STEP G: Find target edge in graph (extended search) ===
    _print_section("STEP G: TARGET EDGE exit_south <-> kitchen_bed_2 in graph (extended)")
    target_edges = _find_edges_in_graph(data, TARGET_EDGE)
    print(f"Direct edge matches: {len(target_edges)}")
    for path, val in target_edges:
        print(f"\n  Path: {path}")
        print(f"  Value:\n{_print_dict(val)}")

    # Also look for adjacency lists containing exit_south OR kitchen_bed_2
    print(f"\n--- Adjacency list references to exit_south ---")
    adj_es = _find_adjacency_lists_for_node(data, "tavern:exit_south")
    adj_es_short = _find_adjacency_lists_for_node(data, "exit_south")
    for path, val in adj_es + adj_es_short:
        print(f"\n  Path: {path}")
        print(f"  Value:\n{_print_dict(val)}")

    print(f"\n--- Adjacency list references to kitchen_bed_2 ---")
    adj_kb = _find_adjacency_lists_for_node(data, "tavern:kitchen_bed_2")
    adj_kb_short = _find_adjacency_lists_for_node(data, "kitchen_bed_2")
    for path, val in adj_kb + adj_kb_short:
        print(f"\n  Path: {path}")
        print(f"  Value:\n{_print_dict(val)}")

    # === STEP H: Look for graph/edges/connections section explicitly ===
    _print_section("STEP H: LOOK FOR GRAPH/EDGES/CONNECTIONS SECTIONS")
    if isinstance(data, dict):
        graph_section_keys = []
        for k, v in data.items():
            if any(kw in k.lower() for kw in ("graph", "edge", "connection", "adjacen", "neighbor", "exit", "transition", "link", "portal")):
                graph_section_keys.append((k, v))
        if graph_section_keys:
            for k, v in graph_section_keys:
                print(f"\n--- top-level key: {k} ---")
                print(f"  type: {type(v).__name__}")
                if isinstance(v, list):
                    print(f"  length: {len(v)}")
                    print(f"  first 3 items:")
                    for i, item in enumerate(v[:3]):
                        print(f"    [{i}]: {_print_dict(item)[:200]}")
                elif isinstance(v, dict):
                    print(f"  keys: {list(v.keys())[:10]}")
                    print(f"  full (truncated to 2000 chars):")
                    print(f"  {_print_dict(v)[:2000]}")
                else:
                    print(f"  value: {v}")
        else:
            print("No graph/edges/connections section found at top level.")
            print("This suggests edges are embedded within node objects (adjacency lists).")
            print("Inspect Step F (node objects) — they may have an 'exits' or 'neighbors' field.")

    # === STEP I: Geometric analysis ===
    _print_section("STEP I: GEOMETRIC ANALYSIS — exit_south and kitchen_bed_2 coordinates")
    # Build node coords map from STEP F
    node_coords: Dict[str, Tuple[float, float]] = {}
    for path, val in nodes:
        if isinstance(val, dict):
            for k, v in val.items():
                if isinstance(v, str) and v in TARGET_NODE_IDS:
                    x, y = _extract_coords(val)
                    if x is not None and y is not None:
                        node_coords[v] = (x, y)
                    break

    print(f"\nNode coordinates extracted:")
    for nid, (x, y) in node_coords.items():
        print(f"  {nid}: ({x}, {y})")

    es = node_coords.get("tavern:exit_south") or node_coords.get("exit_south")
    kb = node_coords.get("tavern:kitchen_bed_2") or node_coords.get("kitchen_bed_2")

    if es and kb:
        print(f"\nexit_south coords: ({es[0]}, {es[1]})")
        print(f"kitchen_bed_2 coords: ({kb[0]}, {kb[1]})")
        # Check if line crosses x=19.5
        if (es[0] - 19.5) * (kb[0] - 19.5) < 0:
            t = (19.5 - es[0]) / (kb[0] - es[0])
            y_cross = es[1] + t * (kb[1] - es[1])
            in_wall = (TARGET_WALL["y1"] - 1e-6) <= y_cross <= (TARGET_WALL["y2"] + 1e-6)
            print(f"\nLine exit_south -> kitchen_bed_2 crosses x=19.5 at y={y_cross:.3f}")
            print(f"Wall y-extent: [{TARGET_WALL['y1']}, {TARGET_WALL['y2']}]")
            print(f"Intersection point (19.5, {y_cross:.3f}) {'IS' if in_wall else 'is NOT'} inside wall extent.")
            if in_wall:
                print(f"\n>>> CONFIRMED: edge crosses wall_5 at (19.5, {y_cross:.3f}).")
                print(">>> Need a door at this point for edge to be valid.")
        else:
            print(f"\nLine does not cross x=19.5 (both nodes on same side of wall_5).")
    else:
        print("\n[WARN] Cannot compute intersection — node coordinates not found.")
        print("Probe v3 needed: investigate object schema more deeply (objects[] with non-standard fields).")

    # === STEP J: Summary ===
    _print_section("STEP J: SUMMARY v2")
    print(f"\nMap file: {candidate}")
    print(f"Top-level keys: {list(data.keys()) if isinstance(data, dict) else 'N/A'}")
    print(f"\nTarget wall_5: confirmed at walls[2]")
    print(f"Target nodes found: {len(node_coords)}/{len(TARGET_NODE_IDS)}")
    if node_coords:
        for nid, (x, y) in node_coords.items():
            print(f"  {nid}: ({x}, {y})")
    print(f"Target edges found: {len(target_edges)}")
    print(f"\nDoor-wall binding schema: door.wall_id (door has 'wall_id' field referencing wall.id)")
    print(f"  - door_0: wall_id='wall_2' (Главный вход на верхней внешней стене)")
    print(f"  - door_1: NO wall_id field (Дверь на кухню, position-based)")
    if objects and isinstance(objects, list):
        door_count = sum(1 for o in objects if isinstance(o, dict) and o.get("type") == "door")
        print(f"\nTotal door objects in map: {door_count}")
        print(f"Door at wall_5 (target wall): {'FOUND' if any(_door_at_wall_5(objects)) else 'NOT FOUND'}")

    return 0


def _door_at_wall_5(objects: List[Any]) -> List[Dict[str, Any]]:
    """Helper: find doors that lie on wall_5 (x=19.5, y in [0.5, 8.0])."""
    out = []
    for obj in objects:
        if not isinstance(obj, dict) or obj.get("type") != "door":
            continue
        pos = obj.get("position") or obj.get("pos")
        if isinstance(pos, dict) and "x" in pos and "y" in pos:
            try:
                dx, dy = float(pos["x"]), float(pos["y"])
                if _approx_equal(dx, 19.5, 0.1) and 0.5 - 0.01 <= dy <= 8.0 + 0.01:
                    out.append(obj)
            except (TypeError, ValueError):
                continue
    return out


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"\n[FATAL] {type(e).__name__}: {e}")
        traceback.print_exc()
        sys.exit(1)
