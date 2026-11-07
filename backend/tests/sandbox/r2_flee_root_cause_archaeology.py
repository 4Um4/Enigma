# backend/tests/sandbox/r2_flee_root_cause_archaeology.py
"""
R2-FLEE-ROOT-CAUSE archaeology probe — find the EXACT root cause.

Цель: установить первопричину FLEE BLOCKED, не нарушая авторскую геометрию.

Гипотеза для проверки:
  В graph_compiler.py _create_boundary_nodes ищет узел по ключу
  "tavern:exit_east" (с префиксом location_id), но в graph узлы хранятся
  под ключами БЕЗ префикса ("exit_east", "entrance", "fireplace").
  Поэтому _existing_node = None, и создаётся phantom с мировыми координатами.

Также проверить:
  1. Как SpatialValidator сравнивает координаты стен (локальные) с координатами
     boundary node (мировые) — это смешение систем координат.
  2. Как Master интерпретирует "южную стену" (Y up vs Y down).
  3. Где именно происходит transition local→world coords.

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

OUT_FILE_DIR = Path("/home/z/my-project/download")
if not OUT_FILE_DIR.exists() or not OUT_FILE_DIR.is_dir():
    OUT_FILE_DIR = _BACKEND / "tests" / "sandbox"
    try:
        OUT_FILE_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        OUT_FILE_DIR = Path(os.getcwd())
OUT_FILE = OUT_FILE_DIR / "r2_flee_root_cause.txt"


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


# ============================================================================
# STEP 1: Read graph_compiler.py — node loading section
# ============================================================================
def step1_node_loading() -> None:
    _print_section("STEP 1: graph_compiler.py — как загружаются nodes в graph")
    gc = _BACKEND / "app/services/spatial/graph_compiler.py"
    if not gc.exists():
        print(f"[file not found: {gc}]")
        return
    src = gc.read_text(encoding="utf-8", errors="replace")
    lines = src.split("\n")

    # Find where nodes are loaded — search for "for node_name" or "for name, nd" or similar
    print("\n--- Поиск циклов загрузки nodes ---")
    keywords = ["for node_name", "for name, node", "for n_name", "for n_id",
                "graph[", "node_id=", "location_id +", "f\"{location_id}",
                "f'{location_id}", "prefix", "namespaced"]
    for i, line in enumerate(lines, 1):
        for kw in keywords:
            if kw in line:
                print(f"  L{i}: {line.rstrip()}")
                break

    # Show compile_graph function — focus on node loading
    print("\n--- compile_graph function — find node loading section ---")
    func_start = None
    for i, line in enumerate(lines):
        if line.startswith("def compile_graph") or (line.startswith("    def compile_graph") is False and line.startswith("def compile_graph")):
            func_start = i
            break
    if func_start is None:
        # Try to find any def compile_graph
        for i, line in enumerate(lines):
            if "def compile_graph" in line:
                func_start = i
                break
    if func_start is not None:
        # Show next 100 lines
        print(f"\nFound compile_graph at L{func_start + 1}")
        for j in range(func_start, min(func_start + 150, len(lines))):
            print(f"L{j+1:4d}: {lines[j]}")


# ============================================================================
# STEP 2: _create_boundary_nodes — exact search key
# ============================================================================
def step2_boundary_search_key() -> None:
    _print_section("STEP 2: _create_boundary_nodes — какой ключ ищется в graph")
    gc = _BACKEND / "app/services/spatial/graph_compiler.py"
    if not gc.exists():
        return
    src = gc.read_text(encoding="utf-8", errors="replace")

    # Show lines around _create_boundary_nodes (focus on search key)
    print("\n--- L930-960: где _existing_node = graph.get(boundary_id) ---")
    for line in _read_lines(gc, 930, 960):
        print(line)

    print(f"""
АНАЛИЗ:
  boundary_id = f"{{location_id}}:exit_{{direction}}"  ← с префиксом "tavern:exit_east"
  _existing_node = graph.get(boundary_id)             ← ищет "tavern:exit_east" в graph

  Если graph хранит узлы под ключами БЕЗ префикса (просто "exit_east"),
  то graph.get("tavern:exit_east") вернёт None → создаётся phantom.

  Если graph хранит узлы под ключами С префиксом ("tavern:exit_east"),
  то graph.get найдёт авторский узел и использует его координаты.

  Probe Step 3 (runtime) подтвердит, какие именно ключи в graph.
