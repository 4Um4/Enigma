# backend/tests/sandbox/r2_flee_root_cause_v2.py
"""
R2-FLEE-ROOT-CAUSE v2 — четыре проверки + контрольный эксперимент.

Цель: установить, ПОЧЕМУ graph.get("tavern:exit_east") возвращает None
       в _create_boundary_nodes, хотя авторский exit_east загружается в graph.

Проверки:
  1. Полный путь compile_graph от начала до _create_boundary_nodes (точные строки)
  2. Состояние graph непосредственно перед вызовом _create_boundary_nodes
     (через monkey-patch — все ключи, включая boundary)
  3. Все операции между загрузкой узлов и созданием boundary nodes
     (удаление, фильтрация, пересборка graph)
  4. Обработка role=BOUNDARY — все места, где такие узлы исключаются/преобразуются

Контрольный эксперимент:
  Monkey-patch _create_boundary_nodes для фиксации _existing_node и его координат
  до вычисления _final_x/_final_y. Это свяжет причину с наблюдаемым runtime-результатом.

READ-ONLY. Никаких production-изменений, JSON, геометрии, adjacency.
"""
from __future__ import annotations
import os, sys, json, traceback, copy, logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import io
from unittest.mock import patch

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
OUT_FILE = OUT_FILE_DIR / "r2_flee_root_cause_v2.txt"


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


def _read_file(path: Path) -> Optional[str]:
    if not path.exists():
        return None
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        print(f"[read error: {e}]")
        return None


# ============================================================================
# ПРОВЕРКА 1: Полный путь compile_graph от начала до _create_boundary_nodes
# ============================================================================
def check1_compile_graph_path() -> None:
    _print_section("ПРОВЕРКА 1: Полный путь compile_graph — от начала до _create_boundary_nodes")

    gc_path = _BACKEND / "app/services/spatial/graph_compiler.py"
    src = _read_file(gc_path)
    if src is None:
        return
    lines = src.split("\n")

    # Find compile_graph function
    func_start = None
    for i, line in enumerate(lines):
        if "def compile_graph" in line:
            func_start = i
            break

    if func_start is None:
        print("[compile_graph not found]")
        return

    print(f"\ncompile_graph начинается на L{func_start + 1}")

    # Find _create_boundary_nodes call site
    boundary_call_line = None
    for i in range(func_start, len(lines)):
        if "_create_boundary_nodes" in lines[i] and "def _create_boundary_nodes" not in lines[i]:
            boundary_call_line = i
            break

    if boundary_call_line is None:
        print("[_create_boundary_nodes call not found in compile_graph]")
        return

    print(f"_create_boundary_nodes вызывается на L{boundary_call_line + 1}")
    print(f"\n>>> Полный путь compile_graph (L{func_start + 1} – L{boundary_call_line + 5}):")
    print(f">>> Это {boundary_call_line - func_start} строк между началом и вызовом")

    # Print all lines between func_start and boundary_call_line + 5
    for j in range(func_start, min(boundary_call_line + 5, len(lines))):
        # Highlight important lines
        line = lines[j]
        marker = ""
        if "graph[" in line or "graph.get" in line:
            marker = "  ← GRAPH OP"
        elif "del graph" in line or "graph.clear" in line or "graph.pop" in line:
            marker = "  ← GRAPH DELETE"
        elif "_create_boundary_nodes" in line:
            marker = "  ← BOUNDARY CALL"
        elif "boundary" in line.lower() and "NodeRole.BOUNDARY" in line:
            marker = "  ← BOUNDARY ROLE"
        elif "NodeRole.BOUNDARY" in line:
            marker = "  ← BOUNDARY ROLE"
        elif "return " in line and func_start < j < boundary_call_line:
            marker = "  ← EARLY RETURN"
        print(f"L{j+1:4d}: {line}{marker}")


