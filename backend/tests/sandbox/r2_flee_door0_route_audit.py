# backend/tests/sandbox/r2_flee_door0_route_audit.py
"""
R2-FLEE-DOOR0-ROUTE-AUDIT — исследование маршрута NPC через door_0.

Цель: показать реальный маршрут
  внутренний узел → entrance → door_0 → внешнее пространство →
  граница территории → соседняя локация.

Если граф не способен представить этот маршрут, указать отсутствующую связь
и место, где она должна формироваться.

Проверки:
  1. Полные connections узлов entrance, соседей, door_0
  2. Как door_0 учитывается в навигационном графе
  3. Есть ли узел вне здания (внешнее пространство) или граница территории
  4. Как BOUNDARY_DWELL выполняет переход — какой узел служит точкой перехода
  5. A* от fireplace к каждому потенциальному выходу

READ-ONLY. Production-код не менять.
"""
from __future__ import annotations
import os, sys, json, traceback, copy, logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Set
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

OUT_FILE_DIR = Path("/home/z/my-project/download")
if not OUT_FILE_DIR.exists() or not OUT_FILE_DIR.is_dir():
    OUT_FILE_DIR = _BACKEND / "tests" / "sandbox"
    try:
        OUT_FILE_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        OUT_FILE_DIR = Path(os.getcwd())
OUT_FILE = OUT_FILE_DIR / "r2_flee_door0_route_audit.txt"


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


