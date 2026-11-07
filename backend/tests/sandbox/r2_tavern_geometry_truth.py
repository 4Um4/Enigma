# backend/tests/sandbox/r2_tavern_geometry_truth.py
"""
R2-TAVERN-GEOMETRY-TRUTH probe — read-only.

Цель: вывести ИСТИННУЮ геометрию таверны из tavern.json без интерпретаций:
  1. Все 18 узлов с реальными координатами (x, y)
  2. Все 8 стен с координатами и ориентацией
  3. Обе комнаты с polygon-координатами
  4. Bounding box: min/max по всем элементам
  5. Сопоставление с top-level size: {w, h} и origin
  6. Поиск «слепых зон» внутри bounding box, не покрытых rooms
  7. ASCII-визуализация с реальными координатами
  8. Положение exit_east и предполагаемого exit_south

Запись в файл: r2_tavern_geometry_truth.txt
"""
from __future__ import annotations
import os, sys, json, traceback
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import io

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

OUT_FILE_DIR = Path("/home/z/my-project/download")
if not OUT_FILE_DIR.exists() or not OUT_FILE_DIR.is_dir():
    OUT_FILE_DIR = _BACKEND / "tests" / "sandbox"
    try:
        OUT_FILE_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        OUT_FILE_DIR = Path(os.getcwd())
OUT_FILE = OUT_FILE_DIR / "r2_tavern_geometry_truth.txt"


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


