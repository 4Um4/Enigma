# backend/tests/sandbox/r2_b5_e2_decision_hub_v2.py
"""
R2-B5-E2 v2 — DecisionHub: report_proposition → SPREAD_RUMOR intent.

v1 failed:
  1. importlib.util.spec_from_file_location returned None for decision_hub.py
     (file uses relative imports inside app.services.npc package)
  2. DecisionHub instance NOT FOUND in runtime (loop._decision_hub, _tick_orch._decision_hub)
     → DecisionHub may be a static class, or wired elsewhere

v2 fixes:
  1. Import via standard `from app.services.npc.decision_hub import DecisionHub`
  2. Search game_loop.py + tick_orchestrator.py for DecisionHub wiring (grep)
  3. Read DecisionHub class structure (all methods, decorators)
  4. Try invoking as static/class method, then as instance if needed
  5. Capture intent selection + modifiers

Key intel from v1:
  - maid disposition (epistemic_dispositions.py L20):
      spread_rumor=1.3 (highest!), talk=0.6, warn=0.3, report=0.1
  - spread_rumor uses FAST-PATH (task_scheduler.py L402) — NO LLM REQUIRED
  - dialogue_executor.py L146 handles spread_rumor
  - intent_event_adapter.py L32 maps spread_rumor → EventType.SPREAD_RUMOR

READ-ONLY. Production-код не менять.
"""
from __future__ import annotations

import os
import sys
import json
import math
import inspect
import traceback
import io
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

PROJECT_ROOT = _BACKEND.parent

OUT_FILE_DIR = Path("/home/z/my-project/download")
if not OUT_FILE_DIR.exists() or not OUT_FILE_DIR.is_dir():
    OUT_FILE_DIR = _BACKEND / "tests" / "sandbox"
    try:
        OUT_FILE_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        OUT_FILE_DIR = Path(os.getcwd())
OUT_FILE = OUT_FILE_DIR / "r2_b5_e2_decision_hub_v2.txt"


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


def _is_production_file(path: Path) -> bool:
    if not path.exists():
        return False
    parts_lower = [p.lower() for p in path.parts]
    for bad in (".venv", "node_modules", ".git", "__pycache__", "site-packages"):
        if bad in parts_lower:
            return False
    fname = path.name.lower()
    if fname.startswith("test_") or fname.endswith("_test.py"):
        return False
    if "sandbox" in parts_lower:
        return False
    if fname.startswith("r2_"):
        return False
    if any(tok in fname for tok in ("probe", "mock", "stub", "fake", "fixture")):
        return False
    for p in parts_lower:
        if p == "tests":
            return False
    return True


def _find_function_bounds(src: str, func_name: str) -> Optional[Tuple[int, int]]:
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


def _inspect_obj(obj: Any, depth: int = 0, max_depth: int = 3) -> Dict[str, Any]:
    if depth > max_depth:
        return {"_truncated": repr(obj)[:200]}
    if obj is None:
        return None
    if isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, (list, tuple, set)):
        return [_inspect_obj(x, depth + 1, max_depth) for x in list(obj)[:10]]
    if isinstance(obj, dict):
        return {str(k): _inspect_obj(v, depth + 1, max_depth) for k, v in list(obj.items())[:20]}
    out: Dict[str, Any] = {"_type": type(obj).__name__}
    try:
        d = vars(obj)
        for k, v in d.items():
            if k.startswith("__"):
                continue
            out[k] = _inspect_obj(v, depth + 1, max_depth)
    except Exception:
        for attr in dir(obj):
            if attr.startswith("__"):
                continue
            try:
                val = getattr(obj, attr)
                if callable(val):
                    continue
                out[attr] = _inspect_obj(val, depth + 1, max_depth)
            except Exception:
                continue
    return out


def _grep_in_dir(
    directory: Path,
    patterns: List[str],
    production_only: bool = True,
) -> List[Tuple[Path, int, str]]:
    out: List[Tuple[Path, int, str]] = []
    if not directory.exists():
        return out
    for f in directory.rglob("*.py"):
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


