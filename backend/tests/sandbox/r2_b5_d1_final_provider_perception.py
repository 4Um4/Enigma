# backend/tests/sandbox/r2_b5_d1_final_provider_perception.py
"""
R2-B5-D1 FINAL PROVIDER AND PERCEPTION PROBE.

Цель: Установить, почему maid_lusya не становится listener для PLAYER_INSULTS,
      несмотря на существующий production wiring.

Этапы:
  A. game_loop.py — полная реализация _get_spatial_query_for_subscriber()
     + все четыре места передачи provider и их назначение.
  B. PerceptualKernel — реальный production-файл (НЕ probe/test/mock),
     полная реализация can_observe().
  C. Runtime verification — на реальном обработчике PLAYER_INSULTS
     захватить 9 значений: provider callable, результат вызова, тип,
     npc_positions, runtime distance, event.radius, can_observe, listeners,
     вызов BeliefRevisionEngine для Люси.
  D. Вердикт — один из четырёх:
       1. provider возвращает None
       2. provider возвращает неактуальный сервис
       3. can_observe исключает Люсю
       4. другая причина с доказанной трассировкой

ОГРАНИЧЕНИЯ:
  - Production не менять.
  - Радиусы не менять.
  - NPC не перемещать.
  - Fallback не расширять.
  - B5-D2 не трогать.
  - Не создавать новый SpatialQueryService.

READ-ONLY. Production-код не менять.
"""
from __future__ import annotations

import os
import sys
import json
import math
import types
import inspect
import traceback
import io
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

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

# Output directory — write into /home/z/my-project/download on this sandbox,
# but Master runs the probe on their local Windows machine; the path is
# resolved defensively below.
OUT_FILE_DIR = Path("/home/z/my-project/download")
if not OUT_FILE_DIR.exists() or not OUT_FILE_DIR.is_dir():
    OUT_FILE_DIR = _BACKEND / "tests" / "sandbox"
    try:
        OUT_FILE_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        OUT_FILE_DIR = Path(os.getcwd())
OUT_FILE = OUT_FILE_DIR / "r2_b5_d1_final_provider_perception.txt"


# ----------------------------------------------------------------------------
# TeeStream — write to both real stdout and an in-memory buffer for file output
# ----------------------------------------------------------------------------
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


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------
def _is_production_file(path: Path) -> bool:
    """Return True if path is a production source file (not a probe/test/mock)."""
    if not path.exists():
        return False
    parts_lower = [p.lower() for p in path.parts]
    # Skip vendored / generated / cache
    for bad in (".venv", "node_modules", ".git", "__pycache__", "site-packages"):
        if bad in parts_lower:
            return False
    # Skip tests, sandbox, probes
    fname = path.name.lower()
    if fname.startswith("test_") or fname.endswith("_test.py"):
        return False
    if "sandbox" in parts_lower:
        return False
    if fname.startswith("r2_"):
        return False
    if any(tok in fname for tok in ("probe", "mock", "stub", "fake", "fixture")):
        return False
    # Path-level filter: tests/ directory
    for p in parts_lower:
        if p == "tests":
            return False
    return True


def _find_function_bounds(src: str, func_name: str) -> Optional[Tuple[int, int]]:
    """
    Find the start/end line indices (0-based, end-exclusive) of a function
    named `func_name` in source `src`. Handles both module-level (`def foo()`)
    and method-level (`    def foo()`) definitions.
    """
    lines = src.split("\n")
    func_start = None
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith("def ") and func_name in stripped.split("(")[0]:
            func_start = i
            break
    if func_start is None:
        return None
    indent_of_def = len(lines[func_start]) - len(lines[func_start].lstrip())
    func_end = len(lines)
    for j in range(func_start + 1, len(lines)):
        line = lines[j]
        if line.strip() == "":
            continue
        cur_indent = len(line) - len(line.lstrip())
        if cur_indent <= indent_of_def and (
            line.lstrip().startswith("def ")
            or line.lstrip().startswith("class ")
            or line.lstrip().startswith("@")
        ):
            func_end = j
            break
    return func_start, func_end


def _read_file_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return f"[read error: {e}]"


def _grep_in_dir(
    directory: Path,
    patterns: List[str],
    production_only: bool = True,
) -> List[Tuple[Path, int, str]]:
    out: List[Tuple[Path, int, str]] = []
    if not directory.exists():
        return out
    for f in directory.rglob("*"):
        if not f.is_file() or f.suffix.lower() != ".py":
            continue
        if production_only and not _is_production_file(f):
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


def _find_files_matching(
    directory: Path,
    match_predicate: Callable[[str], bool],
    production_only: bool = True,
) -> List[Path]:
    out: List[Path] = []
    if not directory.exists():
        return out
    for f in directory.rglob("*.py"):
        if production_only and not _is_production_file(f):
            continue
        try:
            src = f.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        if match_predicate(src):
            out.append(f)
    return out


def _resolve_callable_target(obj: Any) -> Tuple[str, Optional[object]]:
    """
    Resolve a callable to its underlying bound method / closure target.
    Returns (description, underlying_object_or_None).
    """
    if obj is None:
        return ("None", None)
    # bound method?
    self_obj = getattr(obj, "__self__", None)
    if self_obj is not None:
        cls = type(self_obj).__name__
        method_name = getattr(obj, "__name__", "?")
        return (f"bound method {cls}.{method_name}", self_obj)
    # lambda / closure?
    if hasattr(obj, "__closure__") and obj.__closure__:
        cells = []
        for cell in obj.__closure__:
            try:
                val = cell.cell_contents
                cells.append(f"{type(val).__name__}({id(val)})")
            except ValueError:
                cells.append("<empty>")
        name = getattr(obj, "__name__", "?")
        return (f"closure {name} cells=[{', '.join(cells)}]", None)
    name = getattr(obj, "__name__", "?")
    return (f"plain callable {name}", None)