# ============================================================================
# ПРОВЕРКА 2: Состояние graph перед _create_boundary_nodes (runtime)
# ============================================================================
def check2_graph_state_before_boundary() -> None:
    _print_section("ПРОВЕРКА 2: Состояние graph ПЕРЕД вызовом _create_boundary_nodes (runtime)")

    if not TAVERN_FILE.exists():
        print(f"[file not found: {TAVERN_FILE}]")
        return

    data = json.loads(TAVERN_FILE.read_text(encoding="utf-8", errors="replace"))

    try:
        from app.services.spatial import graph_compiler as gc_module
    except Exception as e:
        print(f"[import error: {e}]")
        return

    # Monkey-patch _create_boundary_nodes to capture graph state BEFORE it runs
    captured_state: Dict[str, Any] = {}

    original_fn = gc_module._create_boundary_nodes

    def _capturing_fn(graph, connections, alias_map, boundary_map, location_id, adjacency, origin, size):
        # Capture graph state BEFORE _create_boundary_nodes runs
        captured_state["graph_keys_before"] = sorted(graph.keys())
        captured_state["graph_size_before"] = len(graph)
        captured_state["location_id"] = location_id
        captured_state["adjacency"] = adjacency
        captured_state["origin"] = origin
        captured_state["size"] = size

        # Specifically check for exit_east / exit_south
        captured_state["tavern_exit_east_in_graph"] = "tavern:exit_east" in graph
        captured_state["exit_east_in_graph"] = "exit_east" in graph
        captured_state["tavern_exit_south_in_graph"] = "tavern:exit_south" in graph
        captured_state["exit_south_in_graph"] = "exit_south" in graph

        # If exit_east is in graph, capture its coords
        for key in ("tavern:exit_east", "exit_east", "tavern:exit_south", "exit_south"):
            if key in graph:
                nref = graph[key]
                captured_state[f"coords_of_{key}"] = (getattr(nref, "x", None), getattr(nref, "y", None))
                captured_state[f"role_of_{key}"] = str(getattr(nref, "role", None))

        # Capture all nodes with role=BOUNDARY
        boundary_nodes_before = []
        for k, v in graph.items():
            role = getattr(v, "role", None)
            if role is not None and "BOUNDARY" in str(role):
                boundary_nodes_before.append({
                    "key": k,
                    "x": getattr(v, "x", None),
                    "y": getattr(v, "y", None),
                    "role": str(role),
                })
        captured_state["boundary_nodes_in_graph_before"] = boundary_nodes_before

        # Now call the original function
        result = original_fn(graph, connections, alias_map, boundary_map, location_id, adjacency, origin, size)
        return result

    # Replace the function
    gc_module._create_boundary_nodes = _capturing_fn

    try:
        result = gc_module.compile_graph(data, location_id="tavern")
    except Exception as e:
        print(f"[compile error: {e}]")
        traceback.print_exc()
        return
    finally:
        # Restore
        gc_module._create_boundary_nodes = original_fn

    print(f"\n>>> Состояние graph ПЕРЕД _create_boundary_nodes:")
    print(f"  location_id: {captured_state.get('location_id')}")
    print(f"  adjacency: {captured_state.get('adjacency')}")
    print(f"  origin: {captured_state.get('origin')}")
    print(f"  size: {captured_state.get('size')}")
    print(f"  graph size: {captured_state.get('graph_size_before')} entries")

    print(f"\n  Ключевые проверки:")
    print(f"    'tavern:exit_east' в graph: {captured_state.get('tavern_exit_east_in_graph')}")
    print(f"    'exit_east' (без префикса) в graph: {captured_state.get('exit_east_in_graph')}")
    print(f"    'tavern:exit_south' в graph: {captured_state.get('tavern_exit_south_in_graph')}")
    print(f"    'exit_south' (без префикса) в graph: {captured_state.get('exit_south_in_graph')}")

    print(f"\n  Координаты (если найдены):")
    for key in ("tavern:exit_east", "exit_east", "tavern:exit_south", "exit_south"):
        coords_key = f"coords_of_{key}"
        role_key = f"role_of_{key}"
        if coords_key in captured_state:
            print(f"    {key}: coords={captured_state[coords_key]}, role={captured_state[role_key]}")
        else:
            print(f"    {key}: НЕ в graph")

    print(f"\n  Boundary nodes уже в graph (перед _create_boundary_nodes):")
    bn_before = captured_state.get("boundary_nodes_in_graph_before", [])
    if bn_before:
        for bn in bn_before:
            print(f"    {bn['key']}: ({bn['x']}, {bn['y']}) role={bn['role']}")
    else:
        print(f"    [нет узлов с role=BOUNDARY в graph перед вызовом]")

    print(f"\n  Все ключи graph (первые 30, отсортированные):")
    for k in captured_state.get("graph_keys_before", [])[:30]:
        print(f"    {k}")

    return captured_state