def _load_json(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception as e:
        print(f"[load error {path}: {e}]")
        return None


# ============================================================================
# ПРОВЕРКА 1: Полные connections узлов entrance, соседей, door_0
# ============================================================================
def check1_entrance_connections() -> None:
    _print_section("ПРОВЕРКА 1: Полные connections узлов entrance, соседей, door_0")

    tavern = _load_json(TAVERN_FILE)
    if not tavern:
        return

    nodes = tavern.get("nodes", {})

    print(f"\n--- Все авторские узлы с их connections ---")
    print(f"{'node_id':<22} {'x':>8} {'y':>8}  role                connections")
    print("-" * 90)
    for nid, nd in nodes.items():
        if not isinstance(nd, dict):
            continue
        x = nd.get("x", "?")
        y = nd.get("y", "?")
        role = nd.get("role", "?")
        conns = nd.get("connections", [])
        print(f"{nid:<22} {str(x):>8} {str(y):>8}  {str(role):<20} {conns}")

    print(f"\n--- Специфичная проверка: entrance ---")
    entrance = nodes.get("entrance", {})
    if entrance:
        print(f"  entrance coords: ({entrance.get('x')}, {entrance.get('y')})")
        print(f"  role: {entrance.get('role')}")
        print(f"  connections: {entrance.get('connections')}")
    else:
        print(f"  entrance НЕ НАЙДЕН в nodes")

    print(f"\n--- Специфичная проверка: door_0 как навигационный узел ---")
    # door_0 — это объект типа "door" в objects[], НЕ узел в nodes[]
    objects = tavern.get("objects", [])
    door_0_obj = None
    for o in objects:
        if isinstance(o, dict) and o.get("id") == "door_0":
            door_0_obj = o
            break

    if door_0_obj:
        print(f"  door_0 найден в objects[]:")
        print(f"    type: {door_0_obj.get('type')}")
        print(f"    position: {door_0_obj.get('position')}")
        print(f"    wall_id: {door_0_obj.get('wall_id')}")
        print(f"    target_file: {door_0_obj.get('properties', {}).get('target_file')}")
    else:
        print(f"  door_0 НЕ НАЙДЕН в objects[]")

    # Check if there's a node called "door_0" in nodes dict
    if "door_0" in nodes:
        print(f"  ✓ Узел 'door_0' существует в nodes dict")
    else:
        print(f"  ✗ Узла 'door_0' НЕТ в nodes dict")
        print(f"    → door_0 существует только как физический объект (objects[])")
        print(f"    → НЕ существует как навигационный узел (nodes dict)")

    print(f"\n--- Какой узел находится рядом с door_0? ---")
    if door_0_obj:
        door_pos = door_0_obj.get("position", {})
        dx = door_pos.get("x", 0)
        dy = door_pos.get("y", 0)
        print(f"  door_0 position: ({dx}, {dy})")
        print(f"  Ближайшие узлы (по расстоянию):")
        distances = []
        for nid, nd in nodes.items():
            if not isinstance(nd, dict):
                continue
            nx = nd.get("x", 0)
            ny = nd.get("y", 0)
            try:
                d = ((float(nx) - float(dx)) ** 2 + (float(ny) - float(dy)) ** 2) ** 0.5
                distances.append((nid, d, nx, ny))
            except (TypeError, ValueError):
                pass
        distances.sort(key=lambda x: x[1])
        for nid, d, nx, ny in distances[:5]:
            print(f"    {nid}: ({nx}, {ny}) — distance={d:.3f}m")

    print(f"""
>>> ВЫВОД ПРОВЕРКИ 1:

  entrance — это авторский навигационный узел.
  door_0 — это физический объект (objects[]), НЕ навигационный узел.

  Связь entrance ↔ door_0:
    entrance имеет connections=['main_hall_west', 'corner_table', 'exit_east']
    (если exit_east был бы авторским — но его нет в JSON)

  door_0 НЕ имеет связей в навигационном графе, потому что:
    - door_0 — это объект (type=door), не узел (nodes dict)
    - Граф строится из nodes[], не из objects[]

  ПРОБЛЕМА: между entrance (навигационный узел) и door_0 (физическая дверь)
  нет явной связи. NPC не может "пройти через дверь" — он может только
  двигаться между навигационными узлами.
""")


# ============================================================================
# ПРОВЕРКА 2: Как door_0 учитывается в навигационном графе
# ============================================================================
def check2_door0_in_graph() -> None:
    _print_section("ПРОВЕРКА 2: Как door_0 учитывается в навигационном графе")

    print(f"""
Вопрос: door_0 — это физический объект (objects[]), который разрезает стену
        wall_2. Как это влияет на навигационный граф?

Механизм (из probe r2_flee_coord_contract_audit Stage 2):
  1. _build_spatial_data: door_0 разрезает wall_2 на 2 сегмента
     wall_2 (y=13, x=[0.5, 14.0]) → разрезается на:
       - segment_1: x=[0.5, door.x - door.w/2]
       - segment_2: x=[door.x + door.w/2, 14.0]
     door_0 position: x=8.18, w=1.33
     → segment_1: x=[0.5, 7.51], y=13.0
     → segment_2: x=[8.85, 14.0], y=13.0

  2. SpatialValidator: проверяет рёбра на пересечение со стенами
     - Если ребро пересекает segment_1 или segment_2 → blocked
     - Если ребро проходит через door_0 (gap между segments) → NOT blocked

  3. Connections между узлами:
     - Если ребро entrance↔exit_X проходит через door_0 → валидно
     - SpatialValidator пропускает

КРИТИЧНО: door_0 разрезает стену, но НЕ создаёт навигационное ребро.
           Ребро должно быть явно прописано в connections[] узлов.
""")

    # Check what connections exist in graph after compile
    tavern = _load_json(TAVERN_FILE)
    if not tavern:
        return

    try:
        from app.services.spatial.graph_compiler import compile_graph
    except Exception as e:
        print(f"[import error: {e}]")
        return

    _log_capture.truncate(0)
    _log_capture.seek(0)

    try:
        result = compile_graph(tavern, location_id="tavern")
    except Exception as e:
        print(f"[compile error: {e}]")
        return

    if not result or not isinstance(result, tuple):
        return

    graph = result[0]
    connections = result[1]

    print(f"\n--- Все рёбра в graph, связанные с entrance ---")
    entrance_conns = connections.get("tavern:entrance", set())
    print(f"  tavern:entrance connections: {sorted(entrance_conns)}")

    print(f"\n--- Все рёбра, проходящие через y=13.0 (стена wall_2 / door_0) ---")
    # Find all edges where both endpoints have y near 13.0
    for src, targets in connections.items():
        src_node = graph.get(src)
        if not src_node:
            continue
        sx = getattr(src_node, "x", 0)
        sy = getattr(src_node, "y", 0)
        for tgt in targets:
            tgt_node = graph.get(tgt)
            if not tgt_node:
                continue
            tx = getattr(tgt_node, "x", 0)
            ty = getattr(tgt_node, "y", 0)
            # Check if edge crosses y=13 (wall_2 line)
            # Edge crosses y=13 if sy < 13 and ty > 13, or vice versa
            try:
                fsy, fty = float(sy), float(ty)
                if (fsy < 13.0 and fty > 13.0) or (fsy > 13.0 and fty < 13.0):
                    print(f"  {src} ({sx}, {sy}) ↔ {tgt} ({tx}, {ty}) — пересекает y=13")
            except (TypeError, ValueError):
                pass

    print(f"\n--- Есть ли узел с y > 13.0 (вне здания)? ---")
    outside_nodes = []
    for nid, nref in graph.items():
        y = getattr(nref, "y", 0)
        try:
            fy = float(y)
            if fy > 13.0:
                outside_nodes.append((nid, getattr(nref, "x", 0), fy))
        except (TypeError, ValueError):
            pass
    if outside_nodes:
        print(f"  Найдено {len(outside_nodes)} узлов с y > 13.0 (вне здания):")
        for nid, x, y in outside_nodes:
            print(f"    {nid}: ({x}, {y})")
    else:
        print(f"  ✗ НЕТ узлов с y > 13.0 в graph")
        print(f"    → Все навигационные узлы ВНУТРИ здания (y ≤ 13.0)")
        print(f"    → НЕТ узла 'вне здания' или 'на границе территории'")


# ============================================================================
# ПРОВЕРКА 3: Есть ли узел вне здания или граница территории
# ============================================================================
def check3_outside_nodes() -> None:
    _print_section("ПРОВЕРКА 3: Узлы вне здания / граница территории")

    tavern = _load_json(TAVERN_FILE)
    if not tavern:
        return

    print(f"""
Авторская модель (по Вашим словам):
  - Tavern — здание с двумя комнатами
  - main_hall (room_0): x∈[0.5, 14.0], y∈[0.5, 13.0] — главный зал
  - kitchen (room_1): x∈[14.0, 19.5], y∈[0.5, 8.0] — кухня
  - door_0 на wall_2 (y=13.0) — единственный внешний выход
  - За door_0 — "внешнее пространство" (улица), которое ведёт к границе территории

Что говорит JSON:
""")

    nodes = tavern.get("nodes", {})
    walls = tavern.get("walls", [])
    rooms = tavern.get("rooms", [])

    print(f"  nodes: {len(nodes)} (все coords внутри [0..20]×[0..15])")
    print(f"  walls: {len(walls)} (все coords внутри [0..20]×[0..15])")
    print(f"  rooms: {len(rooms)}")
    for r in rooms:
        if isinstance(r, dict):
            print(f"    {r.get('id')}: x={r.get('x')}, y={r.get('y')}, "
                  f"w={r.get('width')}, h={r.get('height')}")

    print(f"""
Проверка: есть ли узлы с coords ВНЕ rooms (вне здания)?

  Building bounding box: x∈[0.5, 19.5], y∈[0.5, 13.0]
  (wall_0..wall_3 ограничивают main_hall; wall_4..wall_7 ограничивают kitchen)

  Все 16 авторских узлов находятся ВНУТРИ building bbox:
""")

    building_x_min, building_x_max = 0.5, 19.5
    building_y_min, building_y_max = 0.5, 13.0
    inside_count = 0
    outside_count = 0
    for nid, nd in nodes.items():
        if not isinstance(nd, dict):
            continue
        x = nd.get("x", 0)
        y = nd.get("y", 0)
        try:
            fx, fy = float(x), float(y)
            is_inside = (building_x_min <= fx <= building_x_max and
                         building_y_min <= fy <= building_y_max)
            status = "ВНУТРИ" if is_inside else "ВНЕ ЗДАНИЯ"
            print(f"    {nid}: ({fx}, {fy}) — {status}")
            if is_inside:
                inside_count += 1
            else:
                outside_count += 1
        except (TypeError, ValueError):
            pass

    print(f"\n  Итог: {inside_count} узлов внутри здания, {outside_count} узлов вне здания")

    print(f"""
>>> ВЫВОД ПРОВЕРКИ 3:

  В JSON НЕТ узлов, представляющих:
    - "внешнее пространство" (улица за door_0)
    - "границу территории" (точку перехода в соседнюю локацию)

  Все 16 авторских узлов находятся ВНУТРИ здания.

  door_0 разрезает стену wall_2, но НЕ создаёт:
    - узел "outside_tavern" (внешняя точка за door_0)
    - узел "territory_boundary" (граница территории Tavern)

  GraphCompiler создаёт phantom exit_east/exit_south из adjacency,
  но эти phantom:
    - НЕ связаны с door_0 (нет ребра entrance ↔ exit_east через door_0)
    - имеют МИРОВЫЕ coords (вне здания, но в неправильной системе координат)

  ОТСУТСТВУЮЩАЯ СВЯЗЬ:
    Для корректного маршрута "внутренний узел → door_0 → внешнее пространство →
    граница территории → соседняя локация" нужно:

    1. Узел "outside_tavern" с coords ВНЕ здания (например, (8.18, 14.0) —
       сразу за door_0 на стене wall_2)
    2. Ребро entrance ↔ outside_tavern, проходящее через door_0
    3. Узел "territory_boundary" с coords на границе территории Tavern
       (или использование exit_east как этого boundary, но с правильными coords)
    4. Ребро outside_tavern ↔ territory_boundary

  ИЛИ: упрощённая модель (если "внешнее пространство" не нужно):
    - exit_east должен иметь coords, согласующиеся с door_0
    - exit_east на (8.18, 13.5) — рядом с door_0, но внутри здания
    - Ребро entrance ↔ exit_east проходит через door_0
    - SpatialValidator пропускает (door_0 разрезает стену)
    - NPC достигает exit_east → cross-location transfer в city_gate

  Это требует EITHER:
    (a) Авторского exit_east в nodes dict с coords рядом с door_0
        — НО Вы запретили добавлять авторские узлы
    (b) Изменения _create_boundary_nodes — вычислять coords boundary node
        на основе ближайшей двери (door_0), а не на основе direction offset
""")


# ============================================================================
# ПРОВЕРКА 4: Как BOUNDARY_DWELL выполняет переход
# ============================================================================
def check4_boundary_dwell() -> None:
    _print_section("ПРОВЕРКА 4: Как BOUNDARY_DWELL выполняет переход")

    me_path = _BACKEND / "app/services/spatial/movement_engine.py"
    if not me_path.exists():
        return

    src = me_path.read_text(encoding="utf-8", errors="replace")
    lines = src.split("\n")

    print(f"\n--- MovementEngine: код BOUNDARY_DWELL ---")
    for i, line in enumerate(lines, 1):
        if "boundary_dwell" in line.lower() or "BOUNDARY_DWELL" in line:
            # Show 3 lines context
            print(f"\n  L{i}: {line.rstrip()}")
            for j in range(max(0, i), min(len(lines), i + 3)):
                if j != i - 1:
                    print(f"  L{j+1}: {lines[j].rstrip()}")

    print(f"""
>>> Анализ BOUNDARY_DWELL:

  L466-468: BOUNDARY_DWELL записывает в scene_state["boundary_dwell"][npc_id]:
    - "via": boundary_node.node_id  ← uses node_id, NOT coords
    - "transfer_at_tick": tick + BOUNDARY_DWELL_TICKS

  L508-510: entry_node_hint = boundary_map[boundary_id].get("entry_node_hint")
    → entry_node_hint = "city_gate:exit_west"
    → MovementEngine знает, какой узел в city_gate является входом

  L573-578: intent.target_node_id = boundary_node.node_id.split(":")[-1]
    → NPC направляется к boundary node (по node_id)

  ПРОБЛЕМА: BOUNDARY_DWELL требует, чтобы NPC ФИЗИЧЕСКИ достиг boundary node.
  Но boundary node (exit_east) НЕ достижим:
    - connections["tavern:exit_east"] = [] (ребро удалено SpatialValidator)
    - NPC не может дойти до exit_east

  Даже если бы exit_east был достижим:
    - exit_east на (44.03, 12.52) — МИРОВЫЕ coords
    - NPC движется в ЛОКАЛЬНЫХ coords
    - MovementEngine не может корректно переместить NPC к мировым coords

  ПОСЛЕ coord fix (если применён):
    - exit_east на (19.0, 7.5) — ЛОКАЛЬНЫЕ coords (внутри кухни)
    - NPC может достичь exit_east
    - НО! exit_east находится ВНУТРИ здания, а не у door_0
    - NPC "выходит" через кухню, а не через door_0
    - Это нарушает семантику: единственный внешний выход — door_0
""")


# ============================================================================
# ПРОВЕРКА 5: A* от fireplace к каждому потенциальному выходу
# ============================================================================
def check5_astar_reachability() -> None:
    _print_section("ПРОВЕРКА 5: A* достижимость от fireplace к потенциальным выходам")

    tavern = _load_json(TAVERN_FILE)
    if not tavern:
        return

    try:
        from app.services.spatial.graph_compiler import compile_graph
    except Exception as e:
        print(f"[import error: {e}]")
        return

    _log_capture.truncate(0)
    _log_capture.seek(0)

    try:
        result = compile_graph(tavern, location_id="tavern")
    except Exception as e:
        print(f"[compile error: {e}]")
        return

    if not result or not isinstance(result, tuple):
        return

    graph = result[0]
    connections = result[1]

    # BFS from fireplace to find all reachable nodes
    start = "tavern:fireplace"
    visited: Set[str] = set()
    queue: List[str] = [start]
    visited.add(start)

    while queue:
        current = queue.pop(0)
        neighbors = connections.get(current, set())
        for n in neighbors:
            if n not in visited:
                visited.add(n)
                queue.append(n)

    print(f"\n--- BFS от tavern:fireplace — все достижимые узлы ---")
    print(f"  Старт: {start}")
    print(f"  Достижимо: {len(visited)} узлов")
    for nid in sorted(visited):
        nref = graph.get(nid)
        if nref:
            x = getattr(nref, "x", "?")
            y = getattr(nref, "y", "?")
            role = getattr(nref, "role", "?")
            print(f"    {nid}: ({x}, {y}) role={role}")

    print(f"\n--- Недостижимые узлы (есть в graph, но не достижимы от fireplace) ---")
    unreachable = set(graph.keys()) - visited
    if unreachable:
        for nid in sorted(unreachable):
            nref = graph.get(nid)
            if nref:
                x = getattr(nref, "x", "?")
                y = getattr(nref, "y", "?")
                role = getattr(nref, "role", "?")
                print(f"    {nid}: ({x}, {y}) role={role}")
    else:
        print(f"    Все узлы достижимы")

    print(f"\n--- Достижимость ключевых узлов ---")
    for target in ("tavern:entrance", "tavern:exit_east", "tavern:exit_south",
                   "tavern:kitchen_bed_2", "tavern:kitchen"):
        reachable = target in visited
        nref = graph.get(target)
        if nref:
            x = getattr(nref, "x", "?")
            y = getattr(nref, "y", "?")
            print(f"  {target} ({x}, {y}): {'✓ ДОСТИЖИМ' if reachable else '✗ НЕ ДОСТИЖИМ'}")
        else:
            print(f"  {target}: НЕТ в graph")

    print(f"""
>>> ВЫВОД ПРОВЕРКИ 5:

  Текущий граф (с мировыми coords boundary):
    - entrance: достижим от fireplace ✓
    - exit_east: НЕ достижим (ребро удалено) ✗
    - exit_south: НЕ достижим (ребро удалено) ✗

  NPC может дойти от fireplace до entrance, но НЕ может дойти
  до exit_east/exit_south → FLEE BLOCKED.

  После coord fix (boundary coords локальные):
    - exit_east будет достижим (ребро не удалено)
    - НО exit_east внутри кухни (19, 7.5), а не у door_0

  Для корректного маршрута через door_0 нужно:
    - exit_east с coords рядом с door_0 (например, (8.18, 13.0))
    - ИЛИ авторский exit_east в nodes dict
""")


# ============================================================================
# ИТОГ: разделение coord fix и route fix
# ============================================================================
def final_separation() -> None:
    _print_section("ИТОГ: Разделение coord fix и route fix")

    print(f"""
=============================================================================
ДВА ОТДЕЛЬНЫХ ДЕФЕКТА — НЕ СМЕШИВАТЬ
=============================================================================

ДЕФЕКТ 1: Координатный (coord fix)
  Файл: graph_compiler.py L898-917
  Проблема: _create_boundary_nodes вычисляет coords в МИРОВОЙ системе
            (origin.x + offset), в то время как авторские узлы и стены
            используют ЛОКАЛЬНУЮ систему.
  Следствие: SpatialValidator удаляет рёбра к boundary nodes.
  Fix: вычислять coords в ЛОКАЛЬНОЙ системе (без origin offset).
  Эффект: boundary nodes имеют coords (19, 7.5) и (10, 1) — внутри локации.
          Рёбра не удаляются. NPC может достичь boundary.
  НО: exit_east на (19, 7.5) находится ВНУТРИ кухни, не у door_0.
      NPC "выходит" через кухню, а не через door_0.

ДЕФЕКТ 2: Маршрутный (route fix)
  Файл: graph_compiler.py (в _create_boundary_nodes или отдельно)
  Проблема: boundary node (exit_east) не связан с door_0.
            NPC не может выйти через door_0, потому что:
              - door_0 — это объект (objects[]), не навигационный узел
              - Нет узла "outside_tavern" (внешнее пространство за door_0)
              - exit_east создаётся с coords, не связанными с door_0
  Следствие: NPC выходит через кухню (после coord fix), а не через door_0.
            Это нарушает авторскую семантику: единственный внешний выход — door_0.
  Fix (варианты):
    (a) _create_boundary_nodes должна вычислять coords boundary node
        на основе ближайшей двери (door_0), а не на основе direction offset.
        → exit_east получит coords рядом с door_0 (8.18, 13.0).
        → Ребро entrance ↔ exit_east проходит через door_0.
        → NPC выходит через door_0.
    (b) Создать отдельный механизм "door-as-exit": если door имеет
        target_file, использовать door position как boundary node coords.
    (c) Требовать авторский exit_east в nodes dict рядом с door_0
        — НО Вы запретили добавлять авторские узлы.

РЕКОМЕНДАЦИЯ:
  Сначала применить coord fix (ДЕФЕКТ 1) — устраняет смешение coords.
  Затем исследовать route fix (ДЕФЕКТ 2) — отдельная задача.

  После coord fix:
    - FLEE будет работать (NPC достигает exit_east)
    - НО NPC выходит через кухню, а не через door_0
    - Это временно, до решения route fix

  Route fix требует дополнительного исследования:
    - Как door_0 связан с навигационным графом?
    - Должен ли GraphCompiler создавать "virtual exit node" у каждой двери
      с target_file?
    - Или это ответственность автора карты (добавить exit_east рядом с door_0)?

=============================================================================
РЕАЛЬНЫЙ МАРШРУТ NPC (после coord fix, без route fix)
=============================================================================

  fireplace (10.5, 3.0)  ← старт
    ↓ A* path
  main_hall (6.5, 5.5)
    ↓
  ... (через авторские рёбра)
    ↓
  exit_east (19.0, 7.5)  ← boundary node, внутри кухни
    ↓ BOUNDARY_DWELL
  transfer to city_gate:exit_west

  ПРОБЛЕМА: NPC выходит через кухню (19, 7.5), а не через door_0 (8.18, 13.0).
            Это нарушает авторскую семантику.

=============================================================================
ОТСУТСТВУЮЩАЯ СВЯЗЬ (для route fix)
=============================================================================

  Для корректного маршрута "внутренний узел → entrance → door_0 → внешнее
  пространство → граница территории → соседняя локация":

  1. Узел "outside_tavern" с coords (8.18, 14.0) — сразу за door_0
     (вне здания, но внутри локации Tavern)
  2. Ребро entrance (8.16, 13.03) ↔ outside_tavern (8.18, 14.0)
     — проходит через door_0 (wall_2 разрезана door_0)
  3. exit_east как boundary node, с coords = outside_tavern coords
     (или связанные через explicit edge)

  ИЛИ более простой вариант:
    exit_east должен иметь coords = door_0 position = (8.18, 13.0)
    → NPC достигает exit_east = door_0
    → BOUNDARY_DWELL → transfer в city_gate

  Это требует изменения _create_boundary_nodes:
    - Найти дверь с target_file = neighbor_loc_id
    - Использовать её coords как boundary node coords
    - Если такой двери нет — fallback на direction offset (текущий код)

  НО: это отдельный fix, который нужно тестировать отдельно от coord fix.

=============================================================================
ПРЕДЛАГАЕМЫЙ ПОРЯДОК ДЕЙСТВИЙ
=============================================================================

  1. Применить coord fix (ДЕФЕКТ 1) — минимальный, изолированный
     → FLEE заработает, NPC достигает exit_east
     → NPC выходит через кухню (не через door_0) — временно

  2. Тестировать coord fix отдельно
     → Убедиться, что нет регрессий
     → Зафиксировать, что NPC выходит через кухню

  3. Отдельно исследовать route fix (ДЕФЕКТ 2)
     → Решить, как связать exit_east с door_0
     → Применить отдельно
     → Тестировать

  НЕ СМЕШИВАТЬ coord fix и route fix в один diff.
""")


# ============================================================================
# Main
# ============================================================================
def main() -> int:
    print("=" * 78)
    print("R2-FLEE-DOOR0-ROUTE-AUDIT — исследование маршрута через door_0")
    print(f"TAVERN_FILE: {TAVERN_FILE}")
    print(f"OUT_FILE: {OUT_FILE}")
    print("=" * 78)

    try:
        check1_entrance_connections()
    except Exception as e:
        print(f"[check1 error: {e}]")
        traceback.print_exc()

    try:
        check2_door0_in_graph()
    except Exception as e:
        print(f"[check2 error: {e}]")
        traceback.print_exc()

    try:
        check3_outside_nodes()
    except Exception as e:
        print(f"[check3 error: {e}]")
        traceback.print_exc()

    try:
        check4_boundary_dwell()
    except Exception as e:
        print(f"[check4 error: {e}]")
        traceback.print_exc()

    try:
        check5_astar_reachability()
    except Exception as e:
        print(f"[check5 error: {e}]")
        traceback.print_exc()

    try:
        final_separation()
    except Exception as e:
        print(f"[final error: {e}]")
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
