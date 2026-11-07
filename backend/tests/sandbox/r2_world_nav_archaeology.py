# backend/tests/sandbox/r2_world_nav_archaeology.py
"""
R2-WORLD-NAV-ARCHAEOLOGY probe — архитектурное исследование.

Цель: исследовать возможность перехода от искусственных boundary nodes
и изолированных графов локаций к единой мировой системе координат
и непрерывной геометрической навигации NPC.

7 разделов:
  1. Текущий контракт координат
  2. Текущая система переходов
  3. Возможность непрерывной мировой навигации
  4. Архитектурные варианты (A/B/C)
  5. Проверка реальной геометрии (мировые координаты Tavern, MS, CG)
  6. Целевой сценарий NPC
  7. Итоговый отчёт

READ-ONLY: никаких production-изменений, новых дверей, boundary nodes,
изменений авторской геометрии.
"""
from __future__ import annotations
import os, sys, json, traceback, copy
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Set
import io
import re

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
LOCATIONS_DIR = PROJECT_ROOT / "saves/Open_road/locations"
TAVERN_FILE = LOCATIONS_DIR / "tavern.json"
MARKET_SQUARE_FILE = LOCATIONS_DIR / "market_square.json"
CITY_GATE_FILE = LOCATIONS_DIR / "city_gate.json"

OUT_FILE_DIR = Path("/home/z/my-project/download")
if not OUT_FILE_DIR.exists() or not OUT_FILE_DIR.is_dir():
    OUT_FILE_DIR = _BACKEND / "tests" / "sandbox"
    try:
        OUT_FILE_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        OUT_FILE_DIR = Path(os.getcwd())
OUT_FILE = OUT_FILE_DIR / "r2_world_nav_archaeology.txt"


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


def _dump_json(obj: Any, max_chars: int = 0) -> str:
    try:
        s = json.dumps(obj, ensure_ascii=False, indent=2, default=str)
        if max_chars and len(s) > max_chars:
            return s[:max_chars] + f"\n... (truncated, total {len(s)} chars)"
        return s
    except Exception:
        return str(obj)


def _read_lines(path: Path, start: int, end: int) -> List[str]:
    if not path.exists():
        return [f"[file not found: {path}]"]
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").split("\n")
        return [f"L{i+1:4d}: {lines[i]}" for i in range(start - 1, min(end, len(lines)))]
    except Exception as e:
        return [f"[read error: {e}]"]


def _grep_in_dir(directory: Path, patterns: List[str], file_exts: List[str] = (".py",)) -> List[Tuple[Path, int, str]]:
    out: List[Tuple[Path, int, str]] = []
    if not directory.exists():
        return out
    for f in directory.rglob("*"):
        if not f.is_file() or f.suffix.lower() not in file_exts:
            continue
        try:
            src = f.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for i, line in enumerate(src.split("\n"), 1):
            for pat in patterns:
                if pat in line:
                    out.append((f, i, line.rstrip()))
                    break
    return out


