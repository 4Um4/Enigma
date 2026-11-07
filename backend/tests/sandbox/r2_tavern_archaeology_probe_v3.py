# backend/tests/sandbox/r2_tavern_archaeology_probe_v3.py
"""
R2-TAVERN-ARCHAEOLOGY v3 — финальная разведка.

КРИТИЧЕСКОЕ ОТКРЫТИЕ из v2:
  В файле tavern.json есть только 18 узлов в `nodes` dict.
  Среди них есть `exit_east` (с 1 соединением к node_16),
  но НЕТ узла `exit_south`.

  Однако SpatialTargetResolver возвращает anchor_node=tavern:exit_south
  для FLEE intent, а SpatialValidator удаляет ребро exit_south <-> kitchen_bed_2.

Цель v3 — найти источник `exit_south`:
  1. Полный дамп всех 18 ключей nodes dict с координатами и connections
  2. Полный дамп passages, rooms, adjacency секций
  3. Поиск `exit_south` и `tavern:exit_south` как подстроки ВО ВСЁМ ФАЙЛЕ
     (включая любые поля, метки, пути к файлам, и т.д.)
  4. Поиск в OTHER map files (папка maps/, scenes/, locations/) — возможно,
     exit_south определён в другой карте
  5. Поиск в коде проекта (backend/app/services/spatial/*) —
     возможно, есть хардкод fallback списка exit-узлов
  6. Дамп origin, player_spawn — для понимания глобальной системы координат

Read-only.
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

PROJECT_ROOT = _BACKEND.parent  # C:\...\Enigma
MAP_FILE = PROJECT_ROOT / "saves/Open_road/locations/tavern.json"

SEARCH_STRING_VARIANTS = [
    "exit_south",
    "tavern:exit_south",
    "ExitSouth",
    "EXIT_SOUTH",
    "exit-south",
    "exitSouth",
]


def _print_section(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def _print_dict(obj: Any, indent: int = 2, max_chars: int = 0) -> str:
    try:
        s = json.dumps(obj, ensure_ascii=False, indent=indent, default=str)
        if max_chars and len(s) > max_chars:
            return s[:max_chars] + f"\n... (truncated, total {len(s)} chars)"
        return s
    except Exception:
        return str(obj)


def main() -> int:
    print("=" * 78)
    print("R2-TAVERN-ARCHAEOLOGY v3 — find source of `exit_south`")
    print(f"Map file: {MAP_FILE}")
    print("=" * 78)

    if not MAP_FILE.exists():
        print(f"[FATAL] Map file not found: {MAP_FILE}")
        return 1

    raw_text = MAP_FILE.read_text(encoding="utf-8", errors="replace")
    try:
        data = json.loads(raw_text)
    except Exception as e:
        print(f"[FATAL] Cannot parse JSON: {e}")
        return 1

    # === STEP A: Full dump of all 18 nodes ===
    _print_section("STEP A: ALL NODES (full dump of nodes dict, all 18 keys)")
    nodes = data.get("nodes") if isinstance(data, dict) else None
    if isinstance(nodes, dict):
        print(f"Total node keys: {len(nodes)}")
        print(f"All node keys: {list(nodes.keys())}")
        for node_name, node_data in nodes.items():
            print(f"\n--- nodes.{node_name} ---")
            if isinstance(node_data, dict):
                # Compact summary
                x = node_data.get("x") or (node_data.get("position") or {}).get("x") if isinstance(node_data.get("position"), dict) else node_data.get("x")
                y = node_data.get("y") or (node_data.get("position") or {}).get("y") if isinstance(node_data.get("position"), dict) else node_data.get("y")
                pos = node_data.get("position") or node_data.get("pos")
                px = py = None
                if isinstance(pos, dict):
                    px = pos.get("x")
                    py = pos.get("y")
                fx = x if x is not None else px
                fy = y if y is not None else py
                conns = node_data.get("connections") or node_data.get("exits") or node_data.get("neighbors") or []
                print(f"  coords: ({fx}, {fy})")
                print(f"  connections: {conns}")
                # Show ALL top-level fields
                other_keys = set(node_data.keys()) - {"x", "y", "position", "pos", "connections", "exits", "neighbors"}
                if other_keys:
                    print(f"  other fields:")
                    for k in sorted(other_keys):
                        v = node_data[k]
                        v_str = _print_dict(v, max_chars=200)
                        print(f"    {k}: {v_str}")
            else:
                print(f"  (not dict) {type(node_data).__name__}: {node_data}")
    else:
        print(f"nodes is not a dict: {type(nodes).__name__}")

    # === STEP B: passages, adjacency, rooms sections ===
    _print_section("STEP B: PASSAGES / ADJACENCY / ROOMS sections")
    for key in ("passages", "adjacency", "rooms", "labels", "npcs", "origin", "player_spawn"):
        val = data.get(key)
        print(f"\n--- {key} ---")
        print(f"type: {type(val).__name__}")
        if isinstance(val, list):
            print(f"length: {len(val)}")
            for i, item in enumerate(val):
                print(f"  [{i}]: {_print_dict(item, max_chars=400)}")
        elif isinstance(val, dict):
            print(f"keys: {list(val.keys())}")
            print(f"full:\n{_print_dict(val, max_chars=1500)}")
        else:
            print(f"value: {val}")

    # === STEP C: Substring search for "exit_south" anywhere in raw file ===
    _print_section("STEP C: SUBSTRING SEARCH for 'exit_south' in raw tavern.json")
    print(f"Searching for these variants:")
    for v in SEARCH_STRING_VARIANTS:
        count = raw_text.count(v)
        idx_list = []
        start = 0
        while True:
            idx = raw_text.find(v, start)
            if idx == -1:
                break
            idx_list.append(idx)
            start = idx + 1
        print(f"  '{v}': {count} occurrence(s)")
        if idx_list:
            for idx in idx_list[:5]:
                # Show surrounding context (100 chars before and after)
                ctx_start = max(0, idx - 80)
                ctx_end = min(len(raw_text), idx + len(v) + 80)
                ctx = raw_text[ctx_start:ctx_end].replace("\n", "\\n")
                print(f"    at offset {idx}: ...{ctx}...")

    # === STEP D: Search for "exit_south" in OTHER files under project ===
    _print_section("STEP D: SUBSTRING SEARCH for 'exit_south' in OTHER project files")
    print(f"Searching under: {PROJECT_ROOT}")
    print(f"(excluding .venv, node_modules, .git, __pycache__)")
    exclude_dirs = {".venv", "node_modules", ".git", "__pycache__", ".pytest_cache", ".ruff_cache"}
    matches: List[Tuple[Path, int, str]] = []
    try:
        for path in PROJECT_ROOT.rglob("*"):
            if not path.is_file():
                continue
            # Skip excluded dirs
            if any(part in exclude_dirs for part in path.parts):
                continue
            # Only text-like files
            if path.suffix.lower() not in (".json", ".yaml", ".yml", ".py", ".toml", ".md", ".txt", ".ini", ".cfg"):
                continue
            # Skip the tavern.json itself (already analyzed)
            if path == MAP_FILE:
                continue
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            for v in SEARCH_STRING_VARIANTS:
                if v in content:
                    cnt = content.count(v)
                    matches.append((path, cnt, v))
                    break
    except (PermissionError, OSError) as e:
        print(f"  [warn] rglob error: {e}")

    print(f"\nFiles containing 'exit_south' (any variant): {len(matches)}")
    for path, cnt, variant in matches:
        rel = path.relative_to(PROJECT_ROOT) if path.is_relative_to(PROJECT_ROOT) else path
        print(f"  {rel} — {cnt} occurrence(s) of '{variant}'")

    # === STEP E: For each match, show context ===
    _print_section("STEP E: CONTEXT for each file containing 'exit_south'")
    for path, cnt, variant in matches[:10]:  # limit to 10 files
        print(f"\n=== {path.relative_to(PROJECT_ROOT)} (variant='{variant}') ===")
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            print(f"  [read error: {e}]")
            continue
        # Find all occurrences with context
        start = 0
        shown = 0
        while shown < 3:  # show first 3 occurrences per file
            idx = content.find(variant, start)
            if idx == -1:
                break
            ctx_start = max(0, idx - 120)
            ctx_end = min(len(content), idx + len(variant) + 120)
            ctx = content[ctx_start:ctx_end].replace("\n", "\\n").replace("\t", "\\t")
            print(f"  at offset {idx}: ...{ctx}...")
            start = idx + 1
            shown += 1
        if cnt > 3:
            print(f"  ... and {cnt - 3} more occurrence(s)")

    # === STEP F: SpatialValidator / SpatialTargetResolver source code ===
    _print_section("STEP F: SEARCH for SpatialValidator and SpatialTargetResolver source")
    print(f"Looking for class definitions in backend/app/services/spatial/*")
    spatial_dir = _BACKEND / "app/services/spatial"
    if spatial_dir.exists():
        print(f"Spatial services directory: {spatial_dir}")
        for py_file in spatial_dir.rglob("*.py"):
            print(f"\n--- {py_file.relative_to(_BACKEND)} ---")
            try:
                src = py_file.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            # Look for class definitions
            lines = src.split("\n")
            for i, line in enumerate(lines, 1):
                if line.startswith("class ") or "class SpatialValidator" in line or "class SpatialTargetResolver" in line:
                    print(f"  L{i}: {line}")
            # Look for any reference to exit_south or "exit" pattern
            for i, line in enumerate(lines, 1):
                if "exit_south" in line.lower() or "ExitSouth" in line or "EXIT_SOUTH" in line:
                    print(f"  L{i} [exit_south ref]: {line.rstrip()}")
            # Look for "furthest" (since resolver picks furthest node)
            for i, line in enumerate(lines, 1):
                if "furthest" in line.lower() or "farthest" in line.lower():
                    print(f"  L{i} [furthest ref]: {line.rstrip()}")
            # Look for "edge removed" message (from SpatialValidator)
            for i, line in enumerate(lines, 1):
                if "edge" in line.lower() and ("removed" in line.lower() or "crosses" in line.lower() or "wall_id" in line.lower()):
                    print(f"  L{i} [edge validation]: {line.rstrip()}")
    else:
        print(f"[WARN] Spatial services directory not found: {spatial_dir}")
        print("Searching for spatial service files anywhere in backend...")
        for py_file in _BACKEND.rglob("*.py"):
            if any(part in exclude_dirs for part in py_file.parts):
                continue
            try:
                src = py_file.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            if "class SpatialValidator" in src or "class SpatialTargetResolver" in src:
                print(f"  Found: {py_file.relative_to(_BACKEND)}")
                for i, line in enumerate(src.split("\n"), 1):
                    if "class SpatialValidator" in line or "class SpatialTargetResolver" in line:
                        print(f"    L{i}: {line.rstrip()}")

    # === STEP G: Investigate how SpatialValidator builds edges list ===
    _print_section("STEP G: SEARCH for edge-building logic in spatial code")
    if spatial_dir.exists():
        for py_file in spatial_dir.rglob("*.py"):
            try:
                src = py_file.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            lines = src.split("\n")
            for i, line in enumerate(lines, 1):
                # Look for code that builds edges from nodes.X.connections
                if ("connections" in line and ("edge" in line.lower() or "graph" in line.lower() or "build" in line.lower())) or \
                   ("from_nodes" in line or "build_graph" in line or "build_edges" in line) or \
                   ("exit_" in line and "node" in line.lower()):
                    rel = py_file.relative_to(_BACKEND)
                    print(f"  {rel} L{i}: {line.rstrip()}")

    # === STEP H: kitchen_bed_2 deep analysis ===
    _print_section("STEP H: kitchen_bed_2 NODE — full definition + neighbors")
    if isinstance(nodes, dict) and "kitchen_bed_2" in nodes:
        kb2 = nodes["kitchen_bed_2"]
        print(f"\nFull definition of nodes.kitchen_bed_2:")
        print(_print_dict(kb2))
        # Extract coords
        pos = kb2.get("position") or kb2.get("pos")
        if isinstance(pos, dict):
            print(f"\nCoordinates: x={pos.get('x')}, y={pos.get('y')}")
        else:
            print(f"\nDirect coords: x={kb2.get('x')}, y={kb2.get('y')}")
        # Connections
        conns = kb2.get("connections") or []
        print(f"Connections: {conns}")
        print(f"\nFor each connected node, find its coords:")
        for c in conns:
            if c in nodes:
                cn = nodes[c]
                cp = cn.get("position") or cn.get("pos")
                if isinstance(cp, dict):
                    print(f"  {c}: ({cp.get('x')}, {cp.get('y')})")
                else:
                    print(f"  {c}: ({cn.get('x')}, {cn.get('y')}) — connections: {cn.get('connections')}")
    else:
        print("kitchen_bed_2 NOT FOUND in nodes dict!")

    # === STEP I: Check if 'exit_south' could be a typo / hallucination ===
    _print_section("STEP I: CHECK — is 'exit_south' perhaps a resolver hallucination?")
    print(f"\nSummary of evidence:")
    print(f"  1. nodes dict has {len(nodes) if isinstance(nodes, dict) else 'N/A'} keys")
    if isinstance(nodes, dict):
        has_exit_east = "exit_east" in nodes
        has_exit_south = "exit_south" in nodes
        print(f"  2. 'exit_east' in nodes: {has_exit_east}")
        print(f"  3. 'exit_south' in nodes: {has_exit_south}")
    print(f"  4. adjacency.south = '{data.get('adjacency', {}).get('south')}' (external location)")
    print(f"  5. passages list has {len(data.get('passages', []))} items")
    print(f"  6. raw file mentions 'exit_south': {raw_text.count('exit_south')} time(s)")
    print(f"  7. raw file mentions 'exit_east': {raw_text.count('exit_east')} time(s)")
    print(f"\n  >>> CONCLUSION <<<")
    if isinstance(nodes, dict) and "exit_south" not in nodes and raw_text.count("exit_south") == 0:
        print(f"  >>> 'exit_south' DOES NOT EXIST in tavern.json map file.")
        print(f"  >>> SpatialValidator's complaint about edge 'exit_south <-> kitchen_bed_2'")
        print(f"  >>> is itself suspicious — where does it get that edge from?")
        print(f"  >>> SpatialTargetResolver returning anchor_node=tavern:exit_south")
        print(f"  >>> is ALSO suspicious — it's selecting a non-existent node.")
        print(f"  >>>")
        print(f"  >>> Hypothesis: SpatialTargetResolver has a HARDCODED list of exit nodes")
        print(f"  >>> (like ['exit_north', 'exit_east', 'exit_south', 'exit_west'])")
        print(f"  >>> and picks 'furthest from threat' from that list REGARDLESS of map contents.")
        print(f"  >>> SpatialValidator then sees the resolver's anchor_node, treats it as")
        print(f"  >>> a real graph node, tries to validate edges to it, finds they cross walls,")
        print(f"  >>> and removes them — but the edges shouldn't exist in the first place.")
    elif isinstance(nodes, dict) and "exit_south" in nodes:
        print(f"  >>> 'exit_south' IS defined in nodes dict — investigate its definition.")
    else:
        print(f"  >>> Inconclusive — see Step D for cross-file search results.")

    # === STEP J: Final summary ===
    _print_section("STEP J: SUMMARY v3")
    print(f"\nMap file: {MAP_FILE}")
    print(f"File size: {len(raw_text)} chars")
    print(f"Total nodes in nodes dict: {len(nodes) if isinstance(nodes, dict) else 'N/A'}")
    if isinstance(nodes, dict):
        print(f"All node names: {sorted(nodes.keys())}")
    print(f"\nKey findings:")
    print(f"  - 'exit_south' string appears in tavern.json: {raw_text.count('exit_south')} time(s)")
    print(f"  - 'exit_east' string appears in tavern.json: {raw_text.count('exit_east')} time(s)")
    print(f"  - Files containing 'exit_south' elsewhere in project: {len(matches)}")
    print(f"  - adjacency dict: {data.get('adjacency')}")
    print(f"  - passages list: {len(data.get('passages', []))} items")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"\n[FATAL] {type(e).__name__}: {e}")
        traceback.print_exc()
        sys.exit(1)