# ============================================================================
# MAIN
# ============================================================================
def main() -> int:
    print("=" * 78)
    print("R2-B5-E2 v2 — DecisionHub: report_proposition → SPREAD_RUMOR intent")
    print(f"OUT_FILE: {OUT_FILE}")
    print("=" * 78)
    print()
    print("v2 fixes from v1:")
    print("  1. Import DecisionHub via `from app.services.npc.decision_hub import`")
    print("  2. Search game_loop.py + tick_orchestrator.py for DecisionHub wiring")
    print("  3. Read class structure (decorators, methods)")
    print("  4. Try static/class/instance invocation")
    print()

    try:
        from app.services.game_loop_builder import build_game_loop
        from app.services.events.event_bus import get_event_bus
        from app.services.events.event_types import EventType
        from app.domain.events import EventDTO
        from app.services.events.claim_event_subscriber import ClaimEventSubscriber
        from app.services.npc.epistemic_context_resolver import EpistemicContextResolver
        from app.domain.epistemology import Proposition, Predicate, ClaimEvent, EpistemicRecord  # type: ignore
        import tempfile

        saves_dir = Path(tempfile.mkdtemp(prefix="r2_b5_e2_v2_"))
        settings.saves_dir = str(saves_dir)
        settings.environment = "development"

        loop = build_game_loop(data_dir=Path(settings.data_dir))
        scene = loop.scene_manager.get_scene_state("Open_road", "tavern")
        if scene is None:
            scene = loop.scene_manager.initialize_scene("Open_road", "tavern", "12:00")

        bus = get_event_bus()

        # =====================================================================
        # STEP 1: locate sub, store, resolver
        # =====================================================================
        _print_section("STEP 1: locate sub, store, resolver")
        sub: Optional[ClaimEventSubscriber] = None
        for attr in ("_subscribers", "_handlers", "_callbacks"):
            if not hasattr(bus, attr):
                continue
            container = getattr(bus, attr)
            if not isinstance(container, dict):
                continue
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
                        break
                if sub:
                    break
            if sub:
                break
        store = getattr(sub, "_store", None)
        print(f"  sub._store: id={id(store)}")

        resolver: Optional[EpistemicContextResolver] = None
        for parent_name in ("_tick_orch", "_svc"):
            parent = getattr(loop, parent_name, None)
            if parent is None:
                continue
            for attr_name in ("_resolver", "_epistemic_context_resolver"):
                val = getattr(parent, attr_name, None)
                if isinstance(val, EpistemicContextResolver):
                    resolver = val
                    print(f"  resolver: id={id(resolver)} via loop.{parent_name}.{attr_name}")
                    break
            if resolver:
                break

        # =====================================================================
        # STEP 2: import DecisionHub via standard Python import
        # =====================================================================
        _print_section("STEP 2: import DecisionHub via `from app.services.npc.decision_hub`")
        DecisionHubClass: Any = None
        try:
            from app.services.npc.decision_hub import DecisionHub as _DH
            DecisionHubClass = _DH
            print(f"  DecisionHub class imported: {DecisionHubClass}")
            print(f"  module: {DecisionHubClass.__module__}")
            print(f"  file: {inspect.getfile(DecisionHubClass)}")
        except Exception as e:
            print(f"  IMPORT FAILED: {type(e).__name__}: {e}")
            traceback.print_exc()

        # =====================================================================
        # STEP 3: search game_loop.py + tick_orchestrator.py for DecisionHub wiring
        # =====================================================================
        _print_section("STEP 3: search production for DecisionHub wiring")
        dh_wiring_results = _grep_in_dir(
            _BACKEND,
            ["DecisionHub(", "DecisionHub.", "_decision_hub", "decision_hub"],
            production_only=True,
        )
        for path, ln, line in dh_wiring_results[:40]:
            try:
                rel = path.relative_to(_BACKEND)
            except Exception:
                rel = path
            # Skip noise: just references in strings
            if line.strip().startswith("#"):
                continue
            print(f"  {rel} L{ln}: {line}")

        # Specifically look for instance creation: DecisionHub(
        print()
        print(f"  --- DecisionHub( construction sites ---")
        for path, ln, line in dh_wiring_results:
            if "DecisionHub(" in line and not line.strip().startswith("#"):
                try:
                    rel = path.relative_to(_BACKEND)
                except Exception:
                    rel = path
                src = _read_file_text(path)
                src_lines = src.split("\n")
                ctx_start = max(0, ln - 5)
                ctx_end = min(len(src_lines), ln + 15)
                print(f"\n  >>> {rel} L{ln}: {line.strip()}")
                for j in range(ctx_start, ctx_end):
                    marker = ">>>" if j + 1 == ln else "   "
                    print(f"  {marker} L{j+1:4d}: {src_lines[j]}")

        # =====================================================================
        # STEP 4: read DecisionHub class structure (decorators, methods)
        # =====================================================================
        _print_section("STEP 4: read DecisionHub class structure")
        if DecisionHubClass:
            dh_path_str = inspect.getfile(DecisionHubClass)
            dh_src = _read_file_text(Path(dh_path_str))
            dh_lines = dh_src.split("\n")

            # Print class definition + first 30 lines
            print(f"  file: {dh_path_str}")
            print(f"  total lines: {len(dh_lines)}")
            print()
            print(f"  --- class DecisionHub definition + structure ---")
            # Find class definition
            class_start = None
            for i, line in enumerate(dh_lines):
                if line.startswith("class DecisionHub"):
                    class_start = i
                    break
            if class_start is None:
                for i, line in enumerate(dh_lines):
                    if "class DecisionHub" in line:
                        class_start = i
                        break
            if class_start is not None:
                # Find class end
                class_indent = len(dh_lines[class_start]) - len(dh_lines[class_start].lstrip())
                class_end = len(dh_lines)
                for j in range(class_start + 1, len(dh_lines)):
                    if dh_lines[j].strip() == "":
                        continue
                    cur_indent = len(dh_lines[j]) - len(dh_lines[j].lstrip())
                    if cur_indent <= class_indent and (
                        dh_lines[j].lstrip().startswith("class ")
                        or dh_lines[j].lstrip().startswith("def ")
                    ):
                        class_end = j
                        break
                # Print first 80 lines of class
                end_print = min(class_end, class_start + 80)
                for j in range(class_start, end_print):
                    print(f"  L{j+1:4d}: {dh_lines[j]}")
                if class_end > end_print:
                    print(f"  ... ({class_end - end_print} more lines)")

            # List all methods with decorators
            print()
            print(f"  --- all methods in DecisionHub (with decorators) ---")
            for i, line in enumerate(dh_lines, 1):
                stripped = line.lstrip()
                if stripped.startswith("@") or stripped.startswith("def "):
                    print(f"  L{i}: {line.rstrip()}")

            # Print the main decide method
            print()
            for method_name in ("decide", "select_intent", "compute_intent", "choose", "run", "evaluate"):
                bounds = _find_function_bounds(dh_src, method_name)
                if bounds:
                    s, e = bounds
                    print(f"\n  --- {method_name}() at L{s+1}..L{e} ---")
                    for j in range(s, e):
                        print(f"  L{j+1:4d}: {dh_lines[j]}")
                    break
        else:
            print("  [DecisionHub class not imported — skipping]")

        # =====================================================================
        # STEP 5: search for SPREAD_RUMOR boost computation in DecisionHub
        # =====================================================================
        _print_section("STEP 5: SPREAD_RUMOR boost computation in DecisionHub")
        if DecisionHubClass:
            for i, line in enumerate(dh_lines, 1):
                if "SPREAD_RUMOR" in line or "spread_rumor" in line:
                    # Print with context
                    ctx_start = max(0, i - 3)
                    ctx_end = min(len(dh_lines), i + 5)
                    print(f"\n  >>> L{i}: {line.rstrip()}")
                    for j in range(ctx_start, ctx_end):
                        marker = ">>>" if j + 1 == i else "   "
                        print(f"  {marker} L{j+1:4d}: {dh_lines[j]}")

        # =====================================================================
        # STEP 6: read epistemic_dispositions.py — maid disposition
        # =====================================================================
        _print_section("STEP 6: epistemic_dispositions.py — maid disposition")
        ed_path = _BACKEND / "app" / "domain" / "epistemic_dispositions.py"
        if ed_path.exists():
            ed_src = _read_file_text(ed_path)
            ed_lines = ed_src.split("\n")
            # Print maid-related lines with context
            for i, line in enumerate(ed_lines, 1):
                if "maid" in line.lower() or "spread_rumor" in line:
                    print(f"  L{i}: {line.rstrip()}")

        # =====================================================================
        # STEP 7: publish PLAYER_INSULTS + verify belief + ctx
        # =====================================================================
        _print_section("STEP 7: publish PLAYER_INSULTS + verify ctx")
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
        bus.publish(evt)

        expected_prop = Proposition(
            subject_id="player",
            predicate=Predicate.INSULTED,
            object_id="tavern_keeper_tornin",
            polarity=True,
        )
        lusya_rec = store.get("maid_lusya", expected_prop)
        print(f"  store.get('maid_lusya', expected_prop).confidence = {getattr(lusya_rec, 'confidence', None)}")

        ctx = resolver.resolve("maid_lusya")
        print(f"  ctx.report_proposition = {getattr(ctx, 'report_proposition', None)}")
        print(f"  ctx.max_confidence = {getattr(ctx, 'max_confidence', None)}")

        # =====================================================================
        # STEP 8: get maid_lusya NPC state
        # =====================================================================
        _print_section("STEP 8: get maid_lusya NPC state")
        # Try multiple strategies
        npc_states: Dict[str, Any] = {}
        # Strategy 1: scene_state['npc_states']
        npc_states = scene.get("npc_states", {}) or {}
        print(f"  scene['npc_states'] count: {len(npc_states) if hasattr(npc_states, '__len__') else '?'}")

        # Strategy 2: loop._resolve_npcs_snapshot
        if "maid_lusya" not in npc_states:
            try:
                resolve_fn = getattr(loop, "_resolve_npcs_snapshot", None)
                if resolve_fn:
                    snap = resolve_fn("Open_road")
                    if isinstance(snap, dict):
                        npc_states = snap
                        print(f"  loop._resolve_npcs_snapshot('Open_road') returned: {len(snap)} NPCs")
            except Exception as e:
                print(f"  _resolve_npcs_snapshot error: {e}")

        # Strategy 3: loop._svc
        if "maid_lusya" not in npc_states:
            try:
                svc = getattr(loop, "_svc", None)
                if svc:
                    for attr_name in ("_npc_states", "npc_states", "_resolve_npcs_snapshot"):
                        val = getattr(svc, attr_name, None)
                        if val is None:
                            continue
                        if callable(val):
                            try:
                                result = val("Open_road") if "snapshot" in attr_name or "resolve" in attr_name else val()
                                if isinstance(result, dict) and result:
                                    npc_states = result
                                    print(f"  _svc.{attr_name}() returned: {len(result)} NPCs")
                                    break
                            except Exception as e:
                                print(f"  _svc.{attr_name}() error: {e}")
                        elif isinstance(val, dict) and val:
                            npc_states = val
                            print(f"  _svc.{attr_name} returned: {len(val)} NPCs")
                            break
            except Exception as e:
                print(f"  _svc search error: {e}")

        print(f"  available NPCs: {list(npc_states.keys())[:20] if hasattr(npc_states, 'keys') else 'N/A'}")
        lusya_state = npc_states.get("maid_lusya")
        if lusya_state is None:
            print("  [maid_lusya NPC state NOT FOUND]")
        else:
            print(f"  maid_lusya NPC state: type={type(lusya_state).__name__}, id={id(lusya_state)}")
            print(f"  --- maid_lusya state top-level attrs ---")
            try:
                for k, v in vars(lusya_state).items():
                    if not k.startswith("__"):
                        print(f"    {k}: {repr(v)[:100]}")
            except Exception:
                for attr in dir(lusya_state):
                    if not attr.startswith("__"):
                        try:
                            val = getattr(lusya_state, attr)
                            if callable(val):
                                continue
                            print(f"    {attr}: {repr(val)[:100]}")
                        except Exception:
                            pass

        # =====================================================================
        # STEP 9: invoke DecisionHub
        # =====================================================================
        _print_section("STEP 9: invoke DecisionHub for maid_lusya")

        # First inspect the decide() signature
        decide_method = None
        decide_method_name = None
        if DecisionHubClass:
            for method_name in ("decide", "select_intent", "compute_intent", "choose", "evaluate", "run"):
                # Try as instance method
                method = getattr(DecisionHubClass, method_name, None)
                if method is not None:
                    decide_method = method
                    decide_method_name = method_name
                    print(f"  found method: DecisionHub.{method_name}")
                    break

        if decide_method is None:
            print("  [no decide method found on DecisionHub class]")
        else:
            try:
                sig = inspect.signature(decide_method)
                print(f"  signature: DecisionHub.{decide_method_name}{sig}")
            except Exception:
                pass
            # Check if it's staticmethod / classmethod
            for cls_attr_name in ("__dict__",):
                cls_dict = getattr(DecisionHubClass, cls_attr_name, {})
                if isinstance(cls_dict, dict):
                    entry = cls_dict.get(decide_method_name)
                    if entry is not None:
                        is_static = isinstance(entry, staticmethod)
                        is_class = isinstance(entry, classmethod)
                        print(f"  decorator: staticmethod={is_static}, classmethod={is_class}")

        # Now: try to find DecisionHub instance in runtime, OR instantiate
        decision_hub_instance: Any = None
        if DecisionHubClass:
            # Walk loop attributes
            for parent_name in ("loop", "_tick_orch", "_svc"):
                parent = loop if parent_name == "loop" else getattr(loop, parent_name, None)
                if parent is None:
                    continue
                # Direct attr
                for attr_name in dir(parent):
                    if attr_name.startswith("__"):
                        continue
                    try:
                        val = getattr(parent, attr_name)
                    except Exception:
                        continue
                    if isinstance(val, DecisionHubClass):
                        decision_hub_instance = val
                        print(f"  instance found: {parent_name}.{attr_name}")
                        break
                if decision_hub_instance:
                    break
                # vars walk
                try:
                    for k, v in vars(parent).items():
                        if isinstance(v, DecisionHubClass):
                            decision_hub_instance = v
                            print(f"  instance found: {parent_name}.vars[{k}]")
                            break
                        if hasattr(v, "__dict__"):
                            for k2, v2 in vars(v).items():
                                if isinstance(v2, DecisionHubClass):
                                    decision_hub_instance = v2
                                    print(f"  instance found: {parent_name}.{k}.{k2}")
                                    break
                            if decision_hub_instance:
                                break
                    if decision_hub_instance:
                        break
                except Exception:
                    pass

        # Try call signatures
        decision_result: Any = None
        decision_error: Optional[str] = None

        if decide_method is not None:
            # First, try as instance method
            if decision_hub_instance is not None:
                bound_method = getattr(decision_hub_instance, decide_method_name)
                call_attempts: List[Tuple[str, Tuple, Dict]] = [
                    ("npc_state + ctx", (lusya_state, ctx), {}),
                    ("agent_id + npc_state + ctx", ("maid_lusya", lusya_state, ctx), {}),
                    ("npc_state + ctx + tick", (lusya_state, ctx, 1), {}),
                    ("agent_id only", ("maid_lusya",), {}),
                    ("npc_state only", (lusya_state,), {}),
                ]
                for desc, args, kwargs in call_attempts:
                    if lusya_state is None and "npc_state" in desc:
                        continue
                    print(f"\n  --- instance.{decide_method_name}({desc}) ---")
                    try:
                        decision_result = bound_method(*args, **kwargs)
                        print(f"  SUCCESS: result type={type(decision_result).__name__}")
                        print(f"  result: {repr(decision_result)[:300]}")
                        break
                    except TypeError as e:
                        print(f"  TypeError: {e}")
                    except Exception as e:
                        print(f"  {type(e).__name__}: {e}")
                        if any(t in str(e).lower() for t in ("llm", "openai", "client", "api")):
                            decision_error = f"LLM_ERROR: {e}"
                            print(f"  >>> LLM error — reached LLM call (good sign)")
                            break
            else:
                # Try as static/class method
                call_attempts = [
                    ("agent_id + npc_state + ctx", ("maid_lusya", lusya_state, ctx), {}),
                    ("npc_state + ctx", (lusya_state, ctx), {}),
                    ("npc_state + ctx + tick", (lusya_state, ctx, 1), {}),
                    ("agent_id only", ("maid_lusya",), {}),
                ]
                for desc, args, kwargs in call_attempts:
                    if lusya_state is None and "npc_state" in desc:
                        continue
                    print(f"\n  --- DecisionHub.{decide_method_name}({desc}) [static/class] ---")
                    try:
                        decision_result = decide_method(*args, **kwargs)
                        print(f"  SUCCESS: result type={type(decision_result).__name__}")
                        print(f"  result: {repr(decision_result)[:300]}")
                        break
                    except TypeError as e:
                        print(f"  TypeError: {e}")
                    except Exception as e:
                        print(f"  {type(e).__name__}: {e}")
                        if any(t in str(e).lower() for t in ("llm", "openai", "client", "api")):
                            decision_error = f"LLM_ERROR: {e}"
                            print(f"  >>> LLM error — reached LLM call")
                            break

        # =====================================================================
        # STEP 10: inspect decision result
        # =====================================================================
        _print_section("STEP 10: inspect decision result")
        if decision_result is not None:
            print(f"  result type: {type(decision_result).__name__}")
            result_dict = _inspect_obj(decision_result)
            print(f"  --- result dump ---")
            print(json.dumps(result_dict, indent=2, default=str, ensure_ascii=False)[:5000])

            # Look for intent field
            intent_value = None
            for attr_name in ("intent", "selected_intent", "action", "selected_action", "decision", "intent_type"):
                v = getattr(decision_result, attr_name, None) if not isinstance(decision_result, dict) else decision_result.get(attr_name)
                if v is not None:
                    intent_value = v
                    print(f"\n  >>> {attr_name}: {v!r}")
                    break

            # Look for scores
            for attr_name in ("scores", "intent_scores", "modifiers", "intent_modifiers", "evaluations", "weights", "scored_intents"):
                v = getattr(decision_result, attr_name, None) if not isinstance(decision_result, dict) else decision_result.get(attr_name)
                if v is not None:
                    print(f"\n  --- {attr_name} ---")
                    print(json.dumps(_inspect_obj(v), indent=2, default=str, ensure_ascii=False)[:3000])
        elif decision_error:
            print(f"  Decision could not complete: {decision_error}")
        else:
            print(f"  [no decision result captured]")

        # =====================================================================
        # STEP 11: trace execution path
        # =====================================================================
        _print_section("STEP 11: trace execution — where DecisionHub output flows")
        exec_results = _grep_in_dir(
            _BACKEND,
            ["intent_executor", "execute_intent", "action_dispatcher",
             "apply_intent", "intent_handler", "dialogue_executor"],
            production_only=True,
        )
        for path, ln, line in exec_results[:20]:
            try:
                rel = path.relative_to(_BACKEND)
            except Exception:
                rel = path
            print(f"  {rel} L{ln}: {line}")

        # =====================================================================
        # STEP 12: VERDICT
        # =====================================================================
        _print_section("STEP 12: VERDICT")

        print(f"  DecisionHub class imported: {DecisionHubClass is not None}")
        print(f"  DecisionHub instance found: {decision_hub_instance is not None}")
        print(f"  ctx.report_proposition present: {getattr(ctx, 'report_proposition', None) is not None}")
        print(f"  decision result captured: {decision_result is not None}")
        if decision_error:
            print(f"  decision error: {decision_error[:120]}")

        print()
        if decision_result is not None:
            intent_value = None
            for attr_name in ("intent", "selected_intent", "action", "selected_action", "decision", "intent_type"):
                v = getattr(decision_result, attr_name, None) if not isinstance(decision_result, dict) else decision_result.get(attr_name)
                if v is not None:
                    intent_value = v
                    break

            if intent_value is not None:
                intent_str = str(intent_value).upper()
                print(f"  selected intent: {intent_value!r}")
                if "SPREAD_RUMOR" in intent_str or "spread_rumor" in intent_str:
                    print(f"\n  >>> VERDICT: B5-E2 NOT A DEFECT")
                    print(f"  >>> DecisionHub selected SPREAD_RUMOR for maid_lusya")
                    print(f"  >>> WANTS is proven")
                elif "TALK" in intent_str:
                    print(f"\n  >>> VERDICT: B5-E2 DEFECT — TALK chosen instead of SPREAD_RUMOR")
                    print(f"  >>> Investigate why SPREAD_RUMOR modifier (1.3 maid disposition) didn't win")
                else:
                    print(f"\n  >>> VERDICT: B5-E2 DEFECT — neither SPREAD_RUMOR nor TALK")
            else:
                print(f"\n  >>> VERDICT: needs manual inspection of Step 10 dump")
        elif decision_error and "LLM_ERROR" in decision_error:
            print(f"\n  >>> VERDICT: INCONCLUSIVE — DecisionHub requires LLM")
            print(f"  >>> However, v1 confirmed spread_rumor uses fast-path (no LLM)")
            print(f"  >>> Need to find correct call signature OR run full tick")
        else:
            print(f"\n  >>> VERDICT: INCONCLUSIVE — could not invoke DecisionHub")
            print(f"  >>> Need to inspect wiring sites from Step 3 + class structure from Step 4")

        # ---- Cleanup ----
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

    except Exception as e:
        print(f"[FATAL: {e}]")
        traceback.print_exc()

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
