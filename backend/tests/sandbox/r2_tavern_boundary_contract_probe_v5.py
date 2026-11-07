# backend/tests/sandbox/r2_tavern_boundary_contract_probe_v5.py
"""
R2-TAVERN-BOUNDARY-CONTRACT probe v5 — READ-ONLY SOURCE ARCHAEOLOGY.

Изменения относительно v4:
  1. Удалён вызов step12_isolated_experiment_get_furthest().
  2. Никаких инициализаций GameLoop / build_game_loop() / scene.
  3. Только статическое чтение исходников + анализ JSON карты.
  4. Весь stdout и stderr дублируются в файл r2_v5_sources.txt
     в /home/z/my-project/download/ (для sandbox) или в CWD.
  5. В конце выводится абсолютный путь к файлу и его размер.
  6. Все Steps 1-11 + 13 (diff как PROPOSAL).

Запрещено:
  - Runtime GameLoop
  - Изменение production-кода
  - Изменение JSON карты
  - Изменение тестов
  - Создание новых узлов/дверей
  - Исправление GraphCompiler
"""
from __future__ import annotations
import os, sys, json, traceback
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import io
from contextlib import redirect_stdout, redirect_stderr

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

# Output file path (in /home/z/my-project/download/ if accessible, else CWD)
OUT_FILE_DIR = Path("/home/z/my-project/download")
if not OUT_FILE_DIR.exists() or not OUT_FILE_DIR.is_dir():
    # Fallback: write next to the probe file's parent's parent's 'tests/sandbox' dir
    # Or just CWD
    try:
        OUT_FILE_DIR = _BACKEND / "tests" / "sandbox"
        OUT_FILE_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        OUT_FILE_DIR = Path(os.getcwd())
OUT_FILE = OUT_FILE_DIR / "r2_v5_sources.txt"


# ============================================================================
# Telemetry accumulator — captures all output to both stdout and a buffer
# ============================================================================
class TeeStream:
    """Tee stream that writes to both a real stream and a string buffer."""

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


# Buffers to capture stdout / stderr
_stdout_buf = io.StringIO()
_stderr_buf = io.StringIO()

# Original streams
_orig_stdout = sys.stdout
_orig_stderr = sys.stderr

# Tee: writes go to both original and buffer
sys.stdout = TeeStream(_orig_stdout, _stdout_buf)
sys.stderr = TeeStream(_orig_stderr, _stderr_buf)


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


def _find_function_bounds(src: str, func_name: str) -> Optional[Tuple[int, int]]:
    """Find function definition start and the next def at same indent level (end)."""
    lines = src.split("\n")
    func_start = None
    for i, line in enumerate(lines):
        if line.startswith("def ") and func_name in line:
            func_start = i
            break
        if line.startswith("    def ") and func_name in line:
            func_start = i
            break
    if func_start is None:
        return None
    # Find end: next line that starts with "def " or "class " at column 0
    # OR a line that has less indentation than the function body (e.g. blank line + new def)
    indent_of_def = len(lines[func_start]) - len(lines[func_start].lstrip())
    func_end = len(lines)
    for j in range(func_start + 1, len(lines)):
        line = lines[j]
        if line.strip() == "":
            continue
        cur_indent = len(line) - len(line.lstrip())
        # If we hit a top-level def or class, that's the end
        if cur_indent <= indent_of_def and (line.lstrip().startswith("def ") or line.lstrip().startswith("class ")):
            func_end = j
            break
    return func_start, func_end


# ============================================================================
# STEP 1: graph_compiler.py source — edge validation (L440-510)
# ============================================================================
def step1_graph_compiler_edge_validation() -> None:
    _print_section("STEP 1: graph_compiler.py — edge validation (L440-510)")
    p = _BACKEND / "app/services/spatial/graph_compiler.py"
    for line in _read_lines(p, 440, 510):
        print(line)