""")


# ============================================================================
# STEP 3: Runtime — compile tavern.json and dump graph keys
# ============================================================================
def step3_runtime_graph_keys() -> None:
    _print_section("STEP 3: RUNTIME — dump graph keys after compile_graph")
    try:
        from app.services.spatial.graph_compiler import compile_graph
    except Exception as e:
        print(f"[import error: {e}]")
        return

    if not TAVERN_FILE.exists():
        print(f"[file not found: {TAVERN_FILE}]")
        return
    data = json.loads(TAVERN_FILE.read_text(encoding="utf-8", errors="replace"))

    # Clear log capture
    _log_capture.truncate(0)
    _log_capture.seek(0)

    try:
        result = compile_graph(data, location_id="tavern")
    except Exception as e:
        print(f"[compile error: {e}]")
        traceback.print_exc()
        return

    if result is None or not isinstance(result, tuple):
        print(f"[unexpected result: {result}]")
        return

    graph = result[0] if len(result) > 0 else {}
    connections = result[1] if len(result) > 1 else {}

    print(f"\n>>> Graph has {len(graph)} entries")
    print(f">>> All keys in graph (sorted):")
    for key in sorted(graph.keys()):
        nref = graph[key]
        x = getattr(nref, "x", "?")
        y = getattr(nref, "y", "?")
        role = getattr(nref, "role", "?")
        is_boundary = "BOUNDARY" in str(role)
        marker = " ← BOUNDARY (synthetic)" if is_boundary else ""
        print(f"  '{key}'  ({x}, {y})  role={role}{marker}")

    print(f"\n>>> Специфичная проверка: есть ли 'exit_east' (БЕЗ префикса)?")
    if "exit_east" in graph:
        nref = graph["exit_east"]
        print(f"  ✓ НАЙДЕН: 'exit_east' в graph")
        print(f"    x={getattr(nref, 'x', '?')}, y={getattr(nref, 'y', '?')}")
        print(f"    role={getattr(nref, 'role', '?')}")
    else:
        print(f"  ✗ 'exit_east' НЕ в graph (БЕЗ префикса)")

    print(f"\n>>> Специфичная проверка: есть ли 'tavern:exit_east' (С префиксом)?")
    if "tavern:exit_east" in graph:
        nref = graph["tavern:exit_east"]
        print(f"  ✓ НАЙДЕН: 'tavern:exit_east' в graph")
        print(f"    x={getattr(nref, 'x', '?')}, y={getattr(nref, 'y', '?')}")
        print(f"    role={getattr(nref, 'role', '?')}")
    else:
        print(f"  ✗ 'tavern:exit_east' НЕ в graph")

    print(f"\n>>> Сравнение координат:")
    print(f"  authored exit_east в JSON: x=8.22, y=12.45 (ЛОКАЛЬНЫЕ)")
    print(f"  phantom tavern:exit_east:   x=44.03, y=12.52 (МИРОВЫЕ = origin + offset)")
    print(f"  origin: x=25.033, y=5.018")
    print(f"  offset for east: (origin.x + w - 1, origin.y + h/2) = (25.033+19, 5.018+7.5) = (44.033, 12.518)")

    # Also check SpatialValidator logs
    print(f"\n>>> SpatialValidator logs (последние 2000 символов):")
    logs = _log_capture.getvalue()
    if logs:
        # Filter for SPATIAL_VALIDATION messages
        for line in logs.split("\n"):
            if "SPATIAL_VALIDATION" in line or "boundary" in line.lower():
                print(f"  {line}")
    else:
        print(f"  (no logs)")


# ============================================================================
# STEP 4: SpatialValidator — какие координаты используются
# ============================================================================
def step4_spatial_validator_coords() -> None:
    _print_section("STEP 4: SpatialValidator — какие координаты сравниваются")
    gc = _BACKEND / "app/services/spatial/graph_compiler.py"
    if not gc.exists():
        return

    print("""
Вопрос: SpatialValidator сравнивает координаты стен (из JSON, локальные)
        с координатами узлов (могут быть локальные ИЛИ мировые).

        Если boundary node имеет МИРОВЫЕ координаты (44.03, 12.52),
        а стены хранятся в ЛОКАЛЬНЫХ координатах (wall_5: x=19.5, y∈[0.5, 8.0]),
        то отрезок exit_east(44.03, 12.52) → kitchen_bed_2(18.44, 6.27)
        ПЕРЕСЕКАЕТ wall_5 в локальном пространстве.

        Это смешение систем координат — корневая причина.

        ПРОВЕРКА: SpatialValidator должен либо:
          (a) Конвертировать boundary node в локальные координаты перед валидацией, или
          (b) Конвертировать стены в мировые координаты перед валидацией, или
          (c) GraphCompiler должен хранить boundary node в локальных координатах,
              если авторский exit_X есть.