# ============================================================================
# ПРОВЕРКА 3: Все операции между загрузкой узлов и созданием boundary
# ============================================================================
def check3_operations_between() -> None:
    _print_section("ПРОВЕРКА 3: Все операции между загрузкой nodes и созданием boundary")

    gc_path = _BACKEND / "app/services/spatial/graph_compiler.py"
    src = _read_file(gc_path)
    if src is None:
        return
    lines = src.split("\n")

    # Find end of nodes loading (L126-127: graph[canonical_id] = node_ref; alias_map[node_id] = canonical_id)
    nodes_loading_end = None
    for i, line in enumerate(lines):
        if "graph[canonical_id] = node_ref" in line:
            # Find next non-trivial line (after alias_map assignment)
            for j in range(i + 1, min(i + 20, len(lines))):
                if "alias_map[node_id] = canonical_id" in lines[j]:
                    nodes_loading_end = j
                    break
            if nodes_loading_end:
                break

    if nodes_loading_end is None:
        print("[не удалось найти конец загрузки nodes]")
        return

    # Find _create_boundary_nodes call
    boundary_call_line = None
    for i in range(nodes_loading_end, len(lines)):
        if "_create_boundary_nodes" in lines[i] and "def _create_boundary_nodes" not in lines[i]:
            boundary_call_line = i
            break

    if boundary_call_line is None:
        print("[_create_boundary_nodes call not found]")
        return

    print(f"\n>>> Загрузка nodes заканчивается на L{nodes_loading_end + 1}")
    print(f">>> _create_boundary_nodes вызывается на L{boundary_call_line + 1}")
    print(f">>> Между ними {boundary_call_line - nodes_loading_end} строк")
    print(f"\n>>> Все операции между (L{nodes_loading_end + 1} – L{boundary_call_line + 1}):")

    # Print all lines, highlighting operations that modify graph
    suspicious_keywords = [
        "del graph", "graph.clear", "graph.pop", "graph.update",
        "graph = ", "graph[", "graph =",
        "nodes_to_remove", "nodes_to_delete", "remove_node",
        "filter", "exclude", "skip",
        "NodeRole.BOUNDARY", "role == ", "role != ",
        "boundary", "exit_east", "exit_south",
        "return ", "if not", "if _has",
    ]

    for j in range(nodes_loading_end, boundary_call_line + 1):
        if j >= len(lines):
            break
        line = lines[j]
        marker = ""
        for kw in suspicious_keywords:
            if kw in line:
                marker = f"  ← [{kw}]"
                break
        # Only print if non-empty or has marker
        if line.strip() or marker:
            print(f"L{j+1:4d}: {line}{marker}")


# ============================================================================
# ПРОВЕРКА 4: Обработка role=BOUNDARY — все места в graph_compiler.py
# ============================================================================
def check4_boundary_role_handling() -> None:
    _print_section("ПРОВЕРКА 4: Обработка role=BOUNDARY в graph_compiler.py")

    gc_path = _BACKEND / "app/services/spatial/graph_compiler.py"
    src = _read_file(gc_path)
    if src is None:
        return
    lines = src.split("\n")

    print("\n--- Все строки с 'NodeRole.BOUNDARY' или 'BOUNDARY' ---")
    for i, line in enumerate(lines, 1):
        if "NodeRole.BOUNDARY" in line or "BOUNDARY" in line.upper() and "boundary" in line.lower():
            print(f"  L{i}: {line.rstrip()}")

    print("\n--- Все строки с 'exit_east', 'exit_south', 'exit_north', 'exit_west' ---")
    for i, line in enumerate(lines, 1):
        if any(kw in line for kw in ["exit_east", "exit_south", "exit_north", "exit_west"]):
            print(f"  L{i}: {line.rstrip()}")

    print("\n--- Все строки, где может происходить удаление/фильтрация узлов ---")
    delete_keywords = ["del graph", "graph.pop", "graph.clear", "remove_from_graph",
                       "filter_out", "skip_node", "exclude_node", "if role == NodeRole.BOUNDARY",
                       "if role != NodeRole.BOUNDARY", "if n.role == ", "if node.role == "]
    for i, line in enumerate(lines, 1):
        for kw in delete_keywords:
            if kw in line:
                print(f"  L{i}: {line.rstrip()}")
                break