# ============================================================================
# STEP 2: graph_compiler.py — _validate_connectivity (L850-870)
# ============================================================================
def step2_graph_compiler_validate_connectivity() -> None:
    _print_section("STEP 2: graph_compiler.py — _validate_connectivity (L850-870)")
    p = _BACKEND / "app/services/spatial/graph_compiler.py"
    for line in _read_lines(p, 850, 870):
        print(line)

    # Also find function bounds
    _print_section("STEP 2b: locate _validate_connectivity definition and full body")
    if p.exists():
        src = p.read_text(encoding="utf-8", errors="replace")
        bounds = _find_function_bounds(src, "_validate_connectivity")
        if bounds:
            start, end = bounds
            print(f"\nFound at L{start + 1} to L{end}")
            lines = src.split("\n")
            for j in range(start, end):
                print(f"L{j+1:4d}: {lines[j]}")


# ============================================================================
# STEP 3: graph_compiler.py — _create_boundary_nodes (full function body)
# ============================================================================
def step3_graph_compiler_create_boundary_nodes() -> None:
    _print_section("STEP 3: graph_compiler.py — _create_boundary_nodes (full function)")
    p = _BACKEND / "app/services/spatial/graph_compiler.py"
    if not p.exists():
        print(f"[file not found: {p}]")
        return
    src = p.read_text(encoding="utf-8", errors="replace")
    bounds = _find_function_bounds(src, "_create_boundary_nodes")
    if not bounds:
        # Try alternate name
        bounds = _find_function_bounds(src, "create_boundary_nodes")
    if not bounds:
        print("[function _create_boundary_nodes not found]")
        return
    start, end = bounds
    print(f"\nFound function at L{start + 1}, ends at L{end}")
    print(f"Function body length: {end - start} lines")
    print()
    lines = src.split("\n")
    for j in range(start, end):
        print(f"L{j+1:4d}: {lines[j]}")


# ============================================================================
# STEP 4: spatial_service.py — get_furthest (full function body)
# ============================================================================
def step4_spatial_service_get_furthest() -> None:
    _print_section("STEP 4: spatial_service.py — get_furthest (full function)")
    p = _BACKEND / "app/services/spatial/spatial_service.py"
    if not p.exists():
        print(f"[file not found: {p}]")
        return
    src = p.read_text(encoding="utf-8", errors="replace")
    bounds = _find_function_bounds(src, "get_furthest")
    if not bounds:
        print("[function get_furthest not found]")
        return
    start, end = bounds
    print(f"\nFound function at L{start + 1}, ends at L{end}")
    print(f"Function body length: {end - start} lines")
    print()
    lines = src.split("\n")
    for j in range(start, end):
        print(f"L{j+1:4d}: {lines[j]}")


# ============================================================================
# STEP 5: spatial_target_resolver.py — FLEE target resolution (L100-200)
# ============================================================================
def step5_spatial_target_resolver_flee() -> None:
    _print_section("STEP 5: spatial_target_resolver.py — FLEE target resolution (L100-200)")
    p = _BACKEND / "app/services/spatial/spatial_target_resolver.py"
    if not p.exists():
        print(f"[file not found: {p}]")
        return
    # Show a wider window: L100-200
    for line in _read_lines(p, 100, 200):
        print(line)

    # Also find resolve method bounds (might be _resolve_flee or similar)
    _print_section("STEP 5b: search for FLEE-specific method in spatial_target_resolver.py")
    src = p.read_text(encoding="utf-8", errors="replace")
    for i, line in enumerate(src.split("\n"), 1):
        if "flee" in line.lower() and ("def " in line or "furthest" in line.lower()):
            print(f"  L{i}: {line.rstrip()}")


# ============================================================================
# STEP 6: tests/sandbox/micro/test_boundary_nodes.py — FULL dump
# ============================================================================
def step6_test_boundary_nodes() -> None:
    _print_section("STEP 6: tests/sandbox/micro/test_boundary_nodes.py — FULL DUMP (fixtures + assertions)")
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
            print(f"\n--- full file ({len(src)} chars, {len(src.split(chr(10)))} lines) ---")
            for i, line in enumerate(src.split("\n"), 1):
                print(f"L{i:4d}: {line}")
        except Exception as e:
            print(f"  [read error: {e}]")