# ============================================================================
# STAGE A: game_loop.py — _get_spatial_query_for_subscriber()
# + all four places where provider is passed
# ============================================================================
def stage_a_game_loop_provider() -> Dict[str, Any]:
    _print_section(
        "STAGE A: game_loop.py — _get_spatial_query_for_subscriber() + 4 provider wiring sites"
    )
    result: Dict[str, Any] = {"stage": "A", "pass": False}

    # ---- A.1: locate game_loop.py (NOT game_loop_builder.py) ----
    print("\n--- A.1: locate production game_loop.py ---")
    candidates: List[Path] = []
    for f in _BACKEND.rglob("*.py"):
        if not _is_production_file(f):
            continue
        if f.name == "game_loop.py":
            candidates.append(f)

    if not candidates:
        # Maybe there is a package game_loop/ — fall back to game_loop_builder.py
        print("  [game_loop.py NOT FOUND — falling back to game_loop_builder.py and similar]")
        for f in _BACKEND.rglob("*.py"):
            if not _is_production_file(f):
                continue
            if "game_loop" in f.name.lower() and f.suffix.lower() == ".py":
                candidates.append(f)

    for c in candidates:
        try:
            rel = c.relative_to(_BACKEND)
        except Exception:
            rel = c
        print(f"  candidate: {rel}")

    # ---- A.2: search for _get_spatial_query_for_subscriber in all production files ----
    print("\n--- A.2: search for _get_spatial_query_for_subscriber in production files ---")
    sqs_results = _grep_in_dir(
        _BACKEND,
        ["_get_spatial_query_for_subscriber", "_get_spatial_query"],
        production_only=True,
    )
    found_in: List[Tuple[Path, int, str]] = []
    for path, ln, line in sqs_results:
        try:
            rel = path.relative_to(_BACKEND)
        except Exception:
            rel = path
        print(f"  {rel} L{ln}: {line}")
        found_in.append((path, ln, line))

    # ---- A.3: read full implementation of _get_spatial_query_for_subscriber ----
    print("\n--- A.3: full implementation of _get_spatial_query_for_subscriber ---")
    target_path: Optional[Path] = None
    target_func_name: Optional[str] = None
    for path, _ln, line in found_in:
        if "def _get_spatial_query_for_subscriber" in line:
            target_path = path
            target_func_name = "_get_spatial_query_for_subscriber"
            break
    if target_path is None:
        # Try alternate name _get_spatial_query (without _for_subscriber suffix)
        for path, _ln, line in found_in:
            if "def _get_spatial_query" in line:
                target_path = path
                target_func_name = "_get_spatial_query"
                break

    func_text: Optional[str] = None
    func_bounds: Optional[Tuple[int, int]] = None
    if target_path and target_func_name:
        try:
            rel = target_path.relative_to(_BACKEND)
        except Exception:
            rel = target_path
        print(f"  Found in: {rel}")
        src = _read_file_text(target_path)
        bounds = _find_function_bounds(src, target_func_name)
        if bounds:
            start, end = bounds
            func_bounds = (start, end)
            lines_arr = src.split("\n")
            func_lines = lines_arr[start:end]
            func_text = "\n".join(func_lines)
            print(f"  Function spans L{start + 1}..L{end} ({end - start} lines):")
            print()
            for i, line in enumerate(func_lines, start=start + 1):
                print(f"  L{i:4d}: {line}")
            print()
        else:
            print(f"  [function {target_func_name} not parsed; dumping file head]")
            for i, line in enumerate(src.split("\n")[:200], 1):
                print(f"  L{i:4d}: {line}")
    else:
        print("  [function not found — _get_spatial_query_for_subscriber absent]")

    # ---- A.4: analysis of return value, source, None conditions, lifecycle, npc_positions freshness ----
    print("\n--- A.4: static analysis of provider (return value, source, None conditions, lifecycle, npc_positions freshness) ---")
    analysis = {
        "function_found": target_path is not None,
        "function_name": target_func_name,
        "file": str(target_path.relative_to(_BACKEND)) if target_path else None,
        "return_value_kind": None,
        "source_of_spatial_service": None,
        "none_conditions": [],
        "lifecycle_note": None,
        "npc_positions_freshness": None,
    }
    if func_text:
        # Heuristic detection
        low = func_text.lower()
        if "return self." in low or "return self._" in low:
            analysis["return_value_kind"] = "instance attribute (likely callable returning SpatialQueryService)"
        if "lambda" in low:
            analysis["return_value_kind"] = (analysis["return_value_kind"] or "") + " lambda wrapper"
        if "none" in low:
            # extract lines containing 'none'
            for line in func_text.split("\n"):
                if "none" in line.lower():
                    analysis["none_conditions"].append(line.strip())
        if "spatial_service" in low or "spatial_query_service" in low:
            analysis["source_of_spatial_service"] = "loop attribute or service factory"
        if "scene_state" in low or "npc_positions" in low:
            analysis["npc_positions_freshness"] = "likely reads live scene_state['npc_positions']"
        # Try actually importing and inspecting the bound method on a built loop
        print(f"  function_found: {analysis['function_found']}")
        print(f"  function_name: {analysis['function_name']}")
        print(f"  file: {analysis['file']}")
        print(f"  return_value_kind: {analysis['return_value_kind']}")
        print(f"  source_of_spatial_service: {analysis['source_of_spatial_service']}")
        print(f"  none_conditions: {analysis['none_conditions']}")
        print(f"  lifecycle_note: {analysis['lifecycle_note']}")
        print(f"  npc_positions_freshness: {analysis['npc_positions_freshness']}")
    else:
        print("  [no function text to analyze]")

    # ---- A.5: all four places where provider is passed ----
    print("\n--- A.5: all four provider-passing sites ---")
    provider_results = _grep_in_dir(
        _BACKEND,
        [
            "spatial_query_provider=",
            "spatial_query_provider =",
            "_get_spatial_query=",
            "_get_spatial_query =",
            "spatial_query=lambda",
            "spatial_query_service=",
        ],
        production_only=True,
    )
    wiring_sites: List[Dict[str, Any]] = []
    seen_files: Dict[str, int] = {}
    for path, ln, line in provider_results:
        try:
            rel = path.relative_to(_BACKEND)
        except Exception:
            rel = path
        key = str(rel)
        seen_files[key] = seen_files.get(key, 0) + 1
        # Read context: 5 lines before, 5 after
        try:
            src = _read_file_text(path)
            lines_arr = src.split("\n")
            ctx_start = max(0, ln - 6)
            ctx_end = min(len(lines_arr), ln + 6)
            print(f"\n  >>> {rel} L{ln}: {line.strip()}")
            print(f"  --- context L{ctx_start + 1}..L{ctx_end} ---")
            for j in range(ctx_start, ctx_end):
                marker = ">>>" if j + 1 == ln else "   "
                print(f"  {marker} L{j+1:4d}: {lines_arr[j]}")
            wiring_sites.append(
                {
                    "file": key,
                    "line": ln,
                    "snippet": line.strip(),
                }
            )
        except Exception as e:
            print(f"  [context read error: {e}]")

    print(f"\n  Total provider-passing sites found: {len(wiring_sites)}")
    for site in wiring_sites:
        print(f"    {site['file']} L{site['line']}: {site['snippet']}")

    # ---- A.6: the ClaimEventSubscriber constructor signature ----
    print("\n--- A.6: ClaimEventSubscriber.__init__ signature ---")
    ces_path = _BACKEND / "app" / "services" / "events" / "claim_event_subscriber.py"
    if ces_path.exists():
        try:
            src = _read_file_text(ces_path)
            bounds = _find_function_bounds(src, "__init__")
            if bounds:
                start, end = bounds
                lines_arr = src.split("\n")
                print(f"  __init__ at L{start + 1}..L{end}:")
                for j in range(start, end):
                    print(f"  L{j+1:4d}: {lines_arr[j]}")
            else:
                print("  [__init__ not found]")
        except Exception as e:
            print(f"  [read error: {e}]")
    else:
        print(f"  [file not found: {ces_path}]")

    result["pass"] = True
    result["target_func_name"] = target_func_name
    result["target_path"] = str(target_path) if target_path else None
    result["func_text"] = func_text
    result["analysis"] = analysis
    result["wiring_sites"] = wiring_sites
    return result


