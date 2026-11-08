# backend/tests/sandbox/r2_b5_d2_executor_lifecycle_v7.py
"""
R2-B5-D2 v7 — Find WHERE [DIALOGUE_EXEC] log comes from (LogRecord source).

v6 finding:
  - After idle_tick: execute_calls=0, but [DIALOGUE_EXEC] logs=3
  - Spy verified installed (DialogueExecutor.execute is _spy_execute: True)

Hypothesis A: log is captured 3x due to multi-handler attachment (root + app + dialogue_executor)
  → 1 actual log = 3 records in _log_capture
  → If true, deduplicating → 1 actual log per idle_tick
  → But execute_calls=0 still means spy wasn't triggered for that 1 call

Hypothesis B: [DIALOGUE_EXEC] log comes from DIFFERENT file, not dialogue_executor.execute()
  → String matches but emitter is elsewhere

v7 strategy:
  1. Attach _log_capture to ROOT ONLY (avoid duplicate capture)
  2. Capture LogRecord.pathname, lineno, funcName for each [DIALOGUE_EXEC] log
  3. Grep production code for "[DIALOGUE_EXEC] Executing task" string
  4. Identify EXACT source file + line + function of each log

READ-ONLY. Production-код не менять.
"""
from __future__ import annotations

import os
import sys
import gc
import json
import re
import shutil
import traceback
import io
import logging
import tempfile
import types
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
OUT_FILE = OUT_FILE_DIR / "r2_b5_d2_executor_lifecycle_v7.txt"


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
# Log capture — ROOT ONLY (avoid duplicates)
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

    def messages_with_source(self) -> List[Dict[str, Any]]:
        """Return messages with full source info."""
        out = []
        for r in self.records:
            out.append({
                "level": r.levelname,
                "logger_name": r.name,
                "message": r.getMessage(),
                "pathname": r.pathname,
                "lineno": r.lineno,
                "funcName": r.funcName,
                "module": r.module,
            })
        return out

    def messages(self) -> List[str]:
        return [f"[{r.levelname}] {r.name}: {r.getMessage()}" for r in self.records]


_log_capture = _LogCapture()


def _install_log_capture() -> None:
    """Install log capture on ROOT ONLY (avoid duplicate capture)."""
    root = logging.getLogger()
    # Remove existing _LogCapture handlers (in case of reinstall)
    root.handlers = [h for h in root.handlers if not isinstance(h, _LogCapture)]
    if not any(isinstance(h, _LogCapture) for h in root.handlers):
        root.addHandler(_log_capture)
    root.setLevel(logging.DEBUG)


def _reset_log_capture() -> None:
    _log_capture.records.clear()


def _find_de_logs_with_source() -> List[Dict[str, Any]]:
    """Find all [DIALOGUE_EXEC] logs with full source info."""
    msgs = _log_capture.messages_with_source()
    return [m for m in msgs if "DIALOGUE_EXEC" in m["message"] or "dialogue_executor" in m["logger_name"].lower()]


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
# PLAIN MODULE-LEVEL SPY FUNCTIONS (from v5/v6)
# ============================================================================
_executor_calls: List[Dict[str, Any]] = []
_orig_execute: Optional[Callable] = None
_orig_gen: Optional[Callable] = None

_materializer_calls: List[Dict[str, Any]] = []
_orig_materialize: Optional[Callable] = None

_adapter_calls: List[Dict[str, Any]] = []
_orig_to_event: Optional[Callable] = None