""")

    # Find _validate_navigation_geometry function
    src = gc.read_text(encoding="utf-8", errors="replace")
    lines = src.split("\n")
    func_start = None
    for i, line in enumerate(lines):
        if "def _validate_navigation_geometry" in line:
            func_start = i
            break
    if func_start is None:
        print("[function _validate_navigation_geometry not found]")
        return
    print(f"\n--- _validate_navigation_geometry (L{func_start + 1} onwards) ---")
    for j in range(func_start, min(func_start + 80, len(lines))):
        print(f"L{j+1:4d}: {lines[j]}")


# ============================================================================
# STEP 5: Y-axis orientation — "south wall" interpretation
# ============================================================================
def step5_y_axis_orientation() -> None:
    _print_section("STEP 5: Y-axis orientation — интерпретация 'южной стены'")

    print("""
Master сказал: 'У Tavern существует только один внешний выход — door_0 на южной стене.'

Из probe r2_tavern_geometry_truth Step 7 (ASCII visualization):
  wall_0: y=0.5 (минимальный Y) — по моей интерпретации ЮЖНАЯ (если Y↑=север)
  wall_2: y=13.0 (максимальный Y) — по моей интерпретации СЕВЕРНАЯ (если Y↑=север)

Но door_0 находится на wall_2 (y=13.0), НЕ на wall_0 (y=0.5).

Если Master говорит, что door_0 на "южной стене", то возможны две интерпретации:

ИНТЕРПРЕТАЦИЯ 1: Y↓ = север (как в screen coordinates, типично для редакторов)
  - wall_2 (y=13) = max Y = ВНИЗУ экрана = ЮГ
  - wall_0 (y=0.5) = min Y = ВВЕРХУ экрана = СЕВЕР
  - door_0 на wall_2 → действительно на "южной стене" ✓
  - exit_east (label "Выход в Город") — exit на восток, физически на wall_2

ИНТЕРПРЕТАЦИЯ 2: Y↑ = север (как в world coordinates)
  - wall_2 (y=13) = max Y = СЕВЕР
  - wall_0 (y=0.5) = min Y = ЮГ
  - door_0 на wall_2 → на "северной стене" ✗ противоречит Master

Как проверить:
  - В map_editor (frontend) — screen coordinates обычно Y↓
  - В game world — зависит от конвенции
  - global_coords: true в JSON означает, что origin используется для world mapping

Если door_0 физически на wall_2 (y=13), и Master называет её "южной стеной",
то Y в editor увеличивается ВНИЗ (screen-like), и "south" = max Y.

Это означает:
  - exit_south должен быть на wall_0 (y=0.5)? НЕТ — это север в editor convention
  - exit_south должен быть на wall_2 (y=13)? ДА — это юг в editor convention
  - НО! exit_south в boundary_map имеет entry_node_hint "market_square:exit_north"
    → означает, что market_square находится к ЮГУ от tavern (в мировом смысле)

Возможно, GraphCompiler использует МИРОВЫЕ координаты для boundary:
  - north boundary = max world Y (верх мира)
  - south boundary = min world Y (низ мира)
  - Но tavern origin (25.033, 5.018) — южная часть мира
  - tavern max world Y = 5.018 + 15 = 20.018 (северная часть)
  - market_square origin (25.033, 20.018) — к СЕВЕРУ от tavern

Если Master говорит "door_0 на южной стене" (wall_2, y=13), но market_square
находится к СЕВЕРУ (world Y > tavern max Y), то:
  - exit_south (по мировым coords) должен вести к market_square?
  - Но exit_south в мировых coords = (origin.x + w/2, origin.y + 1) = (35.03, 6.02)
    это НИЖЕ tavern в мировом смысле (Y=6 < origin Y=5.018 + что-то ещё)

Похоже, есть СМЕШЕНИЕ:
  - exit_south boundary node: мировые coords (35.03, 6.02) — юг мира
  - Но market_square (adjacency.south) — к северу от tavern (world Y=20+)

Вывод: adjacency.south логически ведёт к market_square, но market_square
физически находится к СЕВЕРУ от tavern. Это противоречие в данных.