def _load_map(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception as e:
        print(f"[load error {path}: {e}]")
        return None


# ============================================================================
# STEP 1: Coordinate contract — how origin works
# ============================================================================
def step1_coordinate_contract() -> None:
    _print_section("STEP 1: Текущий контракт координат — как применяется origin")

    # Search for origin usage in spatial code
    print("\n--- Поиск использования 'origin' в spatial коде ---")
    spatial_dir = _BACKEND / "app/services/spatial"
    if spatial_dir.exists():
        results = _grep_in_dir(spatial_dir, ["origin", "global_coords", "world_coords", "local_to_world", "world_to_local"])
        for path, ln, line in results[:30]:
            rel = path.relative_to(_BACKEND)
            print(f"  {rel} L{ln}: {line}")

    # Look at graph_compiler.py for origin usage
    print("\n--- graph_compiler.py: как используется origin ---")
    gc = spatial_dir / "graph_compiler.py"
    if gc.exists():
        src = gc.read_text(encoding="utf-8", errors="replace")
        for i, line in enumerate(src.split("\n"), 1):
            if "origin" in line.lower() or "global_coords" in line.lower() or "_ox" in line or "_oy" in line:
                print(f"  L{i}: {line.rstrip()}")

    # SpatialRegistry / world coords
    print("\n--- SpatialRegistry / WorldBounds / world coords ---")
    sr = spatial_dir / "spatial_registry.py"
    if sr.exists():
        src = sr.read_text(encoding="utf-8", errors="replace")
        for i, line in enumerate(src.split("\n"), 1):
            if any(kw in line for kw in ["world", "WorldBounds", "global", "origin", "zone_id", "chunk"]):
                print(f"  L{i}: {line.rstrip()}")

    # spatial_service.py for zone/origin handling
    print("\n--- spatial_service.py: zone_id / world / origin ---")
    ss = spatial_dir / "spatial_service.py"
    if ss.exists():
        src = ss.read_text(encoding="utf-8", errors="replace")
        for i, line in enumerate(src.split("\n"), 1):
            if any(kw in line for kw in ["zone_id", "world_", "world_distance", "origin", "global_coords"]):
                print(f"  L{i}: {line.rstrip()}")

    # Check for navmesh / world geometry
    print("\n--- Поиск NavMesh / world geometry / continuous navigation ---")
    navmesh_keywords = ["navmesh", "nav_mesh", "NavMesh", "walkable", "walk_poly",
                        "world_graph", "global_graph", "world_geometry", "world_space"]
    found = _grep_in_dir(_BACKEND, navmesh_keywords, file_exts=(".py",))
    if found:
        print(f"\nFound {len(found)} references:")
        for path, ln, line in found[:30]:
            rel = path.relative_to(_BACKEND) if path.is_relative_to(_BACKEND) else path
            print(f"  {rel} L{ln}: {line}")
    else:
        print("\n[NO NavMesh / world geometry / continuous navigation found]")


# ============================================================================
# STEP 2: Transition system — full path
# ============================================================================
def step2_transition_system() -> None:
    _print_section("STEP 2: Текущая система переходов — полный путь")

    print("""
Полный путь NPC movement между локациями:

  Location JSON
    ↓ DataManager.load_location()
  GraphCompiler.compile_graph(editor_data, location_id)
    ↓ создает graph, connections, alias_map, boundary_map
  _create_boundary_nodes()
    ↓ for direction, neighbor_loc_id in adjacency.items():
    ↓   boundary_id = f"{location_id}:exit_{direction}"
    ↓   _existing_node = graph.get(boundary_id)
    ↓   если _existing_node есть → использует его coords
    ↓   иначе → coords = (origin.x + offset_x, origin.y + offset_y)
    ↓ graph[boundary_id] = NodeRef(role=BOUNDARY, ...)
    ↓ connections.setdefault(...) — авто-связи в радиусе 3м
  SpatialValidator / _validate_navigation_geometry
    ↓ проверяет каждое ребро: пересекает ли стену?
    ↓ если да и нет door → удаляет ребро
  SpatialService
    ↓ хранит graph по zone_id
  SpatialTargetResolver
    ↓ для FLEE: get_furthest(zone_id, threat_xy)
    ↓ возвращает самый дальний узел (без проверки достижимости)
  MovementEngine._resolve_macro_relocation
    ↓ A* pathfinding: source_node → target_node
    ↓ если no path → failure=M005
  MovementEngine.process_intents
    ↓ если path найден → создает traversal
  Tick pipeline: NPC двигается по traversal
    ↓ при достижении boundary node:
    ↓ MovementEngine._handle_boundary_arrival?
    ↓ → смена scene_state, загрузка новой location
""")

    # Check MovementEngine for boundary handling
    print("\n--- MovementEngine: обработка boundary node arrival ---")
    me = _BACKEND / "app/services/spatial/movement_engine.py"
    if me.exists():
        src = me.read_text(encoding="utf-8", errors="replace")
        for i, line in enumerate(src.split("\n"), 1):
            if any(kw in line for kw in ["boundary", "neighbor_chunk", "entry_node_hint", "location_transition",
                                          "scene_change", "load_location", "switch_location"]):
                print(f"  L{i}: {line.rstrip()}")

    # Check scene_state_manager / location transitions
    print("\n--- SceneStateManager: load_location / scene change ---")
    ssm = _BACKEND / "app/services/scene_state_manager.py"
    if not ssm.exists():
        # search elsewhere
        for cand in _BACKEND.rglob("scene_state_manager.py"):
            ssm = cand
            break
    if ssm.exists():
        src = ssm.read_text(encoding="utf-8", errors="replace")
        for i, line in enumerate(src.split("\n"), 1):
            if any(kw in line.lower() for kw in ["def load_location", "def switch_location", "boundary", "neighbor_chunk",
                                                   "location_transition", "scene_change"]):
                print(f"  L{i}: {line.rstrip()}")


# ============================================================================
# STEP 3: Continuous world navigation — search for existing mechanisms
# ============================================================================
def step3_continuous_navigation() -> None:
    _print_section("STEP 3: Непрерывная мировая навигация — поиск существующих механизмов")

    mechanisms = {
        "NavMesh / walkable polygons": ["navmesh", "nav_mesh", "NavMesh", "walkable_poly", "walk_poly",
                                          "polygon_nav", "mesh_navigation"],
        "Geometric passability check": ["passable", "is_walkable", "can_walk", "is_passable",
                                          "geometric_pass", "geometry_pass"],
        "Spatial index (grid/quadtree)": ["spatial_index", "quadtree", "QuadTree", "spatial_grid",
                                            "grid_index", "SpatialHash"],
        "Obstacle avoidance": ["obstacle_avoid", "avoid_obstacle", "steering", "boid",
                                "collision_avoidance"],
        "Multi-location navigation": ["multi_location", "cross_location", "inter_location",
                                       "world_path", "global_path"],
        "Hierarchical navigation": ["hierarchical", "hierarchy", "high_level_graph",
                                     "abstract_graph", "HAN", "HPA"],
        "Dynamic passability": ["dynamic_pass", "dynamic_door", "locked_door",
                                  "conditional_pass"],
        "Different creature sizes": ["creature_size", "actor_size", "radius_nav",
                                       "size_aware_nav"],
    }

    print("\nПоиск по всем backend/ .py файлам:")
    for category, keywords in mechanisms.items():
        found = _grep_in_dir(_BACKEND, keywords, file_exts=(".py",))
        # Filter out test files for clarity
        non_test = [(p, ln, l) for p, ln, l in found if "test" not in str(p).lower()]
        print(f"\n  {category}: {len(found)} total ({len(non_test)} non-test)")
        for path, ln, line in non_test[:5]:
            rel = path.relative_to(_BACKEND) if path.is_relative_to(_BACKEND) else path
            print(f"    {rel} L{ln}: {line}")
        if not found:
            print(f"    [NONE FOUND]")

    # Specifically search for world graph / global navigation
    print("\n--- Поиск 'world graph' / 'global navigation' / 'world map' ---")
    world_nav_keywords = ["world_graph", "global_navigation", "world_map_nav", "world_pathfinding",
                          "GlobalGraph", "WorldGraph", "world_node", "global_node"]
    found = _grep_in_dir(_BACKEND, world_nav_keywords, file_exts=(".py",))
    if found:
        for path, ln, line in found[:10]:
            rel = path.relative_to(_BACKEND) if path.is_relative_to(_BACKEND) else path
            print(f"  {rel} L{ln}: {line}")
    else:
        print("[NO world graph / global navigation found]")


# ============================================================================
# STEP 4: Architectural variants comparison
# ============================================================================
def step4_architectural_variants() -> None:
    _print_section("STEP 4: Архитектурные варианты (A/B/C) — comparison")

    print("""
=============================================================================
VARIANT A: Сохранение графов локаций с улучшенным механизмом стыковки
=============================================================================

Описание:
  - Каждая локация остаётся изолированным графом (как сейчас)
  - GraphCompiler продолжает создавать boundary nodes из adjacency
  - УЛУЧШЕНИЕ: boundary nodes используют АВТОРСКИЕ координаты (если exit_X
    определён в nodes dict) — это уже частично работает (probe v5 Step A)
  - УЛУЧШЕНИЕ: SpatialValidator проверяет достижимость boundary node через
    существующие двери, а не только геометрию

Объём изменений:
  - Минимальный: ~50 строк в graph_compiler.py
  - Карта: добавить авторские exit_X nodes (как вариант C из предыдущего diff)

Совместимость с JSON:
  - Высокая: формат сохраняется, добавляются опциональные поля

Влияние на Map Editor:
  - Минимальное: добавляется UI для размещения exit-узлов

Влияние на NPC movement и FLEE:
  - FLEE работает, если exit_X имеет реальные координаты
  - A* находит путь через дверь

Стоимость пересчёта навигации:
  - Низкая: per-location compile, как сейчас

Масштабирование:
  - 100+ локаций: каждый граф изолирован, переходы через boundary nodes
  - Риск: при большом числе boundary nodes возможны фантомные рёбра

Риск нескольких источников истины:
  - НИЗКИЙ: каждый граф — единственный источник для своей локации
  - boundary_map — единственный источник переходов

=============================================================================
VARIANT B: Единая мировая геометрия и единый навигационный граф
=============================================================================

Описание:
  - ВСЕ локации объединяются в один глобальный граф
  - Координаты — мировые (без origin offset)
  - NavMesh или единый граф проходимости
  - Boundary nodes исчезают (не нужны)
  - adjacency исчезает (геометрия сама определяет соседство)

Объём изменений:
  - ОГРОМНЫЙ: переписать GraphCompiler, SpatialService, MovementEngine
  - Все JSON карт нужно конвертировать (убрать origin, перевести в world coords)
  - Map Editor: переписать для работы с единой геометрией

Совместимость с JSON:
  - НИЗКАЯ: требуется миграция всех карт

Влияние на Map Editor:
  - Полная переработка UI для глобальной карты

Влияние на NPC movement и FLEE:
  - FLEE работает «из коробки» — выбирается самый дальний узел в мире
  - A* ищет путь через всю мировую геометрию

Стоимость пересчёта навигации:
  - ВЫСОКАЯ: при любом изменении карты нужно пересчитывать весь мир
  - Возможно incremental update, но сложно

Масштабирование:
  - 100+ локаций: один гигантский граф, возможны проблемы с памятью/производительностью
  - A* через весь мир может быть медленным

Риск нескольких источников истины:
  - НИЗКИЙ: один граф = один источник
  - Но риск неконсистентности при частичных обновлениях

=============================================================================
VARIANT C: Мировая система координат + локальная навигация + глобальная иерархия
=============================================================================

Описание:
  - Каждая локация имеет локальный навигационный граф (как сейчас)
  - Но координаты — мировые (через origin, как сейчас)
  - Добавляется ГЛОБАЛЬНЫЙ иерархический граф (HPA*)
  - Глобальный граф содержит supernodes (boundary nodes с реальными координатами)
  - Межлокационные рёбра: supernode_A → supernode_B (если они геометрически соседние)
  - A* работает в два уровня:
    1. Найти путь в локальном графе до boundary node
    2. Найти путь в глобальном графе между boundary nodes
    3. Загрузить целевую локацию, продолжить локальный pathfinding

Объём изменений:
  - СРЕДНИЙ: добавить GlobalGraphBuilder, GlobalPathfinder
  - GraphCompiler: гарантировать, что boundary nodes имеют мировые coords
  - SpatialService: добавить get_global_path(start_zone, start_node, end_zone, end_node)
  - MovementEngine: использовать глобальный path для межлокационных переходов

Совместимость с JSON:
  - ВЫСОКАЯ: формат сохраняется, добавляется опциональный world_graph.json
  - existing maps продолжают работать

Влияние на Map Editor:
  - Минимальное: добавить UI для размещения exit-узлов (как в варианте A)
  - Опционально: визуализация глобального графа

Влияние на NPC movement и FLEE:
  - FLEE: выбирает узел в текущей локации (как сейчас)
  - Для FLEE в другую локацию: FLEE target = ближайший boundary node
  - A* использует глобальный граф для межлокационных путей

Стоимость пересчёта навигации:
  - СРЕДНЯЯ: локальные графы пересчитываются при изменении карты
  - Глобальный граф пересчитывается при изменении boundary nodes (редко)

Масштабирование:
  - 100+ локаций: иерархия хорошо масштабируется
  - Глобальный граф содержит только boundary nodes (десятки, не тысячи)

Риск нескольких источников истины:
  - СРЕДНИЙ: локальные графы + глобальный граф
  - Но они согласованы: global graph строится из локальных boundary nodes

=============================================================================
СРАВНЕНИЕ
=============================================================================

| Критерий                          | A         | B         | C         |
|-----------------------------------|-----------|-----------|-----------|
| Объём изменений                   | Минимум   | Огромный  | Средний   |
| Совместимость с JSON              | Высокая   | Низкая    | Высокая   |
| Влияние на Map Editor             | Минимум   | Полный    | Минимум   |
| FLEE работает                     | Да (с diff)| Да       | Да        |
| Стоимость пересчёта               | Низкая    | Высокая   | Средняя   |
| Масштабирование                   | Хорошее   | Плохое    | Отличное  |
| Риск multi-source-of-truth        | Низкий    | Низкий    | Средний   |
| Поддержка текущих сохранений      | Да        | Нет       | Да        |
| Сложность миграции                | Низкая    | Высокая   | Средняя   |
| Подходит для длинных NPC маршрутов| Нет       | Да        | Да        |

РЕКОМЕНДАЦИЯ: Вариант C (мировая система + иерархия)

Обоснование:
  1. Сохраняет текущий формат JSON (низкий риск)
  2. Поддерживает текущие сохранения (без миграции)
  3. Решает проблему FLEE (boundary nodes с реальными coords)
  4. Масштабируется на 100+ локаций
  5. Позволяет NPC идти через несколько локаций (целевой сценарий Master)
  6. Иерархический pathfinding — стандартное решение для больших миров

Минусы варианта C:
  - Два графа (локальный + глобальный) нужно синхронизировать
  - Добавляется новая подсистема (GlobalGraphBuilder)
  - Возможно избыточно для текущих 3 локаций
""")


# ============================================================================
# STEP 5: Real world geometry of Tavern, Market Square, City Gate
# ============================================================================
def step5_real_world_geometry() -> None:
    _print_section("STEP 5: Реальная мировая геометрия Tavern, Market Square, City Gate")

    locations = [
        ("tavern", TAVERN_FILE),
        ("market_square", MARKET_SQUARE_FILE),
        ("city_gate", CITY_GATE_FILE),
    ]

    world_data: Dict[str, dict] = {}
    for name, path in locations:
        print(f"\n--- {name} ({path.name}) ---")
        data = _load_map(path)
        if data is None:
            print(f"  [file not found or invalid]")
            continue
        world_data[name] = data

        size = data.get("size", {})
        origin = data.get("origin", {})
        adjacency = data.get("adjacency", {})
        W = float(size.get("w", 0))
        H = float(size.get("h", 0))
        OX = float(origin.get("x", 0))
        OY = float(origin.get("y", 0))

        # World bounding box (assuming origin is bottom-left corner)
        # or center? Need to check
        print(f"  size: W={W}m, H={H}m")
        print(f"  origin (world coords of location's local 0,0): ({OX}, {OY})")
        print(f"  adjacency: {adjacency}")
        print(f"  global_coords: {data.get('global_coords')}")

        # World extent
        # If origin is the local (0,0) mapped to world (OX, OY),
        # then world extent = [(OX, OY), (OX+W, OY+H)]
        # But need to check direction: is +Y up or down?
        # In probe v2 we saw: tavern origin=(25.033, 5.018), size=20x15
        # exit_east phantom was at (44.033, 12.518) = (25.033+19, 5.018+7.5)
        # That's the east boundary (x=max-1, y=mid)
        # So +X is east, +Y is up (north)
        world_min_x = OX
        world_max_x = OX + W
        world_min_y = OY
        world_max_y = OY + H
        print(f"  world extent (assumed): x=[{world_min_x}, {world_max_x}], y=[{world_min_y}, {world_max_y}]")
        print(f"  world area: {W * H} m²")

        # Show all node world coords
        nodes = data.get("nodes", {})
        print(f"\n  Nodes (local → world coords):")
        for nname, nd in nodes.items():
            if not isinstance(nd, dict):
                continue
            lx = nd.get("x")
            ly = nd.get("y")
            if lx is None or ly is None:
                continue
            try:
                flx, fly = float(lx), float(ly)
                wx = OX + flx
                wy = OY + fly
                role = nd.get("role", "?")
                print(f"    {nname:<20} local=({flx:.2f}, {fly:.2f}) → world=({wx:.2f}, {wy:.2f})  role={role}")
            except (TypeError, ValueError):
                continue

        # Show all walls (local coords)
        walls = data.get("walls", [])
        if walls:
            print(f"\n  Walls (local coords):")
            for w in walls:
                if isinstance(w, dict):
                    print(f"    {w.get('id')}: ({w.get('x1')}, {w.get('y1')}) → ({w.get('x2')}, {w.get('y2')})")

    # Now check if locations overlap or touch in world space
    _print_section("STEP 5b: Проверка соприкосновения локаций в мировом пространстве")
    if len(world_data) >= 2:
        print("\n--- Bounding boxes в мировых координатах ---")
        bboxes: Dict[str, Tuple[float, float, float, float]] = {}
        for name, data in world_data.items():
            size = data.get("size", {})
            origin = data.get("origin", {})
            W = float(size.get("w", 0))
            H = float(size.get("h", 0))
            OX = float(origin.get("x", 0))
            OY = float(origin.get("y", 0))
            bbox = (OX, OY, OX + W, OY + H)
            bboxes[name] = bbox
            print(f"  {name}: x=[{bbox[0]:.2f}, {bbox[2]:.2f}], y=[{bbox[1]:.2f}, {bbox[3]:.2f}]")

        # Check pairwise overlap/touch
        print("\n--- Попарное соприкосновение ---")
        names = list(bboxes.keys())
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                n1, n2 = names[i], names[j]
                b1 = bboxes[n1]
                b2 = bboxes[n2]
                # Check if bboxes overlap or touch (within tolerance 0.1)
                tol = 0.1
                x_overlap = not (b1[2] < b2[0] - tol or b2[2] < b1[0] - tol)
                y_overlap = not (b1[3] < b2[1] - tol or b2[3] < b1[1] - tol)
                # Touch: edges meet (e.g., b1.max_x ≈ b2.min_x with y overlap)
                x_touch = (abs(b1[2] - b2[0]) < tol or abs(b2[2] - b1[0]) < tol) and y_overlap
                y_touch = (abs(b1[3] - b2[1]) < tol or abs(b2[3] - b1[1]) < tol) and x_overlap
                if x_overlap and y_overlap:
                    print(f"  {n1} ↔ {n2}: OVERLAP (вложенные или пересекающиеся)")
                elif x_touch or y_touch:
                    direction = "east-west" if x_touch else "north-south"
                    print(f"  {n1} ↔ {n2}: TOUCH ({direction})")
                else:
                    # Compute gap
                    gap_x = max(0, max(b1[0], b2[0]) - min(b1[2], b2[2]))
                    gap_y = max(0, max(b1[1], b2[1]) - min(b1[3], b2[3]))
                    print(f"  {n1} ↔ {n2}: GAP (gap_x={gap_x:.2f}, gap_y={gap_y:.2f})")

        # Visualize world map
        print("\n--- Мировая карта (ASCII, scale 2m/char) ---")
        all_x = [v for b in bboxes.values() for v in (b[0], b[2])]
        all_y = [v for b in bboxes.values() for v in (b[1], b[3])]
        if all_x and all_y:
            min_x, max_x = min(all_x), max(all_x)
            min_y, max_y = min(all_y), max(all_y)
            scale = 2.0
            grid_w = int((max_x - min_x) / scale) + 2
            grid_h = int((max_y - min_y) / scale) + 2
            grid = [["." for _ in range(grid_w)] for _ in range(grid_h)]
            chars = ["T", "M", "C", "G", "O", "S"]
            for idx, (name, bbox) in enumerate(bboxes.items()):
                char = chars[idx % len(chars)]
                # Fill rectangle
                x_start = int((bbox[0] - min_x) / scale)
                x_end = int((bbox[2] - min_x) / scale)
                y_start = int((bbox[1] - min_y) / scale)
                y_end = int((bbox[3] - min_y) / scale)
                for gx in range(x_start, x_end + 1):
                    for gy in range(y_start, y_end + 1):
                        if 0 <= gx < grid_w and 0 <= gy < grid_h:
                            grid[gy][gx] = char
                print(f"  '{char}' = {name}")

            print()
            print("    " + "".join([str(int((min_x + i * scale)) % 10) for i in range(grid_w)]))
            print("    " + "-" * grid_w)
            for gy in range(grid_h - 1, -1, -1):
                y_label = min_y + gy * scale
                print(f"{y_label:5.0f}|" + "".join(grid[gy]))
            print("    " + "-" * grid_w)


# ============================================================================
# STEP 6: Target NPC scenario
# ============================================================================
def step6_target_scenario() -> None:
    _print_section("STEP 6: Целевой сценарий NPC — main_hall → door_0 → street → city_gate")

    print("""
Целевой маршрут NPC (по замыслу Master):
  1. Начать в main_hall таверны (локальные coords ~6.5, 5.5)
  2. Выйти через door_0 (Главный вход, на стене wall_2, y=13.0)
     - door_0 в мире: world coords ~ (33.22, 18.02) — север таверны
  3. Пройти по улице вдоль южной стены таверны (?! противоречие: door_0
     на СЕВЕРНОЙ стене, не южной)
  4. Продолжить движение вдоль восточной стены в направлении городских ворот
  5. Не проходить сквозь стены
  6. Не использовать несуществующие двери
  7. Не зависеть от искусственных boundary nodes

ЗАМЕЧАНИЕ: door_0 находится на СЕВЕРНОЙ стене таверны (wall_2, y=13.0),
а не на южной. Возможно, Master имел в виду «северной стены» или планировал
другой выход.

Архитектурная проверка:
  - Tavern world extent: x=[25.03, 45.03], y=[5.02, 20.02]
  - door_0 at world (~33.22, 18.02) — на северной стене
  - Если NPC выходит через door_0, он оказывается СЕВЕРНЕЕ таверны (y > 20.02)
  - Если City Gate находится к ВОСТОКУ от таверны, NPC должен идти на восток
  - Но для этого нужна уличная геометрия МЕЖДУ локациями
""")

    # Check if there's any "street" or outdoor location
    print("\n--- Поиск outdoor / street / world locations ---")
    if LOCATIONS_DIR.exists():
        for f in sorted(LOCATIONS_DIR.glob("*.json")):
            data = _load_map(f)
            if data is None:
                continue
            is_outdoor = data.get("is_outdoor", False)
            name = data.get("location_id", f.stem)
            if is_outdoor:
                print(f"  OUTDOOR: {f.name} (location_id={name})")
            else:
                print(f"  indoor:  {f.name} (location_id={name})")

    # Check for "world" / "outdoor" / "street" location files elsewhere
    print("\n--- Поиск world/outdoor/street .json files в проекте ---")
    world_keywords = ["street", "outdoor", "world", "road", "plaza", "yard"]
    for f in PROJECT_ROOT.rglob("*.json"):
        if any(part in {".venv", "node_modules", ".git", "__pycache__"} for part in f.parts):
            continue
        name_lower = f.name.lower()
        if any(kw in name_lower for kw in world_keywords):
            try:
                rel = f.relative_to(PROJECT_ROOT)
                print(f"  {rel}")
            except Exception:
                print(f"  {f}")


# ============================================================================
# STEP 7: Final report
# ============================================================================
def step7_final_report() -> None:
    _print_section("STEP 7: ИТОГОВЫЙ ОТЧЁТ")

    print("""
=============================================================================
1. ТЕКУЩАЯ АРХИТЕКТУРА
=============================================================================

Файлы:
  - saves/Open_road/locations/tavern.json
  - saves/Open_road/locations/market_square.json
  - saves/Open_road/locations/city_gate.json
  - backend/app/services/spatial/graph_compiler.py — компиляция графов
  - backend/app/services/spatial/spatial_service.py — хранение graph по zone_id
  - backend/app/services/spatial/spatial_target_resolver.py — FLEE target
  - backend/app/services/spatial/movement_engine.py — A*, traversal

Координаты:
  - Каждая локация имеет локальные координаты (relative to location)
  - origin (world coords of local 0,0) преобразует local → world
  - global_coords: true означает, что node coords — локальные
  - World coords = origin + local coords

Boundary nodes:
  - Создаются GraphCompiler._create_boundary_nodes из adjacency dict
  - boundary_id = f"{location_id}:exit_{direction}"
  - Если в nodes dict есть узел с ID "{exit_direction}" — он НЕ используется
    (поиск идёт по namespaced ID "tavern:exit_south", а в JSON узлы называются
     просто "exit_south" — без префикса локации)
  - Если нет — создаётся phantom с мировыми координатами

=============================================================================
2. ФАКТИЧЕСКАЯ СХЕМА ПРЕОБРАЗОВАНИЙ КООРДИНАТ
=============================================================================

Location JSON (local coords + origin + size)
  ↓
GraphCompiler.compile_graph():
  - Читает nodes: {"exit_east": {"x": 8.22, "y": 12.45}, ...}
  - Создаёт graph["tavern:exit_east"] = NodeRef(x=8.22, y=12.45, ...)
    (но! добавляет location_id префикс к node_id)
  - _create_boundary_nodes:
    boundary_id = "tavern:exit_east"
    _existing_node = graph.get("tavern:exit_east")  ← НАХОДИТ (тот, что из nodes)
    Использует его координаты
    НО! probe v5 показало: "Authored in JSON: False" — то есть GraphCompiler
    не находит авторский узел. Почему?
    Возможно: authored node имеет ID "exit_east" (без префикса), а boundary
    ищет "tavern:exit_east" (с префиксом). GraphCompiler, загружая nodes,
    добавляет префикс, но boundary ищет ПЕРЕД этим добавлением?

  ИТОГ: probe v5 показало, что для exit_east:
    - authored = False (GraphCompiler не нашёл существующий)
    - coords = (44.03, 12.52) = (origin.x + w - 1, origin.y + h/2)
    - Это МИРОВЫЕ координаты east-границы

SpatialValidator:
  - Проверяет рёбра на пересечение со стенами
  - exit_east (44.03, 12.52) ↔ kitchen_bed_2 (18.44, 6.27)
  - Отрезок пересекает wall_5 → удаляется

SpatialTargetResolver.get_furthest:
  - candidates = все узлы зоны
  - distance = world_distance(threat_xy, node.xy)
  - Возвращает exit_east (дальше всего от угрозы)

MovementEngine._resolve_macro_relocation:
  - A* pathfinding
  - connections["tavern:exit_east"] = [] (пусто, рёбра удалены)
  - failure=M005 "no path"

=============================================================================
3. ПРИЧИНА ТЕКУЩИХ ОШИБОК BOUNDARY NODES
=============================================================================

Корневая причина:
  1. GraphCompiler создаёт boundary nodes с МИРОВЫМИ координатами
     (через origin offset), даже если авторский exit_X есть в nodes dict
  2. Авторский exit_east в nodes dict имеет ID "exit_east" (без префикса)
     GraphCompiler при загрузке добавляет префикс "tavern:" → "tavern:exit_east"
  3. _create_boundary_nodes ищет "tavern:exit_east" в graph
     → должен найти (после добавления префикса)
     → но probe v5 показало: не находит (Authored = False)
  4. Возможные причины:
     a) _create_boundary_nodes вызывается ДО добавления префикса к nodes
     b) Узел с ID "exit_east" в JSON имеет role="boundary", и при загрузке
        он уже используется как boundary (но с другими coords?)
     c) Logic: _existing_node = graph.get(boundary_id) находит авторский,
        но потом его coords перезаписываются мировыми — нужно проверить код
  5. SpatialValidator удаляет рёбра к phantom boundary (мир coords ≠ локальные)
  6. A* не находит путь → FLEE BLOCKED

=============================================================================
4. ТРИ АРХИТЕКТУРНЫХ ВАРИАНТА
=============================================================================

См. STEP 4 выше для детального сравнения.

Краткое резюме:
  - Variant A: минимальные изменения, но не решает межлокационные маршруты
  - Variant B: полная переработка, дорого, несовместимо с текущими сохранениями
  - Variant C: иерархическая навигация, средние изменения, масштабируемое

=============================================================================
5. РЕКОМЕНДАЦИЯ
=============================================================================

Вариант C — иерархическая навигация с мировой системой координат.

Обоснование:
  1. Сохраняет текущий формат JSON (низкий риск для сохранений)
  2. Решает проблему FLEE (boundary nodes с реальными координатами)
  3. Поддерживает целевой сценарий NPC через несколько локаций
  4. Масштабируется на 100+ локаций
  5. Иерархический pathfinding — стандартное решение для больших миров

Этапы внедрения (если Master одобряет):
  Phase 1: Исправить GraphCompiler — использовать авторские exit_X coords
            (probe v5 Experiment A доказал, что код это поддерживает, но
             что-то мешает — нужно изучить порядок инициализации)
  Phase 2: Добавить авторские exit_south в tavern.json (вариант C из предыдущего diff)
  Phase 3: Создать GlobalGraphBuilder — собирает boundary nodes из всех локаций
  Phase 4: Создать GlobalPathfinder — A* по глобальному графу
  Phase 5: MovementEngine использует глобальный path для межлокационных переходов

=============================================================================
6. ЗАТРАГИВАЕМЫЕ ФАЙЛЫ И ПОДСИСТЕМЫ
=============================================================================

Phase 1 (минимальный fix):
  - saves/Open_road/locations/tavern.json — добавить exit_south в nodes dict
  - saves/Open_road/locations/market_square.json — добавить exit_north
  - saves/Open_road/locations/city_gate.json — добавить exit_west

Phase 2-5 (вариант C):
  - backend/app/services/spatial/graph_compiler.py — гарантировать world coords
  - backend/app/services/spatial/spatial_service.py — добавить global graph
  - backend/app/services/spatial/global_graph_builder.py (NEW)
  - backend/app/services/spatial/global_pathfinder.py (NEW)
  - backend/app/services/spatial/movement_engine.py — использовать global path
  - backend/app/services/spatial/spatial_target_resolver.py — FLEE target
  - backend/app/services/spatial/spatial_registry.py — world bounds, zone registry
  - frontend/map_editor/editor_core.py — UI для размещения exit-узлов
  - frontend/map_editor/data_manager.py — управление global graph cache

=============================================================================
7. ПЛАН ПОСТЕПЕННОЙ МИГРАЦИИ
=============================================================================

Этап 1 (минимальный, 1-2 дня):
  - Добавить авторские exit_X nodes в tavern/market_square/city_gate JSON
  - GraphCompiler будет использовать их координаты (probe v5 доказал поддержку)
  - SpatialValidator пропустит рёбра (если они проходят через двери)
  - FLEE заработает (exit_south будет достижим через door_2)

Этап 2 (1 неделя):
  - Добавить GlobalGraphBuilder, который собирает boundary_map из всех локаций
  - Создать supernodes graph: boundary_A ↔ boundary_B (если они геометрически соседние)
  - MovementEngine: при достижении boundary node, проверить global graph

Этап 3 (2-3 недели):
  - GlobalPathfinder: A* по supernodes graph
  - NPC может идти через несколько локаций
  - Целевой сценарий работает

Этап 4 (опционально, 1 месяц):
  - NavMesh для каждой локации (точная навигация внутри, не только по nodes)
  - Поддержка разных размеров существ
  - Динамические препятствия

=============================================================================
8. ТЕСТОВАЯ СТРАТЕГИЯ
=============================================================================

Геометрия:
  - Test: каждая локация имеет корректные origin и size
  - Test: world bounding boxes локаций не пересекаются (или касаются в door)
  - Test: двери находятся на стенах (geometric validation)

Двери:
  - Test: door_id ссылается на существующую стену
  - Test: door.coords лежат на wall segment
  - Test: door разрезает стену → SpatialValidator пропускает рёбра через door

Маршруты:
  - Test: A* находит путь внутри локации (fireplace → exit_south через door_2)
  - Test: A* не находит путь через сплошные стены
  - Test: boundary node достижим из любой точки локации

Смена областей:
  - Test: NPC достигает boundary node → MovementEngine инициирует transition
  - Test: новая локация загружается, NPC появляется в entry_node
  - Test: NPC продолжает движение в новой локации

FLEE:
  - Test: FLEE target = реальный boundary node (с корректными coords)
  - Test: A* находит путь к FLEE target
  - Test: NPC физически движется к exit

Регрессии:
  - Test: существующие маршруты (schedule: working → kitchen) работают
  - Test: SEEK_ALLY работает (NPC движется к другому NPC)
  - Test: TALK/APPROACH работают
  - Test: тесты из test_boundary_nodes.py проходят

НИКАКИХ production-изменений в рамках исследования.
""")


# ============================================================================
# Main
# ============================================================================
def main() -> int:
    print("=" * 78)
    print("R2-WORLD-NAV-ARCHAEOLOGY — архитектурное исследование")
    print(f"PROJECT_ROOT: {PROJECT_ROOT}")
    print(f"LOCATIONS_DIR: {LOCATIONS_DIR}")
    print(f"OUT_FILE: {OUT_FILE}")
    print("=" * 78)

    try:
        step1_coordinate_contract()
    except Exception as e:
        print(f"[step1 error: {e}]")
        traceback.print_exc()

    try:
        step2_transition_system()
    except Exception as e:
        print(f"[step2 error: {e}]")
        traceback.print_exc()

    try:
        step3_continuous_navigation()
    except Exception as e:
        print(f"[step3 error: {e}]")
        traceback.print_exc()

    try:
        step4_architectural_variants()
    except Exception as e:
        print(f"[step4 error: {e}]")
        traceback.print_exc()

    try:
        step5_real_world_geometry()
    except Exception as e:
        print(f"[step5 error: {e}]")
        traceback.print_exc()

    try:
        step6_target_scenario()
    except Exception as e:
        print(f"[step6 error: {e}]")
        traceback.print_exc()

    try:
        step7_final_report()
    except Exception as e:
        print(f"[step7 error: {e}]")
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