# ============================================================================
# STAGE B: real production PerceptualKernel.can_observe()
# ============================================================================
def stage_b_perceptual_kernel() -> Dict[str, Any]:
    _print_section(
        "STAGE B: real production PerceptualKernel.can_observe() — skip probe/test/mock"
    )
    result: Dict[str, Any] = {"stage": "B", "pass": False}

    # ---- B.1: find ALL files containing PerceptualKernel class or can_observe def ----
    print("\n--- B.1: locate all production files defining PerceptualKernel / can_observe ---")
    matches = _find_files_matching(
        _BACKEND,
        lambda src: ("class PerceptualKernel" in src) or ("def can_observe" in src),
        production_only=True,
    )
    pk_files: List[Path] = []
    for f in matches:
        try:
            rel = f.relative_to(_BACKEND)
        except Exception:
            rel = f
        print(f"  production match: {rel}")
        pk_files.append(f)

    if not pk_files:
        print("  [NO production PerceptualKernel found]")
        result["error"] = "PerceptualKernel not found in production"
        return result

    # ---- B.2: read the production PerceptualKernel class ----
    print("\n--- B.2: read PerceptualKernel class from production file ---")
    pk_path = pk_files[0]
    try:
        rel = pk_path.relative_to(_BACKEND)
    except Exception:
        rel = pk_path
    print(f"  chosen file: {rel}")

    src = _read_file_text(pk_path)
    lines_arr = src.split("\n")

    # Locate class PerceptualKernel
    class_start: Optional[int] = None
    for i, line in enumerate(lines_arr):
        if line.startswith("class PerceptualKernel"):
            class_start = i
            break
    if class_start is None:
        print("  [class PerceptualKernel not at column 0; trying indented]")
        for i, line in enumerate(lines_arr):
            if "class PerceptualKernel" in line:
                class_start = i
                break

    if class_start is None:
        print("  [class PerceptualKernel not found in chosen file]")
        result["error"] = "class not found"
        return result

    # Determine class end
    class_indent = len(lines_arr[class_start]) - len(lines_arr[class_start].lstrip())
    class_end = len(lines_arr)
    for j in range(class_start + 1, len(lines_arr)):
        line = lines_arr[j]
        if line.strip() == "":
            continue
        cur_indent = len(line) - len(line.lstrip())
        if cur_indent <= class_indent and (
            line.lstrip().startswith("class ") or line.lstrip().startswith("def ")
        ):
            class_end = j
            break

    print(f"\n  class PerceptualKernel spans L{class_start + 1}..L{class_end}:")
    for j in range(class_start, class_end):
        print(f"  L{j+1:4d}: {lines_arr[j]}")

    # ---- B.3: read full can_observe method ----
    print("\n--- B.3: full can_observe method ---")
    can_observe_bounds: Optional[Tuple[int, int]] = None
    for i, line in enumerate(lines_arr[class_start:class_end], start=class_start):
        if "def can_observe" in line:
            sub_start = i
            sub_indent = len(line) - len(line.lstrip())
            sub_end = class_end
            for k in range(sub_start + 1, class_end):
                l = lines_arr[k]
                if l.strip() == "":
                    continue
                cur_indent = len(l) - len(l.lstrip())
                if cur_indent <= sub_indent and l.lstrip().startswith("def "):
                    sub_end = k
                    break
            can_observe_bounds = (sub_start, sub_end)
            break

    if can_observe_bounds:
        s, e = can_observe_bounds
        print(f"  can_observe at L{s + 1}..L{e}:")
        for j in range(s, e):
            print(f"  L{j+1:4d}: {lines_arr[j]}")
    else:
        print("  [can_observe not found in PerceptualKernel class]")

    # ---- B.4: detect radius source, event.radius usage, HEARING_RADIUS, additional filters, False conditions ----
    print("\n--- B.4: radius semantics — source of radius, event.radius, HEARING_RADIUS, additional filters, False conditions ---")
    semantics = {
        "radius_source": None,
        "uses_event_radius": False,
        "uses_hearing_radius_constant": False,
        "additional_filters": [],
        "false_conditions": [],
    }
    if can_observe_bounds:
        s, e = can_observe_bounds
        method_lines = lines_arr[s:e]
        method_text = "\n".join(method_lines)
        # HEARING_RADIUS
        if "HEARING_RADIUS" in method_text:
            semantics["uses_hearing_radius_constant"] = True
            for ml in method_lines:
                if "HEARING_RADIUS" in ml:
                    semantics["radius_source"] = f"HEARING_RADIUS constant ({ml.strip()})"
                    break
        # event.radius / payload.get('radius')
        if "event.radius" in method_text or "event.radius" in method_text:
            semantics["uses_event_radius"] = True
        if "payload" in method_text and "radius" in method_text:
            semantics["uses_event_radius"] = True
        # return False lines
        for ml in method_lines:
            stripped = ml.strip()
            if stripped.startswith("return False") or "return False" in stripped:
                semantics["false_conditions"].append(stripped)
            # Heuristic for additional filters
            if "if " in stripped and "return False" not in stripped:
                # capture filter-like ifs
                if any(t in stripped.lower() for t in ("location", "scene", "alive", "conscious", "visible", "same_", "loc")):
                    semantics["additional_filters"].append(stripped)

    print(f"  radius_source: {semantics['radius_source']}")
    print(f"  uses_event_radius: {semantics['uses_event_radius']}")
    print(f"  uses_hearing_radius_constant: {semantics['uses_hearing_radius_constant']}")
    print(f"  additional_filters: {semantics['additional_filters']}")
    print(f"  false_conditions: {semantics['false_conditions']}")

    # ---- B.5: search for HEARING_RADIUS definition site (production only) ----
    print("\n--- B.5: HEARING_RADIUS definition site ---")
    hr_results = _grep_in_dir(_BACKEND, ["HEARING_RADIUS"], production_only=True)
    for path, ln, line in hr_results:
        try:
            rel = path.relative_to(_BACKEND)
        except Exception:
            rel = path
        if "=" in line and "HEARING_RADIUS" in line and not line.strip().startswith("#"):
            print(f"  {rel} L{ln}: {line}")

    result["pass"] = True
    result["pk_path"] = str(pk_path.relative_to(_BACKEND))
    result["can_observe_bounds"] = (
        (can_observe_bounds[0] + 1, can_observe_bounds[1]) if can_observe_bounds else None
    )
    result["semantics"] = semantics
    return result