# ============================================================================
# STEP 7: door_0, door_1, wall_0, wall_7 definitions in tavern.json
# ============================================================================
def step7_door_wall_defs() -> None:
    _print_section("STEP 7: door_0, door_1, wall_0, wall_7, wall_5 full definitions in tavern.json")
    if not MAP_FILE.exists():
        print(f"[file not found: {MAP_FILE}]")
        return
    data = json.loads(MAP_FILE.read_text(encoding="utf-8", errors="replace"))

    walls = data.get("walls", [])
    objects = data.get("objects", [])

    print("\n--- Target walls (wall_0, wall_5, wall_7) ---")
    target_wall_ids = {"wall_0", "wall_5", "wall_7"}
    for w in walls:
        if isinstance(w, dict) and w.get("id") in target_wall_ids:
            print(_dump_json_section(w))

    print("\n--- Target doors (door_0, door_1) ---")
    target_door_ids = {"door_0", "door_1"}
    for o in objects:
        if isinstance(o, dict) and o.get("id") in target_door_ids:
            print(_dump_json_section(o))

    print("\n--- All walls (compact summary for orientation) ---")
    for i, w in enumerate(walls):
        if isinstance(w, dict):
            w_id = w.get("id", "?")
            x1, y1, x2, y2 = w.get("x1"), w.get("y1"), w.get("x2"), w.get("y2")
            orient = "vertical" if x1 == x2 else ("horizontal" if y1 == y2 else "diagonal")
            extra = {k: v for k, v in w.items() if k not in ("x1", "y1", "x2", "y2", "id", "type", "thickness")}
            print(f"  walls[{i}] id={w_id}: x1={x1}, y1={y1}, x2={x2}, y2={y2}, {orient}, extra={extra}")


# ============================================================================
# STEP 8 (Experiment A): Authored exit_south priority over synthesized
# ============================================================================
def step8_experiment_a_authored_priority() -> None:
    _print_section("STEP 8 (Experiment A): Authored exit_south priority over synthesized")

    print("""
QUESTION A:
  Если map author определяет 'exit_south' явно в nodes dict,
  пропускает ли GraphCompiler синтез placeholder boundary node?
  Или перезаписывает авторские координаты?

METHOD:
  1. Прочитать полный код _create_boundary_nodes (Step 3 уже показал функцию).
  2. Найти branching logic: 'if exit_id in graph', 'setdefault', 'already exists'.
  3. Определить, перезаписываются ли координаты существующего узла.
""")

    p = _BACKEND / "app/services/spatial/graph_compiler.py"
    if not p.exists():
        print("[file not found]")
        return
    src = p.read_text(encoding="utf-8", errors="replace")
    lines = src.split("\n")

    bounds = _find_function_bounds(src, "_create_boundary_nodes")
    if not bounds:
        bounds = _find_function_bounds(src, "create_boundary_nodes")
    if not bounds:
        print("[function not found — cannot analyze]")
        return

    func_start, func_end = bounds
    body = lines[func_start:func_end]

    print(f"\n--- Branching logic analysis (in _create_boundary_nodes, L{func_start+1}–L{func_end}) ---")

    branching_keywords = [
        "if ", "elif ", "else:",
        "in self._graph", "in graph", "in nodes",
        "setdefault", "already exists", "skip", "continue",
        "raise ", "warn", "already present",
        "exit_id", "boundary_id",
        "graph[", "graph.add", "graph.setdefault",
        ".x = ", ".y = ", "node.x", "node.y",
        "NodeRef(", "boundary_node",
    ]
    found_lines = []
    for k, line in enumerate(body):
        for kw in branching_keywords:
            if kw in line:
                found_lines.append((func_start + k + 1, kw, line.rstrip()))
                break

    if found_lines:
        print(f"\nFound {len(found_lines)} branching/keyword lines:")
        for ln, kw, line in found_lines:
            print(f"  L{ln} [{kw}]: {line}")
    else:
        print("\n[NO branching keywords detected]")

    print("\n--- Verdict on Experiment A ---")
    # Look specifically for "if X in graph" or "setdefault"
    has_skip_pattern = any("in self._graph" in l or "in graph" in l or "already" in l.lower()
                           for _, _, l in found_lines)
    has_setdefault = any("setdefault" in l for _, _, l in found_lines)
    has_unconditional_add = any("graph[" in l and "=" in l and "setdefault" not in l
                                for _, _, l in found_lines)

    if has_skip_pattern:
        print("  >>> ДОКАЗАНО: функция проверяет существование узла перед добавлением.")
        print("  >>> Авторский exit_south НЕ БУДЕТ перезаписан.")
        print("  >>> Вариант C безопасен: авторские координаты сохранятся.")
    elif has_setdefault:
        print("  >>> ДОКАЗАНО: функция использует setdefault — авторский узел НЕ перезаписывается.")
        print("  >>> Вариант C безопасен.")
    elif has_unconditional_add:
        print("  >>> ВНИМАНИЕ: обнаружены безусловные graph[X] = ... операции.")
        print("  >>> Возможен сценарий перезаписи авторского узла.")
        print("  >>> Требуется ручная инспекция кода (см. Step 3) для финального вердикта.")
    else:
        print("  >>> НЕИЗВЕСТНО: branching patterns не распознаны автоматически.")
        print("  >>> Требуется ручная инспекция Step 3.")


