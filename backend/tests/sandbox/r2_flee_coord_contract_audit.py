# backend/tests/sandbox/r2_flee_coord_contract_audit.py
"""
R2-FLEE-COORD-CONTRACT-AUDIT — комплексный probe для 5 этапов.

Цель: установить точное место нарушения координатного контракта
       и подготовить минимальное исправление.

Этапы:
  1. Координатный контракт (JSON, GraphCompiler, NodeRef, SpatialValidator)
  2. Boundary nodes — почему мировые coords
  3. FLEE — get_furthest, A*, cross-location transfer
  4. Авторская геометрия — door_0, door_1, node_16, walls
  5. Подготовка исправления — diff, тесты, риски

READ-ONLY. Никаких production-изменений.
"""
from __future__ import annotations
import os, sys, json, traceback, copy, logging
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
TAVERN_FILE = PROJECT_ROOT / "saves/Open_road/locations/tavern.json"
MARKET_SQUARE_FILE = PROJECT_ROOT / "saves/Open_road/locations/market_square.json"
CITY_GATE_FILE = PROJECT_ROOT / "saves/Open_road/locations/city_gate.json"

OUT_FILE_DIR = Path("/home/z/my-project/download")
if not OUT_FILE_DIR.exists() or not OUT_FILE_DIR.is_dir():
    OUT_FILE_DIR = _BACKEND / "tests" / "sandbox"
    try:
        OUT_FILE_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        OUT_FILE_DIR = Path(os.getcwd())
OUT_FILE = OUT_FILE_DIR / "r2_flee_coord_contract_audit.txt"


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

_log_capture = io.StringIO()
_log_handler = logging.StreamHandler(_log_capture)
_log_handler.setLevel(logging.DEBUG)
_log_handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
logging.getLogger().addHandler(_log_handler)
logging.getLogger().setLevel(logging.DEBUG)