def _spy_execute(self: Any, task: Any) -> Any:
    """Spy on DialogueExecutor.execute."""
    call_record: Dict[str, Any] = {
        "instance_id": id(self),
        "instance_type": type(self).__name__,
        "instance_router": repr(getattr(self, "_router", None))[:120],
        "task_owner_id": getattr(task, "owner_id", None),
        "task_kind": str(getattr(task, "kind", None)),
        "task_payload_type": type(getattr(task, "payload", None)).__name__,
        "exception": None,
        "yielded_artifacts": [],
    }
    payload = getattr(task, "payload", None)
    if payload is not None:
        call_record["payload_target_id"] = getattr(payload, "target_id", None)
        call_record["payload_intent_type"] = getattr(payload, "intent_type", None)
        call_record["payload_topic"] = getattr(payload, "topic", None)
        call_record["payload_proposition"] = str(getattr(payload, "proposition", None))[:200]
    try:
        result = _orig_execute(self, task)
        call_record["return_type"] = type(result).__name__
        if hasattr(result, "__iter__") or hasattr(result, "__next__"):
            call_record["is_generator"] = True
            artifacts = []
            try:
                for art in result:
                    art_info = {
                        "success": getattr(art, "success", None),
                        "result_type": getattr(art, "result_type", None),
                        "error_message": getattr(art, "error_message", None),
                        "data_keys": list(getattr(art, "data", {}).keys()) if hasattr(art, "data") else None,
                    }
                    if hasattr(art, "data") and isinstance(art.data, dict):
                        art_info["data_text"] = str(art.data.get("text", ""))[:200]
                        art_info["data_proposition"] = str(art.data.get("proposition", ""))[:200]
                    artifacts.append(art_info)
            except Exception as e:
                call_record["iteration_exception"] = f"{type(e).__name__}: {e}"
                call_record["iteration_traceback"] = traceback.format_exc()[:1500]
            call_record["yielded_artifacts"] = artifacts
        else:
            call_record["is_generator"] = False
            call_record["return_value"] = repr(result)[:300]
        _executor_calls.append(call_record)
        return _orig_execute(self, task)
    except Exception as e:
        call_record["exception"] = f"{type(e).__name__}: {e}"
        call_record["exception_traceback"] = traceback.format_exc()[:2000]
        _executor_calls.append(call_record)
        raise


def _spy_generate_with_router(self: Any, task: Any, req: Any, verdict: Any = None) -> str:
    call_record: Dict[str, Any] = {
        "instance_id": id(self),
        "task_owner_id": getattr(task, "owner_id", None),
        "req_target_id": getattr(req, "target_id", None),
        "req_intent_type": getattr(req, "intent_type", None),
        "req_topic": getattr(req, "topic", None),
        "req_proposition": str(getattr(req, "proposition", None))[:200],
        "verdict": repr(verdict)[:120],
        "exception": None,
        "return_value": None,
    }
    try:
        result = _orig_gen(self, task, req, verdict)
        call_record["return_value"] = repr(result)[:500] if result is not None else None
        _executor_calls.append(call_record)
        return result
    except Exception as e:
        call_record["exception"] = f"{type(e).__name__}: {e}"
        call_record["exception_traceback"] = traceback.format_exc()[:1500]
        _executor_calls.append(call_record)
        raise


def _spy_materialize(self: Any, artifact: Any) -> Any:
    call_record: Dict[str, Any] = {
        "instance_id": id(self),
        "instance_type": type(self).__name__,
        "artifact_success": getattr(artifact, "success", None),
        "artifact_result_type": getattr(artifact, "result_type", None),
        "artifact_error_message": getattr(artifact, "error_message", None),
        "exception": None,
        "return_value": None,
    }
    if hasattr(artifact, "data") and isinstance(artifact.data, dict):
        call_record["artifact_data_text"] = str(artifact.data.get("text", ""))[:200]
        call_record["artifact_data_proposition"] = str(artifact.data.get("proposition", ""))[:200]
        call_record["artifact_data_intent_type"] = artifact.data.get("intent_type")
    try:
        result = _orig_materialize(self, artifact)
        call_record["return_value"] = repr(result)[:300] if result is not None else None
        if hasattr(result, "__len__"):
            call_record["result_count"] = len(result)
        _materializer_calls.append(call_record)
        return result
    except Exception as e:
        call_record["exception"] = f"{type(e).__name__}: {e}"
        call_record["exception_traceback"] = traceback.format_exc()[:1500]
        _materializer_calls.append(call_record)
        raise


def _spy_to_event(intent: Any) -> Any:
    call_record: Dict[str, Any] = {
        "intent_speaker": getattr(intent, "speaker", None),
        "intent_target": getattr(intent, "target_id", None) or getattr(intent, "audience", None),
        "intent_type": getattr(intent, "intent_type", None),
        "intent_proposition": str(getattr(intent, "proposition", None))[:200],
        "exception": None,
    }
    try:
        result = _orig_to_event(intent)
        call_record["return_event_type"] = str(getattr(result, "type", "?")) if result is not None else None
        _adapter_calls.append(call_record)
        return result
    except Exception as e:
        call_record["exception"] = f"{type(e).__name__}: {e}"
        _adapter_calls.append(call_record)
        raise