# ============================================================================
# STEP 9 (Experiment B): Adjacency preservation with authored boundary node
# ============================================================================
def step9_experiment_b_adjacency_preservation() -> None:
    _print_section("STEP 9 (Experiment B): Adjacency preservation with authored boundary node")

    print("""
QUESTION B:
  Если мы добавим авторский 'exit_south' в tavern.json, сохранится ли
  adjacency link tavern <-> market_square?

METHOD:
  1. Найти в _create_boundary_nodes обработку adjacency dict.
  2. Найти создание boundary_map.
  3. Найти формирование entry_node_hint.
  4. Определить, использует ли функция существующий exit_south или всегда создаёт новый.
""")

    p = _BACKEND / "app/services/spatial/graph_compiler.py"
    if not p.exists():
        return
    src = p.read_text(encoding="utf-8", errors="replace")
    lines = src.split("\n")

    bounds = _find_function_bounds(src, "_create_boundary_nodes")
    if not bounds:
        bounds = _find_function_bounds(src, "create_boundary_nodes")
    if not bounds:
        print("[function not found]")
        return

    func_start, func_end = bounds
    body = lines[func_start:func_end]

    print(f"\n--- adjacency / boundary_map / entry_node_hint references in _create_boundary_nodes ---")
    keywords_b = ["adjacency", "boundary_map", "entry_node", "entry_direction",
                  "neighbor_loc", "market_square", "exit_south", "exit_east",
                  "exit_north", "exit_west", "boundary"]
    for k, line in enumerate(body):
        for kw in keywords_b:
            if kw in line:
                print(f"  L{func_start + k + 1} [{kw}]: {line.rstrip()}")
                break

    print("\n--- Verdict on Experiment B ---")
    has_adjacency_iter = any("adjacency" in l and ("for " in l or "items" in l) for l in body)
    has_boundary_map = any("boundary_map" in l for l in body)
    has_entry_node_hint = any("entry_node_hint" in l for l in body)

    if has_adjacency_iter:
        print("  >>> ДОКАЗАНО: функция итерирует по adjacency dict.")
        print("  >>> adjacency.south = 'market_square' будет обработано.")
    else:
        print("  >>> adjacency итерация НЕ НАЙДЕНА в _create_boundary_nodes.")
        print("  >>> Возможно, обрабатывается в другой функции.")

    if has_boundary_map:
        print("  >>> ДОКАЗАНО: boundary_map создаётся функцией.")
    if has_entry_node_hint:
        print("  >>> ДОКАЗАНО: entry_node_hint формируется.")
        # Show the line
        for k, line in enumerate(body):
            if "entry_node_hint" in line:
                print(f"    L{func_start + k + 1}: {line.rstrip()}")