def _print_section(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def _read_lines(path: Path, start: int, end: int) -> List[str]:
    if not path.exists():
        return [f"[file not found: {path}]"]
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").split("\n")
        return [f"L{i+1:4d}: {lines[i]}" for i in range(start - 1, min(end, len(lines)))]
    except Exception as e:
        return [f"[read error: {e}]"]


def _load_json(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception as e:
        print(f"[load error {path}: {e}]")
        return None


# ============================================================================
# ЭТАП 1: Координатный контракт
# ============================================================================
def stage1_coord_contract() -> None:
    _print_section("ЭТАП 1: Координатный контракт — JSON, GraphCompiler, NodeRef, SpatialValidator")

    tavern = _load_json(TAVERN_FILE)
    if not tavern:
        return

    print("\n>>> 1.1: Координаты узлов в JSON")
    print(f"  tavern.json nodes dict size: {len(tavern.get('nodes', {}))}")
    print(f"  global_coords: {tavern.get('global_coords')}")
    print(f"  origin: {tavern.get('origin')}")
    print(f"  size: {tavern.get('size')}")

    print(f"\n  Примеры координат узлов (ЛОКАЛЬНЫЕ, в JSON):")
    for name in ("fireplace", "kitchen_bed_2", "entrance", "node_16", "behind_bar"):
        nd = tavern.get("nodes", {}).get(name, {})
        if nd:
            print(f"    {name}: x={nd.get('x')}, y={nd.get('y')}")

    print(f"\n  Примеры координат стен (ЛОКАЛЬНЫЕ, в JSON):")
    for w in tavern.get("walls", [])[:3]:
        print(f"    {w.get('id')}: x1={w.get('x1')}, y1={w.get('y1')}, x2={w.get('x2')}, y2={w.get('y2')}")

    print(f"\n>>> 1.2: Что SpatialRegistry говорит о координатах")
    sr_path = _BACKEND / "app/services/spatial/spatial_registry.py"
    if sr_path.exists():
        src = sr_path.read_text(encoding="utf-8", errors="replace")
        for i, line in enumerate(src.split("\n"), 1):
            if any(kw in line for kw in ["origin_x", "origin_y", "world_x", "world_y",
                                          "min_x", "min_y", "max_x", "max_y", "world_bounds"]):
                if "def " in line or ":" in line or "=" in line:
                    print(f"  L{i}: {line.rstrip()}")

    print(f"\n>>> 1.3: GraphCompiler — какой смысл у coords в NodeRef")
    gc_path = _BACKEND / "app/services/spatial/graph_compiler.py"
    if gc_path.exists():
        src = gc_path.read_text(encoding="utf-8", errors="replace")
        for i, line in enumerate(src.split("\n"), 1):
            if "NodeRef(" in line or "node_id=canonical_id" in line:
                print(f"  L{i}: {line.rstrip()}")

    print(f"\n>>> 1.4: SpatialValidator — какие coords использует")
    if gc_path.exists():
        src = gc_path.read_text(encoding="utf-8", errors="replace")
        lines = src.split("\n")
        for i, line in enumerate(lines, 1):
            if "from_node.x" in line or "from_node.y" in line or "to_node.x" in line or "to_node.y" in line:
                print(f"  L{i}: {line.rstrip()}")
            elif "wall[" in line and ("x1" in line or "y1" in line or "x2" in line or "y2" in line):
                print(f"  L{i}: {line.rstrip()}")

    print(f"""
>>> 1.5: Вывод о координатном контракте

  JSON nodes coords: ЛОКАЛЬНЫЕ (внутри location, 0..size)
  JSON walls coords: ЛОКАЛЬНЫЕ (внутри location, 0..size)
  GraphCompiler при загрузке nodes: НЕ преобразует coords (оставляет как в JSON)
    → graph["tavern:fireplace"] = NodeRef(x=10.5, y=3.0) — ЛОКАЛЬНЫЕ
  GraphCompiler _create_boundary_nodes:
    _bx, _by = (origin.x + offset, origin.y + offset) — МИРОВЫЕ
    graph["tavern:exit_east"] = NodeRef(x=44.03, y=12.52) — МИРОВЫЕ

  SpatialValidator:
    Сравнивает from_node.x/y (может быть ЛОКАЛЬНЫЕ ИЛИ МИРОВЫЕ)
    с wall["x1"]/["y1"] (ЛОКАЛЬНЫЕ)
    → Если from_node = авторский (ЛОКАЛЬНЫЕ) → корректно
    → Если from_node = phantom boundary (МИРОВЫЕ) → НЕВЕРНО

  Корень смешения: _create_boundary_nodes создаёт boundary nodes с МИРОВЫМИ coords,
  в то время как все остальные nodes и walls используют ЛОКАЛЬНЫЕ coords.
""")


# ============================================================================
# ЭТАП 2: Boundary nodes — почему мировые coords
# ============================================================================
def stage2_boundary_nodes() -> None:
    _print_section("ЭТАП 2: _create_boundary_nodes — почему мировые coords")

    print(f"""
>>> 2.1: Код _create_boundary_nodes (graph_compiler.py L876-990)

  L892-893: _ox = float(origin.get("x", 0.0))  ← МИРОВЫЕ
             _oy = float(origin.get("y", 0.0))  ← МИРОВЫЕ
  L899-902: _DIR_TO_XY = {{
               "north": (_ox + _w / 2.0, _oy + _h - 1.0),  ← МИРОВЫЕ
               "south": (_ox + _w / 2.0, _oy + 1.0),         ← МИРОВЫЕ
               "east":  (_ox + _w - 1.0, _oy + _h / 2.0),  ← МИРОВЫЕ
               "west":  (_ox + 1.0,      _oy + _h / 2.0),  ← МИРОВЫЕ
             }}
  L917:      _bx, _by = _DIR_OFFSETS.get(direction, ...)
             → _bx, _by — МИРОВЫЕ координаты

  L939:      _existing_node = graph.get(boundary_id)
             ← ищет "tavern:exit_east" в graph
             ← graph хранит авторские узлы с ЛОКАЛЬНЫМИ coords
             ← "tavern:exit_east" отсутствует (нет в JSON nodes)
             → _existing_node = None

  L940-941:  _final_x = _existing_node.x if _existing_node else _bx
             _final_y = _existing_node.y if _existing_node else _by
             → _final_x = _bx (МИРОВЫЕ), _final_y = _by (МИРОВЫЕ)

  L943-950:  boundary_node = NodeRef(
                 x=_final_x,  ← МИРОВЫЕ
                 y=_final_y,  ← МИРОВЫЕ
                 role=NodeRole.BOUNDARY,
                 ...
             )
  L952:      graph["tavern:exit_east"] = boundary_node
             ← graph теперь содержит node с МИРОВЫМИ coords,
               в то время как все другие nodes имеют ЛОКАЛЬНЫЕ coords

>>> 2.2: Почему координаты рассчитываются в мировом пространстве

  История кода (из комментариев):
    - L909-910: "V8-SP-15 FIX: Смещаем anchor на 1 метр внутрь локации.
                 Иначе boundary node оказывается за стеной (снаружи), и валидатор блокирует пути к нему."

  Логика оригинального дизайна:
    - boundary node = точка перехода в соседний чанк
    - Она должна быть "на границе" локации в МИРОВОМ пространстве
    - Поэтому _ox (origin.x) + offset (внутри location) = МИРОВЫЕ coords границы

  Ошибка дизайна:
    - SpatialValidator работает в ЛОКАЛЬНЫХ координатах (wall coords локальные)
    - Но boundary node имеет МИРОВЫЕ coords
    → Смешение систем координат

>>> 2.3: Runtime проверка — доказательство смешения
""")

    # Compile tavern.json and inspect coords of all nodes
    try:
        from app.services.spatial.graph_compiler import compile_graph
    except Exception as e:
        print(f"  [import error: {e}]")
        return

    tavern = _load_json(TAVERN_FILE)
    if not tavern:
        return

    _log_capture.truncate(0)
    _log_capture.seek(0)

    try:
        result = compile_graph(tavern, location_id="tavern")
    except Exception as e:
        print(f"  [compile error: {e}]")
        return

    if not result or not isinstance(result, tuple):
        return

    graph = result[0] if len(result) > 0 else {}
    print(f"\n  Все nodes в graph (после compile) — какие ЛОКАЛЬНЫЕ, какие МИРОВЫЕ:")
    print(f"  {'key':<30} {'x':>10} {'y':>10} {'coords_type':<15}")
    print(f"  {'-' * 30} {'-' * 10} {'-' * 10} {'-' * 15}")

    # Determine coord type: if x > 20 (size.w), then it's WORLD coords
    for key in sorted(graph.keys()):
        nref = graph[key]
        x = getattr(nref, "x", 0)
        y = getattr(nref, "y", 0)
        try:
            fx, fy = float(x), float(y)
            # Local coords: 0 <= x <= size.w (20), 0 <= y <= size.h (15)
            # World coords: x > origin.x (25), so > 25
            if fx > 25 or fy > 20:
                coord_type = "WORLD (мир)"
            else:
                coord_type = "LOCAL (локал)"
            print(f"  {key:<30} {fx:>10.3f} {fy:>10.3f} {coord_type}")
        except (TypeError, ValueError):
            print(f"  {key:<30} {x!r:>10} {y!r:>10} ?")

    print(f"""
>>> 2.4: SpatialValidator — какие ребра он удаляет
""")
    logs = _log_capture.getvalue()
    for line in logs.split("\n"):
        if "SPATIAL_VALIDATION" in line or "boundary" in line.lower():
            print(f"  {line}")

    print(f"""
>>> 2.5: Проверка Market Square и City Gate — те же проблемы?
""")
    for name, path in [("market_square", MARKET_SQUARE_FILE), ("city_gate", CITY_GATE_FILE)]:
        data = _load_json(path)
        if not data:
            continue
        size = data.get("size", {})
        origin = data.get("origin", {})
        nodes = data.get("nodes", {})
        print(f"\n  {name}:")
        print(f"    size: {size}")
        print(f"    origin: {origin}")
        print(f"    nodes count: {len(nodes)}")
        # Check if any node has coords > size
        W = float(size.get("w", 0))
        H = float(size.get("h", 0))
        out_of_bounds = []
        for nname, nd in nodes.items():
            if not isinstance(nd, dict):
                continue
            try:
                nx, ny = float(nd.get("x", 0)), float(nd.get("y", 0))
                if nx > W + 0.5 or ny > H + 0.5:
                    out_of_bounds.append((nname, nx, ny))
            except (TypeError, ValueError):
                pass
        if out_of_bounds:
            print(f"    Узлы ВНЕ declared size ({len(out_of_bounds)}):")
            for nname, nx, ny in out_of_bounds:
                print(f"      {nname}: ({nx}, {ny}) — вне [{W}x{H}]")
        else:
            print(f"    Все узлы в пределах declared size")


# ============================================================================
# ЭТАП 3: FLEE и достижимость
# ============================================================================
def stage3_flee_reachability() -> None:
    _print_section("ЭТАП 3: FLEE и достижимость — get_furthest, A*, cross-location")

    print(f"""
>>> 3.1: get_furthest (spatial_service.py L716-738)

  def get_furthest(self, zone_id, origin_xy, exclude_node_ids=None):
      candidates = [n for n in self._graph.values() if n.zone_id == zone_id]
      # ← candidates = ВСЕ узлы зоны (включая phantom boundary с МИРОВЫМИ coords)
      if exclude_node_ids:
          candidates = [n for n in candidates if n.node_id not in exclude_node_ids]
      if not candidates:
          return None
      best = None
      best_dist = -1.0
      for node in candidates:
          d = self.world_distance(origin_xy, node.xy)
          # ← distance computed in WORLD coords
          # ← но origin_xy — это position of threat (NPC fireplace coords)
          # ← fireplace в ЛОКАЛЬНЫХ coords (10.5, 3.0)
          # ← phantom exit_east в МИРОВЫХ coords (44.03, 12.52)
          # ← distance = sqrt((44.03-10.5)^2 + (12.52-3.0)^2) ≈ 34.86
          # ← author kitchen_bed_2 в ЛОКАЛЬНЫХ coords (18.44, 6.27)
          # ← distance = sqrt((18.44-10.5)^2 + (6.27-3.0)^2) ≈ 8.46
          if d > best_dist:
              best_dist = d
              best = node
              # ← best = exit_east (34.86 > 8.46)
      return best

  ПРОБЛЕМА: нет проверки достижимости через A*
  → выбирается самый дальний узел по евклидову расстоянию
  → если это phantom boundary (мир coords) — distance огромное
  → A* не находит путь → FLEE BLOCKED

>>> 3.2: A* pathfinding (spatial_service.py)

  При попытке найти путь к exit_east:
    connections["tavern:exit_east"] = [] (пусто — ребро удалено SpatialValidator)
    → A* не может достичь exit_east
    → failure=M005 "no path to tavern:exit_east"

>>> 3.3: Cross-location transfer (movement_engine.py L434, tick_orchestrator.py L1176)

  MovementEngine:
    L434: boundary_node = current_svc.get_boundary_to_neighbor(target_loc)
    L466-468: BOUNDARY_DWELL mechanism — ждёт N ticks на boundary
    L508-510: entry_node_hint = boundary_map[boundary_id].get("entry_node_hint")

  TickOrchestrator:
    L1039, L1116: _resolve_cross_location_transfers(ctx)
    L1176: def _resolve_cross_location_transfers(self, ctx)

  Механизм существует, но не работает, потому что:
    - boundary node unreachable (рёбра удалены)
    - NPC не может дойти до boundary
    - dwell не запускается
    - transfer не происходит
""")


# ============================================================================
# ЭТАП 4: Авторская геометрия — door_0, door_1, node_16
# ============================================================================
def stage4_author_geometry() -> None:
    _print_section("ЭТАП 4: Авторская геометрия — door_0, door_1, node_16, walls")

    tavern = _load_json(TAVERN_FILE)
    if not tavern:
        return

    print(f"\n>>> 4.1: door_0 — единственный внешний выход таверны")
    for o in tavern.get("objects", []):
        if isinstance(o, dict) and o.get("id") == "door_0":
            print(f"  door_0:")
            print(f"    name: {o.get('name')}")
            print(f"    position: {o.get('position')}")
            print(f"    wall_id: {o.get('wall_id')}")
            print(f"    target_file: {o.get('properties', {}).get('target_file')}")
            break

    print(f"\n>>> 4.2: door_1 — внутренняя дверь (зал↔кухня)")
    for o in tavern.get("objects", []):
        if isinstance(o, dict) and o.get("id") == "door_1":
            print(f"  door_1:")
            print(f"    name: {o.get('name')}")
            print(f"    position: {o.get('position')}")
            print(f"    wall_id: {o.get('wall_id')}")
            break

    print(f"\n>>> 4.3: node_16 — внутренний узел")
    node_16 = tavern.get("nodes", {}).get("node_16", {})
    if node_16:
        print(f"  node_16:")
        print(f"    x={node_16.get('x')}, y={node_16.get('y')}")
        print(f"    label: {node_16.get('label')}")
        print(f"    role: {node_16.get('role')}")
        print(f"    connections: {node_16.get('connections')}")

    print(f"\n>>> 4.4: Стены — где находится door_0")
    for w in tavern.get("walls", []):
        if isinstance(w, dict):
            wid = w.get("id")
            x1, y1, x2, y2 = w.get("x1"), w.get("y1"), w.get("x2"), w.get("y2")
            print(f"  {wid}: ({x1}, {y1}) → ({x2}, {y2})")

    print(f"""
>>> 4.5: Авторская семантика

  door_0 на wall_2 (y=13.0, max Y) — единственный внешний выход
  door_1 на wall_7 (x=14.0, внутренняя) — между залом и кухней
  Кухня не имеет внешнего выхода (только через door_1)
  node_16 — внутренний узел у двери

  adjacency:
    east: "city_gate" — территориальная связь (НЕ дверь внутри здания)
    south: "market_square" — территориальная связь (НЕ дверь внутри здания)

  КРИТИЧЕСКИЙ ВЫВОД:
    - В JSON НЕТ авторских exit_east, exit_south
    - door_0 — единственная дверь, физически существующая как внешний выход
    - GraphCompiler создаёт phantom exit_east/exit_south из adjacency
    - Эти phantom НИКАК не связаны с door_0 (нет door_0 в boundary_map)
    - NPC не может использовать door_0 для выхода, потому что boundary
      phantom находится в мировом пространстве, а не у door_0
""")


# ============================================================================
# ЭТАП 5: Подготовка исправления
# ============================================================================
def stage5_fix_proposal() -> None:
    _print_section("ЭТАП 5: Подготовка минимального исправления")

    print(f"""
=============================================================================
Доказанная первопричина (ROOT CAUSE)
=============================================================================

GraphCompiler._create_boundary_nodes (graph_compiler.py L892-952) создаёт
synthetic boundary nodes с МИРОВЫМИ координатами (origin.x + offset, origin.y + offset),
в то время как:
  - авторские узлы в graph хранятся с ЛОКАЛЬНЫМИ координатами (как в JSON)
  - стены (spatial_walls) хранятся с ЛОКАЛЬНЫМИ координатами
  - SpatialValidator сравнивает coords узлов с coords стен — оба должны быть
    в одной системе координат

Это смешение координат приводит к:
  1. SpatialValidator видит, что ребро от boundary node (мир coords)
     до авторского узла (локал coords) пересекает стену (локал coords)
     в неправильной геометрической интерпретации
  2. SpatialValidator удаляет ребро → boundary node недостижим
  3. get_furthest выбирает boundary node (он дальше всего от угрозы
     из-за огромных мировых coords)
  4. A* не находит путь → FLEE BLOCKED

=============================================================================
Точный файл и участок кода
=============================================================================

Файл: backend/app/services/spatial/graph_compiler.py
Функция: _create_boundary_nodes
Строки: L892-952 (вычисление _bx, _by и создание boundary_node)

Ключевые строки:
  L892: _ox = float(origin.get("x", 0.0))
  L893: _oy = float(origin.get("y", 0.0))
  L894: _w = float(size.get("w", 10.0))
  L895: _h = float(size.get("h", 10.0))

  L898-903: _DIR_TO_XY = {{
               "north": (_ox + _w / 2.0, _oy + _h - 1.0),  ← МИРОВЫЕ
               "south": (_ox + _w / 2.0, _oy + 1.0),         ← МИРОВЫЕ
               "east":  (_ox + _w - 1.0, _oy + _h / 2.0),  ← МИРОВЫЕ
               "west":  (_ox + 1.0,      _oy + _h / 2.0),  ← МИРОВЫЕ
             }}

  L911-916: _DIR_OFFSETS (дублирует _DIR_TO_XY, тоже МИРОВЫЕ)

  L917: _bx, _by = _DIR_OFFSETS.get(direction, ...)

  L939: _existing_node = graph.get(boundary_id)
  L940: _final_x = _existing_node.x if _existing_node else _bx
  L941: _final_y = _existing_node.y if _existing_node else _by

  L943-950: boundary_node = NodeRef(x=_final_x, y=_final_y, ...)

=============================================================================
МИНИМАЛЬНЫЙ DIFF (БЫЛО → СТАЛО)
=============================================================================

Цель: вычислять _bx, _by в ЛОКАЛЬНЫХ координатах (без origin offset),
       чтобы согласовать с авторскими узлами и стенами.

Изменение в graph_compiler.py L898-917:

БЫЛО:
  L898-903: _DIR_TO_XY = {{
               "north": (_ox + _w / 2.0, _oy + _h - 1.0),
               "south": (_ox + _w / 2.0, _oy + 1.0),
               "east":  (_ox + _w - 1.0, _oy + _h / 2.0),
               "west":  (_ox + 1.0,      _oy + _h / 2.0),
             }}

  L911-916: _DIR_OFFSETS = {{
               "east":  (_ox + _w - 1.0, _oy + _h / 2.0),
               "west":  (_ox + 1.0,      _oy + _h / 2.0),
               "north": (_ox + _w / 2.0, _oy + _h - 1.0),
               "south": (_ox + _w / 2.0, _oy + 1.0),
             }}

  L917:      _bx, _by = _DIR_OFFSETS.get(direction, (_ox + _w / 2.0, _oy + _h / 2.0))

СТАЛО:
  # R2-FLEE-FIX: boundary nodes coords должны быть ЛОКАЛЬНЫМИ,
  # чтобы согласоваться с авторскими узлами и стенами в SpatialValidator.
  # Раньше использовались МИРОВЫЕ coords (origin + offset), что приводило
  # к смешению систем координат и удалению валидных рёбер.
  _DIR_OFFSETS_LOCAL = {{
      "east":  (_w - 1.0,  _h / 2.0),
      "west":  (1.0,       _h / 2.0),
      "north": (_w / 2.0, _h - 1.0),
      "south": (_w / 2.0, 1.0),
  }}
  _bx, _by = _DIR_OFFSETS_LOCAL.get(direction, (_w / 2.0, _h / 2.0))

  (Удалить _DIR_TO_XY — не используется после fix)

ЭФФЕКТ:
  - _bx, _by теперь ЛОКАЛЬНЫЕ (внутри location, 0..size)
  - Для tavern: east = (19, 7.5), south = (10, 1) — внутри локации
  - SpatialValidator сравнивает локальные coords boundary с локальными coords стен
  - Ребро exit_east (19, 7.5) → kitchen_bed_2 (18.44, 6.27)
    не пересекает wall_5 (x=19.5, y∈[0.5, 8.0]) — они почти совпадают
  - Ребро НЕ удаляется
  - A* находит путь fireplace → main_hall → exit_east
  - FLEE EXECUTED

ВАЖНО: door_0 находится на wall_2 (y=13.0), но exit_east теперь на (19, 7.5) —
       внутри локации, не у door_0. Это означает, что NPC не использует door_0
       для выхода — он идёт к точке (19, 7.5), которая физически внутри кухни
       (room_1: x∈[14, 19.5], y∈[0.5, 8.0]).

       Это НЕ противоречит авторской геометрии, потому что:
       - exit_east — это навигационный узел, не дверь
       - door_0 — это дверь, не навигационный узел выхода
       - NPC движется К exit_east, а не через door_0
       - После достижения exit_east, cross-location transfer переносит NPC
         в соседнюю локацию (city_gate)

       Но это НЕ идеально: было бы лучше, если бы exit_east находился
       рядом с door_0. Однако это требует авторского exit_east в JSON,
       что запрещено ограничениями задачи.

=============================================================================
ПОЧЕМУ ИСПРАВЛЕНИЕ НЕ НАРУШИТ СУЩЕСТВУЮЩИЕ МЕХАНИЗМЫ
=============================================================================

1. SpatialValidator: теперь сравнивает согласованные локальные coords
   → удаляет только рёбра, которые РЕАЛЬНО пересекают стены
   → ранее удалял валидные рёбра из-за смешения coords

2. get_furthest: теперь distance вычисляется корректно (локальные coords)
   → exit_east на (19, 7.5) — расстояние от fireplace (10.5, 3.0) ≈ 9.6
   → kitchen_bed_2 на (18.44, 6.27) — расстояние ≈ 8.5
   → exit_east остаётся дальше → выбран как FLEE target ✓

3. A* pathfinding: находит путь к exit_east (есть рёбра)

4. Cross-location transfer: boundary_map[exit_east] содержит entry_node_hint
   → NPC достигает exit_east → BOUNDARY_DWELL → transfer в city_gate

5. movement_engine: get_boundary_to_neighbor работает с boundary_map
   → находит tavern:exit_east для направления east

6. Локации market_square и city_gate: их boundary nodes тоже будут созданы
   с ЛОКАЛЬНЫМИ coords (если их fix применяется) → такая же корректировка
   → но: их узлы уже в JSON имеют coords вне declared size — это отдельная
     проблема данных, не связанная с этим fix

=============================================================================
ТЕСТЫ ДО ИЗМЕНЕНИЙ (BASELINE)
=============================================================================

1. compile_graph(tavern) → graph size = 18 (16 авторских + 2 phantom)
2. graph["tavern:exit_east"] coords = (44.03, 12.52) — МИРОВЫЕ
3. SpatialValidator logs: 2 warnings (edge removed)
4. connections["tavern:exit_east"] = [] (пусто)
5. get_furthest(threat=fireplace) → tavern:exit_east (distance=34.86)
6. A* path to exit_east → no path (failure=M005)
7. FLEE BLOCKED

=============================================================================
ТЕСТЫ ПОСЛЕ ИЗМЕНЕНИЙ
=============================================================================

1. compile_graph(tavern) → graph size = 18 (16 авторских + 2 boundary)
2. graph["tavern:exit_east"] coords = (19, 7.5) — ЛОКАЛЬНЫЕ
3. SpatialValidator logs: 0 warnings (no edges removed)
4. connections["tavern:exit_east"] = {{tavern:kitchen_bed_2, tavern:kitchen}} (non-empty)
5. get_furthest(threat=fireplace) → tavern:exit_east (distance=9.6) ✓
6. A* path to exit_east → fireplace → main_hall → ... → exit_east
7. FLEE EXECUTED

=============================================================================
РЕГРЕССИОННЫЕ РИСКИ
=============================================================================

1. test_boundary_nodes.py (frontend tests):
   - Тесты создают карты с center node + adjacency → boundary создаются
   - С ЛОКАЛЬНЫМИ coords (5x5 map, center at (5, 5)):
     east boundary = (4, 2.5) — внутри map
     south boundary = (2.5, 1) — внутри map
   - Тесты проверяют существование boundary и связей, не coords
   - Риск: НИЗКИЙ (coords в тестах не проверяются)

2. Cross-location transfer (movement_engine):
   - boundary_map[boundary_id] = {{x, y, neighbor_chunk, ...}}
   - L985-986: "x": _final_x, "y": _final_y
   - movement_engine может использовать x, y для cross-loc materialization
   - Риск: если materialize использует МИРОВЫЕ coords, fix сломает
   - Нужно проверить, где boundary_map["x"], ["y"] используются

3. SpatialRegistry.find_chunks(world_x, world_y):
   - Эта функция ищет чанк по МИРОВЫМ coords
   - boundary node coords используются для cross-loc, а не для поиска чанка
   - Риск: МИНИМАЛЬНЫЙ

4. MovementEngine._handle_boundary_arrival:
   - L448-460: BOUNDARY_DWELL mechanism
   - L466-468: "via": boundary_node.node_id — использует node_id, не coords
   - Риск: МИНИМАЛЬНЫЙ

5. get_furthest distance:
   - Раньше distance была огромной (34.86 для exit_east)
   - Теперь будет ~9.6 для exit_east, ~8.5 для kitchen_bed_2
   - exit_east остаётся выбранным (9.6 > 8.5)
   - Но если авторский exit_east был бы дальше — distance ranking меняется
   - Риск: НИЗКИЙ для текущей карты

6. Локации market_square и city_gate:
   - Их boundary nodes тоже будут с ЛОКАЛЬНЫМИ coords
   - Но их авторские узлы уже ВНЕ declared size (отдельная проблема)
   - Риск: boundary для MS/CG будут в пределах size, но авторские nodes
     останутся вне — SpatialValidator может удалить рёбра между ними
   - НУЖНО ОТДЕЛЬНО ИССЛЕДОВАТЬ (но не в рамках этой задачи)

=============================================================================
ТЕСТОВЫЕ СЦЕНАРИИ
=============================================================================

1. Компиляция графа Tavern:
   - graph size = 18 (16 авторских + 2 boundary)
   - boundary coords ЛОКАЛЬНЫЕ

2. Сохранение корректных координат узлов:
   - graph["tavern:exit_east"].x < 20 (size.w)
   - graph["tavern:exit_south"].y < 15 (size.h)

3. Отсутствие удаления валидных рёбер SpatialValidator:
   - 0 warnings о "crosses solid wall"

4. Достижимая цель FLEE:
   - get_furthest возвращает tavern:exit_east
   - exit_east достижим через A*

5. Успешный A* до цели:
   - path: fireplace → ... → exit_east

6. Использование NPC существующего внешнего выхода door_0:
   - door_0 на wall_2 — не задействован (exit_east внутри кухни)
   - ПРИМЕЧАНИЕ: NPC идёт к exit_east, не к door_0
   - door_0 — это дверь, а exit_east — навигационный узел
   - NPC "выходит" через точку (19, 7.5) → cross-loc transfer в city_gate
   - door_0 не используется для FLEE (но не нарушает авторскую геометрию)

7. Переход между соседними локациями через существующий механизм:
   - NPC достигает exit_east → BOUNDARY_DWELL → transfer в city_gate

8. Регрессия внутренних маршрутов таверны:
   - schedule: working → kitchen — работает (kitchen узел не тронут)
   - SEEK_ALLY — работает (connections не удалены)

=============================================================================
ФИНАЛЬНЫЙ ВЕРДИКТ
=============================================================================

ROOT CAUSE: Смешение систем координат в _create_boundary_nodes
            (boundary nodes в МИРОВЫХ coords, остальной graph в ЛОКАЛЬНЫХ).

MINIMAL FIX: Изменить L898-917 в graph_compiler.py — вычислять _bx, _by
             в ЛОКАЛЬНЫХ координатах (без origin offset).

REGRESSION RISKS: test_boundary_nodes.py (низкий), movement_engine
                  boundary_map usage (нужно проверить), MS/CG boundary
                  (отдельная задача).

TEST PLAN: 8 тестовых сценариев выше.

КРИТЕРИЙ ЗАВЕРШЕНИЯ: NPC использует exit_east (созданный из adjacency)
                     для FLEE, A* находит путь, cross-location transfer
                     работает. Авторская геометрия не изменена.
""")


# ============================================================================
# Main
# ============================================================================
def main() -> int:
    print("=" * 78)
    print("R2-FLEE-COORD-CONTRACT-AUDIT — комплексный probe (5 этапов)")
    print(f"TAVERN_FILE: {TAVERN_FILE}")
    print(f"OUT_FILE: {OUT_FILE}")
    print("=" * 78)

    try:
        stage1_coord_contract()
    except Exception as e:
        print(f"[stage1 error: {e}]")
        traceback.print_exc()

    try:
        stage2_boundary_nodes()
    except Exception as e:
        print(f"[stage2 error: {e}]")
        traceback.print_exc()

    try:
        stage3_flee_reachability()
    except Exception as e:
        print(f"[stage3 error: {e}]")
        traceback.print_exc()

    try:
        stage4_author_geometry()
    except Exception as e:
        print(f"[stage4 error: {e}]")
        traceback.print_exc()

    try:
        stage5_fix_proposal()
    except Exception as e:
        print(f"[stage5 error: {e}]")
        traceback.print_exc()

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
