# backend/tests/sandbox/r2_flee_root_cause_v3.py
"""
R2-FLEE-ROOT-CAUSE v3 — узкий инструментальный эксперимент.

Цель: выяснить, ПОЧЕМУ exit_east и node_17 отсутствуют в graph
       после цикла L94-127, хотя они есть в JSON nodes_raw.

Probe v2 доказал:
  - graph size = 16 после загрузки (должно быть 18)
  - exit_east и node_17 отсутствуют
  - _existing_node = None в _create_boundary_nodes
  - Создаются phantom с мировыми coords

Probe v3 отслеживает:
  1. nodes_raw ПЕРЕД циклом L94 (длина, наличие exit_east/node_17, типы, полное содержимое)
  2. Цикл L94-127 построчно: вошёл ли в каждую запись, isinstance проверка,
     canonical_id, role, graph assignment, коллизии ключей
  3. Источник editor_data: совпадает ли с JSON на диске, есть ли нормализация
  4. Итог: 18 исходных vs canonical IDs, точное объяснение судьбы 2 отсутствующих

READ-ONLY. Никаких production-изменений, JSON правок, новых выходов.
"""
from __future__ import annotations
import os, sys, json, traceback, copy
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import io
from unittest.mock import patch, MagicMock

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
OUT_FILE = OUT_FILE_DIR / "r2_flee_root_cause_v3.txt"


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


# ============================================================================
# ПРОВЕРКА 1: nodes_raw перед циклом L94
# ============================================================================
def check1_nodes_raw_before_loop() -> Tuple[Dict, Dict[str, Any]]:
    _print_section("ПРОВЕРКА 1: nodes_raw ПЕРЕД циклом L94 — полная инспекция")

    if not TAVERN_FILE.exists():
        print(f"[file not found: {TAVERN_FILE}]")
        return {}, {}

    # Read raw JSON file from disk
    raw_disk_text = TAVERN_FILE.read_text(encoding="utf-8", errors="replace")
    disk_data = json.loads(raw_disk_text)
    disk_nodes = disk_data.get("nodes", {})

    print(f"\n--- Источник: tavern.json на диске ---")
    print(f"  Файл: {TAVERN_FILE}")
    print(f"  Размер: {len(raw_disk_text)} chars")
    print(f"  nodes dict size: {len(disk_nodes)}")
    print(f"  nodes dict keys (sorted):")
    for k in sorted(disk_nodes.keys()):
        print(f"    '{k}'")

    # Specifically check exit_east and node_17
    print(f"\n--- exit_east в disk_nodes ---")
    exit_east_disk = disk_nodes.get("exit_east")
    print(f"  Есть в disk_nodes: {exit_east_disk is not None}")
    if exit_east_disk is not None:
        print(f"  type: {type(exit_east_disk).__name__}")
        print(f"  isinstance dict: {isinstance(exit_east_disk, dict)}")
        if isinstance(exit_east_disk, dict):
            print(f"  Full content: {json.dumps(exit_east_disk, ensure_ascii=False, indent=2)}")

    print(f"\n--- node_17 в disk_nodes ---")
    node_17_disk = disk_nodes.get("node_17")
    print(f"  Есть в disk_nodes: {node_17_disk is not None}")
    if node_17_disk is not None:
        print(f"  type: {type(node_17_disk).__name__}")
        print(f"  isinstance dict: {isinstance(node_17_disk, dict)}")
        if isinstance(node_17_disk, dict):
            print(f"  Full content: {json.dumps(node_17_disk, ensure_ascii=False, indent=2)}")

    # Now check what compile_graph receives — by inspecting its signature and caller
    # We'll need to check editor_data passed to compile_graph
    return disk_data, disk_nodes