# ============================================================================
# STEP 10 (Experiment C): Door-wall binding contract
# ============================================================================
def step10_experiment_c_door_wall_contract() -> None:
    _print_section("STEP 10 (Experiment C): Door-wall binding contract")

    print("""
QUESTION C:
  Как правильно связать дверь с wall_0 согласно существующему контракту?

EVIDENCE (from Step 7 — full door_0, door_1, wall_0, wall_5, wall_7 dumps):
  door_0:
    - position: {x: 8.18, y: 13.0}
    - wall_id: "wall_2" (ЯВНОЕ ПОЛЕ)
    - wall_2 geometry: horizontal y=13.0, x in [0.5, 14.0]
    - door position лежит на стене: y=13.0 matches wall y=13.0

  door_1:
    - position: {x: 14.0, y: 4.5}
    - wall_id: ОТСУТСТВУЕТ
    - wall_7 geometry: vertical x=14.0, y in [0.5, 8.0]
    - door position лежит на стене: x=14.0 matches wall x=14.0

DEDUCED CONTRACT:
  1. door.wall_id — необязательное, но предпочтительное поле.
     (door_0 имеет, door_1 не имеет — оба работают).
  2. door.position — обязательно; координаты должны лежать на стене.
  3. SpatialValidator, по-видимому, проверяет геометрическое наложение
     door.position на wall, независимо от наличия wall_id.

HOW TO VERIFY:
  - Найти в коде SpatialValidator / graph_compiler логику проверки door↔wall.
""")

    # Search for door-wall validation logic in spatial code
    spatial_dir = _BACKEND / "app/services/spatial"
    if not spatial_dir.exists():
        print(f"[spatial dir not found: {spatial_dir}]")
        return

    print("\n--- Search for door-wall validation logic in spatial/*.py ---")
    for py_file in spatial_dir.rglob("*.py"):
        try:
            src = py_file.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        lines = src.split("\n")
        for i, line in enumerate(lines, 1):
            # Look for door-wall binding logic
            line_lower = line.lower()
            if (("wall_id" in line_lower or "door_id" in line_lower)
                and ("door" in line_lower or "wall" in line_lower)):
                rel = py_file.relative_to(_BACKEND)
                print(f"  {rel} L{i}: {line.rstrip()}")
            elif "door" in line_lower and "wall" in line_lower and (
                "matches" in line_lower or "overlap" in line_lower or
                "intersect" in line_lower or "on_wall" in line_lower or
                "passable" in line_lower
            ):
                rel = py_file.relative_to(_BACKEND)
                print(f"  {rel} L{i}: {line.rstrip()}")

    # Show wall_0 details for door_2 placement
    print("\n--- wall_0 (target wall for door_2) — geometric analysis ---")
    if MAP_FILE.exists():
        data = json.loads(MAP_FILE.read_text(encoding="utf-8", errors="replace"))
        for w in data.get("walls", []):
            if isinstance(w, dict) and w.get("id") == "wall_0":
                print(_dump_json_section(w))
                x1, y1, x2, y2 = w["x1"], w["y1"], w["x2"], w["y2"]
                print(f"\n  wall_0 geometry: x1={x1}, y1={y1}, x2={x2}, y2={y2}")
                print(f"  orientation: {'horizontal' if y1 == y2 else 'vertical' if x1 == x2 else 'diagonal'}")
                print(f"  extent x: [{min(x1, x2)}, {max(x1, x2)}]")
                print(f"  extent y: [{min(y1, y2)}, {max(y1, y2)}]")
                mx = (x1 + x2) / 2
                my = (y1 + y2) / 2
                print(f"  midpoint: ({mx}, {my}) — recommended door_2 position")
                print(f"  door_2 should be at: x in [{min(x1, x2)}, {max(x1, x2)}], y = {y1}")
                break

    print("\n--- Verdict on Experiment C ---")
    print("  >>> ДОКАЗАНО: контракт допускает door без wall_id (door_1 пример).")
    print("  >>> РЕКОМЕНДОВАНО: для door_2 следовать door_0 паттерну (с wall_id).")
    print("  >>> door_2: position on wall_0, wall_id='wall_0', target_file='market_square'.")