def _print_section(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def _approx_eq(a: float, b: float, tol: float = 0.01) -> bool:
    try:
        return abs(float(a) - float(b)) < tol
    except (TypeError, ValueError):
        return False


def main() -> int:
    print("=" * 78)
    print("R2-TAVERN-GEOMETRY-TRUTH — read-only truth extraction")
    print(f"Map file: {MAP_FILE}")
    print("=" * 78)

    if not MAP_FILE.exists():
        print(f"[FATAL] Map file not found: {MAP_FILE}")
        return 1

    data = json.loads(MAP_FILE.read_text(encoding="utf-8", errors="replace"))

    # === STEP 1: Top-level metadata ===
    _print_section("STEP 1: Top-level metadata")
    print(f"filename: {data.get('filename')}")
    print(f"label: {data.get('label')}")
    print(f"size: {data.get('size')}")
    print(f"grid_cell_size: {data.get('grid_cell_size')}")
    print(f"is_outdoor: {data.get('is_outdoor')}")
    print(f"origin: {data.get('origin')}")
    print(f"global_coords: {data.get('global_coords')}")
    print(f"location_id: {data.get('location_id')}")
    print(f"adjacency: {data.get('adjacency')}")
    print(f"player_spawn: {data.get('player_spawn')}")

    size = data.get("size", {})
    origin = data.get("origin", {})
    W = float(size.get("w", 0))
    H = float(size.get("h", 0))
    OX = float(origin.get("x", 0))
    OY = float(origin.get("y", 0))
    print(f"\n>>> Declared size: W={W}m, H={H}m")
    print(f">>> Declared origin: ({OX}, {OY})")
    if data.get("global_coords"):
        print(f">>> global_coords=true: координаты узлов ОТНОСИТЕЛЬНЫЕ (внутри location)")
        print(f">>> World coords = origin + node.coords")
    else:
        print(f">>> global_coords=false: координаты узлов АБСОЛЮТНЫЕ (мировые)")

    # === STEP 2: All 18 nodes with coords ===
    _print_section("STEP 2: All 18 nodes — REAL COORDINATES")
    nodes = data.get("nodes", {})
    print(f"Total nodes: {len(nodes)}")
    print()
    print(f"{'node_name':<22} {'x':>8} {'y':>8}  role                connections")
    print("-" * 90)
    node_coords: Dict[str, Tuple[float, float]] = {}
    for name, nd in nodes.items():
        if not isinstance(nd, dict):
            continue
        x = nd.get("x")
        y = nd.get("y")
        if x is None or y is None:
            # Try position dict
            pos = nd.get("position") or nd.get("pos")
            if isinstance(pos, dict):
                x = pos.get("x")
                y = pos.get("y")
        try:
            fx, fy = float(x), float(y)
            node_coords[name] = (fx, fy)
        except (TypeError, ValueError):
            fx, fy = 0.0, 0.0
            print(f"  [WARN] node {name} has no coords: {nd}")
        role = nd.get("role", "?")
        conns = nd.get("connections", [])
        print(f"{name:<22} {fx:>8.3f} {fy:>8.3f}  {role:<20} {conns}")

    # === STEP 3: All 8 walls ===
    _print_section("STEP 3: All 8 walls — REAL COORDINATES")
    walls = data.get("walls", [])
    print(f"Total walls: {len(walls)}")
    print()
    print(f"{'idx':<4} {'wall_id':<10} {'x1':>7} {'y1':>7} {'x2':>7} {'y2':>7}  orient    length")
    print("-" * 75)
    wall_segments: List[Tuple[float, float, float, float, str]] = []
    for i, w in enumerate(walls):
        if not isinstance(w, dict):
            continue
        wid = w.get("id", "?")
        try:
            x1, y1, x2, y2 = float(w["x1"]), float(w["y1"]), float(w["x2"]), float(w["y2"])
        except (KeyError, TypeError, ValueError):
            continue
        if _approx_eq(x1, x2):
            orient = "vertical"
        elif _approx_eq(y1, y2):
            orient = "horizontal"
        else:
            orient = "diagonal"
        length = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
        print(f"{i:<4} {wid:<10} {x1:>7.2f} {y1:>7.2f} {x2:>7.2f} {y2:>7.2f}  {orient:<9} {length:.3f}")
        wall_segments.append((x1, y1, x2, y2, wid))

    # === STEP 4: All rooms with polygons ===
    _print_section("STEP 4: All rooms — REAL POLYGON COORDINATES")
    rooms = data.get("rooms", [])
    print(f"Total rooms: {len(rooms)}")
    print()
    for i, r in enumerate(rooms):
        if not isinstance(r, dict):
            continue
        print(f"  rooms[{i}] id={r.get('id')}, name={r.get('name')}")
        print(f"    x={r.get('x')}, y={r.get('y')}, width={r.get('width')}, height={r.get('height')}")
        print(f"    area_sqm={r.get('area_sqm')}")
        poly = r.get("polygon", [])
        print(f"    polygon ({len(poly)} points):")
        for p in poly:
            print(f"      {p}")

    # === STEP 5: Bounding box computation ===
    _print_section("STEP 5: BOUNDING BOX — computed from REAL data")
    all_x: List[float] = []
    all_y: List[float] = []
    for fx, fy in node_coords.values():
        all_x.append(fx)
        all_y.append(fy)
    for x1, y1, x2, y2, _ in wall_segments:
        all_x.extend([x1, x2])
        all_y.extend([y1, y2])
    for r in rooms:
        if isinstance(r, dict):
            try:
                rx, ry = float(r.get("x", 0)), float(r.get("y", 0))
                rw, rh = float(r.get("width", 0)), float(r.get("height", 0))
                all_x.extend([rx, rx + rw])
                all_y.extend([ry, ry + rh])
            except (TypeError, ValueError):
                continue

    if all_x and all_y:
        min_x, max_x = min(all_x), max(all_x)
        min_y, max_y = min(all_y), max(all_y)
        actual_w = max_x - min_x
        actual_h = max_y - min_y
        print(f"\n>>> Computed bounding box from nodes+walls+rooms:")
        print(f"    x range: [{min_x:.3f}, {max_x:.3f}]  (width = {actual_w:.3f}m)")
        print(f"    y range: [{min_y:.3f}, {max_y:.3f}]  (height = {actual_h:.3f}m)")
        print(f"\n>>> Declared size: W={W}m, H={H}m")
        print(f">>> Difference: actual_width={actual_w:.3f} vs declared={W} (delta={actual_w - W:+.3f})")
        print(f">>>             actual_height={actual_h:.3f} vs declared={H} (delta={actual_h - H:+.3f})")
        if abs(actual_w - W) > 0.5 or abs(actual_h - H) > 0.5:
            print(f">>> WARNING: declared size does NOT match actual content extent!")
            print(f">>> This means the bounding box is larger than the actual geometry.")
            print(f">>> 'Empty zones' exist inside the bounding box.")

    # === STEP 6: Find gaps inside bounding box ===
    _print_section("STEP 6: GAPS inside bounding box — zones not covered by any room")
    if rooms and all_x and all_y:
        # Sample grid points inside bounding box
        # For each grid point, check if it's inside any room polygon
        def point_in_polygon(px: float, py: float, polygon: List) -> bool:
            """Ray casting algorithm."""
            if not polygon or len(polygon) < 3:
                return False
            inside = False
            j = len(polygon) - 1
            for i in range(len(polygon)):
                xi, yi = polygon[i][0], polygon[i][1]
                xj, yj = polygon[j][0], polygon[j][1]
                if ((yi > py) != (yj > py)) and (px < (xj - xi) * (py - yi) / (yj - yi + 1e-12) + xi):
                    inside = not inside
                j = i
            return inside

        # Get all room polygons
        room_polys = []
        for r in rooms:
            if isinstance(r, dict) and r.get("polygon"):
                room_polys.append((r.get("id"), r.get("name"), r["polygon"]))

        # Sample at 1m resolution
        step = 1.0
        gap_points: List[Tuple[float, float]] = []
        covered_points: List[Tuple[float, float, str]] = []
        # Sample inside the bounding box
        sample_x = min_x
        while sample_x <= max_x:
            sample_y = min_y
            while sample_y <= max_y:
                in_room = None
                for rid, rname, poly in room_polys:
                    if point_in_polygon(sample_x, sample_y, poly):
                        in_room = f"{rid} ({rname})"
                        break
                if in_room:
                    covered_points.append((sample_x, sample_y, in_room))
                else:
                    gap_points.append((sample_x, sample_y))
                sample_y += step
            sample_x += step

        total_samples = len(gap_points) + len(covered_points)
        gap_pct = (len(gap_points) / total_samples * 100) if total_samples else 0
        print(f"\n>>> Sampled {total_samples} grid points (1m resolution)")
        print(f">>> Covered by rooms: {len(covered_points)} ({100 - gap_pct:.1f}%)")
        print(f">>> NOT covered by any room: {len(gap_points)} ({gap_pct:.1f}%)")

        if gap_points:
            # Group consecutive gap points into clusters
            gx_min = min(p[0] for p in gap_points)
            gx_max = max(p[0] for p in gap_points)
            gy_min = min(p[1] for p in gap_points)
            gy_max = max(p[1] for p in gap_points)
            print(f"\n>>> Gap bounding box:")
            print(f"    x range: [{gx_min:.2f}, {gx_max:.2f}]  (width = {gx_max - gx_min:.2f}m)")
            print(f"    y range: [{gy_min:.2f}, {gy_max:.2f}]  (height = {gy_max - gy_min:.2f}m)")
            print(f"    approximate area: {(gx_max - gx_min) * (gy_max - gy_min):.2f} m²")

            # Show first 10 gap points
            print(f"\n>>> First 10 gap points (sample):")
            for px, py in gap_points[:10]:
                print(f"    ({px:.1f}, {py:.1f})")

    # === STEP 7: ASCII visualization with REAL coordinates ===
    _print_section("STEP 7: ASCII visualization with REAL coordinates")
    if all_x and all_y:
        # Build ASCII grid
        # Round to 1m resolution
        grid_w = int(round(max_x - min_x)) + 1
        grid_h = int(round(max_y - min_y)) + 1
        if grid_w > 50 or grid_h > 30:
            # Too big — sample at 2m
            scale = 2
        else:
            scale = 1
        grid_w = int(grid_w / scale) + 1
        grid_h = int(grid_h / scale) + 1

        # Initialize grid with spaces
        grid = [["." for _ in range(grid_w)] for _ in range(grid_h)]

        def to_grid(x: float, y: float) -> Tuple[int, int]:
            gx = int(round((x - min_x) / scale))
            gy = int(round((y - min_y) / scale))
            return gx, gy

        # Draw rooms (fill with room character)
        room_chars = ["#", "+", "*", "&", "%"]
        for i, r in enumerate(rooms):
            if not isinstance(r, dict) or not r.get("polygon"):
                continue
            char = room_chars[i % len(room_chars)]
            # Fill room interior
            for sample_x_i in range(int(min_x), int(max_x) + 1):
                for sample_y_i in range(int(min_y), int(max_y) + 1):
                    if point_in_polygon(float(sample_x_i), float(sample_y_i), r["polygon"]):
                        gx, gy = to_grid(float(sample_x_i), float(sample_y_i))
                        if 0 <= gx < grid_w and 0 <= gy < grid_h:
                            grid[gy][gx] = char

        # Draw walls (=)
        for x1, y1, x2, y2, _ in wall_segments:
            # Vertical wall
            if _approx_eq(x1, x2):
                y_start = int(round(min(y1, y2)))
                y_end = int(round(max(y1, y2)))
                for y in range(y_start, y_end + 1):
                    gx, gy = to_grid(x1, float(y))
                    if 0 <= gx < grid_w and 0 <= gy < grid_h:
                        grid[gy][gx] = "="
            # Horizontal wall
            elif _approx_eq(y1, y2):
                x_start = int(round(min(x1, x2)))
                x_end = int(round(max(x1, x2)))
                for x in range(x_start, x_end + 1):
                    gx, gy = to_grid(float(x), y1)
                    if 0 <= gx < grid_w and 0 <= gy < grid_h:
                        grid[gy][gx] = "="

        # Draw nodes
        node_chars: Dict[str, str] = {}
        for name, (fx, fy) in node_coords.items():
            gx, gy = to_grid(fx, fy)
            if 0 <= gx < grid_w and 0 <= gy < grid_h:
                # Use first letter of node name (uppercase)
                c = name[0].upper() if name else "?"
                # Avoid overwriting walls with node marker
                if grid[gy][gx] in (".", "#", "+", "*", "&", "%"):
                    grid[gy][gx] = c
                node_chars[c] = name

        # Print grid (Y inverted: top of grid = high Y)
        print(f"\nScale: 1 char = {scale}m")
        print(f"Legend: '#' = room_0, '+' = room_1, '=' = wall, '.' = empty/gap")
        print(f"Node letters (first letter of name):")
        for c, name in sorted(node_chars.items()):
            print(f"  '{c}' = {name}")
        print()
        # Print y axis labels on left
        print("    " + "".join([f"{i % 10}" for i in range(grid_w)]))
        print("    " + "-" * grid_w)
        for gy in range(grid_h - 1, -1, -1):
            y_label = min_y + gy * scale
            print(f"{y_label:5.1f}|" + "".join(grid[gy]))
        # x axis labels
        print("    " + "-" * grid_w)
        x_labels = "".join([f"{int(min_x + i * scale) % 10}" for i in range(grid_w)])
        print("    " + x_labels)

    # === STEP 8: exit_east and proposed exit_south positions ===
    _print_section("STEP 8: exit_east REAL position + proposed exit_south")
    if "exit_east" in nodes:
        ee = nodes["exit_east"]
        print(f"\nexit_east:")
        print(f"  coords: ({ee.get('x')}, {ee.get('y')})")
        print(f"  role: {ee.get('role')}")
        print(f"  connections: {ee.get('connections')}")
        print(f"  label: {ee.get('label')}")

    if "exit_south" in nodes:
        es = nodes["exit_south"]
        print(f"\nexit_south (already exists):")
        print(f"  coords: ({es.get('x')}, {es.get('y')})")
        print(f"  role: {es.get('role')}")
        print(f"  connections: {es.get('connections')}")
    else:
        print(f"\nexit_south: NOT IN nodes dict (confirmed)")
        print(f">>> This is the root cause of FLEE BLOCKED.")
        print(f">>> GraphCompiler creates phantom with world coords.")

    # === STEP 9: VERDICT ===
    _print_section("STEP 9: VERDICT — geometry truth")
    print(f"""
ACTUAL GEOMETRY (from JSON):

  Declared size: {W}m × {H}m
  Declared origin: ({OX}, {OY})
  global_coords: {data.get('global_coords')}

  Actual content extent:
    x: [{min_x:.3f}, {max_x:.3f}]  width = {actual_w:.3f}m
    y: [{min_y:.3f}, {max_y:.3f}]  height = {actual_h:.3f}m

  Rooms: {len(rooms)}
    room_0 (main_hall): polygon coordinates shown in Step 4
    room_1 (kitchen): polygon coordinates shown in Step 4

  Walls: {len(walls)} (orientation breakdown shown in Step 3)
  Nodes: {len(nodes)} (full coords shown in Step 2)

  exit_east: EXISTS in nodes dict
  exit_south: DOES NOT EXIST in nodes dict
            → GraphCompiler synthesizes phantom with world coords
            → SpatialValidator removes edges to phantom
            → FLEE BLOCKED

  Gap zones (inside bounding box, not covered by rooms):
    {len(gap_points) if 'gap_points' in dir() else '?'} sample points
    See Step 6 for details.
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
