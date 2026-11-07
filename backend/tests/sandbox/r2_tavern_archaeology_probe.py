# backend/tests/sandbox/r2_tavern_archaeology_probe.py
"""
R2-TAVERN-ARCHAEOLOGY probe.

Read-only archaeological survey of the tavern map:
  1. Locate the map file (search candidates in settings.data_dir and known paths).
  2. Find the WALL with x1=19.5, y1=0.5, x2=19.5, y2=8.0 (the one SpatialValidator flagged).
  3. Find ALL doors / passages and their `wall_id` (or equivalent linking mechanism).
  4. Determine whether a door physically exists at the intersection of edge
     `exit_south <-> kitchen_bed_2` with the flagged wall.
  5. Survey neighbouring edges and analogous door-wall links elsewhere in the map.
  6. Establish the exact schema by which a door is bound to a wall.

NO production changes. NO map edits. Read-only.

Run from backend/ root:
  python -m tests.sandbox.r2_tavern_archaeology_probe
  python tests/sandbox/r2_tavern_archaeology_probe.py
"""
from __future__ import annotations
import os, sys, json, traceback
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

TARGET_WALL = {"x1": 19.5, "y1": 0.5, "x2": 19.5, "y2": 8.0}
TARGET_EDGE = ("tavern:exit_south", "tavern:kitchen_bed_2")

# Known node IDs we are interested in.
TARGET_NODES = {
    "tavern:exit_south": "exit_south",
    "tavern:kitchen_bed_2": "kitchen_bed_2",
    "tavern:fireplace": "fireplace (NPC starting position)",
    "tavern:kitchen": "kitchen (common schedule target)",
    "tavern:kitchen_bed_1": "kitchen_bed_1 (sister node)",
}


def _approx_equal(a: float, b: float, tol: float = 1e-6) -> bool:
    try:
        return abs(float(a) - float(b)) < tol
    except (TypeError, ValueError):
        return False


def _match_wall(wall: Dict[str, Any], target: Dict[str, float]) -> bool:
    """Check if a wall dict matches the target geometry."""
    if not isinstance(wall, dict):
        return False
    keys = ("x1", "y1", "x2", "y2")
    return all(_approx_equal(wall.get(k), target.get(k)) for k in keys)


def _find_candidate_map_files() -> List[Path]:
    """Search for tavern map files in known locations."""
    candidates: List[Path] = []
    search_roots: List[Path] = []

    # 1. settings.data_dir (most likely location)
    try:
        data_dir = Path(settings.data_dir)
        search_roots.append(data_dir)
    except Exception:
        pass

    # 2. BASE_DIR
    try:
        search_roots.append(Path(BASE_DIR))
    except Exception:
        pass

    # 3. backend/data, backend/maps, backend/static/maps
    if _BACKEND.exists():
        for sub in ("data", "maps", "static", "static/maps", "app/data", "app/maps"):
            p = _BACKEND / sub
            if p.exists():
                search_roots.append(p)

    # 4. Walk for any file with 'tavern' in the name under search roots
    seen = set()
    for root in search_roots:
        if not root.exists():
            continue
        try:
            for path in root.rglob("*tavern*"):
                if path.is_file() and path.suffix.lower() in (".json", ".yaml", ".yml", ".toml", ".py"):
                    if path not in seen:
                        candidates.append(path)
                        seen.add(path)
        except (PermissionError, OSError):
            continue

    # 5. Also try the common data/scenes/locations path
    for root in search_roots:
        for sub in ("scenes", "locations", "maps", "scenes/tavern", "locations/tavern"):
            p = root / sub
            if p.exists():
                try:
                    for path in p.rglob("*"):
                        if path.is_file() and "tavern" in path.name.lower():
                            if path not in seen:
                                candidates.append(path)
                                seen.add(path)
                except (PermissionError, OSError):
                    continue

    return candidates