# ============================================================================
# STAGE C: Runtime verification — capture 9 values on real PLAYER_INSULTS handler
# ============================================================================
def stage_c_runtime_verification() -> Dict[str, Any]:
    _print_section(
        "STAGE C: Runtime verification — 9 values on real PLAYER_INSULTS handler"
    )
    result: Dict[str, Any] = {"stage": "C", "pass": False}

    try:
        from app.services.game_loop_builder import build_game_loop
        from app.services.events.event_bus import get_event_bus
        from app.services.events.event_types import EventType
        from app.domain.events import EventDTO
        from app.services.events.claim_event_subscriber import ClaimEventSubscriber
        import tempfile

        saves_dir = Path(tempfile.mkdtemp(prefix="r2_b5_d1_final_"))
        settings.saves_dir = str(saves_dir)
        settings.environment = "development"

        loop = build_game_loop(data_dir=Path(settings.data_dir))
        scene = loop.scene_manager.get_scene_state("Open_road", "tavern")
        if scene is None:
            scene = loop.scene_manager.initialize_scene("Open_road", "tavern", "12:00")

        # ---- C.0: locate the real ClaimEventSubscriber instance ----
        print("\n--- C.0: locate real ClaimEventSubscriber instance ---")
        sub: Optional[ClaimEventSubscriber] = None
        # Strategy: walk event bus subscribers
        bus = get_event_bus()
        for attr in ("_subscribers", "_handlers", "_callbacks", "_listeners"):
            if not hasattr(bus, attr):
                continue
            container = getattr(bus, attr)
            if isinstance(container, dict):
                for ev_type, cbs in container.items():
                    if cbs is None:
                        continue
                    try:
                        iter_cbs = list(cbs)
                    except TypeError:
                        iter_cbs = [cbs]
                    for cb in iter_cbs:
                        target_obj = getattr(cb, "__self__", None)
                        if target_obj and isinstance(target_obj, ClaimEventSubscriber):
                            sub = target_obj
                            print(f"  found via bus.{attr}[{ev_type}]: ClaimEventSubscriber id={id(sub)}")
                            break
                    if sub:
                        break
            if sub:
                break
        # Strategy 2: walk loop attributes
        if sub is None:
            for attr_name in sorted(dir(loop)):
                if attr_name.startswith("__"):
                    continue
                try:
                    val = getattr(loop, attr_name)
                except Exception:
                    continue
                if isinstance(val, ClaimEventSubscriber):
                    sub = val
                    print(f"  found via loop.{attr_name}: id={id(sub)}")
                    break
                if hasattr(val, "__dict__"):
                    for k2, v2 in vars(val).items():
                        if isinstance(v2, ClaimEventSubscriber):
                            sub = v2
                            print(f"  found via loop.{attr_name}.{k2}: id={id(sub)}")
                            break
                    if sub:
                        break
        # Strategy 3: walk tick_orch and _svc
        if sub is None:
            for parent_name in ("_tick_orch", "_svc", "_tick_orchestrator"):
                parent = getattr(loop, parent_name, None)
                if parent is None:
                    continue
                for attr_name in sorted(dir(parent)):
                    if attr_name.startswith("__"):
                        continue
                    try:
                        val = getattr(parent, attr_name)
                    except Exception:
                        continue
                    if isinstance(val, ClaimEventSubscriber):
                        sub = val
                        print(f"  found via loop.{parent_name}.{attr_name}: id={id(sub)}")
                        break
                    if hasattr(val, "__dict__"):
                        for k2, v2 in vars(val).items():
                            if isinstance(v2, ClaimEventSubscriber):
                                sub = v2
                                print(f"  found via loop.{parent_name}.{attr_name}.{k2}: id={id(sub)}")
                                break
                        if sub:
                            break
                if sub:
                    break

        if sub is None:
            print("  [ClaimEventSubscriber NOT FOUND in runtime]")
            result["error"] = "subscriber not found"
            return result

        print(f"\n  Subscriber confirmed: id={id(sub)}, type={type(sub).__name__}")
        # Check _engine and _store
        engine = getattr(sub, "_engine", None)
        store = getattr(sub, "_store", None)
        print(f"  sub._engine: {engine} ({type(engine).__name__ if engine else 'None'})")
        print(f"  sub._store:  {store} ({type(store).__name__ if store else 'None'})")

        # ---- C.1: spy on on_claim_event AND on BeliefRevisionEngine ----
        print("\n--- C.1: attach spy on on_claim_event + BeliefRevisionEngine ---")

        captured: Dict[str, Any] = {}

        # Spy on BeliefRevisionEngine — wrap revise/ingest methods
        engine_calls: List[Dict[str, Any]] = []
        if engine is not None:
            for method_name in ("revise", "ingest_claim", "add_claim", "ingest", "update", "consider"):
                orig_method = getattr(engine, method_name, None)
                if orig_method is None or not callable(orig_method):
                    continue
                # Build closure capturing orig_method + method_name
                def _make_spy(orig, name):
                    def _spy(*args, **kwargs):
                        try:
                            args_repr = []
                            for a in args:
                                try:
                                    args_repr.append(repr(a)[:200])
                                except Exception:
                                    args_repr.append("<unrepr>")
                            kwargs_repr = {k: repr(v)[:200] for k, v in kwargs.items()}
                            engine_calls.append(
                                {
                                    "method": name,
                                    "args": args_repr,
                                    "kwargs": kwargs_repr,
                                }
                            )
                        except Exception:
                            pass
                        return orig(*args, **kwargs)
                    return _spy
                try:
                    setattr(engine, method_name, _make_spy(orig_method, method_name))
                    print(f"  spy attached: engine.{method_name}")
                except Exception as e:
                    print(f"  [cannot spy engine.{method_name}: {e}]")

        # Spy on BeliefRevisionEngine via store.add_record / store.update if needed
        store_calls: List[Dict[str, Any]] = []
        if store is not None:
            for method_name in ("add_record", "add_belief", "update", "store", "set_belief", "ingest"):
                orig_method = getattr(store, method_name, None)
                if orig_method is None or not callable(orig_method):
                    continue

                def _make_store_spy(orig, name):
                    def _spy(*args, **kwargs):
                        try:
                            args_repr = []
                            for a in args:
                                try:
                                    args_repr.append(repr(a)[:200])
                                except Exception:
                                    args_repr.append("<unrepr>")
                            store_calls.append({"method": name, "args": args_repr})
                        except Exception:
                            pass
                        return orig(*args, **kwargs)
                    return _spy
                try:
                    setattr(store, method_name, _make_store_spy(orig_method, method_name))
                    print(f"  spy attached: store.{method_name}")
                except Exception as e:
                    print(f"  [cannot spy store.{method_name}: {e}]")

        # Spy on on_claim_event
        orig_on_claim = sub.on_claim_event

        def _spy_on_claim(event):
            payload = getattr(event, "payload", {}) or {}
            captured["event_source"] = getattr(event, "source", "?")
            captured["event_type"] = str(getattr(event, "type", "?"))
            captured["payload_action_type"] = payload.get("action_type")
            captured["payload_target_id"] = payload.get("target_id")
            captured["payload_radius"] = payload.get("radius")  # Value 6: event.radius
            captured["payload_location"] = payload.get("location")
            captured["has_proposition_in_payload"] = bool(payload.get("proposition"))

            # Value 1: Provider callable
            provider = getattr(sub, "_get_spatial_query", None)
            captured["provider_callable"] = provider is not None and callable(provider)
            captured["provider_repr"] = repr(provider)
            captured["provider_description"], captured["provider_underlying"] = _resolve_callable_target(provider)
            # Strip non-serializable underlying object
            captured.pop("provider_underlying", None)

            # Value 2: Result of calling provider
            sq = None
            if captured["provider_callable"]:
                try:
                    sq = provider()
                except Exception as e:
                    captured["provider_call_error"] = f"{type(e).__name__}: {e}"
            captured["provider_call_result"] = sq

            # Value 3: Type of returned object
            if sq is not None:
                captured["provider_result_type"] = type(sq).__name__
                captured["provider_result_id"] = id(sq)
                # Inspect attributes
                captured["provider_result_module"] = getattr(type(sq), "__module__", "?")
                captured["provider_result_file"] = inspect.getfile(type(sq)) if hasattr(type(sq), "__module__") else "?"
            else:
                captured["provider_result_type"] = "None"
                captured["provider_result_id"] = None

            # Value 4: Actual npc_positions list
            sq_npc_pos: Dict[str, Any] = {}
            if sq is not None:
                sq_npc_pos = getattr(sq, "_npc_positions", {}) or {}
            captured["sq_npc_positions_keys"] = list(sq_npc_pos.keys())
            captured["sq_npc_positions_count"] = len(sq_npc_pos)

            # Try to extract coords
            captured["sq_player_pos"] = None
            captured["sq_lusya_pos"] = None
            if sq_npc_pos:
                # Player
                player_data = sq_npc_pos.get("player")
                if player_data is not None:
                    captured["sq_player_pos"] = _safe_pos(player_data)
                # maid_lusya
                lusya_data = sq_npc_pos.get("maid_lusya")
                if lusya_data is not None:
                    captured["sq_lusya_pos"] = _safe_pos(lusya_data)

            # Also try scene_state['npc_positions'] (independent of provider)
            scene_npc_pos = scene.get("npc_positions", {}) or {}
            captured["scene_npc_positions_keys"] = list(scene_npc_pos.keys())
            captured["scene_player_pos"] = _safe_pos(scene_npc_pos.get("player"))
            captured["scene_lusya_pos"] = _safe_pos(scene_npc_pos.get("maid_lusya"))

            # Value 5: Runtime distance player → maid_lusya
            distance_value = None
            distance_source = None
            # Try sq.distance
            if sq is not None and hasattr(sq, "distance"):
                try:
                    distance_value = sq.distance("player", "maid_lusya")
                    distance_source = "sq.distance(player, maid_lusya)"
                except Exception as e:
                    captured["sq_distance_error"] = f"{type(e).__name__}: {e}"
            # Manual computation
            player_pos = captured.get("sq_player_pos") or captured.get("scene_player_pos")
            lusya_pos = captured.get("sq_lusya_pos") or captured.get("scene_lusya_pos")
            if player_pos and lusya_pos:
                try:
                    px, py = float(player_pos["x"]), float(player_pos["y"])
                    lx, ly = float(lusya_pos["x"]), float(lusya_pos["y"])
                    manual = math.hypot(px - lx, py - ly)
                    captured["manual_distance_player_lusya"] = manual
                    captured["manual_distance_detail"] = {
                        "px": px, "py": py, "lx": lx, "ly": ly,
                        "dx": px - lx, "dy": py - ly,
                    }
                    if distance_value is None:
                        distance_value = manual
                        distance_source = "manual hypot"
                except Exception as e:
                    captured["manual_distance_error"] = f"{type(e).__name__}: {e}"
            captured["runtime_distance_player_lusya"] = distance_value
            captured["runtime_distance_source"] = distance_source

            # Value 7: can_observe result for maid_lusya
            can_observe_result = None
            can_observe_error = None
            try:
                # Find production PerceptualKernel
                pk_files = _find_files_matching(
                    _BACKEND,
                    lambda s: ("class PerceptualKernel" in s),
                    production_only=True,
                )
                if pk_files:
                    pk_path = pk_files[0]
                    # Import dynamically
                    import importlib.util
                    spec = importlib.util.spec_from_file_location(
                        f"_pk_probe_{pk_path.stem}", pk_path
                    )
                    if spec and spec.loader:
                        pk_mod = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(pk_mod)
                        PerceptualKernel = getattr(pk_mod, "PerceptualKernel", None)
                        if PerceptualKernel is not None:
                            # Try both classmethod / staticmethod / instance call patterns
                            try:
                                can_observe_result = PerceptualKernel.can_observe(
                                    event,
                                    distance_value if isinstance(distance_value, (int, float)) else 999.0,
                                    "maid_lusya",
                                    payload.get("target_id"),
                                )
                            except TypeError:
                                # Maybe signature differs
                                try:
                                    sig = inspect.signature(PerceptualKernel.can_observe)
                                    captured["can_observe_signature"] = str(sig)
                                except Exception:
                                    pass
                                try:
                                    can_observe_result = PerceptualKernel.can_observe(event)
                                except Exception as e2:
                                    can_observe_error = f"TypeError then {type(e2).__name__}: {e2}"
                            except Exception as e:
                                can_observe_error = f"{type(e).__name__}: {e}"
                else:
                    can_observe_error = "PerceptualKernel production file not found"
            except Exception as e:
                can_observe_error = f"{type(e).__name__}: {e}"
            captured["can_observe_maid_lusya"] = can_observe_result
            captured["can_observe_error"] = can_observe_error

            # Save pre-call engine calls count
            captured["engine_calls_before_on_claim"] = len(engine_calls)

            # Call original on_claim_event — this may populate listeners, call engine, etc.
            try:
                orig_return = orig_on_claim(event)
                captured["on_claim_event_return"] = repr(orig_return)[:200]
            except Exception as e:
                captured["on_claim_event_error"] = f"{type(e).__name__}: {e}"

            # Value 8: Final listeners
            # The listeners list is local to on_claim_event — we need to capture it differently.
            # Try to read it via store / engine changes.
            # If the engine was called for maid_lusya, that means she was a listener.
            captured["engine_calls_after_on_claim"] = len(engine_calls)
            captured["engine_calls_delta"] = (
                captured["engine_calls_after_on_claim"]
                - captured["engine_calls_before_on_claim"]
            )

            # Inspect engine calls for maid_lusya
            lusya_calls = []
            for call in engine_calls[captured["engine_calls_before_on_claim"]:]:
                args_str = " ".join(call.get("args", []))
                if "maid_lusya" in args_str:
                    lusya_calls.append(call)
            captured["engine_calls_for_lusya"] = lusya_calls

            # Also inspect store calls
            lusya_store_calls = []
            for call in store_calls:
                args_str = " ".join(call.get("args", []))
                if "maid_lusya" in args_str:
                    lusya_store_calls.append(call)
            captured["store_calls_for_lusya"] = lusya_store_calls

            # Value 9: BeliefRevisionEngine call for Lusya (yes/no + details)
            captured["belief_revision_called_for_lusya"] = len(lusya_calls) > 0 or len(lusya_store_calls) > 0
            if captured["belief_revision_called_for_lusya"]:
                captured["lusya_call_count"] = len(lusya_calls) + len(lusya_store_calls)
                captured["lusya_call_samples"] = (lusya_calls + lusya_store_calls)[:3]
            else:
                captured["lusya_call_count"] = 0

            # Also inspect EpistemicStore directly
            if store is not None:
                # try get_all_for_agent
                try:
                    lusya_records = store.get_all_for_agent("maid_lusya")
                    captured["epistemic_records_for_lusya_after"] = len(lusya_records)
                    captured["lusya_records_sample"] = []
                    for r in lusya_records[:3]:
                        try:
                            captured["lusya_records_sample"].append(
                                {
                                    "proposition": str(getattr(r, "proposition", "?")),
                                    "confidence": getattr(r, "confidence", "?"),
                                    "source_id": getattr(r, "source_id", "?"),
                                }
                            )
                        except Exception:
                            captured["lusya_records_sample"].append({"repr": repr(r)[:200]})
                except Exception as e:
                    captured["epistemic_get_all_error"] = f"{type(e).__name__}: {e}"

            return orig_return

        sub.on_claim_event = _spy_on_claim
        print("  spy attached: sub.on_claim_event")

        # Clear bus
        try:
            bus.clear()
        except Exception:
            pass

        # Publish real PLAYER_INSULTS
        payload = {
            "action_type": "player_insults",
            "target_id": "tavern_keeper_tornin",
            "content": "оскорбление",
            "event_tick": 1,
            "visibility": "public",
            "radius": 999.0,
            "location": "tavern",
            "campaign_id": "Open_road",
            "raw_input": "оскорбление",
        }
        evt = EventDTO.create(
            event_type=EventType.PLAYER_INSULTS,
            source="player",
            payload=payload,
            persistence_level="working",
        )

        print(f"\n--- Publishing PLAYER_INSULTS ---")
        print(f"  event.source={evt.source}, payload.target_id={payload['target_id']}, payload.radius={payload['radius']}")
        bus.publish(evt)

        # If on_player_spoke is the subscriber's entry, we may need to also publish PLAYER_SPOKE
        # But PLAYER_INSULTS is what was specified by the user.

        # Restore original on_claim_event
        sub.on_claim_event = orig_on_claim

        # ---- C.2: print all 9 captured values ----
        print(f"\n--- C.2: captured 9 runtime values ---")
        ordered_keys = [
            ("1. provider_callable", "provider_callable"),
            ("1. provider_repr", "provider_repr"),
            ("1. provider_description", "provider_description"),
            ("2. provider_call_result", "provider_call_result"),
            ("2. provider_call_error", "provider_call_error"),
            ("3. provider_result_type", "provider_result_type"),
            ("3. provider_result_id", "provider_result_id"),
            ("3. provider_result_module", "provider_result_module"),
            ("3. provider_result_file", "provider_result_file"),
            ("4. sq_npc_positions_count", "sq_npc_positions_count"),
            ("4. sq_npc_positions_keys", "sq_npc_positions_keys"),
            ("4. sq_player_pos", "sq_player_pos"),
            ("4. sq_lusya_pos", "sq_lusya_pos"),
            ("4. scene_npc_positions_keys", "scene_npc_positions_keys"),
            ("4. scene_player_pos", "scene_player_pos"),
            ("4. scene_lusya_pos", "scene_lusya_pos"),
            ("5. runtime_distance_player_lusya", "runtime_distance_player_lusya"),
            ("5. runtime_distance_source", "runtime_distance_source"),
            ("5. manual_distance_player_lusya", "manual_distance_player_lusya"),
            ("5. manual_distance_detail", "manual_distance_detail"),
            ("6. payload_radius (event.radius)", "payload_radius"),
            ("7. can_observe_maid_lusya", "can_observe_maid_lusya"),
            ("7. can_observe_error", "can_observe_error"),
            ("7. can_observe_signature", "can_observe_signature"),
            ("8. listeners (indirect via engine calls)", "engine_calls_delta"),
            ("8. engine_calls_for_lusya", "engine_calls_for_lusya"),
            ("9. belief_revision_called_for_lusya", "belief_revision_called_for_lusya"),
            ("9. lusya_call_count", "lusya_call_count"),
            ("9. lusya_call_samples", "lusya_call_samples"),
            ("9. epistemic_records_for_lusya_after", "epistemic_records_for_lusya_after"),
            ("9. lusya_records_sample", "lusya_records_sample"),
            ("on_claim_event_return", "on_claim_event_return"),
            ("on_claim_event_error", "on_claim_event_error"),
        ]
        for label, key in ordered_keys:
            if key in captured:
                val = captured[key]
                # Truncate long values
                if isinstance(val, str) and len(val) > 300:
                    val = val[:300] + "...[truncated]"
                print(f"  {label}: {val}")

        # ---- C.3: also dump ALL engine_calls and store_calls for forensics ----
        print(f"\n--- C.3: all engine_calls during PLAYER_INSULTS ---")
        for i, call in enumerate(engine_calls):
            print(f"  [{i}] method={call.get('method')} args={call.get('args')}")
        if not engine_calls:
            print("  (none)")

        print(f"\n--- C.4: all store_calls during PLAYER_INSULTS ---")
        for i, call in enumerate(store_calls):
            print(f"  [{i}] method={call.get('method')} args={call.get('args')}")
        if not store_calls:
            print("  (none)")

        # ---- C.5: cleanup ----
        try:
            ts = loop._get_task_scheduler()
            if hasattr(ts, "_executor_pool"):
                ts._executor_pool.shutdown(wait=False, cancel_futures=True)
        except Exception:
            pass
        del loop
        import gc
        gc.collect()
        import shutil
        shutil.rmtree(saves_dir, ignore_errors=True)

        result["pass"] = True
        result["captured"] = captured
        return result

    except Exception as e:
        print(f"[FATAL: {e}]")
        traceback.print_exc()
        result["error"] = str(e)
        return result