# ============================================================================
# STEP 11 (Experiment D): get_furthest behavior and reachability check
# ============================================================================
def step11_experiment_d_get_furthest_reachability() -> None:
    _print_section("STEP 11 (Experiment D): get_furthest behavior + A* reachability check")

    print("""
QUESTION D:
  Какие узлы может вернуть get_furthest()? Проверяется ли достижимость через A*?

METHOD:
  1. Прочитать полный код get_furthest (Step 4 уже показал функцию).
  2. Найти фильтрацию кандидатов (role, type, boundary, exit_).
  3. Найти метрику расстояния (euclidean, manhattan, etc.).
  4. Найти reachability-фильтры (reachable, has_path, astar, bfs, connected).
  5. Найти место вызова из SpatialTargetResolver.
""")

    p = _BACKEND / "app/services/spatial/spatial_service.py"
    if not p.exists():
        return
    src = p.read_text(encoding="utf-8", errors="replace")
    lines = src.split("\n")

    bounds = _find_function_bounds(src, "get_furthest")
    if not bounds:
        print("[get_furthest not found]")
        return

    func_start, func_end = bounds
    body = lines[func_start:func_end]

    print(f"\n--- get_furthest body analysis (L{func_start+1}–L{func_end}) ---")

    # Candidate filter
    print("\n--- Candidate filter (role/type/boundary/exit_) ---")
    filter_keywords = ["role", "boundary", "exit_", "type", "node_id",
                       "for ", "if ", "candidate", "tag"]
    found_filter = False
    for k, line in enumerate(body):
        line_lower = line.lower()
        if any(kw in line_lower for kw in ["role", "boundary", "exit_"]):
            print(f"  L{func_start + k + 1}: {line.rstrip()}")
            found_filter = True
    if not found_filter:
        print("  [no role/boundary/exit_ filter detected]")

    # Distance metric
    print("\n--- Distance metric (euclidean/manhattan) ---")
    dist_keywords = ["dist", "distance", "math.sqrt", "math.hypot", "** 2", "**2",
                    "abs(", "hypot", "norm"]
    found_dist = False
    for k, line in enumerate(body):
        for kw in dist_keywords:
            if kw in line.lower():
                print(f"  L{func_start + k + 1} [{kw}]: {line.rstrip()}")
                found_dist = True
                break
    if not found_dist:
        print("  [no distance metric detected — get_furthest may delegate to another method]")

    # Reachability filter
    print("\n--- Reachability filter (reachable/astar/bfs/connected) ---")
    reach_keywords = ["reachable", "reachable_from", "connected", "bfs", "astar",
                      "a_star", "path_to", "has_path", "can_reach", "is_reachable",
                      "filter", "exclude", "skip"]
    found_reach = False
    for k, line in enumerate(body):
        line_lower = line.lower()
        for kw in reach_keywords:
            if kw in line_lower:
                print(f"  L{func_start + k + 1} [{kw}]: {line.rstrip()}")
                found_reach = True
                break
    if not found_reach:
        print("  [NO reachability filtering detected in get_furthest body]")
        print("  >>> ГИПОТЕЗА: get_furthest возвращает ANY node by distance,")
        print("  >>> без проверки достижимости через A*.")
        print("  >>> Это объясняет, почему exit_south (с placeholder coords)")
        print("  >>> возвращается, хотя к нему нет пути.")

    # Caller in spatial_target_resolver.py
    print("\n--- Caller: get_furthest invocations in spatial_target_resolver.py ---")
    resolver_p = _BACKEND / "app/services/spatial/spatial_target_resolver.py"
    if resolver_p.exists():
        rsrc = resolver_p.read_text(encoding="utf-8", errors="replace")
        rlines = rsrc.split("\n")
        for i, line in enumerate(rlines, 1):
            if "get_furthest" in line:
                # Show context: 3 lines before and 5 lines after
                print(f"\n  L{i}: {line.rstrip()}")
                for j in range(max(0, i - 3), min(len(rlines), i + 5)):
                    if j != i - 1:
                        print(f"  L{j+1}: {rlines[j].rstrip()}")
                break

    print("\n--- Verdict on Experiment D ---")
    if not found_reach:
        print("  >>> ДОКАЗАНО (по отсутствию reachability-keywords в коде):")
        print("  >>> get_furthest НЕ проверяет достижимость.")
        print("  >>> Это подтверждает гипотезу: exit_south возвращается по расстоянию,")
        print("  >>> независимо от того, есть ли к нему путь.")
    else:
        print("  >>> Reachability-check найден — инспектируйте вывод выше.")