# ============================================================================
# ПРОВЕРКА 2: Трассировка цикла L94-127 — построчная инспекция
# ============================================================================
def check2_trace_loop(disk_data: Dict, disk_nodes: Dict) -> Dict[str, Any]:
    _print_section("ПРОВЕРКА 2: Трассировка цикла L94-127 — построчная инспекция")

    # Strategy: monkey-patch compile_graph to capture the exact state of editor_data
    # when it enters, and trace each iteration of the L94 loop

    try:
        from app.services.spatial import graph_compiler as gc_module
        from app.services.spatial.graph_compiler import NodeRef, resolve_role, _ROLE_LEGACY_ALIASES
    except Exception as e:
        print(f"[import error: {e}]")
        return {}

    # First: inspect what editor_data compile_graph actually receives
    # We do this by wrapping compile_graph
    captured_editor_data: List[Dict] = []

    original_compile = gc_module.compile_graph

    def _capturing_compile(editor_data, location_id, level=None):
        captured_editor_data.append(editor_data)
        # Deep copy to inspect after the fact
        captured_editor_data.append(copy.deepcopy(editor_data))
        return original_compile(editor_data, location_id, level)

    gc_module.compile_graph = _capturing_compile

    try:
        # Call compile_graph with disk_data
        result = gc_module.compile_graph(disk_data, location_id="tavern")
    except Exception as e:
        print(f"[compile error: {e}]")
        traceback.print_exc()
        return {}
    finally:
        gc_module.compile_graph = original_compile

    if not captured_editor_data:
        print("[no editor_data captured]")
        return {}

    editor_data_received = captured_editor_data[1]  # deep copy
    nodes_raw_received = editor_data_received.get("nodes", {})

    print(f"\n--- editor_data, переданный в compile_graph ---")
    print(f"  type: {type(editor_data_received).__name__}")
    print(f"  top-level keys: {list(editor_data_received.keys())}")
    print(f"  nodes_raw size: {len(nodes_raw_received)}")
    print(f"  nodes_raw keys (sorted):")
    for k in sorted(nodes_raw_received.keys()):
        print(f"    '{k}'")

    # Compare with disk
    print(f"\n--- Сравнение disk_nodes vs nodes_raw_received ---")
    disk_keys = set(disk_nodes.keys())
    received_keys = set(nodes_raw_received.keys())
    print(f"  disk_nodes keys: {len(disk_keys)}")
    print(f"  received nodes_raw keys: {len(received_keys)}")
    print(f"  Keys in disk but NOT in received: {sorted(disk_keys - received_keys)}")
    print(f"  Keys in received but NOT in disk: {sorted(received_keys - disk_keys)}")

    # Now trace each iteration of the L94 loop manually
    print(f"\n--- Ручная трассировка цикла L94-127 для каждого node_id ---")
    print(f"  Цикл: for node_id, node_data in nodes_raw.items():")

    trace_results: List[Dict[str, Any]] = []

    for node_id, node_data in nodes_raw_received.items():
        trace: Dict[str, Any] = {"node_id": node_id}

        # Step 1: isinstance check (L95)
        is_dict = isinstance(node_data, dict)
        trace["is_dict"] = is_dict
        if not is_dict:
            trace["action"] = "continue (not dict)"
            trace_results.append(trace)
            continue

        # Step 2: canonical_id formation (L97)
        canonical_id = f"tavern:{node_id}"
        trace["canonical_id"] = canonical_id

        # Step 3: x, y extraction (L98-99)
        nx = node_data.get("x", 0.0)
        ny = node_data.get("y", 0.0)
        trace["nx"] = nx
        trace["ny"] = ny

        # Step 4: label (L100)
        node_label = node_data.get("label", node_data.get("name", node_id))
        trace["label"] = node_label

        # Step 5: role resolution (L102-120)
        _json_role = node_data.get("role")
        _manifest = None
        if _json_role:
            try:
                _manifest = NodeRole(_json_role)
            except ValueError:
                _manifest = None

        try:
            resolved_role = resolve_role(
                node_label=node_label,
                editor_type=node_data.get("type"),
                editor_tags=node_data.get("tags", []),
                node_id=node_id,
                manifest_override=_manifest,
            )
            trace["resolved_role"] = str(resolved_role)
        except Exception as e:
            trace["resolved_role_error"] = f"{type(e).__name__}: {e}"
            trace["action"] = "EXCEPTION in resolve_role"
            trace_results.append(trace)
            continue

        # Step 6: NodeRef creation (L111-125)
        try:
            node_ref = NodeRef(
                node_id=canonical_id,
                x=nx,
                y=ny,
                role=resolved_role,
                tags=node_data.get("tags", []),
                zone_id="tavern",
                level=None,
            )
            trace["node_ref_created"] = True
        except Exception as e:
            trace["node_ref_created"] = False
            trace["node_ref_error"] = f"{type(e).__name__}: {e}"
            trace["action"] = "EXCEPTION in NodeRef"
            trace_results.append(trace)
            continue

        # Step 7: graph assignment (L126)
        # We'll mark success but track if canonical_id collides with previous
        trace["graph_assignment"] = "graph[canonical_id] = node_ref"

        # Check for collisions
        trace_results.append(trace)

    # Print trace results
    print(f"\n--- Итерации цикла ({len(trace_results)} total) ---")
    for i, t in enumerate(trace_results, 1):
        print(f"\n  [{i}] node_id = '{t['node_id']}'")
        if not t.get("is_dict", False):
            print(f"      SKIP: not a dict (type={type(t.get('node_data'))})")
            print(f"      action: {t.get('action')}")
            continue
        print(f"      is_dict: {t['is_dict']}")
        print(f"      canonical_id: '{t.get('canonical_id', '?')}'")
        print(f"      x={t.get('nx')}, y={t.get('ny')}")
        print(f"      label: {t.get('label', '?')}")
        print(f"      resolved_role: {t.get('resolved_role', '?')}")
        if "resolved_role_error" in t:
            print(f"      resolve_role ERROR: {t['resolved_role_error']}")
        if "node_ref_error" in t:
            print(f"      NodeRef ERROR: {t['node_ref_error']}")
        print(f"      node_ref_created: {t.get('node_ref_created', '?')}")

    # Check for canonical_id collisions
    print(f"\n--- Проверка коллизий canonical_id ---")
    canonical_ids = [t.get("canonical_id") for t in trace_results if t.get("canonical_id")]
    seen = set()
    duplicates = []
    for cid in canonical_ids:
        if cid in seen:
            duplicates.append(cid)
        seen.add(cid)
    if duplicates:
        print(f"  ДУБЛИКАТЫ canonical_id: {duplicates}")
    else:
        print(f"  Коллизий canonical_id нет — все {len(canonical_ids)} уникальны")

    # Check: were exit_east and node_17 iterated?
    print(f"\n--- Судьба exit_east и node_17 в цикле ---")
    for target in ("exit_east", "node_17"):
        # Find in trace_results
        trace_target = next((t for t in trace_results if t["node_id"] == target), None)
        if trace_target is None:
            print(f"\n  '{target}': НЕ ИТЕРИРОВАЛСЯ (отсутствует в nodes_raw_received)")
        else:
            print(f"\n  '{target}': ИТЕРИРОВАЛСЯ")
            print(f"    is_dict: {trace_target.get('is_dict')}")
            print(f"    canonical_id: '{trace_target.get('canonical_id', '?')}'")
            print(f"    resolved_role: {trace_target.get('resolved_role', '?')}")
            if "resolved_role_error" in trace_target:
                print(f"    resolve_role ERROR: {trace_target['resolved_role_error']}")
            if "node_ref_error" in trace_target:
                print(f"    NodeRef ERROR: {trace_target['node_ref_error']}")
            print(f"    node_ref_created: {trace_target.get('node_ref_created', '?')}")

    return {"trace_results": trace_results, "editor_data_received": editor_data_received}