ИЛИ: exit_east — это просто имя (по направлению в мире), а не направление
физической стены. door_0 (Главный вход) на wall_2 — это вход, через который
NPC попадает в tavern, и одновременно выход в city_gate (на восток мира).

ВОЗМОЖНАЯ АВТОРСКАЯ МОДЕЛЬ:
  - door_0 на wall_2 — Главный вход таверны (выход в город)
  - exit_east — authored узел рядом с door_0, ведёт в city_gate (восток мира)
  - exit_south (если бы был) — вёл бы в market_square
  - Но фактически в tavern нет exit_south → рынок недостижим напрямую
  - Возможно, NPC должен идти через city_gate к market_square
""")

    # Check door_0 in JSON
    if TAVERN_FILE.exists():
        data = json.loads(TAVERN_FILE.read_text(encoding="utf-8", errors="replace"))
        objects = data.get("objects", [])
        print("\n--- doors in tavern.json ---")
        for o in objects:
            if isinstance(o, dict) and o.get("type") == "door":
                print(f"  door_id={o.get('id')}, name={o.get('name')}")
                print(f"    position: {o.get('position')}")
                print(f"    wall_id: {o.get('wall_id')}")
                print(f"    target_file: {o.get('properties', {}).get('target_file')}")
        # Check which wall has door_0
        walls = data.get("walls", [])
        for w in walls:
            if isinstance(w, dict) and w.get("id") == "wall_2":
                print(f"\n  wall_2: x1={w.get('x1')}, y1={w.get('y1')}, x2={w.get('x2')}, y2={w.get('y2')}")
                print(f"  → door_0 at y=13.0 — это wall_2")
        for w in walls:
            if isinstance(w, dict) and w.get("id") == "wall_0":
                print(f"\n  wall_0: x1={w.get('x1')}, y1={w.get('y1')}, x2={w.get('x2')}, y2={w.get('y2')}")
                print(f"  → Это другая стена (без door в JSON)")


# ============================================================================
# STEP 6: Minimal fix proposal
# ============================================================================
def step6_minimal_fix_proposal() -> None:
    _print_section("STEP 6: Минимальный production fix — PROPOSAL")

    print("""
=============================================================================
ГИПОТЕЗА (требует подтверждения Step 3):
=============================================================================

GraphCompiler хранит авторские узлы под ключами БЕЗ префикса ("exit_east"),
но _create_boundary_nodes ищет "tavern:exit_east" (С префиксом).
→ _existing_node = None → создаётся phantom с мировыми координатами.

SpatialValidator сравнивает мировые coords phantom с локальными coords стен.
→ находит пересечение → удаляет ребро.
→ A* не находит путь → FLEE BLOCKED.

=============================================================================
МИНИМАЛЬНЫЙ FIX (одна строка в graph_compiler.py L939):
=============================================================================

Было:
  boundary_id = f"{location_id}:exit_{direction}"   # L936
  _existing_node = graph.get(boundary_id)            # L939 — ищет "tavern:exit_east"

Стало:
  boundary_id = f"{location_id}:exit_{direction}"   # L936 (не меняется)
  short_id = f"exit_{direction}"                     # NEW: "exit_east" (без префикса)
  _existing_node = graph.get(boundary_id) or graph.get(short_id)  # L939 — fallback на short_id

ИЛИ (более чисто):
  # Если в graph узлы хранятся БЕЗ префикса, ищем по short_id:
  short_id = f"exit_{direction}"
  _existing_node = graph.get(short_id) or graph.get(boundary_id)

ЭФФЕКТ:
  - _existing_node находит авторский exit_east (локальные coords)
  - _final_x = _existing_node.x (8.22, локальные)
  - _final_y = _existing_node.y (12.45, локальные)
  - graph["tavern:exit_east"] = NodeRef(x=8.22, y=12.45, role=BOUNDARY)
    → использует ЛОКАЛЬНЫЕ координаты, как и все другие узлы

SpatialValidator теперь сравнивает локальные coords boundary с локальными coords стен.
→ ребро exit_east(8.22, 12.45) ↔ kitchen_bed_2(18.44, 6.27)
→ отрезок не пересекает wall_5 (которая на x=19.5, y∈[0.5, 8.0])
   (отрезок проходит через main_hall, не через kitchen)
→ ребро НЕ удаляется
→ A* находит путь → FLEE EXECUTED