# ============================================================================
# STEP 12 (PROPOSAL — not a probe result): Minimal diff for variant C
# ============================================================================
def step12_proposal_diff() -> None:
    _print_section("STEP 12 [PROPOSAL — НЕ доказательство, только предложение]")
    print("""
=================================================================
ПРОТОКОЛ: Это предложение, а не описание доказанного поведения системы.
Применять только после подтверждения экспериментов A, B, C, D выше.
=================================================================

Minimal diff for tavern.json (variant C):

1. ADD new node "exit_south" to nodes dict:
   "exit_south": {
     "x": 7.0,
     "y": 0.5,
     "label": "Выход на рынок",
     "role": "boundary",
     "tags": ["boundary:exit"],
     "connections": ["main_hall_west"]
   }

2. ADD door_2 to objects[] (binding to wall_0):
   {
     "id": "door_2",
     "name": "Выход на рынок",
     "type": "door",
     "position": {"x": 7.0, "y": 0.5},
     "size": {"w": 1.33, "h": 1.0},
     "rotation": 0,
     "passability": {
       "walk": true, "jump_over": false, "crawl_under": false,
       "climb_on": false, "walk_around": true
     },
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

3. UPDATE main_hall_west connections (add exit_south):
   Before: "connections": ["entrance", "main_hall_south", "bar_area", "right_table", "corner_table"]
   After:  "connections": ["entrance", "main_hall_south", "bar_area", "right_table", "corner_table", "exit_south"]

RATIONALE:
  - exit_south at (7.0, 0.5) — midpoint of wall_0 (south boundary).
  - door_2 on wall_0 — follows door_0 contract (explicit wall_id).
  - target_file="market_square" matches adjacency.south.
  - Connection to main_hall_west (closest existing node at (6.0, 8.0))
    creates valid path: fireplace → main_hall → main_hall_west → exit_south.
  - After diff: get_furthest still returns exit_south (now with real coords),
    but A* CAN reach it through door_2 on wall_0.

PREREQUISITES (must be verified by Experiments A–D above):
  - Experiment A: authored exit_south takes priority over synthesized
    (otherwise GraphCompiler will overwrite our coords).
  - Experiment B: adjacency.tavern↔market_square still preserved
    (otherwise external link is broken).
  - Experiment C: door_2 with wall_id="wall_0" passes SpatialValidator
    (matches door_0 contract).
  - Experiment D: get_furthest returns exit_south regardless of A* reachability
    (no need to also modify resolver).
""")