def _safe_pos(data: Any) -> Optional[Dict[str, Any]]:
    """Extract a (x, y, source) dict from a position-like structure."""
    if data is None:
        return None
    out: Dict[str, Any] = {}
    # Try several shapes
    if isinstance(data, dict):
        # Direct x, y
        if "x" in data and "y" in data:
            out["x"] = data.get("x")
            out["y"] = data.get("y")
            out["source"] = "dict(x,y)"
            return out
        # local_position dict
        lp = data.get("local_position")
        if isinstance(lp, dict) and "x" in lp and "y" in lp:
            out["x"] = lp.get("x")
            out["y"] = lp.get("y")
            out["position_node"] = data.get("position")
            out["source"] = "dict(local_position)"
            return out
        # position dict
        pos = data.get("position")
        if isinstance(pos, dict) and "x" in pos and "y" in pos:
            out["x"] = pos.get("x")
            out["y"] = pos.get("y")
            out["source"] = "dict(position)"
            return out
        # tuple-like
        if "local_x" in data and "local_y" in data:
            out["x"] = data.get("local_x")
            out["y"] = data.get("local_y")
            out["source"] = "dict(local_x,local_y)"
            return out
        return {"raw": str(data)[:200]}
    # Object with attributes
    if hasattr(data, "x") and hasattr(data, "y"):
        out["x"] = getattr(data, "x")
        out["y"] = getattr(data, "y")
        out["source"] = "obj(x,y)"
        return out
    return {"raw": repr(data)[:200]}


