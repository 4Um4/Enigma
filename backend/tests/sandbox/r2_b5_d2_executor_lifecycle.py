# backend/tests/sandbox/r2_b5_d2_executor_lifecycle.py
"""
R2-B5-D2 v2 — Trace ONE task lifecycle: DialogueExecutor → NPC_SPOKE publish.

Master's order:
  Step 1: Read DialogueExecutor.execute() full path — branch selection,
          router presence, text result, IntentEventAdapter.to_event(),
          bus.publish(NPC_SPOKE) conditions.
  Step 2: Read task_scheduler._process_tasks_async — does it await executor?
          Where are exceptions handled? Does result get published?
  Step 3: Compare idle_tick vs run_turn execution paths (only after Steps 1-2).

Then RUN a probe that:
  - Spies on DialogueExecutor.execute() — captures input, return value, exception
  - Spies on IntentEventAdapter.to_event — captures input intent, output event
  - Spies on EventBus.publish — captures all events
  - Distinguishes PRE-EXISTING Tornin belief (source_id=player) from NEW
    Tornin belief (source_id=guard_borko)
  - Captures full log trail of guard_borko's task

CONSTRAINTS:
  - Read-only on production
  - No fixes
  - Track ONE task lifecycle (guard_borko → tavern_keeper_tornin)

Success criteria (corrected per Master):
  - NEW belief for Tornin with source_id='guard_borko' AND original_source_id='player'
  - OR: belief for Tornin with proposition sourced from spread_rumor event
  - Pre-existing belief with source_id='player' does NOT count as success
"""
from __future__ import annotations

import os
import sys
import json
import re
import shutil
import traceback
import io
import logging
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Callable

_THIS = Path(__file__).resolve()
_BACKEND = _THIS.parent.parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

try:
    from app.core.config import settings, BASE_DIR
except Exception as e:
    print(f"[FATAL] Cannot import app.core.config: {e}")
    sys.exit(2)

OUT_FILE_DIR = Path("/home/z/my-project/download")
if not OUT_FILE_DIR.exists() or not OUT_FILE_DIR.is_dir():
    OUT_FILE_DIR = _BACKEND / "tests" / "sandbox"
    try:
        OUT_FILE_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        OUT_FILE_DIR = Path(os.getcwd())