=============================================================================
АВТОРСКИЕ ОГРАНИЧЕНИЯ — СОБЛЮДЕНЫ:
=============================================================================

✓ У Tavern только один внешний выход — door_0 на wall_2 (Master: "южная стена")
✓ door_1 — внутренняя дверь (не трогается)
✓ exit_east — это authored узел (label "Выход в Город"), ведёт в city_gate
  (через door_0 на wall_2)
✓ Не добавляется exit_south, exit_east, door_2 — используются существующие
✓ Не перемещаются двери, стены, комнаты, node_16
✓ Не меняется авторская геометрия
✓ Не меняется adjacency и JSON
✓ Не создаётся новый источник истины — используется существующий authored exit_east

=============================================================================
ПОЧЕМУ ЭТО РАБОТАЕТ (если гипотеза подтверждена):
=============================================================================

1. authored exit_east уже есть в nodes dict с правильными координатами
2. GraphCompiler просто должен его НАЙТИ при создании boundary node
3. Фикс одной строки: fallback search по short_id
4. SpatialValidator работает корректно, потому что все координаты локальные
5. A* находит путь fireplace → main_hall → exit_east (через door_0 на wall_2)

ВАЖНО: exit_east в authored nodes имеет координаты (8.22, 12.45).
Это на wall_2 (y=13.0) — той же стене, что и door_0 (8.18, 13.0).
Два узла рядом — это правильно: exit_east — это навигационный узел выхода,
door_0 — физическая дверь на той же стене.

Ребро exit_east ↔ (ближайший внутренний узел) проходит через door_0
(т.к. door_0 разрезает wall_2) → SpatialValidator пропускает.

=============================================================================
ТЕСТЫ — ДО ИЗМЕНЕНИЙ (BASELINE):
=============================================================================

1. FLEE из tavern → BLOCKED (текущее поведение)
2. tavern:exit_east в graph: phantom с coords (44.03, 12.52)
3. SpatialValidator: 2 edge removals (exit_east и exit_south)
4. A* path to exit_east: no path

ТЕСТЫ — ПОСЛЕ ИЗМЕНЕНИЙ:
1. FLEE из tavern → EXECUTED (NPC идёт к exit_east через door_0)
2. tavern:exit_east в graph: authored coords (8.22, 12.45)
3. SpatialValidator: 0-1 edge removals (только exit_south phantom, если есть)
4. A* path to exit_east: fireplace → main_hall → ... → exit_east

РЕГРЕССИИ:
- market_square и city_gate НЕ затрагиваются (fix только в graph_compiler.py L939)
- test_boundary_nodes.py — должен продолжать работать (тесты используют compile_graph
  с maps без authored exit_X, тогда fallback создаёт phantom — корректное поведение)

=============================================================================
ОСТАЮЩИЕСЯ РИСКИ:
=============================================================================

1. Если GraphCompiler ХРАНИТ узлы С префиксом (а не без), то мой fix не нужен
   — нужно подтвердить Step 3.

2. Если authored exit_east в JSON имеет role="boundary" и НЕ загружается в graph
   как навигационный узел, нужно изменить и логику загрузки.

3. Если fix ломает другие локации (где нет authored exit_X), нужно добавить
   guard: использовать short_id только если exit_X имеет role="boundary".

4. Cross-location transfer может всё ещё не работать, если boundary_map
   использует мировые coords. Но это отдельная задача.
""")


# ============================================================================
# Main
# ============================================================================
def main() -> int:
    print("=" * 78)
    print("R2-FLEE-ROOT-CAUSE archaeology — find EXACT root cause")
    print(f"TAVERN_FILE: {TAVERN_FILE}")
    print("=" * 78)

    try:
        step1_node_loading()
    except Exception as e:
        print(f"[step1 error: {e}]")
        traceback.print_exc()

    try:
        step2_boundary_search_key()
    except Exception as e:
        print(f"[step2 error: {e}]")
        traceback.print_exc()

    try:
        step3_runtime_graph_keys()
    except Exception as e:
        print(f"[step3 error: {e}]")
        traceback.print_exc()

    try:
        step4_spatial_validator_coords()
    except Exception as e:
        print(f"[step4 error: {e}]")
        traceback.print_exc()

    try:
        step5_y_axis_orientation()
    except Exception as e:
        print(f"[step5 error: {e}]")
        traceback.print_exc()

    try:
        step6_minimal_fix_proposal()
    except Exception as e:
        print(f"[step6 error: {e}]")
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