# ============================================================================
# STAGE D: Verdict — one of 4 confirmed causes
# ============================================================================
def stage_d_verdict(
    stage_a: Dict[str, Any],
    stage_b: Dict[str, Any],
    stage_c: Dict[str, Any],
) -> Dict[str, Any]:
    _print_section("STAGE D: VERDICT — confirmed cause")
    result: Dict[str, Any] = {"stage": "D"}

    captured = stage_c.get("captured", {})
    provider_callable = captured.get("provider_callable", False)
    provider_result_type = captured.get("provider_result_type", "None")
    sq_npc_positions_count = captured.get("sq_npc_positions_count", 0)
    sq_npc_positions_keys = captured.get("sq_npc_positions_keys", [])
    runtime_distance = captured.get("runtime_distance_player_lusya")
    can_observe_result = captured.get("can_observe_maid_lusya")
    can_observe_error = captured.get("can_observe_error")
    belief_revision_called = captured.get("belief_revision_called_for_lusya", False)
    epistemic_records = captured.get("epistemic_records_for_lusya_after", 0)
    semantics = stage_b.get("semantics", {})

    print(f"\n  FACTS:")
    print(f"    provider_callable: {provider_callable}")
    print(f"    provider_result_type: {provider_result_type}")
    print(f"    sq_npc_positions_count: {sq_npc_positions_count}")
    print(f"    sq_npc_positions_keys: {sq_npc_positions_keys}")
    print(f"    runtime_distance_player_lusya: {runtime_distance}")
    print(f"    can_observe_maid_lusya: {can_observe_result}")
    print(f"    can_observe_error: {can_observe_error}")
    print(f"    belief_revision_called_for_lusya: {belief_revision_called}")
    print(f"    epistemic_records_for_lusya_after: {epistemic_records}")
    print(f"    semantics.radius_source: {semantics.get('radius_source')}")
    print(f"    semantics.uses_event_radius: {semantics.get('uses_event_radius')}")
    print(f"    semantics.uses_hearing_radius_constant: {semantics.get('uses_hearing_radius_constant')}")

    # Decision tree
    verdict: str
    rationale: str

    if not provider_callable or provider_result_type == "None":
        verdict = "1. PROVIDER RETURNS None"
        rationale = (
            "ClaimEventSubscriber._get_spatial_query exists but returns None at runtime. "
            "on_claim_event falls back to target_id-only listener list. maid_lusya != target_id "
            "(target_id=tavern_keeper_tornin), so she is not in listeners, no belief created."
        )
    elif sq_npc_positions_count == 0 or "maid_lusya" not in sq_npc_positions_keys or "player" not in sq_npc_positions_keys:
        verdict = "2. PROVIDER RETURNS STALE SERVICE"
        rationale = (
            "Provider returns a non-None object, but its _npc_positions is empty or "
            "missing 'player'/'maid_lusya'. The service is not bound to the live scene_state. "
            "distance(player, maid_lusya) cannot be computed; listeners fall back to target_id-only."
        )
    elif can_observe_result is False or (
        isinstance(runtime_distance, (int, float))
        and runtime_distance > 10.0
        and semantics.get("uses_hearing_radius_constant")
    ):
        verdict = "3. CAN_OBSERVE EXCLUDES LUSYA"
        rationale = (
            f"Provider works (npc_positions has maid_lusya), but can_observe returned "
            f"{can_observe_result}. Runtime distance player↔maid_lusya = {runtime_distance}m. "
            f"PerceptualKernel uses HEARING_RADIUS=10.0; if distance > 10.0, can_observe returns False."
        )
    elif belief_revision_called and epistemic_records > 0:
        verdict = "4. NOT A DEFECT — belief was created"
        rationale = (
            "Provider works, can_observe returns True, listeners list includes maid_lusya, "
            "BeliefRevisionEngine was called for her, and EpistemicStore has records. "
            "The bug is elsewhere — likely in EpistemicContextResolver or downstream consumers."
        )
    else:
        verdict = "4. OTHER CAUSE — needs further tracing"
        rationale = (
            "Provider works and returns live service; can_observe did not return False; "
            "but BeliefRevisionEngine was NOT called for maid_lusya. "
            "Likely the listeners list logic in on_claim_event excludes maid_lusya via a different "
            "filter (e.g., a location/visibility check) or the event payload lacks the proposition "
            "needed to trigger belief creation (B5-D2 territory, but noted here for completeness)."
        )

    print(f"\n  >>> VERDICT: {verdict}")
    print(f"  >>> RATIONALE: {rationale}")

    # ---- Minimal fix plan ----
    print(f"\n  >>> MINIMAL FIX PLAN:")
    if verdict.startswith("1."):
        print(f"    - Locate where ClaimEventSubscriber is constructed in production")
        print(f"      (see Stage A.5 wiring sites — usually game_loop.py or game_loop_builder.py)")
        print(f"    - Pass a provider that returns the live SpatialQueryService bound to scene_state")
        print(f"    - DO NOT create a new SpatialQueryService; re-bind to loop.scene_manager")
    elif verdict.startswith("2."):
        print(f"    - The provider returns a stale SpatialQueryService instance")
        print(f"    - Re-bind it to loop.scene_manager so its _npc_positions stays live")
        print(f"    - Possibly: provider should be `lambda: loop.scene_manager.spatial_query_service`")
    elif verdict.startswith("3."):
        print(f"    - Constraint: радиусы не менять. NPC не перемещать.")
        print(f"    - Without changing radii or moving NPCs, the only fix is the spatial membrane itself")
        print(f"      cannot include maid_lusya at the current distance (10.086m > 10.0m HEARING_RADIUS)")
        print(f"    - RECOMMEND: confirm with Master whether to relax constraint (move NPC by 0.1m,")
        print(f"      or bump HEARING_RADIUS by 1m) — otherwise B5 chain cannot complete at this position")
    elif verdict.startswith("4."):
        print(f"    - Trace downstream: EpistemicContextResolver, DecisionHub, post_decision")
        print(f"    - Confirm BeliefRevisionEngine.revise() output (confidence, source_id)")
        print(f"    - Check whether report_proposition activation threshold (0.25) is reached")

    # ---- Affected files ----
    print(f"\n  >>> AFFECTED FILES:")
    if verdict.startswith("1.") or verdict.startswith("2."):
        print(f"    - app/services/game_loop.py (or game_loop_builder.py — see Stage A)")
        print(f"    - app/services/events/claim_event_subscriber.py (consumer of provider)")
    elif verdict.startswith("3."):
        print(f"    - app/models/npc_state.py (PerceptualKernel.can_observe — DO NOT change radii)")
        print(f"    - OR: saves/Open_road/locations/tavern.json (NPC start positions — DO NOT move)")
        print(f"    - This verdict requires Master's decision on which constraint to relax")
    else:
        print(f"    - app/services/npc/epistemic_context_resolver.py")
        print(f"    - app/services/npc/belief_revision_engine.py")
        print(f"    - app/services/phases/post_decision.py")

    # ---- Risks ----
    print(f"\n  >>> RISKS:")
    if verdict.startswith("1."):
        print(f"    - Spatial membrane will start filtering listeners by distance")
        print(f"    - NPCs >10m from speaker will be excluded (may affect existing scenes)")
        print(f"    - maid_lusya at 10.086m > 10.0m HEARING_RADIUS — still excluded even with fix!")
        print(f"    - So fix #1 alone will NOT unblock B5 — combined with constraint #3 (can_observe excludes)")
    elif verdict.startswith("2."):
        print(f"    - Same as #1 — once provider is bound live, distance filtering applies")
        print(f"    - maid_lusya at 10.086m > 10.0m HEARING_RADIUS — still excluded")
    elif verdict.startswith("3."):
        print(f"    - Cannot fix without violating one of: радиусы не менять / NPC не перемещать")
        print(f"    - Need Master's explicit relaxation of one constraint")
    else:
        print(f"    - Downstream changes may have side effects on existing NPC decisions")

    # ---- Tests ----
    print(f"\n  >>> REQUIRED TESTS:")
    print(f"    1. distance('player', 'maid_lusya') returns correct value")
    print(f"    2. distance('player', 'tavern_keeper_tornin') returns correct value")
    print(f"    3. NPC↔NPC distance computation does not regress")
    print(f"    4. PLAYER_INSULTS at valid distance creates belief at maid_lusya")
    print(f"    5. Confidence and provenance of created belief are correct")
    print(f"    6. Existing NPC↔NPC communication tests still pass")
    if verdict.startswith("3."):
        print(f"    7. Boundary test: NPC at exactly HEARING_RADIUS is included")
        print(f"    8. Boundary test: NPC at HEARING_RADIUS + 0.001m is excluded")

    result["verdict"] = verdict
    result["rationale"] = rationale
    return result