# ============================================================================
# КОНТРОЛЬНЫЙ ЭКСПЕРИМЕНТ: Зафиксировать _existing_node и его координаты
# ============================================================================
def control_experiment_existing_node() -> None:
    _print_section("КОНТРОЛЬНЫЙ ЭКСПЕРИМЕНТ: зафиксировать _existing_node до вычисления _final_x/_final_y")

    if not TAVERN_FILE.exists():
        return
    data = json.loads(TAVERN_FILE.read_text(encoding="utf-8", errors="replace"))

    try:
        from app.services.spatial import graph_compiler as gc_module
    except Exception as e:
        print(f"[import error: {e}]")
        return

    # We need to monkey-patch _create_boundary_nodes in a way that captures
    # _existing_node value. But we can't directly patch the line.
    # Instead, we replicate the function logic with prints.

    original_fn = gc_module._create_boundary_nodes

    experiment_log: List[Dict[str, Any]] = []

    def _experiment_fn(graph, connections, alias_map, boundary_map, location_id, adjacency, origin, size):
        """Replicates _create_boundary_nodes logic but with detailed logging."""
        _OPPOSITE_DIRS = {"north": "south", "south": "north", "east": "west", "west": "east"}

        if not graph:
            print("[experiment] graph is empty, returning")
            return original_fn(graph, connections, alias_map, boundary_map, location_id, adjacency, origin, size)

        _ox = float(origin.get("x", 0.0))
        _oy = float(origin.get("y", 0.0))
        _w = float(size.get("w", 10.0))
        _h = float(size.get("h", 10.0))

        _DIR_OFFSETS = {
            "east":  (_ox + _w - 1.0, _oy + _h / 2.0),
            "west":  (_ox + 1.0,      _oy + _h / 2.0),
            "north": (_ox + _w / 2.0, _oy + _h - 1.0),
            "south": (_ox + _w / 2.0, _oy + 1.0),
        }

        for direction, neighbor_loc_id in adjacency.items():
            if not isinstance(neighbor_loc_id, str):
                continue

            _bx, _by = _DIR_OFFSETS.get(direction, (_ox + _w / 2.0, _oy + _h / 2.0))

            boundary_id = f"{location_id}:exit_{direction}"

            # CRITICAL: check what graph.get actually returns
            _existing_node = graph.get(boundary_id)

            entry = {
                "direction": direction,
                "neighbor_loc_id": neighbor_loc_id,
                "boundary_id": boundary_id,
                "_bx": _bx,
                "_by": _by,
                "_existing_node_is_None": _existing_node is None,
            }

            if _existing_node is not None:
                entry["_existing_node_x"] = getattr(_existing_node, "x", "?")
                entry["_existing_node_y"] = getattr(_existing_node, "y", "?")
                entry["_existing_node_role"] = str(getattr(_existing_node, "role", "?"))
                entry["_existing_node_id"] = getattr(_existing_node, "node_id", "?")
                entry["_final_x_will_be"] = getattr(_existing_node, "x", "?")
                entry["_final_y_will_be"] = getattr(_existing_node, "y", "?")
            else:
                entry["_final_x_will_be"] = _bx  # phantom coords
                entry["_final_y_will_be"] = _by

            experiment_log.append(entry)

        # Print experiment results
        print(f"\n>>> КОНТРОЛЬНЫЙ ЭКСПЕРИМЕНТ — _existing_node для каждого direction:")
        for e in experiment_log:
            print(f"\n  Direction: {e['direction']}")
            print(f"    neighbor_loc_id: {e['neighbor_loc_id']}")
            print(f"    boundary_id (ищется в graph): '{e['boundary_id']}'")
            print(f"    _bx, _by (placeholder coords): ({e['_bx']:.3f}, {e['_by']:.3f})")
            print(f"    _existing_node is None: {e['_existing_node_is_None']}")
            if not e["_existing_node_is_None"]:
                print(f"    _existing_node.x: {e['_existing_node_x']}")
                print(f"    _existing_node.y: {e['_existing_node_y']}")
                print(f"    _existing_node.role: {e['_existing_node_role']}")
                print(f"    _existing_node.node_id: {e['_existing_node_id']}")
                print(f"    → _final_x БУДЕТ: {e['_final_x_will_be']} (из авторского)")
                print(f"    → _final_y БУДЕТ: {e['_final_y_will_be']} (из авторского)")
            else:
                print(f"    → _final_x БУДЕТ: {e['_final_x_will_be']:.3f} (PHANTOM — мировые coords)")
                print(f"    → _final_y БУДЕТ: {e['_final_y_will_be']:.3f} (PHANTOM — мировые coords)")

        # Now call the original to keep production behavior
        return original_fn(graph, connections, alias_map, boundary_map, location_id, adjacency, origin, size)

    # Patch and run
    gc_module._create_boundary_nodes = _experiment_fn
    try:
        result = gc_module.compile_graph(data, location_id="tavern")
    except Exception as e:
        print(f"[compile error: {e}]")
        traceback.print_exc()
    finally:
        gc_module._create_boundary_nodes = original_fn