def _install_class_spies() -> bool:
    global _orig_execute, _orig_gen, _orig_materialize, _orig_to_event
    try:
        from app.services.execution.dialogue_executor import DialogueExecutor
        _orig_execute = DialogueExecutor.execute
        DialogueExecutor.execute = _spy_execute
        _orig_gen = DialogueExecutor._generate_with_router
        DialogueExecutor._generate_with_router = _spy_generate_with_router
    except Exception as e:
        print(f"  [DialogueExecutor spy install failed: {e}]")
        traceback.print_exc()
        return False
    try:
        from app.services.execution.dialogue_materializer import DialogueMaterializer
        _orig_materialize = DialogueMaterializer.materialize
        DialogueMaterializer.materialize = _spy_materialize
    except Exception as e:
        print(f"  [DialogueMaterializer spy install failed: {e}]")
    try:
        from app.services.events.intent_event_adapter import IntentEventAdapter
        _orig_to_event = IntentEventAdapter.to_event
        IntentEventAdapter.to_event = staticmethod(_spy_to_event)
    except Exception as e:
        print(f"  [IntentEventAdapter spy install failed: {e}]")
    return True


def _restore_class_spies() -> None:
    global _orig_execute, _orig_gen, _orig_materialize, _orig_to_event
    try:
        from app.services.execution.dialogue_executor import DialogueExecutor
        if _orig_execute is not None:
            DialogueExecutor.execute = _orig_execute
        if _orig_gen is not None:
            DialogueExecutor._generate_with_router = _orig_gen
    except Exception:
        pass
    try:
        from app.services.execution.dialogue_materializer import DialogueMaterializer
        if _orig_materialize is not None:
            DialogueMaterializer.materialize = _orig_materialize
    except Exception:
        pass
    try:
        from app.services.events.intent_event_adapter import IntentEventAdapter
        if _orig_to_event is not None:
            IntentEventAdapter.to_event = _orig_to_event
    except Exception:
        pass


def _clear_spy_calls() -> None:
    _executor_calls.clear()
    _materializer_calls.clear()
    _adapter_calls.clear()


# ============================================================================
# Grep production code for [DIALOGUE_EXEC] log string
# ============================================================================
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


def _grep_dialogue_exec_in_production() -> List[Tuple[Path, int, str]]:
    """Grep production code for [DIALOGUE_EXEC] Executing task."""
    out: List[Tuple[Path, int, str]] = []
    if not _BACKEND.exists():
        return out
    for f in _BACKEND.rglob("*.py"):
        if not _is_production_file(f):
            continue
        try:
            src = f.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for i, line in enumerate(src.split("\n"), 1):
            if "DIALOGUE_EXEC" in line and ("Executing" in line or "Executing task" in line):
                out.append((f, i, line.rstrip()))
    return out