def _load_map_file(path: Path) -> Tuple[Optional[Any], str]:
    """Try to load map file as JSON/YAML/TOML. Returns (data, format)."""
    suffix = path.suffix.lower()
    raw = path.read_text(encoding="utf-8", errors="replace")
    if suffix == ".json":
        try:
            return json.loads(raw), "json"
        except Exception:
            return None, "json-error"
    elif suffix in (".yaml", ".yml"):
        try:
            import yaml  # type: ignore
            return yaml.safe_load(raw), "yaml"
        except ImportError:
            return raw, "yaml-text-no-parser"
        except Exception:
            return None, "yaml-error"
    elif suffix == ".toml":
        try:
            import tomllib  # py3.11+
            return tomllib.loads(raw), "toml"
        except Exception:
            try:
                import toml  # type: ignore
                return toml.loads(raw), "toml"
            except Exception:
                return raw, "toml-text-no-parser"
    elif suffix == ".py":
        # If it's a python file, return raw text — we can search for patterns.
        return raw, "python-text"
    return raw, "text"


def _flatten_search(obj: Any, key_path: str = "") -> List[Tuple[str, Any]]:
    """Recursively flatten a dict/list structure for keyword searching.
    Returns list of (dotted_path, value) tuples where value is non-dict/non-list leaf,
    OR dict nodes whose keys contain certain keywords.
    """
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


def _find_target_wall_in_data(data: Any) -> List[Tuple[str, Dict[str, Any]]]:
    """Search the loaded data for any dict matching TARGET_WALL geometry."""
    matches: List[Tuple[str, Dict[str, Any]]] = []
    flat = _flatten_search(data)
    for path, val in flat:
        if isinstance(val, dict) and _match_wall(val, TARGET_WALL):
            matches.append((path, val))
    return matches


def _find_all_walls(data: Any) -> List[Tuple[str, Dict[str, Any]]]:
    """Find all wall-like dicts (have x1, y1, x2, y2 numeric keys)."""
    walls: List[Tuple[str, Dict[str, Any]]] = []
    flat = _flatten_search(data)
    for path, val in flat:
        if isinstance(val, dict):
            keys_present = all(k in val for k in ("x1", "y1", "x2", "y2"))
            if keys_present:
                try:
                    float(val["x1"]); float(val["y1"])
                    float(val["x2"]); float(val["y2"])
                    walls.append((path, val))
                except (TypeError, ValueError):
                    continue
    return walls


def _find_all_doors(data: Any) -> List[Tuple[str, Dict[str, Any]]]:
    """Find all door-like dicts (have 'door' in path or in keys/values)."""
    doors: List[Tuple[str, Dict[str, Any]]] = []
    flat = _flatten_search(data)
    door_keywords = ("door", "passage", "portal", "gateway", "opening")
    for path, val in flat:
        path_lower = path.lower()
        # Match by path keyword
        if any(kw in path_lower for kw in door_keywords):
            if isinstance(val, dict):
                doors.append((path, val))
            elif isinstance(val, list):
                for i, item in enumerate(val):
                    if isinstance(item, dict):
                        doors.append((f"{path}[{i}]", item))
            elif isinstance(val, str):
                # door id reference
                doors.append((path, {"_value": val}))
        # Match by dict content
        elif isinstance(val, dict):
            for k, v in val.items():
                if isinstance(k, str) and any(kw in k.lower() for kw in door_keywords):
                    doors.append((path, val))
                    break
                if isinstance(v, str) and any(kw in v.lower() for kw in door_keywords):
                    doors.append((path, val))
                    break
    # Deduplicate by path
    seen = set()
    unique = []
    for path, val in doors:
        if path not in seen:
            unique.append((path, val))
            seen.add(path)
    return unique