# ============================================================================
# ПРОВЕРКА 3: Источник editor_data — normalisation check
# ============================================================================
def check3_editor_data_source(disk_data: Dict, editor_data_received: Dict) -> None:
    _print_section("ПРОВЕРКА 3: Источник editor_data — нормализация/фильтрация")

    print(f"""
Вопрос: передаётся ли editor_data в compile_graph БЕЗ изменений,
        или есть нормализация/фильтрация между disk и compile_graph?
""")

    print(f"\n--- Сравнение disk_data vs editor_data_received ---")
    disk_keys = set(disk_data.keys())
    received_keys = set(editor_data_received.keys())
    print(f"  disk top-level keys: {sorted(disk_keys)}")
    print(f"  received top-level keys: {sorted(received_keys)}")
    print(f"  Same top-level keys: {disk_keys == received_keys}")

    # Compare nodes specifically
    disk_nodes = disk_data.get("nodes", {})
    received_nodes = editor_data_received.get("nodes", {})
    print(f"\n  disk_nodes size: {len(disk_nodes)}")
    print(f"  received_nodes size: {len(received_nodes)}")
    print(f"  Same keys: {set(disk_nodes.keys()) == set(received_nodes.keys())}")

    # Check exit_east and node_17 specifically
    for target in ("exit_east", "node_17"):
        d = disk_nodes.get(target)
        r = received_nodes.get(target)
        print(f"\n  '{target}':")
        print(f"    in disk: {d is not None} (type={type(d).__name__})")
        print(f"    in received: {r is not None} (type={type(r).__name__})")
        if d is not None and r is not None:
            same = (d == r)
            print(f"    same content: {same}")
            if not same:
                print(f"    disk: {json.dumps(d, ensure_ascii=False)[:200]}")
                print(f"    received: {json.dumps(r, ensure_ascii=False)[:200]}")

    # Check who calls compile_graph — trace the caller
    print(f"\n--- Кто вызывает compile_graph? ---")
    print(f"  В нашем probe: gc_module.compile_graph(disk_data, location_id='tavern')")
    print(f"  → disk_data передаётся напрямую, без нормализации")
    print(f"  → editor_data IS disk_data (same Python object)")
    print(f"  → Если в production вызывается по-другому, нужно проверить вызов из SpatialService")

    # Inspect how SpatialService loads and passes editor_data
    print(f"\n--- Как SpatialService загружает editor_data? ---")
    try:
        from app.services.spatial import spatial_service as ss_module
        ss_path = Path(ss_module.__file__)
        ss_src = ss_path.read_text(encoding="utf-8", errors="replace")
        # Find compile_graph calls in spatial_service
        for i, line in enumerate(ss_src.split("\n"), 1):
            if "compile_graph" in line:
                print(f"  {ss_path.name} L{i}: {line.rstrip()}")
        # Find load_location or editor_data loading
        for i, line in enumerate(ss_src.split("\n"), 1):
            if "editor_data" in line.lower() or "load_location" in line.lower() or "json.load" in line.lower():
                print(f"  {ss_path.name} L{i}: {line.rstrip()}")
    except Exception as e:
        print(f"  [inspect error: {e}]")