# ============================================================================
# ИТОГОВЫЙ АНАЛИЗ
# ============================================================================
def final_analysis() -> None:
    _print_section("ИТОГОВЫЙ АНАЛИЗ — связать причину с наблюдаемым результатом")

    print("""
ОЖИДАЕМЫЕ РЕЗУЛЬТАТЫ ПРОБ:

ПРОВЕРКА 1 (путь compile_graph):
  Покажет точные строки от L44 (start) до вызова _create_boundary_nodes.
  Ожидается: ~370 строк между ними (L44 → ~L380).

ПРОВЕРКА 2 (состояние graph перед _create_boundary_nodes):
  КРИТИЧНО: есть ли "tavern:exit_east" в graph перед вызовом?
  - Если ДА → _existing_node должен найтись, и coords будут локальные (8.22, 12.45)
    → парадокс: probe v1 показал мировые coords. Значит, что-то перезаписывает
    ПОСЛЕ вызова, или _existing_node теряет ссылку.
  - Если НЕТ → авторский exit_east не попал в graph под этим ключом.
    Нужно искать, где он удаляется/переименовывается/фильтруется.

ПРОВЕРКА 3 (операции между загрузкой и boundary):
  Покажет ВСЕ операции между L127 (graph[canonical_id] = node_ref) и
  L~380 (_create_boundary_nodes call).
  Ищем: del graph, graph.pop, filter, if role==BOUNDARY, return early.

ПРОВЕРКА 4 (обработка role=BOUNDARY):
  Покажет все места в graph_compiler.py, где обрабатывается BOUNDARY role.
  Ищем: special-casing, filtering, exclusion, role override.

КОНТРОЛЬНЫЙ ЭКСПЕРИМЕНТ:
  Прямой захват _existing_node внутри _create_boundary_nodes.
  Даст однозначный ответ: None или не None.
  Если None → причина в том, что exit_east не в graph под ключом "tavern:exit_east"
            в момент вызова.
  Если не None → парадокс, нужно искать перезапись после.

ВОЗМОЖНЫЕ СЦЕНАРИИ:

СЦЕНАРИЙ A: _existing_node = None
  → exit_east не в graph под "tavern:exit_east" в момент вызова
  → ПРОВЕРКА 2 покажет, какие ключи ЕСТЬ в graph
  → ПРОВЕРКА 3 покажет, где exit_east удаляется/переименовывается
  → Возможно: nodes с role=boundary фильтруются перед _create_boundary_nodes
    (чтобы избежать дублирования), но потом boundary создаются с мировыми coords

СЦЕНАРИЙ B: _existing_node не None, но coords (44.03, 12.52) мировые
  → парадокс: авторский exit_east имеет локальные coords (8.22, 12.45)
  → Значит, в graph лежит НЕ авторский узел, а уже синтетический
  → Возможно: _create_boundary_nodes вызывается ДВАЖДЫ?
    Первый раз создаёт phantom, второй раз находит его как "_existing_node"

СЦЕНАРИЙ C: _existing_node не None, coords (8.22, 12.45) локальные
  → Тогда probe v1 показал неверные данные (что невозможно)
  → Или graph в probe v1 проверялся ПОСЛЕ какой-то перезаписи

После probe v2 мы выберем ОДИН доказанный дефект и исправим его изолированно.
""")


# ============================================================================
# Main
# ============================================================================
def main() -> int:
    print("=" * 78)
    print("R2-FLEE-ROOT-CAUSE v2 — 4 проверки + контрольный эксперимент")
    print(f"TAVERN_FILE: {TAVERN_FILE}")
    print(f"OUT_FILE: {OUT_FILE}")
    print("=" * 78)

    try:
        check1_compile_graph_path()
    except Exception as e:
        print(f"[check1 error: {e}]")
        traceback.print_exc()

    try:
        check2_graph_state_before_boundary()
    except Exception as e:
        print(f"[check2 error: {e}]")
        traceback.print_exc()

    try:
        check3_operations_between()
    except Exception as e:
        print(f"[check3 error: {e}]")
        traceback.print_exc()

    try:
        check4_boundary_role_handling()
    except Exception as e:
        print(f"[check4 error: {e}]")
        traceback.print_exc()

    try:
        control_experiment_existing_node()
    except Exception as e:
        print(f"[control experiment error: {e}]")
        traceback.print_exc()

    try:
        final_analysis()
    except Exception as e:
        print(f"[final analysis error: {e}]")
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