def _find_target_edge_in_data(data: Any) -> List[Tuple[str, Any]]:
    """Find edges in graph connecting exit_south <-> kitchen_bed_2."""
    edges: List[Tuple[str, Any]] = []
    flat = _flatten_search(data)
    targets = [TARGET_EDGE[0], TARGET_EDGE[1]]
    for path, val in flat:
        if isinstance(val, dict):
            # Common edge representation: {"from": ..., "to": ...} or {"source": ..., "target": ...}
            for from_k, to_k in (("from", "to"), ("source", "target"),
                                  ("src", "dst"), ("a", "b"),
                                  ("node_a", "node_b"), ("u", "v")):
                if from_k in val and to_k in val:
                    f = str(val[from_k]); t = str(val[to_k])
                    if (f in targets and t in targets) or (t in targets and f in targets):
                        edges.append((path, val))
                        break
        elif isinstance(val, list) and len(val) == 2:
            a, b = str(val[0]), str(val[1])
            if (a in targets and b in targets) or (b in targets and a in targets):
                edges.append((path, val))
        elif isinstance(val, str) and "->" in val:
            parts = [p.strip() for p in val.split("->")]
            if len(parts) == 2 and all(p in targets for p in parts):
                edges.append((path, val))
    return edges


def _find_all_nodes_referencing_target(data: Any) -> List[Tuple[str, Dict[str, Any]]]:
    """Find all dicts that describe exit_south, kitchen_bed_2, fireplace, etc."""
    refs: List[Tuple[str, Dict[str, Any]]] = []
    flat = _flatten_search(data)
    for path, val in flat:
        if isinstance(val, dict):
            # Check all string values for node IDs
            for k, v in val.items():
                if isinstance(v, str) and v in TARGET_NODES:
                    refs.append((path, val))
                    break
                # Some maps use 'id' or 'node_id' for the node itself
                if k in ("id", "node_id", "node", "name") and isinstance(v, str) and v in TARGET_NODES:
                    refs.append((path, val))
                    break
        elif isinstance(val, str) and val in TARGET_NODES:
            refs.append((path, {"_value": val}))
    # Deduplicate by path
    seen = set()
    unique = []
    for path, val in refs:
        if path not in seen:
            unique.append((path, val))
            seen.add(path)
    return unique


def _find_door_wall_bindings(data: Any) -> List[Dict[str, Any]]:
    """Find door-wall binding patterns.

    Look for:
      - doors with explicit wall_id reference
      - doors with geometry overlapping a wall (x/y within wall extent)
      - walls with door_id reference
      - doors with from/to matching wall endpoints
    """
    bindings: List[Dict[str, Any]] = []
    flat = _flatten_search(data)
    doors = _find_all_doors(data)
    walls = _find_all_walls(data)

    for d_path, d_val in doors:
        if not isinstance(d_val, dict):
            continue
        # Pattern 1: door has wall_id
        wall_id = d_val.get("wall_id") or d_val.get("wall") or d_val.get("wall_ref") or d_val.get("wallId")
        if wall_id:
            bindings.append({
                "binding_type": "door.wall_id",
                "door_path": d_path,
                "door": d_val,
                "wall_id_referenced": wall_id,
            })
            continue
        # Pattern 2: door has wall_x1..y2
        if all(k in d_val for k in ("wall_x1", "wall_y1", "wall_x2", "wall_y2")):
            bindings.append({
                "binding_type": "door.wall_geometry",
                "door_path": d_path,
                "door": d_val,
            })
            continue
        # Pattern 3: door has its own geometry that overlaps a wall
        door_x = d_val.get("x") or d_val.get("pos_x") or d_val.get("px")
        door_y = d_val.get("y") or d_val.get("pos_y") or d_val.get("py")
        if door_x is not None and door_y is not None:
            try:
                dx, dy = float(door_x), float(door_y)
                for w_path, w_val in walls:
                    try:
                        wx1, wy1 = float(w_val["x1"]), float(w_val["y1"])
                        wx2, wy2 = float(w_val["x2"]), float(w_val["y2"])
                        # Check if door point lies on wall segment
                        # Wall is along x or y axis
                        on_wall = False
                        if _approx_equal(wx1, wx2):  # vertical wall
                            on_wall = _approx_equal(dx, wx1) and (min(wy1, wy2) - 1e-6 <= dy <= max(wy1, wy2) + 1e-6)
                        elif _approx_equal(wy1, wy2):  # horizontal wall
                            on_wall = _approx_equal(dy, wy1) and (min(wx1, wx2) - 1e-6 <= dx <= max(wx1, wx2) + 1e-6)
                        if on_wall:
                            bindings.append({
                                "binding_type": "door.geometry_overlap",
                                "door_path": d_path,
                                "door": d_val,
                                "wall_path": w_path,
                                "wall": w_val,
                            })
                            break
                    except (TypeError, ValueError, KeyError):
                        continue
            except (TypeError, ValueError):
                pass
    return bindings


