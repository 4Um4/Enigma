# backend/tests/sandbox/r2_b5_e2_decision_hub.py
"""
R2-B5-E2 — DecisionHub: does Lusya's EpistemicContext produce SPREAD_RUMOR intent?

GOAL (from Master):
  Trace EpistemicContext.report_proposition → DecisionHub → SPREAD_RUMOR
  Distinguish three states: KNOWS / WANTS / DOES.
  B5-D1 proved KNOWS. B5-E1 proved context reach.
  B5-E2 must prove WANTS — does DecisionHub produce SPREAD_RUMOR for Lusya?

What this probe must establish:
  1. Runtime wiring — which DecisionHub instance handles maid_lusya decisions.
  2. Knowledge availability — confirm report_proposition present in the actually-passed context.
  3. Decision modifiers — which intent modifiers are computed; check SPREAD_RUMOR boost specifically.
  4. Competing intents — which intents participate in selection, with what final scores.
  5. Result — which intent is selected (SPREAD_RUMOR / TALK / other).
  6. Execution — does the selected intent reach the executor, not just DecisionHub output.

DO NOT:
  - Modify production code
  - Touch B5-D2

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
OUT_FILE = OUT_FILE_DIR / "r2_b5_e2_decision_hub.txt"


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
    print("R2-B5-E2 — DecisionHub: report_proposition → SPREAD_RUMOR intent")
    print(f"OUT_FILE: {OUT_FILE}")
    print("=" * 78)
    print()
    print("GOAL: prove WANTS — does DecisionHub produce SPREAD_RUMOR for maid_lusya")
    print("      after PLAYER_INSULTS?")
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

        saves_dir = Path(tempfile.mkdtemp(prefix="r2_b5_e2_"))
        settings.saves_dir = str(saves_dir)
        settings.environment = "development"

        loop = build_game_loop(data_dir=Path(settings.data_dir))
        scene = loop.scene_manager.get_scene_state("Open_road", "tavern")
        if scene is None:
            scene = loop.scene_manager.initialize_scene("Open_road", "tavern", "12:00")

        bus = get_event_bus()

        # =====================================================================
        # STEP 1: locate ClaimEventSubscriber + EpistemicStore + Resolver
        # =====================================================================
        _print_section("STEP 1: locate subscriber, store, resolver")
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
        if sub is None:
            print("  [FATAL: ClaimEventSubscriber not found]")
            return 1
        store = getattr(sub, "_store", None)
        print(f"  sub._store: id={id(store)}")

        # Find resolver
        resolver: Optional[EpistemicContextResolver] = None
        for parent_name in ("_tick_orch", "_svc", "_tick_orchestrator"):
            parent = getattr(loop, parent_name, None)
            if parent is None:
                continue
            for attr_name in ("_resolver", "_epistemic_context_resolver", "context_resolver", "epistemic_context_resolver"):
                val = getattr(parent, attr_name, None)
                if isinstance(val, EpistemicContextResolver):
                    resolver = val
                    print(f"  resolver: id={id(resolver)} via loop.{parent_name}.{attr_name}")
                    break
            if resolver:
                break
        if resolver is None:
            print("  [FATAL: EpistemicContextResolver not found]")
            return 1

        # =====================================================================
        # STEP 2: locate DecisionHub class and production instance
        # =====================================================================
        _print_section("STEP 2: locate DecisionHub class + production instance")

        # 2a: Search production files for "class DecisionHub"
        print("\n--- 2a: search production files for DecisionHub class ---")
        candidates: List[Path] = []
        for f in _BACKEND.rglob("*.py"):
            if not _is_production_file(f):
                continue
            try:
                src = f.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            if "class DecisionHub" in src:
                candidates.append(f)
        for c in candidates:
            try:
                rel = c.relative_to(_BACKEND)
            except Exception:
                rel = c
            print(f"  found: {rel}")

        # 2b: Search for SPREAD_RUMOR boost computation in production
        print("\n--- 2b: search SPREAD_RUMOR boost computation sites ---")
        sr_results = _grep_in_dir(
            _BACKEND,
            ["SPREAD_RUMOR", "spread_rumor"],
            production_only=True,
        )
        for path, ln, line in sr_results[:30]:
            try:
                rel = path.relative_to(_BACKEND)
            except Exception:
                rel = path
            print(f"  {rel} L{ln}: {line}")

        # 2c: Find DecisionHub instance in runtime
        print("\n--- 2c: search runtime for DecisionHub instance ---")
        # First, try importing the class
        DecisionHubClass = None
        for c in candidates:
            try:
                import importlib.util
                spec = importlib.util.spec_from_file_location(f"_dh_{c.stem}", c)
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    DecisionHubClass = getattr(mod, "DecisionHub", None)
                    if DecisionHubClass:
                        print(f"  imported DecisionHub from {c.relative_to(_BACKEND)}")
                        break
            except Exception as e:
                print(f"  [import failed for {c.name}: {e}]")
                continue

        decision_hub: Optional[Any] = None
        dh_path_desc = ""
        if DecisionHubClass:
            # Walk loop, _tick_orch, _svc
            for parent_name in ("loop", "_tick_orch", "_svc", "_tick_orchestrator"):
                if parent_name == "loop":
                    parent = loop
                else:
                    parent = getattr(loop, parent_name, None)
                if parent is None:
                    continue
                # Direct attr
                for attr_name in ("_decision_hub", "_decision_hub", "decision_hub", "_hub", "hub"):
                    val = getattr(parent, attr_name, None)
                    if isinstance(val, DecisionHubClass):
                        decision_hub = val
                        dh_path_desc = f"{parent_name}.{attr_name}"
                        break
                if decision_hub:
                    break
                # vars walk
                if decision_hub:
                    break
                try:
                    for k, v in vars(parent).items():
                        if isinstance(v, DecisionHubClass):
                            decision_hub = v
                            dh_path_desc = f"{parent_name}.{k}"
                            break
                        if hasattr(v, "__dict__"):
                            for k2, v2 in vars(v).items():
                                if isinstance(v2, DecisionHubClass):
                                    decision_hub = v2
                                    dh_path_desc = f"{parent_name}.{k}.{k2}"
                                    break
                            if decision_hub:
                                break
                    if decision_hub:
                        break
                except Exception:
                    pass

        if decision_hub is None:
            print("  [DecisionHub instance NOT FOUND in runtime — trying deeper search]")
            # Brute force: walk all attributes of loop recursively
            try:
                visited = set()
                def _walk(obj, path, depth=0):
                    nonlocal decision_hub, dh_path_desc
                    if depth > 5 or id(obj) in visited:
                        return
                    visited.add(id(obj))
                    if DecisionHubClass and isinstance(obj, DecisionHubClass):
                        decision_hub = obj
                        dh_path_desc = path
                        return
                    try:
                        for k, v in vars(obj).items() if hasattr(obj, "__dict__") else []:
                            if k.startswith("__"):
                                continue
                            _walk(v, f"{path}.{k}", depth + 1)
                            if decision_hub:
                                return
                    except Exception:
                        pass
                _walk(loop, "loop")
            except Exception as e:
                print(f"  [deep walk error: {e}]")

        if decision_hub is None:
            print("  [FATAL: DecisionHub instance NOT FOUND in runtime]")
            print("  Dumping loop attributes with 'hub' / 'decision' in name:")
            for attr_name in sorted(dir(loop)):
                if "hub" in attr_name.lower() or "decision" in attr_name.lower():
                    try:
                        val = getattr(loop, attr_name)
                        print(f"    loop.{attr_name}: type={type(val).__name__}, id={id(val)}")
                    except Exception:
                        pass
            return 1

        print(f"\n  >>> DecisionHub FOUND")
        print(f"      id: {id(decision_hub)}")
        print(f"      type: {type(decision_hub).__name__}")
        print(f"      via: {dh_path_desc}")
        print(f"      module: {type(decision_hub).__module__}")

        # =====================================================================
        # STEP 3: read DecisionHub main method (decide / select_intent / etc.)
        # =====================================================================
        _print_section("STEP 3: read DecisionHub main decision method")
        dh_path = inspect.getfile(type(decision_hub))
        try:
            dh_path_obj = Path(dh_path)
            rel = dh_path_obj.relative_to(_BACKEND) if _BACKEND in dh_path_obj.parents or dh_path_obj == _BACKEND else dh_path_obj
            print(f"  file: {rel}")
        except Exception:
            print(f"  file: {dh_path}")
        dh_src = _read_file_text(Path(dh_path))
        dh_lines = dh_src.split("\n")

        # List all methods
        print(f"\n  --- methods in DecisionHub ---")
        for i, line in enumerate(dh_lines, 1):
            stripped = line.lstrip()
            if stripped.startswith("def "):
                print(f"  L{i}: {stripped.rstrip()}")

        # Read each candidate decision method
        for method_name in ("decide", "select_intent", "compute_intent", "choose", "run", "execute", "process"):
            bounds = _find_function_bounds(dh_src, method_name)
            if bounds:
                s, e = bounds
                print(f"\n  --- {method_name}() at L{s+1}..L{e} ---")
                for j in range(s, e):
                    print(f"  L{j+1:4d}: {dh_lines[j]}")
                break

        # Also search for SPREAD_RUMOR references within DecisionHub file
        print(f"\n  --- SPREAD_RUMOR / spread_rumor references in DecisionHub file ---")
        for i, line in enumerate(dh_lines, 1):
            if "SPREAD_RUMOR" in line or "spread_rumor" in line:
                print(f"  L{i}: {line.rstrip()}")

        # =====================================================================
        # STEP 4: read SPREAD_RUMOR boost computation site
        # =====================================================================
        _print_section("STEP 4: read SPREAD_RUMOR boost computation in production")
        for path, ln, line in sr_results:
            if "boost" in line.lower() or "0.9" in line or "modifier" in line.lower():
                try:
                    rel = path.relative_to(_BACKEND)
                except Exception:
                    rel = path
                src = _read_file_text(path)
                src_lines = src.split("\n")
                ctx_start = max(0, ln - 5)
                ctx_end = min(len(src_lines), ln + 15)
                print(f"\n  >>> {rel} L{ln}: {line.strip()}")
                print(f"  context L{ctx_start + 1}..L{ctx_end}:")
                for j in range(ctx_start, ctx_end):
                    marker = ">>>" if j + 1 == ln else "   "
                    print(f"  {marker} L{j+1:4d}: {src_lines[j]}")

        # =====================================================================
        # STEP 5: publish PLAYER_INSULTS + capture context
        # =====================================================================
        _print_section("STEP 5: publish PLAYER_INSULTS + capture EpistemicContext")
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
        print(f"  Publishing PLAYER_INSULTS...")
        bus.publish(evt)
        print(f"  Published.")

        # Sanity check
        expected_prop = Proposition(
            subject_id="player",
            predicate=Predicate.INSULTED,
            object_id="tavern_keeper_tornin",
            polarity=True,
        )
        lusya_rec = store.get("maid_lusya", expected_prop)
        print(f"  sanity: store.get('maid_lusya', expected_prop).confidence = {getattr(lusya_rec, 'confidence', None)}")

        ctx = resolver.resolve("maid_lusya")
        print(f"\n  --- EpistemicContext after publish ---")
        ctx_dict = _inspect_obj(ctx)
        print(json.dumps(ctx_dict, indent=2, default=str, ensure_ascii=False)[:4000])

        # =====================================================================
        # STEP 6: get maid_lusya NPC state from loop
        # =====================================================================
        _print_section("STEP 6: get maid_lusya NPC state")
        npc_states_provider = None
        for parent_name in ("_tick_orch", "_svc"):
            parent = getattr(loop, parent_name, None)
            if parent is None:
                continue
            for attr_name in ("_npc_states_provider", "npc_states_provider", "_get_npc_states"):
                val = getattr(parent, attr_name, None)
                if val is not None:
                    npc_states_provider = val
                    print(f"  npc_states_provider found via loop.{parent_name}.{attr_name}")
                    break
            if npc_states_provider:
                break
        if npc_states_provider is None:
            # Try direct attr on loop
            for attr_name in ("_npc_states_provider", "npc_states_provider", "_resolve_npcs_snapshot"):
                val = getattr(loop, attr_name, None)
                if val is not None:
                    npc_states_provider = val
                    print(f"  npc_states_provider found via loop.{attr_name}")
                    break

        # Try calling the provider
        npc_states: Dict[str, Any] = {}
        if npc_states_provider is not None:
            try:
                npc_states = npc_states_provider() if callable(npc_states_provider) else npc_states_provider
                print(f"  npc_states_provider returned: {len(npc_states) if hasattr(npc_states, '__len__') else '?'} NPCs")
            except Exception as e:
                print(f"  npc_states_provider call error: {e}")
        if not npc_states:
            # Try scene_state['npc_states'] directly
            npc_states = scene.get("npc_states", {}) or {}
            print(f"  fallback to scene['npc_states']: {len(npc_states)} NPCs")

        print(f"  available NPCs: {list(npc_states.keys()) if hasattr(npc_states, 'keys') else 'not a dict'}")
        lusya_state = npc_states.get("maid_lusya") if hasattr(npc_states, "get") else None
        if lusya_state is None:
            print("  [maid_lusya NPC state NOT FOUND]")
            # Try loop.npc_manager
            for attr_name in ("_npc_manager", "npc_manager", "_npcs"):
                val = getattr(loop, attr_name, None)
                if val is not None:
                    print(f"    trying loop.{attr_name}: type={type(val).__name__}")
                    try:
                        for k, v in vars(val).items():
                            if "maid_lusya" in str(k):
                                print(f"      {k}: {v!r}")
                    except Exception:
                        pass
        else:
            print(f"  maid_lusya NPC state: type={type(lusya_state).__name__}")
            print(f"  --- maid_lusya state dump (top-level) ---")
            try:
                for k, v in vars(lusya_state).items():
                    if not k.startswith("__"):
                        print(f"    {k}: {repr(v)[:120]}")
            except Exception:
                for attr in dir(lusya_state):
                    if not attr.startswith("__"):
                        try:
                            val = getattr(lusya_state, attr)
                            if callable(val):
                                continue
                            print(f"    {attr}: {repr(val)[:120]}")
                        except Exception:
                            pass

        # =====================================================================
        # STEP 7: invoke DecisionHub for maid_lusya
        # =====================================================================
        _print_section("STEP 7: invoke DecisionHub for maid_lusya")

        # Inspect decide signature
        decide_method = None
        decide_method_name = None
        for method_name in ("decide", "select_intent", "compute_intent", "choose", "run", "execute", "process", "evaluate"):
            method = getattr(decision_hub, method_name, None)
            if method is not None and callable(method):
                decide_method = method
                decide_method_name = method_name
                break

        if decide_method is None:
            print(f"  [FATAL: no decide method found on DecisionHub]")
            return 1

        print(f"  method: {decide_method_name}")
        try:
            sig = inspect.signature(decide_method)
            print(f"  signature: {decide_method_name}{sig}")
        except Exception:
            pass

        # Try various call signatures
        # Signature variants: decide(agent_id), decide(npc_state), decide(npc_state, ctx), decide(agent_id, ctx, npc_state)
        decision_result: Any = None
        decision_error: Optional[str] = None

        call_attempts: List[Tuple[str, Tuple, Dict]] = [
            ("npc_state + ctx", (lusya_state, ctx), {}),
            ("agent_id + npc_state + ctx", ("maid_lusya", lusya_state, ctx), {}),
            ("npc_state + ctx + tick", (lusya_state, ctx, 1), {}),
            ("agent_id only", ("maid_lusya",), {}),
            ("npc_state only", (lusya_state,), {}),
            ("agent_id + ctx", ("maid_lusya", ctx), {}),
            ("agent_id + npc_state + ctx + tick", ("maid_lusya", lusya_state, ctx, 1), {}),
            ("agent_id + npc_state", ("maid_lusya", lusya_state), {}),
        ]

        for desc, args, kwargs in call_attempts:
            if lusya_state is None and "npc_state" in desc:
                continue
            print(f"\n  --- trying: {decide_method_name}({desc}) ---")
            try:
                decision_result = decide_method(*args, **kwargs)
                print(f"  SUCCESS: result type={type(decision_result).__name__}")
                print(f"  result: {repr(decision_result)[:300]}")
                break
            except TypeError as e:
                print(f"  TypeError: {e}")
            except Exception as e:
                print(f"  {type(e).__name__}: {e}")
                # If we get an LLM-related error, that's actually a positive sign:
                # DecisionHub reached LLM call which means it accepted our context and tried to decide.
                if "llm" in str(e).lower() or "openai" in str(e).lower() or "client" in str(e).lower():
                    decision_error = f"LLM_ERROR: {e}"
                    print(f"  >>> LLM error indicates DecisionHub REACHED LLM call (good sign)")

        # =====================================================================
        # STEP 8: inspect decision result
        # =====================================================================
        _print_section("STEP 8: inspect decision result")
        if decision_result is not None:
            print(f"  result type: {type(decision_result).__name__}")
            result_dict = _inspect_obj(decision_result)
            print(f"  --- result dump ---")
            print(json.dumps(result_dict, indent=2, default=str, ensure_ascii=False)[:5000])

            # Look for intent field
            intent_value = None
            for attr_name in ("intent", "selected_intent", "action", "selected_action", "decision"):
                v = getattr(decision_result, attr_name, None) if not isinstance(decision_result, dict) else decision_result.get(attr_name)
                if v is not None:
                    intent_value = v
                    print(f"\n  >>> {attr_name}: {v!r}")
                    break

            # Look for scores / modifiers
            for attr_name in ("scores", "intent_scores", "modifiers", "intent_modifiers", "evaluations", "weights"):
                v = getattr(decision_result, attr_name, None) if not isinstance(decision_result, dict) else decision_result.get(attr_name)
                if v is not None:
                    print(f"\n  --- {attr_name} ---")
                    print(json.dumps(_inspect_obj(v), indent=2, default=str, ensure_ascii=False)[:2000])
        elif decision_error:
            print(f"  Decision could not complete: {decision_error}")
            print(f"  Cannot inspect intent selection — LLM call would be required.")
            print(f"  >>> For B5-E2 verification, need to run a full tick with real LLM.")
        else:
            print(f"  [no decision result captured]")

        # =====================================================================
        # STEP 9: trace execution — does selected intent reach executor?
        # =====================================================================
        _print_section("STEP 9: trace execution — does selected intent reach executor?")
        print("  --- search production for executor / action dispatcher ---")
        exec_results = _grep_in_dir(
            _BACKEND,
            ["intent_executor", "execute_intent", "action_dispatcher", "execute_action",
             "apply_intent", "intent_handler"],
            production_only=True,
        )
        for path, ln, line in exec_results[:15]:
            try:
                rel = path.relative_to(_BACKEND)
            except Exception:
                rel = path
            print(f"  {rel} L{ln}: {line}")

        # =====================================================================
        # STEP 10: VERDICT
        # =====================================================================
        _print_section("STEP 10: VERDICT")

        print(f"  DecisionHub instance:           {decision_hub is not None}")
        print(f"  resolver.store IS sub._store:   {getattr(resolver, '_store', None) is store}")
        print(f"  ctx.report_proposition:         {getattr(ctx, 'report_proposition', None)}")
        print(f"  decision result captured:       {decision_result is not None}")
        if decision_error:
            print(f"  decision error:                 {decision_error[:120]}")

        print()
        if decision_result is not None:
            intent_value = None
            for attr_name in ("intent", "selected_intent", "action", "selected_action", "decision"):
                v = getattr(decision_result, attr_name, None) if not isinstance(decision_result, dict) else decision_result.get(attr_name)
                if v is not None:
                    intent_value = v
                    break

            if intent_value is not None:
                intent_str = str(intent_value).upper()
                print(f"  selected intent: {intent_value!r}")
                if "SPREAD_RUMOR" in intent_str or "spread_rumor" in intent_str:
                    print(f"\n  >>> VERDICT: B5-E2 NOT A DEFECT (with caveat)")
                    print(f"  >>> DecisionHub selected SPREAD_RUMOR for maid_lusya")
                    print(f"  >>> WANTS is proven (modulo real LLM call)")
                    print(f"  >>> Caveat: this run may have used LLM — verify Step 8 to confirm intent")
                elif "TALK" in intent_str:
                    print(f"\n  >>> VERDICT: B5-E2 DEFECT — TALK chosen instead of SPREAD_RUMOR")
                    print(f"  >>> DecisionHub had report_proposition but selected TALK")
                    print(f"  >>> Investigate why SPREAD_RUMOR modifier didn't win")
                else:
                    print(f"\n  >>> VERDICT: B5-E2 DEFECT — neither SPREAD_RUMOR nor TALK")
                    print(f"  >>> DecisionHub chose {intent_value!r}")
            else:
                print(f"  no intent field found in result — full dump shown above")
                print(f"\n  >>> VERDICT: needs manual inspection of Step 8 dump")
        elif decision_error and "LLM_ERROR" in decision_error:
            print(f"\n  >>> VERDICT: INCONCLUSIVE — DecisionHub requires LLM call")
            print(f"  >>> The hub accepted our context (no TypeError) and tried to invoke LLM.")
            print(f"  >>> Without LLM, cannot capture final intent selection.")
            print(f"  >>> NEXT: run a full tick with real LLM (port 8181) to capture DecisionHub output.")
        else:
            print(f"\n  >>> VERDICT: INCONCLUSIVE — could not invoke DecisionHub")
            print(f"  >>> All call signature attempts failed (see Step 7)")
            print(f"  >>> Need to inspect DecisionHub signature and adapt probe.")

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