# ============================================================================
# MAIN
# ============================================================================
def main() -> int:
    print("=" * 78)
    print("R2-B5-D1 FINAL PROVIDER AND PERCEPTION PROBE")
    print(f"OUT_FILE: {OUT_FILE}")
    print("=" * 78)

    stage_a_result: Dict[str, Any] = {}
    stage_b_result: Dict[str, Any] = {}
    stage_c_result: Dict[str, Any] = {}
    stage_d_result: Dict[str, Any] = {}

    try:
        stage_a_result = stage_a_game_loop_provider()
    except Exception as e:
        print(f"[stage A error: {e}]")
        traceback.print_exc()

    try:
        stage_b_result = stage_b_perceptual_kernel()
    except Exception as e:
        print(f"[stage B error: {e}]")
        traceback.print_exc()

    try:
        stage_c_result = stage_c_runtime_verification()
    except Exception as e:
        print(f"[stage C error: {e}]")
        traceback.print_exc()

    try:
        stage_d_result = stage_d_verdict(stage_a_result, stage_b_result, stage_c_result)
    except Exception as e:
        print(f"[stage D error: {e}]")
        traceback.print_exc()

    # Final summary
    print()
    print("=" * 78)
    print("FINAL SUMMARY")
    print("=" * 78)
    print(f"  Stage A pass: {stage_a_result.get('pass', False)}")
    print(f"  Stage B pass: {stage_b_result.get('pass', False)}")
    print(f"  Stage C pass: {stage_c_result.get('pass', False)}")
    print(f"  Verdict:     {stage_d_result.get('verdict', '?')}")

    # Write output file
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