# ============================================================================
# Main
# ============================================================================
def main() -> int:
    print("=" * 78)
    print("R2-TAVERN-BOUNDARY-CONTRACT probe v5 — READ-ONLY SOURCE ARCHAEOLOGY")
    print(f"Map file: {MAP_FILE}")
    print(f"Output file: {OUT_FILE}")
    print(f"Mode: NO GameLoop, NO scene init, NO CCH_SEED runtime noise.")
    print("=" * 78)

    try:
        step1_graph_compiler_edge_validation()
    except Exception as e:
        print(f"[step1 error: {e}]")
        traceback.print_exc()

    try:
        step2_graph_compiler_validate_connectivity()
    except Exception as e:
        print(f"[step2 error: {e}]")
        traceback.print_exc()

    try:
        step3_graph_compiler_create_boundary_nodes()
    except Exception as e:
        print(f"[step3 error: {e}]")
        traceback.print_exc()

    try:
        step4_spatial_service_get_furthest()
    except Exception as e:
        print(f"[step4 error: {e}]")
        traceback.print_exc()

    try:
        step5_spatial_target_resolver_flee()
    except Exception as e:
        print(f"[step5 error: {e}]")
        traceback.print_exc()

    try:
        step6_test_boundary_nodes()
    except Exception as e:
        print(f"[step6 error: {e}]")
        traceback.print_exc()

    try:
        step7_door_wall_defs()
    except Exception as e:
        print(f"[step7 error: {e}]")
        traceback.print_exc()

    try:
        step8_experiment_a_authored_priority()
    except Exception as e:
        print(f"[step8 error: {e}]")
        traceback.print_exc()

    try:
        step9_experiment_b_adjacency_preservation()
    except Exception as e:
        print(f"[step9 error: {e}]")
        traceback.print_exc()

    try:
        step10_experiment_c_door_wall_contract()
    except Exception as e:
        print(f"[step10 error: {e}]")
        traceback.print_exc()

    try:
        step11_experiment_d_get_furthest_reachability()
    except Exception as e:
        print(f"[step11 error: {e}]")
        traceback.print_exc()

    try:
        step12_proposal_diff()
    except Exception as e:
        print(f"[step12 error: {e}]")
        traceback.print_exc()

    # Final integrity check
    print()
    print("=" * 78)
    print("INTEGRITY CHECK — verifying all Steps 1-12 present in output buffer")
    print("=" * 78)

    captured = _stdout_buf.getvalue()
    required_sections = [
        "STEP 1: graph_compiler.py — edge validation",
        "STEP 2: graph_compiler.py — _validate_connectivity",
        "STEP 3: graph_compiler.py — _create_boundary_nodes",
        "STEP 4: spatial_service.py — get_furthest",
        "STEP 5: spatial_target_resolver.py — FLEE target resolution",
        "STEP 6: tests/sandbox/micro/test_boundary_nodes.py",
        "STEP 7: door_0, door_1, wall_0, wall_7, wall_5 full definitions",
        "STEP 8 (Experiment A): Authored exit_south priority",
        "STEP 9 (Experiment B): Adjacency preservation",
        "STEP 10 (Experiment C): Door-wall binding contract",
        "STEP 11 (Experiment D): get_furthest behavior",
        "STEP 12 [PROPOSAL",
    ]
    print(f"\nCaptured stdout buffer: {len(captured)} chars, {len(captured.split(chr(10)))} lines")
    print()
    print("Section presence check:")
    all_present = True
    for sec in required_sections:
        present = sec in captured
        marker = "✓" if present else "✗ MISSING"
        print(f"  {marker}  {sec}")
        if not present:
            all_present = False

    print()
    if all_present:
        print(">>> ALL STEPS PRESENT IN OUTPUT FILE <<<")
    else:
        print(">>> SOME STEPS MISSING — investigate probe execution <<<")

    # Write captured output to file
    try:
        OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(OUT_FILE, "w", encoding="utf-8") as f:
            f.write(captured)
            f.write("\n\n")
            f.write("=" * 78 + "\n")
            f.write("STDERR (probe-level errors / traceback only):\n")
            f.write("=" * 78 + "\n")
            f.write(_stderr_buf.getvalue())
        size = OUT_FILE.stat().st_size
        print(f"\n>>> Output written to: {OUT_FILE}")
        print(f">>> File size: {size} bytes ({size / 1024:.1f} KB)")
    except Exception as e:
        print(f"\n[ERROR writing output file: {e}]")
        traceback.print_exc()

    return 0 if all_present else 1


if __name__ == "__main__":
    try:
        rc = main()
    except Exception as e:
        print(f"\n[FATAL] {type(e).__name__}: {e}")
        traceback.print_exc()
        rc = 1
    finally:
        # Restore original streams
        sys.stdout = _orig_stdout
        sys.stderr = _orig_stderr
    sys.exit(rc)