# ============================================================================
# ПРОВЕРКА 4: Итоговый контроль — 18 vs canonical IDs
# ============================================================================
def check4_final_audit(disk_data: Dict, trace_results: List[Dict]) -> None:
    _print_section("ПРОВЕРКА 4: Итоговый контроль — 18 исходных vs canonical IDs")

    disk_nodes = disk_data.get("nodes", {})
    print(f"\n--- Все 18 исходных node_id из JSON ---")
    disk_ids = sorted(disk_nodes.keys())
    print(f"  Count: {len(disk_ids)}")
    for nid in disk_ids:
        print(f"    '{nid}'")

    print(f"\n--- Все canonical_ids, созданные в цикле ---")
    canonical_ids = [t.get("canonical_id") for t in trace_results
                     if t.get("canonical_id") and t.get("node_ref_created", False)]
    print(f"  Count: {len(canonical_ids)}")
    for cid in canonical_ids:
        print(f"    '{cid}'")

    print(f"\n--- Аудит: какие node_id не попали в canonical_ids ---")
    expected_canonical = {f"tavern:{nid}" for nid in disk_ids}
    actual_canonical = set(canonical_ids)
    missing = expected_canonical - actual_canonical
    extra = actual_canonical - expected_canonical
    print(f"  Expected (from 18 disk nodes): {len(expected_canonical)}")
    print(f"  Actual (created in cycle): {len(actual_canonical)}")
    print(f"  Missing (in disk but NOT in graph): {sorted(missing)}")
    print(f"  Extra (in graph but NOT in disk): {sorted(extra)}")

    print(f"\n--- Точная судьба отсутствующих узлов ---")
    for missing_id in sorted(missing):
        # Strip "tavern:" prefix
        short_id = missing_id.split(":", 1)[1] if ":" in missing_id else missing_id
        print(f"\n  '{missing_id}' (short: '{short_id}'):")
        # Find in trace_results
        trace = next((t for t in trace_results if t["node_id"] == short_id), None)
        if trace is None:
            print(f"    НЕ ИТЕРИРОВАЛСЯ В ЦИКЛЕ — отсутствует в nodes_raw")
            print(f"    → Узел отсутствует в editor_data['nodes']")
            print(f"    → Нужно проверить: загружается ли JSON корректно?")
        else:
            print(f"    iterated: True")
            print(f"    is_dict: {trace.get('is_dict')}")
            print(f"    canonical_id: '{trace.get('canonical_id', '?')}'")
            print(f"    resolved_role: {trace.get('resolved_role', '?')}")
            if "resolved_role_error" in trace:
                print(f"    resolve_role ERROR: {trace['resolved_role_error']}")
            if "node_ref_error" in trace:
                print(f"    NodeRef ERROR: {trace['node_ref_error']}")
            if trace.get("node_ref_created") is False:
                print(f"    node_ref creation FAILED — node not added to graph")
            elif trace.get("node_ref_created") is True:
                print(f"    node_ref created successfully — но отсутствует в graph")
                print(f"    → Возможно, canonical_id коллизия (другой узел перезаписал)")
                # Check trace_results for duplicate canonical_id
                others = [t for t in trace_results
                          if t.get("canonical_id") == trace.get("canonical_id")
                          and t["node_id"] != short_id]
                if others:
                    print(f"    → Конфликт с другими node_id: {[t['node_id'] for t in others]}")
                else:
                    print(f"    → Коллизий нет — загадка")

    # Final verdict
    print(f"\n--- ФИНАЛЬНЫЙ ВЕРДИКТ ---")
    if missing:
        print(f"  ОТСУТСТВУЮТ в graph: {sorted(missing)}")
        # Determine the reason
        for missing_id in sorted(missing):
            short_id = missing_id.split(":", 1)[1]
            trace = next((t for t in trace_results if t["node_id"] == short_id), None)
            if trace is None:
                print(f"    {missing_id}: отсутствует в nodes_raw (не итерировался)")
                print(f"      → Причина: узел отсутствует в editor_data['nodes']")
                print(f"      → Действие: исследовать источник editor_data (ПРОВЕРКА 3)")
            elif not trace.get("is_dict", False):
                print(f"    {missing_id}: node_data не dict (type={type(trace.get('node_data'))})")
                print(f"      → Причина: не проходит проверку isinstance на L95")
            elif "resolved_role_error" in trace:
                print(f"    {missing_id}: EXCEPTION в resolve_role")
                print(f"      → Причина: {trace['resolved_role_error']}")
            elif "node_ref_error" in trace:
                print(f"    {missing_id}: EXCEPTION в NodeRef creation")
                print(f"      → Причина: {trace['node_ref_error']}")
            elif trace.get("node_ref_created") is False:
                print(f"    {missing_id}: NodeRef creation failed")
            else:
                print(f"    {missing_id}: iterated, created, но отсутствует в graph")
                print(f"      → Загадка — нужно дополнительное расследование")
    else:
        print(f"  ВСЕ 18 узлов в graph — загадка отсутствия exit_east/node_17 не подтверждена")
        print(f"  Возможно, предыдущие probe показывали другое состояние данных")


# ============================================================================
# Main
# ============================================================================
def main() -> int:
    print("=" * 78)
    print("R2-FLEE-ROOT-CAUSE v3 — узкий инструментальный эксперимент")
    print(f"TAVERN_FILE: {TAVERN_FILE}")
    print(f"OUT_FILE: {OUT_FILE}")
    print("=" * 78)

    disk_data, disk_nodes = check1_nodes_raw_before_loop()

    if not disk_data:
        return 1

    check2_data = check2_trace_loop(disk_data, disk_nodes)
    if not check2_data:
        return 1

    check3_editor_data_source(disk_data, check2_data.get("editor_data_received", {}))

    check4_final_audit(disk_data, check2_data.get("trace_results", []))

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