def _find_walls_with_door_id(data: Any) -> List[Tuple[str, Dict[str, Any]]]:
    """Find walls that have a door_id / door_ref field."""
    walls = _find_all_walls(data)
    out: List[Tuple[str, Dict[str, Any]]] = []
    for path, val in walls:
        for k in ("door_id", "door_ref", "door", "doorId", "passage_id", "passage_ref"):
            if k in val and val[k]:
                out.append((path, val))
                break
    return out


def _print_section(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def _print_dict(obj: Any, indent: int = 2, max_depth: int = 5) -> str:
    """Pretty print dict as JSON (or fallback)."""
    try:
        return json.dumps(obj, ensure_ascii=False, indent=2, default=str)
    except Exception:
        return str(obj)


def main() -> int:
    print("=" * 78)
    print("R2-TAVERN-ARCHAEOLOGY — read-only survey")
    print(f"Target wall: {TARGET_WALL}")
    print(f"Target edge: {TARGET_EDGE}")
    print("=" * 78)

    # === Step 1: Locate candidate map files ===
    _print_section("STEP 1: Locate candidate map files")
    candidates = _find_candidate_map_files()
    if not candidates:
        print("[FATAL] No tavern map files found in known locations.")
        print("Search roots tried:")
        try:
            print(f"  settings.data_dir = {settings.data_dir}")
        except Exception:
            pass
        try:
            print(f"  BASE_DIR = {BASE_DIR}")
        except Exception:
            pass
        print(f"  _BACKEND = {_BACKEND}")
        return 1

    print(f"Found {len(candidates)} candidate file(s):")
    for i, p in enumerate(candidates):
        try:
            size = p.stat().st_size
        except OSError:
            size = -1
        print(f"  [{i}] {p} ({size} bytes)")

    # === Step 2: Load each and look for target wall ===
    _print_section("STEP 2: Load and locate TARGET WALL (x1=19.5, y1=0.5, x2=19.5, y2=8.0)")
    chosen_file: Optional[Path] = None
    chosen_data: Any = None
    chosen_format: Optional[str] = None
    target_wall_matches: List[Tuple[str, Dict[str, Any]]] = []

    for p in candidates:
        try:
            data, fmt = _load_map_file(p)
        except Exception as e:
            print(f"  [skip] {p}: load error {e}")
            continue
        if data is None:
            print(f"  [skip] {p}: load returned None (format={fmt})")
            continue
        matches = _find_target_wall_in_data(data)
        if matches:
            print(f"\n*** MATCH in {p} (format={fmt}) ***")
            print(f"  Found {len(matches)} matching wall(s):")
            for path, val in matches:
                print(f"\n  Path: {path}")
                print(f"  Value:\n{_print_dict(val)}")
            chosen_file = p
            chosen_data = data
            chosen_format = fmt
            target_wall_matches = matches
            break
        else:
            print(f"  [no match] {p} (format={fmt})")

    if chosen_file is None or chosen_data is None:
        print("\n[FATAL] TARGET WALL not found in any candidate file.")
        print("Attempting broader analysis: dumping all walls from all candidates.")
        for p in candidates:
            try:
                data, fmt = _load_map_file(p)
            except Exception:
                continue
            if data is None:
                continue
            walls = _find_all_walls(data)
            if walls:
                print(f"\n--- {p} ({fmt}): {len(walls)} walls ---")
                for wpath, wval in walls[:5]:
                    print(f"  {wpath}: {wval}")
        return 1

    # === Step 3: All walls in chosen file ===
    _print_section("STEP 3: All walls in chosen map file")
    all_walls = _find_all_walls(chosen_data)
    print(f"Total walls: {len(all_walls)}")
    for path, val in all_walls:
        is_target = _match_wall(val, TARGET_WALL)
        marker = " <== TARGET" if is_target else ""
        try:
            x1, y1, x2, y2 = val["x1"], val["y1"], val["x2"], val["y2"]
            # Detect orientation
            if _approx_equal(x1, x2):
                orient = "vertical"
            elif _approx_equal(y1, y2):
                orient = "horizontal"
            else:
                orient = "diagonal"
            length = ((float(x2)-float(x1))**2 + (float(y2)-float(y1))**2)**0.5
            print(f"  {path}: x1={x1}, y1={y1}, x2={x2}, y2={y2}, {orient}, len={length:.3f}{marker}")
            # Show extra fields (door_id, etc.)
            extra_keys = set(val.keys()) - {"x1", "y1", "x2", "y2"}
            if extra_keys:
                print(f"    extra keys: {dict({k: val[k] for k in extra_keys})}")
        except Exception as e:
            print(f"  {path}: {val} (parse error: {e}){marker}")

    # === Step 4: All doors / passages ===
    _print_section("STEP 4: All doors / passages")
    all_doors = _find_all_doors(chosen_data)
    print(f"Total doors/passages: {len(all_doors)}")
    for path, val in all_doors:
        print(f"\n  Path: {path}")
        print(f"  Value:\n{_print_dict(val)}")

    # === Step 5: Door-wall bindings ===
    _print_section("STEP 5: Door-wall binding analysis")
    bindings = _find_door_wall_bindings(chosen_data)
    walls_with_door = _find_walls_with_door_id(chosen_data)

    print(f"\n5a. Door-wall bindings detected: {len(bindings)}")
    for b in bindings:
        print(f"\n  Binding type: {b['binding_type']}")
        print(f"  Door path: {b.get('door_path')}")
        print(f"  Door: {_print_dict(b.get('door'))}")
        if "wall_id_referenced" in b:
            print(f"  Wall ID referenced: {b['wall_id_referenced']}")
        if "wall_path" in b:
            print(f"  Wall path: {b['wall_path']}")
            print(f"  Wall: {_print_dict(b.get('wall'))}")

    print(f"\n5b. Walls with explicit door_id/door_ref: {len(walls_with_door)}")
    for path, val in walls_with_door:
        print(f"\n  Wall path: {path}")
        print(f"  Wall value: {_print_dict(val)}")

    # === Step 6: Target edge in graph ===
    _print_section("STEP 6: TARGET EDGE exit_south <-> kitchen_bed_2 in graph")
    target_edges = _find_target_edge_in_data(chosen_data)
    print(f"Target edge matches: {len(target_edges)}")
    for path, val in target_edges:
        print(f"\n  Path: {path}")
        print(f"  Value:\n{_print_dict(val)}")

    # === Step 7: All node references to target nodes ===
    _print_section("STEP 7: Node definitions for exit_south / kitchen_bed_2 / fireplace / etc.")
    node_refs = _find_all_nodes_referencing_target(chosen_data)
    print(f"Node references found: {len(node_refs)}")
    for path, val in node_refs:
        print(f"\n  Path: {path}")
        print(f"  Value:\n{_print_dict(val)}")

    # === Step 8: Geometric analysis of target edge intersection ===
    _print_section("STEP 8: Geometric analysis — where does exit_south <-> kitchen_bed_2 cross the wall?")
    # Find coordinates of exit_south and kitchen_bed_2 nodes
    node_coords: Dict[str, Tuple[Optional[float], Optional[float]]] = {}
    for path, val in node_refs:
        if isinstance(val, dict):
            # Find the node_id
            node_id = (val.get("id") or val.get("node_id") or val.get("node")
                       or val.get("name") or val.get("node_name"))
            if not node_id:
                for k, v in val.items():
                    if isinstance(v, str) and v in TARGET_NODES:
                        node_id = v
                        break
            if not node_id:
                continue
            # Find x/y
            x = (val.get("x") or val.get("pos_x") or val.get("px")
                 or val.get("position_x") or val.get("coord_x"))
            y = (val.get("y") or val.get("pos_y") or val.get("py")
                 or val.get("position_y") or val.get("coord_y"))
            if x is not None and y is not None:
                try:
                    node_coords[str(node_id)] = (float(x), float(y))
                except (TypeError, ValueError):
                    pass
            # Also look for nested position dict
            for pos_key in ("position", "pos", "coords", "coordinates"):
                if pos_key in val and isinstance(val[pos_key], dict):
                    pp = val[pos_key]
                    xx = pp.get("x") or pp.get("px")
                    yy = pp.get("y") or pp.get("py")
                    if xx is not None and yy is not None:
                        try:
                            node_coords[str(node_id)] = (float(xx), float(yy))
                        except (TypeError, ValueError):
                            pass

    print(f"\nNode coordinates found:")
    for nid, (x, y) in node_coords.items():
        print(f"  {nid}: ({x}, {y})")

    # Geometry of the target wall
    print(f"\nTarget wall geometry: x1={TARGET_WALL['x1']}, y1={TARGET_WALL['y1']}, "
          f"x2={TARGET_WALL['x2']}, y2={TARGET_WALL['y2']}")
    print(f"Wall is VERTICAL at x={TARGET_WALL['x1']}, spanning y=[{TARGET_WALL['y1']}, {TARGET_WALL['y2']}]")

    # Compute where a straight line exit_south -> kitchen_bed_2 crosses x=19.5
    es = node_coords.get(TARGET_EDGE[0])
    kb = node_coords.get(TARGET_EDGE[1])
    if es and kb:
        print(f"\nexit_south coords: ({es[0]}, {es[1]})")
        print(f"kitchen_bed_2 coords: ({kb[0]}, {kb[1]})")
        # Check if line crosses x=19.5
        if (es[0] - 19.5) * (kb[0] - 19.5) < 0:
            # Crosses — compute intersection y
            t = (19.5 - es[0]) / (kb[0] - es[0])
            y_cross = es[1] + t * (kb[1] - es[1])
            in_wall = (TARGET_WALL["y1"] - 1e-6) <= y_cross <= (TARGET_WALL["y2"] + 1e-6)
            print(f"\nLine exit_south -> kitchen_bed_2 crosses x=19.5 at y={y_cross:.3f}")
            print(f"Wall y-extent: [{TARGET_WALL['y1']}, {TARGET_WALL['y2']}]")
            print(f"Intersection point (19.5, {y_cross:.3f}) {'IS' if in_wall else 'is NOT'} inside wall extent.")
            if in_wall:
                print(f"\n>>> CONFIRMED: edge crosses the target wall at (19.5, {y_cross:.3f}).")
                print(">>> A door MUST exist at this point for the edge to be valid.")
                print(">>> Checking for door at this coordinate...")

                # Look for a door at (19.5, y_cross)
                door_at_intersection = None
                for d_path, d_val in all_doors:
                    if isinstance(d_val, dict):
                        dx = (d_val.get("x") or d_val.get("pos_x") or d_val.get("px"))
                        dy = (d_val.get("y") or d_val.get("pos_y") or d_val.get("py"))
                        if dx is not None and dy is not None:
                            try:
                                fdx, fdy = float(dx), float(dy)
                                if _approx_equal(fdx, 19.5, tol=0.01) and abs(fdy - y_cross) < 0.5:
                                    door_at_intersection = (d_path, d_val)
                                    break
                            except (TypeError, ValueError):
                                continue
                if door_at_intersection:
                    print(f"\n*** DOOR FOUND at intersection point ***")
                    print(f"  Path: {door_at_intersection[0]}")
                    print(f"  Value:\n{_print_dict(door_at_intersection[1])}")
                else:
                    print(f"\n>>> NO DOOR FOUND at intersection point (19.5, {y_cross:.3f})")
                    print(">>> This confirms the SpatialValidator's complaint: edge crosses solid wall without a door.")
        else:
            print(f"\nLine exit_south -> kitchen_bed_2 does NOT cross x=19.5.")
            print("(This would contradict SpatialValidator — investigate further.)")

    # === Step 9: Survey analogous door-wall links (existing valid examples) ===
    _print_section("STEP 9: Survey analogous door-wall bindings (valid examples to use as template)")
    print(f"Looking at the {len(bindings)} door-wall bindings found in step 5:")
    print("These are the established patterns by which doors are bound to walls in this map.")
    print("If any exist, they should be used as the template for the proposed fix.")
    if bindings:
        print("\n--- Examples to use as template ---")
        # Show first 3 examples with full structure
        for i, b in enumerate(bindings[:3]):
            print(f"\nExample {i+1}: {b.get('binding_type')}")
            print(f"  Door: {_print_dict(b.get('door'))}")
            if "wall" in b:
                print(f"  Wall: {_print_dict(b.get('wall'))}")
            if "wall_id_referenced" in b:
                print(f"  Wall ID referenced: {b['wall_id_referenced']}")
    else:
        print("\n[WARN] No door-wall bindings detected. The map may use a different schema.")
        print("Suggest manual inspection of the raw map file structure.")

    # === Step 10: Summary ===
    _print_section("STEP 10: ARCHAEOLOGICAL SUMMARY")
    print(f"\nMap file: {chosen_file}")
    print(f"Format: {chosen_format}")
    print(f"\nTarget wall found: {len(target_wall_matches) > 0}")
    if target_wall_matches:
        print(f"  Path in file: {target_wall_matches[0][0]}")
        print(f"  Wall value: {_print_dict(target_wall_matches[0][1])}")
    print(f"\nTotal walls in map: {len(all_walls)}")
    print(f"Total doors/passages detected: {len(all_doors)}")
    print(f"Door-wall bindings detected: {len(bindings)}")
    print(f"Walls with explicit door_id: {len(walls_with_door)}")
    print(f"Target edge matches in graph: {len(target_edges)}")
    print(f"Node coordinate lookups: {len(node_coords)}")
    print(f"\nNode coordinates:")
    for nid, (x, y) in node_coords.items():
        print(f"  {nid}: ({x}, {y})")

    # === Proposed minimal diff ===
    _print_section("PROPOSED MINIMAL DIFF (schematic — DO NOT APPLY)")
    print("""
Based on the analysis above, the minimal fix is one of:

OPTION A: Add `door` wall_id to the target wall (preferred if door-wall pattern A is used).
  wall_id="..." must reference an existing door definition.

  wall_dict = {
      "x1": 19.5, "y1": 0.5,
      "x2": 19.5, "y2": 8.0,
      "door_id": "<existing_or_new_door_id>",   # <- ADD THIS
  }

OPTION B: Define a new door object at the intersection point (19.5, y_cross),
  and add door_id to the wall.

  {
    "id": "<new_door_id>",
    "x": 19.5,
    "y": <y_cross>,
    "wall_id": "<wall_id_of_target_wall>",
    "type": "door",
    ...
  }

OPTION C: Remove the edge `exit_south <-> kitchen_bed_2` from the graph
  and let the pathfinder route through an alternative path.
  (Only valid if such an alternative exists in the graph.)

The exact field names (door_id, wall_id, etc.) MUST match the schema
detected in step 5. Apply the fix only after Master verifies this report.
""")

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"\n[FATAL] {type(e).__name__}: {e}")
        traceback.print_exc()
        sys.exit(1)
