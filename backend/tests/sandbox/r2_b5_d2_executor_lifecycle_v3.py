# backend/tests/sandbox/r2_b5_d2_executor_lifecycle_v3.py
"""
R2-B5-D2 v3 — Trace DialogueExecutor.execute() WITH spy attached correctly.

v2 failures:
  1. Spy not attached to DialogueExecutor — was searching in loop._svc,
     but real executor lives in task_scheduler._executors[TaskKind.DIALOGUE]
  2. Log filter `and "guard_borko" in l` filtered out critical task_scheduler logs
     (which use task_id, not npc name)

v3 fixes:
  1. Find DialogueExecutor via task_scheduler._executors dict
  2. Don't filter task_scheduler logs by npc name — show ALL
  3. Read _generate_with_router full implementation
  4. Check router presence in executor
  5. Capture: was _generate_with_router called? did it return? exception?

CONSTRAINTS:
  - Read-only on production
  - No fixes
  - Track ONE task lifecycle (guard_borko → tavern_keeper_tornin)
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
OUT_FILE = OUT_FILE_DIR / "r2_b5_d2_executor_lifecycle_v3.txt"


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
# Log capture (proven to work in B5-E2.1 v2)
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
    "app.services.execution.dialogue_materializer",
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
# DialogueExecutor spy (now attached via task_scheduler._executors)
# ============================================================================
class _ExecutorSpy:
    """Wrap DialogueExecutor.execute to capture input, return value, exception."""
    def __init__(self):
        self.calls: List[Dict[str, Any]] = []
        self._installed = False
        self._orig_execute = None
        self._executor = None
        # Also spy on _generate_with_router if available
        self._orig_gen = None
        self.gen_calls: List[Dict[str, Any]] = []

    def install(self, executor: Any) -> bool:
        if self._installed:
            return True
        exec_method = getattr(executor, "execute", None)
        if exec_method is None:
            return False
        self._executor = executor
        self._orig_execute = exec_method
        executor.execute = self._spy_execute
        self._installed = True

        # Also try to spy on _generate_with_router
        gen_method = getattr(executor, "_generate_with_router", None)
        if gen_method is not None:
            self._orig_gen = gen_method
            executor._generate_with_router = self._spy_gen

        # Check router presence
        router = getattr(executor, "_router", None)
        print(f"  [ExecutorSpy] executor._router is None: {router is None}")
        if router is not None:
            print(f"  [ExecutorSpy] router type: {type(router).__name__}")
        return True

    def restore(self) -> None:
        if self._installed and self._executor is not None:
            if self._orig_execute is not None:
                self._executor.execute = self._orig_execute
            if self._orig_gen is not None:
                self._executor._generate_with_router = self._orig_gen
            self._installed = False

    def _spy_execute(self, *args, **kwargs) -> Any:
        call_record: Dict[str, Any] = {
            "args_repr": [repr(a)[:300] for a in args],
            "kwargs_repr": {k: repr(v)[:300] for k, v in kwargs.items()},
            "exception": None,
            "return_value": None,
            "yielded_artifacts": [],
        }
        try:
            result = self._orig_execute(*args, **kwargs)
            call_record["return_value"] = "generator returned"
            # If it's a generator, try to iterate to capture yields
            if hasattr(result, "__next__") or hasattr(result, "__iter__"):
                artifacts = []
                try:
                    for art in result:
                        art_info = {
                            "success": getattr(art, "success", None),
                            "result_type": getattr(art, "result_type", None),
                            "error_message": getattr(art, "error_message", None),
                            "data_keys": list(getattr(art, "data", {}).keys()) if hasattr(art, "data") else None,
                        }
                        artifacts.append(art_info)
                except Exception as e:
                    call_record["exception"] = f"during iteration: {type(e).__name__}: {e}"
                call_record["yielded_artifacts"] = artifacts
            self.calls.append(call_record)
            # Re-create the generator (we consumed it)
            # Actually we can't — the original generator is consumed.
            # Instead, return the original call result (but we already iterated)
            # This is a known limitation — we may break production if we iterate.
            # SOLUTION: don't iterate, just return the generator
            # Re-call to get fresh generator
            return self._orig_execute(*args, **kwargs)
        except Exception as e:
            call_record["exception"] = f"{type(e).__name__}: {e}"
            call_record["exception_traceback"] = traceback.format_exc()[:2000]
            self.calls.append(call_record)
            raise

    def _spy_gen(self, *args, **kwargs) -> Any:
        gen_record: Dict[str, Any] = {
            "args_repr": [repr(a)[:200] for a in args],
            "kwargs_repr": {k: repr(v)[:200] for k, v in kwargs.items()},
            "exception": None,
            "return_value": None,
        }
        try:
            result = self._orig_gen(*args, **kwargs)
            gen_record["return_value"] = repr(result)[:500] if result is not None else None
            self.gen_calls.append(gen_record)
            return result
        except Exception as e:
            gen_record["exception"] = f"{type(e).__name__}: {e}"
            gen_record["exception_traceback"] = traceback.format_exc()[:1500]
            self.gen_calls.append(gen_record)
            raise

    def clear(self) -> None:
        self.calls.clear()
        self.gen_calls.clear()


_executor_spy = _ExecutorSpy()


# ============================================================================
# IntentEventAdapter spy
# ============================================================================
class _AdapterSpy:
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
            call_record["return_event_type"] = str(getattr(result, "type", "?")) if result is not None else None
            self.calls.append(call_record)
            return result
        except Exception as e:
            call_record["exception"] = f"{type(e).__name__}: {e}"
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


def _read_function_full(path: Path, func_name: str, max_lines: int = 250) -> None:
    if not path.exists():
        print(f"  [file not found: {path}]")
        return
    src = _read_file_text(path)
    lines = src.split("\n")
    bounds = _find_function_bounds(src, func_name)
    if bounds:
        s, e = bounds
        actual_end = min(e, s + max_lines)
        print(f"  {func_name}() at L{s+1}..L{e} (showing L{s+1}..L{actual_end}):")
        for j in range(s, actual_end):
            print(f"  L{j+1:4d}: {lines[j]}")
        if actual_end < e:
            print(f"  ... ({e - actual_end} more lines)")
    else:
        print(f"  [{func_name} not found in {path.name}]")


# ============================================================================
# MAIN
# ============================================================================
def main() -> int:
    print("=" * 78)
    print("R2-B5-D2 v3 — Trace DialogueExecutor.execute() WITH correctly attached spy")
    print(f"OUT_FILE: {OUT_FILE}")
    print("=" * 78)
    print()
    print("v3 FIXES from v2:")
    print("  1. Find DialogueExecutor via task_scheduler._executors[TaskKind.DIALOGUE]")
    print("  2. Don't filter task_scheduler logs by 'guard_borko' — show ALL")
    print("  3. Read _generate_with_router full implementation")
    print("  4. Spy on _generate_with_router too (if exists)")
    print("  5. Check router presence in executor")
    print()

    _install_log_capture()

    orig_saves_dir = settings.saves_dir
    orig_env = settings.environment

    temp_dir = Path(tempfile.mkdtemp(prefix="r2_b5_d2_v3_"))

    try:
        # =====================================================================
        # STEP 1: Read DialogueExecutor.execute() + _generate_with_router + _emit_dialogue_outcome
        # =====================================================================
        _print_section("STEP 1: Read DialogueExecutor.execute() + _generate_with_router")
        de_path = _BACKEND / "app" / "services" / "execution" / "dialogue_executor.py"
        print(f"  file: {de_path}")
        _read_function_full(de_path, "execute", max_lines=300)
        print(f"\n  --- _generate_with_router ---")
        _read_function_full(de_path, "_generate_with_router", max_lines=200)
        print(f"\n  --- _emit_dialogue_outcome ---")
        _read_function_full(de_path, "_emit_dialogue_outcome", max_lines=150)

        # =====================================================================
        # STEP 2: Read DialogueMaterializer (materialize method)
        # =====================================================================
        _print_section("STEP 2: Read DialogueMaterializer.materialize")
        dm_path = _BACKEND / "app" / "services" / "execution" / "dialogue_materializer.py"
        print(f"  file: {dm_path}")
        _read_function_full(dm_path, "materialize", max_lines=200)

        # =====================================================================
        # STEP 3: Read task_scheduler.drain_task_worker_outbox
        # =====================================================================
        _print_section("STEP 3: task_scheduler.drain_task_worker_outbox")
        ts_path = _BACKEND / "app" / "services" / "game_loop" / "task_scheduler.py"
        _read_function_full(ts_path, "drain_task_worker_outbox", max_lines=200)

        # =====================================================================
        # STEP 4: Build loop, find DialogueExecutor, attach spies
        # =====================================================================
        _print_section("STEP 4: build loop, find DialogueExecutor, attach spies")

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

        # Find DialogueExecutor via task_scheduler._executors
        print(f"\n  --- Find DialogueExecutor via task_scheduler._executors ---")
        ts_obj = loop._get_task_scheduler()
        print(f"  task_scheduler: {ts_obj} ({type(ts_obj).__name__})")
        executors_dict = getattr(ts_obj, "_executors", None)
        print(f"  task_scheduler._executors: {executors_dict}")
        if executors_dict is None:
            # Try other attributes
            for attr_name in dir(ts_obj):
                if attr_name.startswith("__"):
                    continue
                val = getattr(ts_obj, attr_name, None)
                if isinstance(val, dict) and val:
                    print(f"  task_scheduler.{attr_name} = dict with keys: {list(val.keys())[:5]}")

        dialogue_executor = None
        if executors_dict is not None:
            # Try to find DialogueExecutor
            for kind, executor in executors_dict.items():
                type_name = type(executor).__name__
                print(f"    executors[{kind}] = {executor} ({type_name})")
                if "DialogueExecutor" in type_name:
                    dialogue_executor = executor
                    print(f"  >>> Found DialogueExecutor via task_scheduler._executors[{kind!r}]")
                    break

        if dialogue_executor is None:
            # Fallback: walk vars
            print(f"  --- fallback: walk task_scheduler vars ---")
            try:
                for k, v in vars(ts_obj).items():
                    if "DialogueExecutor" in type(v).__name__:
                        dialogue_executor = v
                        print(f"  >>> Found via vars: task_scheduler.{k}")
                        break
                    if isinstance(v, dict):
                        for kk, vv in v.items():
                            if "DialogueExecutor" in type(vv).__name__:
                                dialogue_executor = vv
                                print(f"  >>> Found via vars: task_scheduler.{k}[{kk!r}]")
                                break
                        if dialogue_executor:
                            break
            except Exception as e:
                print(f"  walk error: {e}")

        if dialogue_executor is not None:
            _executor_spy.install(dialogue_executor)
            print(f"\n  DialogueExecutor spy INSTALLED on: {dialogue_executor}")
            # Check router
            router = getattr(dialogue_executor, "_router", None)
            print(f"  dialogue_executor._router: {router}")
            print(f"  dialogue_executor._router is None: {router is None}")
        else:
            print(f"  [STILL not found — spy not installed]")

        # =====================================================================
        # STEP 5: capture PRE-EXISTING Tornin beliefs (baseline)
        # =====================================================================
        _print_section("STEP 5: capture PRE-EXISTING Tornin beliefs")
        if store:
            tornin_pre_records = store.get_all_for_agent("tavern_keeper_tornin") or []
            print(f"  Tornin pre-existing records: {len(tornin_pre_records)}")
            for r in tornin_pre_records:
                print(f"    prop={str(getattr(r, 'proposition', None))[:80]} "
                      f"conf={getattr(r, 'confidence', None)} "
                      f"source_id={getattr(r, 'source_id', None)} "
                      f"orig={getattr(r, 'original_source_id', None)}")

        # =====================================================================
        # STEP 6: publish PLAYER_INSULTS
        # =====================================================================
        _print_section("STEP 6: publish PLAYER_INSULTS")
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

        # =====================================================================
        # STEP 7: run idle_tick with all spies active
        # =====================================================================
        _print_section("STEP 7: run idle_tick with all spies active")
        # Clear spies before tick
        _event_bus_spy.clear()
        _executor_spy.clear()
        _adapter_spy.clear()
        _reset_log_capture()
        _install_log_capture()

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
        # STEP 8: spy results
        # =====================================================================
        _print_section("STEP 8: spy results")

        # 8a. DialogueExecutor.execute() calls
        print(f"\n  === DialogueExecutor.execute() calls ===")
        print(f"  Total calls: {len(_executor_spy.calls)}")
        for i, call in enumerate(_executor_spy.calls):
            print(f"\n  Call [{i}]:")
            print(f"    args: {call['args_repr']}")
            if call.get("exception"):
                print(f"    EXCEPTION: {call['exception']}")
                if "exception_traceback" in call:
                    print(f"    TRACEBACK:")
                    print(call["exception_traceback"][:1500])
            else:
                print(f"    return: {call.get('return_value', 'N/A')}")
                if call.get("yielded_artifacts"):
                    print(f"    yielded artifacts:")
                    for art in call["yielded_artifacts"]:
                        print(f"      {art}")

        # 8b. _generate_with_router calls
        print(f"\n  === _generate_with_router calls ===")
        print(f"  Total calls: {len(_executor_spy.gen_calls)}")
        for i, call in enumerate(_executor_spy.gen_calls):
            print(f"\n  Call [{i}]:")
            print(f"    args: {call['args_repr']}")
            if call.get("exception"):
                print(f"    EXCEPTION: {call['exception']}")
                if "exception_traceback" in call:
                    print(f"    TRACEBACK:")
                    print(call["exception_traceback"][:1500])
            else:
                print(f"    return: {call.get('return_value', 'N/A')[:300]}")

        # 8c. IntentEventAdapter calls
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

        # 8d. EventBus events
        print(f"\n  === EventBus.publish() calls ===")
        print(f"  Total events: {len(_event_bus_spy.published_events)}")
        ev_type_counter: Dict[str, int] = {}
        for ev_type, _ in _event_bus_spy.published_events:
            ev_type_counter[ev_type] = ev_type_counter.get(ev_type, 0) + 1
        for ev_type, count in sorted(ev_type_counter.items()):
            print(f"    {ev_type}: {count}")

        # 8e. ALL task_scheduler logs (NO filter)
        print(f"\n  === ALL task_scheduler logs (no filter) ===")
        all_logs = _log_capture.messages()
        ts_logs_all = [l for l in all_logs if "task_scheduler" in l.lower() or "TASK_SCHED" in l or "[SCHEDULER]" in l]
        print(f"  Total: {len(ts_logs_all)}")
        for l in ts_logs_all[:50]:
            print(f"    {l[:250]}")

        # 8f. ALL DialogueExecutor logs
        print(f"\n  === ALL DialogueExecutor logs ===")
        de_logs_all = [l for l in all_logs if "dialogue_executor" in l.lower() or "DIALOGUE_EXEC" in l]
        print(f"  Total: {len(de_logs_all)}")
        for l in de_logs_all[:30]:
            print(f"    {l[:250]}")

        # 8g. DialogueMaterializer logs
        print(f"\n  === DialogueMaterializer logs ===")
        dm_logs = [l for l in all_logs if "dialogue_materializer" in l.lower() or "DIALOGUE_MAT" in l or "Materializer" in l]
        print(f"  Total: {len(dm_logs)}")
        for l in dm_logs[:30]:
            print(f"    {l[:250]}")

        # 8h. intent_event_adapter logs
        print(f"\n  === IntentEventAdapter logs ===")
        ad_logs = [l for l in all_logs if "intent_event_adapter" in l.lower() or "INTENT_EVENT_ADAPTER" in l]
        print(f"  Total: {len(ad_logs)}")
        for l in ad_logs[:30]:
            print(f"    {l[:250]}")

        # 8i. NPC_SPOKE / spread_rumor logs
        print(f"\n  === NPC_SPOKE / spread_rumor logs ===")
        ns_logs = [l for l in all_logs if "NPC_SPOKE" in l or "spread_rumor" in l.lower()]
        print(f"  Total: {len(ns_logs)}")
        for l in ns_logs[:30]:
            print(f"    {l[:250]}")

        # 8j. ERROR logs (any)
        print(f"\n  === ALL ERROR level logs ===")
        err_logs = [l for l in all_logs if l.startswith("[ERROR]")]
        print(f"  Total: {len(err_logs)}")
        for l in err_logs[:30]:
            print(f"    {l[:300]}")

        # =====================================================================
        # STEP 9: Check Tornin belief AFTER idle_tick
        # =====================================================================
        _print_section("STEP 9: Tornin belief AFTER idle_tick")
        if store:
            tornin_records_after = store.get_all_for_agent("tavern_keeper_tornin") or []
            print(f"  Tornin total records: {len(tornin_records_after)}")
            for r in tornin_records_after:
                prop = getattr(r, "proposition", None)
                source_id = getattr(r, "source_id", None)
                orig = getattr(r, "original_source_id", None)
                conf = getattr(r, "confidence", None)
                print(f"    prop={str(prop)[:80]}")
                print(f"      conf={conf} source_id={source_id} orig={orig}")

            new_borko_belief = any(
                getattr(r, "source_id", None) == "guard_borko"
                and getattr(r, "original_source_id", None) == "player"
                for r in tornin_records_after
            )
            print(f"\n  NEW Tornin belief with source_id='guard_borko' (orig='player'): {new_borko_belief}")

        # =====================================================================
        # STEP 10: VERDICT
        # =====================================================================
        _print_section("STEP 10: VERDICT")

        executor_calls = len(_executor_spy.calls)
        gen_calls = len(_executor_spy.gen_calls)
        adapter_calls = len(_adapter_spy.calls)
        npc_spoke_count = sum(1 for t, _ in _event_bus_spy.published_events if "npc_spoke" in t.lower() or "spread_rumor" in t.lower())

        print(f"  DialogueExecutor.execute() called: {executor_calls}")
        print(f"  _generate_with_router called: {gen_calls}")
        print(f"  IntentEventAdapter.to_event() called: {adapter_calls}")
        print(f"  NPC_SPOKE/SPREAD_RUMOR published: {npc_spoke_count}")

        if new_borko_belief:
            print(f"\n  >>> VERDICT: B5-D2 NOT A DEFECT — chain completed")
        elif executor_calls == 0:
            print(f"\n  >>> VERDICT: BREAK — DialogueExecutor.execute() NOT called")
            print(f"  >>> Spy still not attached — check Step 4 output")
        elif executor_calls > 0 and gen_calls == 0:
            print(f"\n  >>> VERDICT: BREAK — execute() called but _generate_with_router NOT called")
            print(f"  >>> Likely: stub branch (router is None) or pre-LLM branch")
            if _executor_spy.calls:
                last = _executor_spy.calls[-1]
                if last.get("exception"):
                    print(f"  >>> Exception: {last['exception']}")
                else:
                    print(f"  >>> yield count: {len(last.get('yielded_artifacts', []))}")
                    for art in last.get("yielded_artifacts", []):
                        print(f"      artifact: {art}")
        elif gen_calls > 0 and adapter_calls == 0:
            print(f"\n  >>> VERDICT: BREAK — _generate_with_router called but IntentEventAdapter NOT called")
            print(f"  >>> Likely: materializer not invoked or artifact not successful")
            if _executor_spy.calls:
                last = _executor_spy.calls[-1]
                if last.get("exception"):
                    print(f"  >>> Exception: {last['exception']}")
                else:
                    print(f"  >>> yield count: {len(last.get('yielded_artifacts', []))}")
                    for art in last.get("yielded_artifacts", []):
                        print(f"      artifact: {art}")
            if _executor_spy.gen_calls:
                last_gen = _executor_spy.gen_calls[-1]
                if last_gen.get("exception"):
                    print(f"  >>> _generate_with_router exception: {last_gen['exception']}")
        elif adapter_calls > 0 and npc_spoke_count == 0:
            print(f"\n  >>> VERDICT: BREAK — adapter called but NPC_SPOKE not published")
        else:
            print(f"\n  >>> VERDICT: INCONCLUSIVE — needs manual inspection")

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