# ============================================================================
# MAIN
# ============================================================================
def main() -> int:
    print("=" * 78)
    print("R2-B5-D2 v7 — Find EXACT source of [DIALOGUE_EXEC] log")
    print(f"OUT_FILE: {OUT_FILE}")
    print("=" * 78)
    print()
    print("v7 STRATEGY:")
    print("  1. Attach log capture to ROOT ONLY (avoid duplicate capture)")
    print("  2. Capture LogRecord.pathname, lineno, funcName for each [DIALOGUE_EXEC] log")
    print("  3. Grep production code for the log string")
    print("  4. Identify EXACT source file + line + function")
    print()

    _install_log_capture()

    orig_saves_dir = settings.saves_dir
    orig_env = settings.environment

    temp_dir = Path(tempfile.mkdtemp(prefix="r2_b5_d2_v7_"))

    try:
        # =====================================================================
        # STEP 1: Grep production code for [DIALOGUE_EXEC] Executing task
        # =====================================================================
        _print_section("STEP 1: Grep production code for [DIALOGUE_EXEC] log string")
        matches = _grep_dialogue_exec_in_production()
        print(f"  Found {len(matches)} production files emitting [DIALOGUE_EXEC] Executing task:")
        for path, ln, line in matches:
            try:
                rel = path.relative_to(_BACKEND)
            except Exception:
                rel = path
            print(f"  {rel} L{ln}: {line}")

        # =====================================================================
        # STEP 2: Install spies BEFORE build_game_loop
        # =====================================================================
        _print_section("STEP 2: install spies BEFORE build_game_loop")
        if _install_class_spies():
            print(f"  Class spies installed (plain functions)")

        from app.services.execution.dialogue_executor import DialogueExecutor
        from app.services.execution.dialogue_materializer import DialogueMaterializer
        from app.services.events.intent_event_adapter import IntentEventAdapter

        print(f"\n  Verify spy installation:")
        print(f"    DialogueExecutor.execute is _spy_execute: {DialogueExecutor.execute is _spy_execute}")
        print(f"    DialogueExecutor._generate_with_router is _spy_generate_with_router: "
              f"{DialogueExecutor._generate_with_router is _spy_generate_with_router}")
        print(f"    DialogueMaterializer.materialize is _spy_materialize: "
              f"{DialogueMaterializer.materialize is _spy_materialize}")

        _clear_spy_calls()
        _reset_log_capture()

        # =====================================================================
        # STEP 3: build_game_loop + load NPCs + publish PLAYER_INSULTS
        # =====================================================================
        _print_section("STEP 3: build_game_loop + load NPCs + publish PLAYER_INSULTS")
        from app.services.game_loop_builder import build_game_loop
        from app.services.events.event_bus import get_event_bus
        from app.services.events.event_types import EventType
        from app.domain.events import EventDTO
        from app.services.events.claim_event_subscriber import ClaimEventSubscriber
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
        _event_bus_spy.install(bus)
        print(f"  EventBus spy installed")

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
        print(f"  PLAYER_INSULTS published")

        # Verify spies still installed
        print(f"\n  Verify spies BEFORE idle_tick:")
        print(f"    DialogueExecutor.execute is _spy_execute: {DialogueExecutor.execute is _spy_execute}")

        # =====================================================================
        # STEP 4: clear state + run idle_tick
        # =====================================================================
        _print_section("STEP 4: clear state + run idle_tick")
        _clear_spy_calls()
        _reset_log_capture()
        _event_bus_spy.clear()

        try:
            result = loop.idle_tick("Open_road", "tavern")
            print(f"  idle_tick returned: {type(result).__name__}")
            if isinstance(result, dict):
                print(f"  status: {result.get('status')}")
        except Exception as e:
            print(f"  ERROR: {type(e).__name__}: {e}")
            traceback.print_exc()

        # =====================================================================
        # STEP 5: Analyze [DIALOGUE_EXEC] logs with FULL SOURCE INFO
        # =====================================================================
        _print_section("STEP 5: [DIALOGUE_EXEC] logs with FULL SOURCE INFO")

        de_logs = _find_de_logs_with_source()
        print(f"  Total [DIALOGUE_EXEC] log records: {len(de_logs)}")
        for i, log in enumerate(de_logs):
            print(f"\n  Log [{i}]:")
            print(f"    level: {log['level']}")
            print(f"    logger_name: {log['logger_name']}")
            print(f"    message: {log['message'][:200]}")
            print(f"    pathname: {log['pathname']}")
            print(f"    lineno: {log['lineno']}")
            print(f"    funcName: {log['funcName']}")
            print(f"    module: {log['module']}")

        # Group by source (pathname + lineno) to detect duplicates
        print(f"\n  === Group by source (pathname + lineno) ===")
        source_groups: Dict[Tuple[str, int], int] = {}
        for log in de_logs:
            key = (log["pathname"], log["lineno"])
            source_groups[key] = source_groups.get(key, 0) + 1
        for (path, line), count in source_groups.items():
            print(f"    {path}:{line} → {count} record(s)")

        # =====================================================================
        # STEP 6: Spy results
        # =====================================================================
        _print_section("STEP 6: spy results")
        print(f"  execute() calls: {len(_executor_calls)}")
        print(f"  _generate_with_router calls: {len([c for c in _executor_calls if 'req_target_id' in c])}")
        print(f"  materialize() calls: {len(_materializer_calls)}")
        print(f"  to_event() calls: {len(_adapter_calls)}")

        for i, call in enumerate(_executor_calls):
            print(f"\n  Call [{i}]:")
            print(f"    instance_id: {call.get('instance_id')}")
            print(f"    instance_router: {call.get('instance_router', 'N/A')[:100]}")
            if "task_owner_id" in call:
                print(f"    task_owner_id: {call.get('task_owner_id')}")
                print(f"    payload_target_id: {call.get('payload_target_id')}")
                print(f"    payload_intent_type: {call.get('payload_intent_type')}")
            if call.get("exception"):
                print(f"    EXCEPTION: {call['exception']}")
                if "exception_traceback" in call:
                    print(f"    TRACEBACK:")
                    print(call["exception_traceback"][:1500])

        # =====================================================================
        # STEP 7: EventBus events
        # =====================================================================
        _print_section("STEP 7: EventBus events after idle_tick")
        print(f"  Total events: {len(_event_bus_spy.published_events)}")
        ev_type_counter: Dict[str, int] = {}
        for ev_type, _ in _event_bus_spy.published_events:
            ev_type_counter[ev_type] = ev_type_counter.get(ev_type, 0) + 1
        for ev_type, count in sorted(ev_type_counter.items()):
            print(f"    {ev_type}: {count}")

        # =====================================================================
        # STEP 8: Tornin belief AFTER idle_tick
        # =====================================================================
        _print_section("STEP 8: Tornin belief AFTER idle_tick")
        new_borko_belief = False
        if store:
            tornin_after = store.get_all_for_agent("tavern_keeper_tornin") or []
            print(f"  Tornin total records: {len(tornin_after)}")
            for r in tornin_after:
                print(f"    prop={str(getattr(r, 'proposition', None))[:80]}")
                print(f"      conf={getattr(r, 'confidence', None)} "
                      f"source_id={getattr(r, 'source_id', None)} "
                      f"orig={getattr(r, 'original_source_id', None)}")
            new_borko_belief = any(
                getattr(r, "source_id", None) == "guard_borko"
                and getattr(r, "original_source_id", None) == "player"
                for r in tornin_after
            )
            print(f"\n  NEW Tornin belief with source_id='guard_borko' (orig='player'): {new_borko_belief}")

        # =====================================================================
        # STEP 9: VERDICT
        # =====================================================================
        _print_section("STEP 9: VERDICT")

        execute_calls_count = len(_executor_calls)
        unique_de_sources = len(source_groups)

        print(f"  [DIALOGUE_EXEC] log records: {len(de_logs)}")
        print(f"  Unique source locations: {unique_de_sources}")
        print(f"  execute() spy calls: {execute_calls_count}")

        if new_borko_belief:
            print(f"\n  >>> VERDICT: B5-D2 NOT A DEFECT — chain completed")
        elif execute_calls_count > 0:
            print(f"\n  >>> VERDICT: execute() WAS called (spy captured)")
            print(f"  >>> Investigate spy call details in Step 6")
        elif unique_de_sources == 1 and de_logs:
            # Single source — let's check if it's dialogue_executor.execute
            src_path, src_line = next(iter(source_groups.keys()))
            print(f"\n  >>> Single source of [DIALOGUE_EXEC] log:")
            print(f"  >>> {src_path}:{src_line}")
            if "dialogue_executor.py" in src_path:
                print(f"  >>> Source IS dialogue_executor.py")
                print(f"  >>> But spy didn't trigger — descriptor protocol issue?")
                print(f"  >>> Try: wrap logger.debug directly to capture call stack")
            else:
                print(f"  >>> Source is NOT dialogue_executor.py!")
                print(f"  >>> Log comes from a DIFFERENT file")
                print(f"  >>> This explains why spy on DialogueExecutor.execute didn't trigger")
        elif len(de_logs) == 0:
            print(f"\n  >>> VERDICT: No [DIALOGUE_EXEC] logs — execute() not called at all")
            print(f"  >>> task_scheduler didn't dispatch task during idle_tick")
        else:
            print(f"\n  >>> VERDICT: Multiple sources — see Step 5 for details")

        # ---- Cleanup ----
        _event_bus_spy.restore()
        _restore_class_spies()
        try:
            ts = loop._get_task_scheduler()
            if hasattr(ts, "_executor_pool"):
                ts._executor_pool.shutdown(wait=False, cancel_futures=True)
        except Exception:
            pass
        del loop
        gc.collect()

    except Exception as e:
        print(f"[FATAL: {e}]")
        traceback.print_exc()
    finally:
        settings.saves_dir = orig_saves_dir
        settings.environment = orig_env
        _event_bus_spy.restore()
        _restore_class_spies()
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