OUT_FILE = OUT_FILE_DIR / "r2_b5_d2_executor_lifecycle.txt"


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
# Log capture
# ============================================================================
class _LogCapture(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.DEBUG)
        self.records: List[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.records.append(record)
        except Exception:
            pass

    def messages(self) -> List[str]:
        return [f"[{r.levelname}] {r.name}: {r.getMessage()}" for r in self.records]


_log_capture = _LogCapture()

_TARGET_LOGGERS = [
    "app.services.npc.decision_hub",
    "app.services.npc.npc_tick_pipeline",
    "app.services.execution.dialogue_executor",
    "app.services.events.intent_event_adapter",
    "app.services.events.event_bus",
    "app.services.game_loop.task_scheduler",
    "app.services.game_loop.game_loop",
    "app.services.world.world_tick_engine",
    "app.services.npc.state_applicator",
    "app", "",  # root + catch-all
]


def _install_log_capture() -> None:
    root = logging.getLogger()
    if not any(isinstance(h, _LogCapture) for h in root.handlers):
        root.addHandler(_log_capture)
    root.setLevel(logging.DEBUG)
    for name in _TARGET_LOGGERS:
        lg = logging.getLogger(name)
        lg.setLevel(logging.DEBUG)
        lg.propagate = True
        if not any(isinstance(h, _LogCapture) for h in lg.handlers):
            lg.addHandler(_log_capture)


def _reset_log_capture() -> None:
    _log_capture.records.clear()


# ============================================================================
# EventBus spy
# ============================================================================
class _EventBusSpy:
    def __init__(self):
        self.published_events: List[Tuple[str, Any]] = []
        self._installed = False
        self._orig_publish = None
        self._bus = None

    def install(self, bus) -> bool:
        if self._installed:
            return True
        self._bus = bus
        self._orig_publish = bus.publish
        bus.publish = self._spy_publish
        self._installed = True
        return True

    def restore(self) -> None:
        if self._installed and self._bus is not None and self._orig_publish is not None:
            self._bus.publish = self._orig_publish
            self._installed = False

    def _spy_publish(self, event) -> None:
        try:
            ev_type = str(getattr(event, "type", "?"))
            self.published_events.append((ev_type, event))
        except Exception:
            pass
        return self._orig_publish(event)

    def clear(self) -> None:
        self.published_events.clear()


_event_bus_spy = _EventBusSpy()


# ============================================================================
# DialogueExecutor spy
# ============================================================================
class _ExecutorSpy:
    """Wrap DialogueExecutor.execute to capture input, return value, exception."""
    def __init__(self):
        self.calls: List[Dict[str, Any]] = []
        self._installed = False
        self._orig_execute = None
        self._executor = None

    def install(self, executor: Any) -> bool:
        if self._installed:
            return True
        # Find execute method
        exec_method = getattr(executor, "execute", None)
        if exec_method is None:
            return False
        self._executor = executor
        self._orig_execute = exec_method
        executor.execute = self._spy_execute
        self._installed = True
        return True

    def restore(self) -> None:
        if self._installed and self._executor is not None and self._orig_execute is not None:
            self._executor.execute = self._orig_execute
            self._installed = False

    def _spy_execute(self, *args, **kwargs) -> Any:
        call_record: Dict[str, Any] = {
            "args_repr": [repr(a)[:300] for a in args],
            "kwargs_repr": {k: repr(v)[:300] for k, v in kwargs.items()},
            "exception": None,
            "return_value": None,
        }
        try:
            result = self._orig_execute(*args, **kwargs)
            call_record["return_value"] = repr(result)[:500] if result is not None else None
            call_record["return_type"] = type(result).__name__ if result is not None else "None"
            self.calls.append(call_record)
            return result
        except Exception as e:
            call_record["exception"] = f"{type(e).__name__}: {e}"
            call_record["exception_traceback"] = traceback.format_exc()[:2000]
            self.calls.append(call_record)
            raise

    def clear(self) -> None:
        self.calls.clear()


_executor_spy = _ExecutorSpy()


# ============================================================================
# IntentEventAdapter spy
# ============================================================================
class _AdapterSpy:
    """Wrap IntentEventAdapter.to_event to capture input/output."""
    def __init__(self):
        self.calls: List[Dict[str, Any]] = []
        self._installed = False
        self._orig_to_event = None
        self._adapter_class = None

    def install(self) -> bool:
        if self._installed:
            return True
        try:
            from app.services.events.intent_event_adapter import IntentEventAdapter
            self._adapter_class = IntentEventAdapter
            self._orig_to_event = IntentEventAdapter.to_event
            IntentEventAdapter.to_event = staticmethod(self._spy_to_event)
            self._installed = True
            return True
        except Exception as e:
            print(f"  [_AdapterSpy install failed: {e}]")
            return False

    def restore(self) -> None:
        if self._installed and self._adapter_class is not None and self._orig_to_event is not None:
            self._adapter_class.to_event = self._orig_to_event
            self._installed = False

    def _spy_to_event(self, intent: Any) -> Any:
        call_record: Dict[str, Any] = {
            "intent_repr": repr(intent)[:500],
            "intent_speaker": getattr(intent, "speaker", None),
            "intent_target": getattr(intent, "target_id", None) or getattr(intent, "audience", None),
            "intent_type": getattr(intent, "intent_type", None),
            "intent_proposition": str(getattr(intent, "proposition", None))[:300],
            "exception": None,
            "return_value": None,
        }
        try:
            result = self._orig_to_event(intent)
            call_record["return_value"] = repr(result)[:300] if result is not None else None
            call_record["return_type"] = type(result).__name__ if result is not None else "None"
            call_record["return_event_type"] = str(getattr(result, "type", "?")) if result is not None else None
            self.calls.append(call_record)
            return result
        except Exception as e:
            call_record["exception"] = f"{type(e).__name__}: {e}"
            call_record["exception_traceback"] = traceback.format_exc()[:1500]
            self.calls.append(call_record)
            raise

    def clear(self) -> None:
        self.calls.clear()


_adapter_spy = _AdapterSpy()


# ============================================================================
# Source readers
# ============================================================================
def _read_file_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return f"[read error: {e}]"


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


def _read_function_full(path: Path, func_name: str, max_lines: int = 200) -> None:
    if not path.exists():
        print(f"  [file not found: {path}]")
        return
    src = _read_file_text(path)
    lines = src.split("\n")
    bounds = _find_function_bounds(src, func_name)
    if bounds:
        s, e = bounds
        # Limit max_lines
        actual_end = min(e, s + max_lines)
        print(f"  {func_name}() at L{s+1}..L{e} (showing L{s+1}..L{actual_end}):")
        for j in range(s, actual_end):
            print(f"  L{j+1:4d}: {lines[j]}")
        if actual_end < e:
            print(f"  ... ({e - actual_end} more lines)")
    else:
        print(f"  [{func_name} not found]")
        # List all defs in file
        for i, line in enumerate(lines, 1):
            stripped = line.lstrip()
            if stripped.startswith("def "):
                print(f"  L{i}: {stripped.rstrip()}")


def _grep_in_file(path: Path, pattern: str, context: int = 3, max_matches: int = 5) -> None:
    if not path.exists():
        print(f"  [file not found: {path}]")
        return
    src = _read_file_text(path)
    lines = src.split("\n")
    matches = []
    for i, line in enumerate(lines):
        if pattern.lower() in line.lower():
            matches.append(i)
    if not matches:
        print(f"  no matches for '{pattern}'")
        return
    print(f"  Found {len(matches)} matches for '{pattern}':")
    for i in matches[:max_matches]:
        ctx_start = max(0, i - context)
        ctx_end = min(len(lines), i + context + 1)
        print(f"\n  >>> L{i+1}: {lines[i].rstrip()}")
        for j in range(ctx_start, ctx_end):
            marker = ">>>" if j + 1 == i + 1 else "   "
            print(f"  {marker} L{j+1:4d}: {lines[j]}")


# ============================================================================
# MAIN
# ============================================================================
def main() -> int:
    print("=" * 78)
    print("R2-B5-D2 v2 — Trace ONE task lifecycle: DialogueExecutor → NPC_SPOKE")
    print(f"OUT_FILE: {OUT_FILE}")
    print("=" * 78)
    print()
    print("STRATEGY (per Master):")
    print("  STEP 1: Read DialogueExecutor.execute() full path")
    print("  STEP 2: Read task_scheduler._process_tasks_async")
    print("  STEP 3: Compare idle_tick vs run_turn execution paths")
    print("  STEP 4: Run probe with spies on DialogueExecutor + IntentEventAdapter + EventBus")
    print("  STEP 5: Verify success criteria (NEW belief, source_id=guard_borko)")
    print()

    _install_log_capture()

    orig_saves_dir = settings.saves_dir
    orig_env = settings.environment

    temp_dir = Path(tempfile.mkdtemp(prefix="r2_b5_d2_v2_"))

    try:
        # =====================================================================
        # STEP 1: Read DialogueExecutor.execute() full path
        # =====================================================================
        _print_section("STEP 1: DialogueExecutor.execute() full path")
        de_path = _BACKEND / "app" / "services" / "execution" / "dialogue_executor.py"
        print(f"  file: {de_path}")
        _read_function_full(de_path, "execute", max_lines=300)

        # Search for NPC_SPOKE / IntentEventAdapter / bus.publish / to_event
        print(f"\n  --- search for NPC_SPOKE / publish / to_event / IntentEventAdapter ---")
        _grep_in_file(de_path, "NPC_SPOKE", context=3, max_matches=10)
        _grep_in_file(de_path, "publish", context=3, max_matches=10)
        _grep_in_file(de_path, "to_event", context=3, max_matches=10)
        _grep_in_file(de_path, "IntentEventAdapter", context=3, max_matches=10)

        # =====================================================================
        # STEP 2: Read task_scheduler._process_tasks_async
        # =====================================================================
        _print_section("STEP 2: task_scheduler._process_tasks_async")
        ts_path = _BACKEND / "app" / "services" / "game_loop" / "task_scheduler.py"
        print(f"  file: {ts_path}")
        _read_function_full(ts_path, "_process_tasks_async", max_lines=200)

        # Also look for execute_pending and drain_commitment_outbox
        print(f"\n  --- _execute_pending or execute_pending ---")
        _read_function_full(ts_path, "execute_pending", max_lines=150)
        print(f"\n  --- drain_commitment_outbox ---")
        _read_function_full(ts_path, "drain_commitment_outbox", max_lines=150)

        # =====================================================================
        # STEP 3: Compare idle_tick vs run_turn
        # =====================================================================
        _print_section("STEP 3: idle_tick vs run_turn")
        gl_path = _BACKEND / "app" / "services" / "game_loop" / "game_loop.py"
        print(f"  file: {gl_path}")
        print(f"\n  --- idle_tick ---")
        _read_function_full(gl_path, "idle_tick", max_lines=200)
        print(f"\n  --- run_turn ---")
        _read_function_full(gl_path, "run_turn", max_lines=150)

        # =====================================================================
        # STEP 4: Run probe with spies
        # =====================================================================
        _print_section("STEP 4: Run probe with spies")

        from app.services.game_loop_builder import build_game_loop
        from app.services.events.event_bus import get_event_bus
        from app.services.events.event_types import EventType
        from app.domain.events import EventDTO
        from app.services.events.claim_event_subscriber import ClaimEventSubscriber
        from app.services.npc.epistemic_context_resolver import EpistemicContextResolver
        from app.domain.epistemology import Proposition, Predicate  # type: ignore

        settings.saves_dir = str(temp_dir)
        settings.environment = "development"
        loop = build_game_loop(data_dir=Path(settings.data_dir))
        _install_log_capture()

        scene = loop.scene_manager.get_scene_state("Open_road", "tavern")
        if scene is None:
            scene = loop.scene_manager.initialize_scene("Open_road", "tavern", "12:00")

        loaded = loop._load_npcs_with_runtime("Open_road")
        print(f"  loaded {len(loaded) if hasattr(loaded, '__len__') else '?'} NPCs")

        bus = get_event_bus()

        # Find sub + store
        sub = None
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
        store = getattr(sub, "_store", None) if sub else None

        # Install EventBus spy
        _event_bus_spy.install(bus)
        print(f"  EventBus spy installed")

        # Install IntentEventAdapter spy
        _adapter_spy.install()
        print(f"  IntentEventAdapter spy installed")

        # Find DialogueExecutor instance and install spy
        # Try loop._svc or task_scheduler
        dialogue_executor = None
        for parent_name in ("_svc", "_tick_orch", "_task_scheduler"):
            parent = getattr(loop, parent_name, None)
            if parent is None:
                continue
            # Direct attr
            for attr_name in ("_dialogue_executor", "dialogue_executor", "_executor", "executor"):
                val = getattr(parent, attr_name, None)
                # Check if it's DialogueExecutor type
                if val is not None and "DialogueExecutor" in type(val).__name__:
                    dialogue_executor = val
                    print(f"  dialogue_executor found via loop.{parent_name}.{attr_name}")
                    break
            if dialogue_executor:
                break
            # vars walk
            try:
                for k, v in vars(parent).items():
                    if "DialogueExecutor" in type(v).__name__:
                        dialogue_executor = v
                        print(f"  dialogue_executor found via loop.{parent_name}.vars[{k}]")
                        break
                if dialogue_executor:
                    break
            except Exception:
                pass

        # Also try task_scheduler
        if dialogue_executor is None:
            ts_obj = getattr(loop, "_get_task_scheduler", None)
            if ts_obj:
                ts_inst = ts_obj() if callable(ts_obj) else ts_obj
                for attr_name in dir(ts_inst):
                    if attr_name.startswith("__"):
                        continue
                    try:
                        val = getattr(ts_inst, attr_name)
                    except Exception:
                        continue
                    if val is not None and "DialogueExecutor" in type(val).__name__:
                        dialogue_executor = val
                        print(f"  dialogue_executor found via task_scheduler.{attr_name}")
                        break

        if dialogue_executor is not None:
            _executor_spy.install(dialogue_executor)
            print(f"  DialogueExecutor spy installed")
        else:
            print(f"  [DialogueExecutor not found in runtime — trying class-level]")
            try:
                from app.services.execution.dialogue_executor import DialogueExecutor
                # Find any instance in loop
                # Walk loop recursively
                visited = set()
                def _walk(obj, path, depth=0):
                    nonlocal dialogue_executor
                    if depth > 5 or id(obj) in visited:
                        return
                    visited.add(id(obj))
                    if isinstance(obj, DialogueExecutor):
                        dialogue_executor = obj
                        print(f"  dialogue_executor found via {path}")
                        return
                    try:
                        for k, v in vars(obj).items() if hasattr(obj, "__dict__") else []:
                            if k.startswith("__"):
                                continue
                            _walk(v, f"{path}.{k}", depth + 1)
                            if dialogue_executor:
                                return
                    except Exception:
                        pass
                _walk(loop, "loop")
                if dialogue_executor:
                    _executor_spy.install(dialogue_executor)
                    print(f"  DialogueExecutor spy installed (via walk)")
            except Exception as e:
                print(f"  [DialogueExecutor walk failed: {e}]")

        # =====================================================================
        # STEP 4b: Capture PRE-EXISTING Tornin beliefs
        # =====================================================================
        _print_section("STEP 4b: capture PRE-EXISTING Tornin beliefs (baseline)")
        if store:
            tornin_pre_records = store.get_all_for_agent("tavern_keeper_tornin") or []
            print(f"  Tornin pre-existing records: {len(tornin_pre_records)}")
            for r in tornin_pre_records:
                prop = getattr(r, "proposition", None)
                print(f"    proposition={str(prop)[:100]}")
                print(f"      confidence={getattr(r, 'confidence', None)} "
                      f"source_id={getattr(r, 'source_id', None)} "
                      f"original_source_id={getattr(r, 'original_source_id', None)}")

        # =====================================================================
        # STEP 4c: Publish PLAYER_INSULTS
        # =====================================================================
        _print_section("STEP 4c: publish PLAYER_INSULTS")
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
        if store:
            tornin_after_publish = store.get("tavern_keeper_tornin", expected_prop)
            print(f"  Tornin belief after publish: confidence={getattr(tornin_after_publish, 'confidence', None)} "
                  f"source_id={getattr(tornin_after_publish, 'source_id', None)} "
                  f"original_source_id={getattr(tornin_after_publish, 'original_source_id', None)}")

        # Clear spies
        _event_bus_spy.clear()
        _executor_spy.clear()
        _adapter_spy.clear()
        _reset_log_capture()

        # =====================================================================
        # STEP 4d: Run idle_tick (with spies active)
        # =====================================================================
        _print_section("STEP 4d: run idle_tick with spies")
        try:
            result = loop.idle_tick("Open_road", "tavern")
            print(f"  idle_tick returned: {type(result).__name__}")
            if isinstance(result, dict):
                print(f"  status: {result.get('status')}")
                events_count = len(result.get("events", [])) if isinstance(result.get("events"), list) else 0
                print(f"  events count: {events_count}")
        except Exception as e:
            print(f"  ERROR: {type(e).__name__}: {e}")
            traceback.print_exc()

        # =====================================================================
        # STEP 5: Inspect spy results
        # =====================================================================
        _print_section("STEP 5: spy results")

        # 5a. DialogueExecutor calls
        print(f"\n  === DialogueExecutor.execute() calls ===")
        print(f"  Total calls: {len(_executor_spy.calls)}")
        for i, call in enumerate(_executor_spy.calls):
            print(f"\n  Call [{i}]:")
            print(f"    args: {call['args_repr']}")
            print(f"    kwargs: {call['kwargs_repr']}")
            if call.get("exception"):
                print(f"    EXCEPTION: {call['exception']}")
                print(f"    TRACEBACK:")
                print(call.get("exception_traceback", "")[:1500])
            else:
                print(f"    return_type: {call.get('return_type', 'N/A')}")
                print(f"    return_value: {call.get('return_value', 'N/A')[:300]}")

        # 5b. IntentEventAdapter calls
        print(f"\n  === IntentEventAdapter.to_event() calls ===")
        print(f"  Total calls: {len(_adapter_spy.calls)}")
        for i, call in enumerate(_adapter_spy.calls):
            print(f"\n  Call [{i}]:")
            print(f"    speaker: {call['intent_speaker']}")
            print(f"    target: {call['intent_target']}")
            print(f"    intent_type: {call['intent_type']}")
            print(f"    proposition: {call['intent_proposition']}")
            if call.get("exception"):
                print(f"    EXCEPTION: {call['exception']}")
            else:
                print(f"    return_event_type: {call.get('return_event_type', 'N/A')}")
                print(f"    return_value: {call.get('return_value', 'N/A')[:200]}")

        # 5c. EventBus events
        print(f"\n  === EventBus.publish() calls ===")
        print(f"  Total events published: {len(_event_bus_spy.published_events)}")
        ev_type_counter: Dict[str, int] = {}
        for ev_type, _ in _event_bus_spy.published_events:
            ev_type_counter[ev_type] = ev_type_counter.get(ev_type, 0) + 1
        for ev_type, count in sorted(ev_type_counter.items()):
            print(f"    {ev_type}: {count}")

        # NPC_SPOKE specific
        npc_spoke_events = [e for t, e in _event_bus_spy.published_events if "npc_spoke" in t.lower()]
        spread_rumor_events = [e for t, e in _event_bus_spy.published_events if "spread_rumor" in t.lower()]
        print(f"\n  NPC_SPOKE events: {len(npc_spoke_events)}")
        print(f"  SPREAD_RUMOR events: {len(spread_rumor_events)}")

        # If spread_rumor or npc_spoke events were published, dump details
        for ev_list, ev_name in [(npc_spoke_events, "NPC_SPOKE"), (spread_rumor_events, "SPREAD_RUMOR")]:
            if ev_list:
                print(f"\n  --- {ev_name} event details ---")
                for i, e in enumerate(ev_list[:5]):
                    p = getattr(e, "payload", {}) or {}
                    print(f"    [{i}] source={getattr(e, 'source', '?')} "
                          f"target_id={p.get('target_id')} "
                          f"intent_type={p.get('intent_type')} "
                          f"topic={p.get('topic')} "
                          f"has_proposition={bool(p.get('proposition'))}")
                    if p.get("proposition"):
                        print(f"         proposition: {p.get('proposition')}")

        # 5d. DecisionHub logs for guard_borko
        print(f"\n  === DecisionHub logs for guard_borko ===")
        all_logs = _log_capture.messages()
        borko_logs = [l for l in all_logs if "guard_borko" in l and "DECISION_HUB" in l]
        for l in borko_logs[:15]:
            print(f"    {l[:200]}")
        print(f"  total borko DH logs: {len(borko_logs)}")

        # 5e. DialogueExecutor logs
        print(f"\n  === DialogueExecutor logs ===")
        de_logs = [l for l in all_logs if "dialogue_executor" in l.lower() or "DIALOGUE_EXEC" in l]
        for l in de_logs[:20]:
            print(f"    {l[:200]}")
        print(f"  total DE logs: {len(de_logs)}")

        # 5f. Adapter logs
        print(f"\n  === IntentEventAdapter logs ===")
        ad_logs = [l for l in all_logs if "intent_event_adapter" in l.lower() or "INTENT_EVENT_ADAPTER" in l]
        for l in ad_logs[:20]:
            print(f"    {l[:200]}")
        print(f"  total adapter logs: {len(ad_logs)}")

        # 5g. Task scheduler logs (borko-related)
        print(f"\n  === Task scheduler logs (borko-related) ===")
        ts_logs = [l for l in all_logs if ("task_scheduler" in l.lower() or "TASK_SCHED" in l) and "guard_borko" in l]
        for l in ts_logs[:20]:
            print(f"    {l[:200]}")
        print(f"  total TS borko logs: {len(ts_logs)}")

        # 5h. NPC_SPOKE logs
        print(f"\n  === NPC_SPOKE / spread_rumor logs ===")
        ns_logs = [l for l in all_logs if "NPC_SPOKE" in l or "spread_rumor" in l.lower()]
        for l in ns_logs[:20]:
            print(f"    {l[:200]}")
        print(f"  total: {len(ns_logs)}")

        # =====================================================================
        # STEP 6: Check Tornin belief AFTER idle_tick (with corrected success criteria)
        # =====================================================================
        _print_section("STEP 6: Tornin belief AFTER idle_tick (corrected success criteria)")
        if store:
            tornin_records_after = store.get_all_for_agent("tavern_keeper_tornin") or []
            print(f"  Tornin total records: {len(tornin_records_after)}")
            for r in tornin_records_after:
                prop = getattr(r, "proposition", None)
                source_id = getattr(r, "source_id", None)
                orig_source = getattr(r, "original_source_id", None)
                conf = getattr(r, "confidence", None)
                print(f"    proposition={str(prop)[:80]}")
                print(f"      confidence={conf} source_id={source_id} original_source_id={orig_source}")

            # NEW belief from guard_borko?
            new_borko_belief = [
                r for r in tornin_records_after
                if getattr(r, "source_id", None) == "guard_borko"
            ]
            print(f"\n  Tornin beliefs with source_id='guard_borko': {len(new_borko_belief)}")
            for r in new_borko_belief:
                prop = getattr(r, "proposition", None)
                print(f"    proposition={str(prop)[:120]}")
                print(f"      confidence={getattr(r, 'confidence', None)} "
                      f"original_source_id={getattr(r, 'original_source_id', None)}")

        # =====================================================================
        # STEP 7: VERDICT
        # =====================================================================
        _print_section("STEP 7: VERDICT")

        # Correct success criteria:
        # NEW belief for Tornin with source_id='guard_borko' AND original_source_id='player'
        has_new_borko_belief = False
        if store:
            tornin_records = store.get_all_for_agent("tavern_keeper_tornin") or []
            for r in tornin_records:
                if (getattr(r, "source_id", None) == "guard_borko"
                    and getattr(r, "original_source_id", None) == "player"):
                    has_new_borko_belief = True
                    break

        npc_spoke_count = len(npc_spoke_events) + len(spread_rumor_events)
        executor_called = len(_executor_spy.calls) > 0
        adapter_called = len(_adapter_spy.calls) > 0

        print(f"  Executor called: {executor_called}")
        print(f"  Adapter called: {adapter_called}")
        print(f"  NPC_SPOKE/SPREAD_RUMOR events published: {npc_spoke_count}")
        print(f"  NEW Tornin belief with source_id='guard_borko' (orig='player'): {has_new_borko_belief}")
        print()

        if has_new_borko_belief:
            print("  >>> VERDICT: B5-D2 NOT A DEFECT — chain completed")
            print("  >>> Tornin received NEW belief from guard_borko with provenance chain")
        elif npc_spoke_count > 0:
            print("  >>> VERDICT: PARTIAL — NPC_SPOKE published but no new Tornin belief")
            print("  >>> Investigate on_npc_spoke handler for spread_rumor (B5-D2 original)")
        elif executor_called and not adapter_called:
            print("  >>> VERDICT: BREAK — DialogueExecutor called but IntentEventAdapter NOT called")
            print("  >>> Executor returned without producing event")
            if _executor_spy.calls:
                last_call = _executor_spy.calls[-1]
                if last_call.get("exception"):
                    print(f"  >>> Exception: {last_call['exception']}")
                else:
                    print(f"  >>> Return: {last_call.get('return_value', 'N/A')[:200]}")
        elif executor_called and adapter_called and npc_spoke_count == 0:
            print("  >>> VERDICT: BREAK — Adapter called but NPC_SPOKE not published")
            print("  >>> Something between IntentEventAdapter.to_event() and bus.publish() failed")
            if _adapter_spy.calls:
                last_call = _adapter_spy.calls[-1]
                if last_call.get("exception"):
                    print(f"  >>> Adapter exception: {last_call['exception']}")
                else:
                    print(f"  >>> Adapter returned event_type: {last_call.get('return_event_type', 'N/A')}")
        elif not executor_called:
            print("  >>> VERDICT: BREAK — DialogueExecutor.execute() NOT called")
            print("  >>> Task scheduler didn't dispatch task")
        else:
            print("  >>> VERDICT: INCONCLUSIVE — needs manual inspection of spy results")

        # ---- Cleanup ----
        _event_bus_spy.restore()
        _adapter_spy.restore()
        _executor_spy.restore()
        try:
            ts = loop._get_task_scheduler()
            if hasattr(ts, "_executor_pool"):
                ts._executor_pool.shutdown(wait=False, cancel_futures=True)
        except Exception:
            pass
        del loop
        import gc
        gc.collect()

    except Exception as e:
        print(f"[FATAL: {e}]")
        traceback.print_exc()
    finally:
        settings.saves_dir = orig_saves_dir
        settings.environment = orig_env
        _event_bus_spy.restore()
        _adapter_spy.restore()
        _executor_spy.restore()
        shutil.rmtree(temp_dir, ignore_errors=True)

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
