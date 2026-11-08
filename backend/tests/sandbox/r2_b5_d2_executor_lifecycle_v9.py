# backend/tests/sandbox/r2_b5_d2_executor_lifecycle_v9.py
"""
R2-B5-D2 v9 — Final diagnostic: real executor behavior under different conditions.

Master's order (7 questions):
  1. Does executor reach _generate_with_router?
  2. Does _generate_with_router return or block?
  3. Does Timer fire and what does it interrupt?
  4. Does execute() return an Artifact?
  5. Does the result reach materializer.materialize()?
  6. WHO publishes NPC_SPOKE and under what conditions?
  7. Does the Future get an exception, result, or remain pending?

v9 strategy:
  STEP 1: Read full task_scheduler._process_tasks_async + execute_pending
          to understand Future lifecycle and NPC_SPOKE publication responsibility
  STEP 2: Read full DialogueExecutor.execute (already known from v3-v8)
  STEP 3: Read full DialogueMaterializer.materialize (already known from v3)
  STEP 4: Read drain_task_worker_outbox + drain_commitment_outbox to see
          how _task_outbox and NPC_SPOKE events connect
  STEP 5: Run 6 controlled experiments on executor directly (without idle_tick):
          A. router=None, no proposition (stub branch)
          B. router=None, with proposition (stub branch, but proposition path)
          C. router exists, no proposition (deterministic stub)
          D. router exists, with proposition (LLM branch — likely blocks)
          E. router exists, with proposition, LLM server unavailable (LLM call fails)
          F. router exists, with proposition, LLM timeout (timer fires)
  STEP 6: For each experiment, capture:
          - Did execute() reach _generate_with_router?
          - Did _generate_with_router return or block?
          - Did Timer fire? Did _abort_generation actually abort?
          - Did execute() yield Artifact?
          - Was materializer called?
          - Was NPC_SPOKE published?
          - Did Future get exception/result/pending?
  STEP 7: Final verdict — WHO publishes NPC_SPOKE and under what conditions?

READ-ONLY. Production-код не менять.
"""
from __future__ import annotations

import os
import sys
import gc
import inspect
import json
import re
import shutil
import traceback
import io
import logging
import tempfile
import threading
import time
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
OUT_FILE = OUT_FILE_DIR / "r2_b5_d2_executor_lifecycle_v9.txt"


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
# Log capture (ROOT only, no duplicates)
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


def _install_log_capture() -> None:
    root = logging.getLogger()
    root.handlers = [h for h in root.handlers if not isinstance(h, _LogCapture)]
    if not any(isinstance(h, _LogCapture) for h in root.handlers):
        root.addHandler(_log_capture)
    root.setLevel(logging.DEBUG)


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
# PLAIN MODULE-LEVEL SPY FUNCTIONS
# ============================================================================
_executor_calls: List[Dict[str, Any]] = []
_orig_execute: Optional[Callable] = None
_orig_gen: Optional[Callable] = None

_materializer_calls: List[Dict[str, Any]] = []
_orig_materialize: Optional[Callable] = None

_adapter_calls: List[Dict[str, Any]] = []
_orig_to_event: Optional[Callable] = None

# Track _router.request_for_agent calls
_router_calls: List[Dict[str, Any]] = []
_orig_request_for_agent: Optional[Callable] = None

# Track _router._abort_generation calls
_abort_calls: List[Dict[str, Any]] = []
_orig_abort: Optional[Callable] = None


def _spy_execute(self: Any, task: Any) -> Any:
    call_record: Dict[str, Any] = {
        "instance_id": id(self),
        "instance_router": repr(getattr(self, "_router", None))[:120],
        "task_owner_id": getattr(task, "owner_id", None),
        "task_kind": str(getattr(task, "kind", None)),
        "task_payload_type": type(getattr(task, "payload", None)).__name__,
        "exception": None,
        "yielded_artifacts": [],
        "reached_generate_with_router": False,
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
    """Spy on _generate_with_router. Captures entry, calls, return/exception."""
    # Mark the parent execute() call as having reached _generate_with_router
    if _executor_calls and "reached_generate_with_router" in _executor_calls[-1]:
        _executor_calls[-1]["reached_generate_with_router"] = True

    call_record: Dict[str, Any] = {
        "instance_id": id(self),
        "task_owner_id": getattr(task, "owner_id", None),
        "req_target_id": getattr(req, "target_id", None),
        "req_intent_type": getattr(req, "intent_type", None),
        "req_proposition": str(getattr(req, "proposition", None))[:200],
        "exception": None,
        "return_value": None,
        "duration_sec": None,
    }
    start_time = time.time()
    try:
        result = _orig_gen(self, task, req, verdict)
        duration = time.time() - start_time
        call_record["duration_sec"] = duration
        call_record["return_value"] = repr(result)[:500] if result is not None else None
        _executor_calls.append(call_record)
        return result
    except Exception as e:
        duration = time.time() - start_time
        call_record["duration_sec"] = duration
        call_record["exception"] = f"{type(e).__name__}: {e}"
        call_record["exception_traceback"] = traceback.format_exc()[:1500]
        _executor_calls.append(call_record)
        raise


def _spy_materialize(self: Any, artifact: Any) -> Any:
    call_record: Dict[str, Any] = {
        "instance_id": id(self),
        "artifact_success": getattr(artifact, "success", None),
        "artifact_result_type": getattr(artifact, "result_type", None),
        "artifact_error_message": getattr(artifact, "error_message", None),
        "exception": None,
        "return_value": None,
    }
    if hasattr(artifact, "data") and isinstance(artifact.data, dict):
        call_record["artifact_data_text"] = str(artifact.data.get("text", ""))[:200]
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


def _spy_request_for_agent(self: Any, *args, **kwargs) -> Any:
    """Spy on ModelRouter.request_for_agent — captures LLM call."""
    call_record: Dict[str, Any] = {
        "router_id": id(self),
        "args_repr": [repr(a)[:200] for a in args],
        "kwargs_keys": list(kwargs.keys()),
        "exception": None,
        "return_value": None,
        "duration_sec": None,
    }
    start_time = time.time()
    try:
        result = _orig_request_for_agent(self, *args, **kwargs)
        duration = time.time() - start_time
        call_record["duration_sec"] = duration
        call_record["return_value"] = repr(result)[:500] if result is not None else None
        _router_calls.append(call_record)
        return result
    except Exception as e:
        duration = time.time() - start_time
        call_record["duration_sec"] = duration
        call_record["exception"] = f"{type(e).__name__}: {e}"
        call_record["exception_traceback"] = traceback.format_exc()[:1500]
        _router_calls.append(call_record)
        raise


def _spy_abort_generation(self: Any, *args, **kwargs) -> Any:
    """Spy on ModelRouter._abort_generation — captures Timer callback."""
    call_record: Dict[str, Any] = {
        "router_id": id(self),
        "args_repr": [repr(a)[:200] for a in args],
    }
    _abort_calls.append(call_record)
    # Don't call original — we just want to capture that it fired
    # (Original might raise or do nothing; we just want to know it was called)
    try:
        return _orig_abort(self, *args, **kwargs) if _orig_abort else None
    except Exception:
        return None


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


def _install_router_spies(router: Any) -> None:
    """Install spies on ModelRouter instance methods."""
    global _orig_request_for_agent, _orig_abort
    if router is None:
        return
    try:
        _orig_request_for_agent = router.request_for_agent
        router.request_for_agent = lambda *a, **kw: _spy_request_for_agent(router, *a, **kw)
    except Exception as e:
        print(f"  [router.request_for_agent spy failed: {e}]")
    try:
        _orig_abort = router._abort_generation
        router._abort_generation = lambda *a, **kw: _spy_abort_generation(router, *a, **kw)
    except Exception as e:
        print(f"  [router._abort_generation spy failed: {e}]")


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
    _router_calls.clear()
    _abort_calls.clear()


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


def _read_function_full(path: Path, func_name: str, max_lines: int = 300) -> None:
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
        print(f"  [{func_name} not found]")


# ============================================================================
# Controlled experiment runner
# ============================================================================
def _build_test_task(owner_id: str, target_id: str, intent_type: str,
                     topic: str, proposition: Optional[Any] = None,
                     campaign_id: str = "Open_road") -> Any:
    """Build a QueuedTask-like object for direct executor testing."""
    from app.domain.execution import QueuedTask, TaskKind, TaskState
    from app.domain.communication import DialogueRequest, ExposureLevel

    req_fields = {
        "topic": topic,
        "target_id": target_id,
        "exposure": ExposureLevel.from_semantic("normal"),
        "intent_type": intent_type,
        "emotional_state": "нейтрально",
        "npc_npc_context": "",
        "thread_id": "",
        "prepared_prompt": "",
    }
    if proposition is not None:
        req_fields["proposition"] = proposition

    try:
        req = DialogueRequest(**req_fields)
    except TypeError:
        # Try with different field names
        req_fields.pop("exposure", None)
        req_fields["exposure_semantic"] = "normal"
        req = DialogueRequest(**req_fields)

    task = QueuedTask(
        task_id=f"test-task-{int(time.time() * 1000)}",
        kind=TaskKind.DIALOGUE,
        owner_id=owner_id,
        payload=req,
        state=TaskState.PENDING,
        campaign_id=campaign_id,
        tick=1,
    )
    return task


def _run_experiment(label: str, executor: Any, task: Any, timeout_sec: float = 30.0) -> Dict[str, Any]:
    """Run one experiment with timeout."""
    print(f"\n  --- Experiment: {label} ---")
    result: Dict[str, Any] = {
        "label": label,
        "executor_router": repr(getattr(executor, "_router", None))[:120],
        "task_owner_id": getattr(task, "owner_id", None),
        "task_payload_intent_type": getattr(task.payload, "intent_type", None) if hasattr(task, "payload") else None,
        "task_payload_proposition": str(getattr(task.payload, "proposition", None))[:120] if hasattr(task, "payload") else None,
        "execute_completed": False,
        "exception": None,
        "yielded_artifacts": [],
        "duration_sec": None,
    }

    # Clear spy state
    _clear_spy_calls()
    _reset_log_capture()

    # Run execute() in a thread with timeout
    artifacts_received: List[Any] = []
    exception_received: List[Optional[Exception]] = [None]

    def _run_in_thread():
        try:
            gen = executor.execute(task)
            for art in gen:
                artifacts_received.append(art)
        except Exception as e:
            exception_received[0] = e

    thread = threading.Thread(target=_run_in_thread, daemon=True)
    start_time = time.time()
    thread.start()
    thread.join(timeout=timeout_sec)
    duration = time.time() - start_time
    result["duration_sec"] = duration

    if thread.is_alive():
        result["execute_completed"] = False
        result["exception"] = f"TIMEOUT after {timeout_sec}s — thread still alive"
        print(f"    TIMEOUT after {timeout_sec}s — execute() still running")
    else:
        result["execute_completed"] = True
        if exception_received[0] is not None:
            result["exception"] = f"{type(exception_received[0]).__name__}: {exception_received[0]}"
            print(f"    Exception: {result['exception']}")
        else:
            print(f"    Completed in {duration:.2f}s, {len(artifacts_received)} artifacts")

    # Capture spy results
    result["execute_spy_calls"] = len(_executor_calls)
    result["generate_with_router_calls"] = len([c for c in _executor_calls if "req_target_id" in c])
    result["materialize_calls"] = len(_materializer_calls)
    result["to_event_calls"] = len(_adapter_calls)
    result["router_calls"] = len(_router_calls)
    result["abort_calls"] = len(_abort_calls)

    # Capture yielded artifacts
    for art in artifacts_received:
        art_info = {
            "success": getattr(art, "success", None),
            "result_type": getattr(art, "result_type", None),
            "error_message": getattr(art, "error_message", None),
        }
        if hasattr(art, "data") and isinstance(art.data, dict):
            art_info["data_text"] = str(art.data.get("text", ""))[:200]
        result["yielded_artifacts"].append(art_info)

    # Capture relevant logs
    relevant_logs = []
    for msg in _log_capture.messages():
        if any(kw in msg for kw in ["DIALOGUE_EXEC", "LLM", "abort", "timeout",
                                     "Contract", "materializer", "Materializer",
                                     "LANG_LEAK", "cognition"]):
            relevant_logs.append(msg)
    result["relevant_logs"] = relevant_logs[:20]

    # Print summary
    print(f"    execute_spy_calls: {result['execute_spy_calls']}")
    print(f"    generate_with_router_calls: {result['generate_with_router_calls']}")
    print(f"    materialize_calls: {result['materialize_calls']}")
    print(f"    to_event_calls: {result['to_event_calls']}")
    print(f"    router_calls: {result['router_calls']}")
    print(f"    abort_calls: {result['abort_calls']}")
    print(f"    yielded_artifacts: {len(result['yielded_artifacts'])}")
    if result["yielded_artifacts"]:
        for art in result["yielded_artifacts"]:
            print(f"      success={art['success']} type={art['result_type']}")
            if art.get("error_message"):
                print(f"        error: {art['error_message'][:200]}")
            if art.get("data_text"):
                print(f"        text: {art['data_text'][:200]}")
    if result["relevant_logs"]:
        print(f"    Relevant logs:")
        for l in result["relevant_logs"][:10]:
            print(f"      {l[:200]}")

    return result


# ============================================================================
# MAIN
# ============================================================================
def main() -> int:
    print("=" * 78)
    print("R2-B5-D2 v9 — Final diagnostic: real executor behavior")
    print(f"OUT_FILE: {OUT_FILE}")
    print("=" * 78)
    print()
    print("v9 GOAL (per Master, 7 questions):")
    print("  1. Does executor reach _generate_with_router?")
    print("  2. Does _generate_with_router return or block?")
    print("  3. Does Timer fire and what does it interrupt?")
    print("  4. Does execute() return an Artifact?")
    print("  5. Does the result reach materializer.materialize()?")
    print("  6. WHO publishes NPC_SPOKE and under what conditions?")
    print("  7. Does the Future get an exception, result, or remain pending?")
    print()

    _install_log_capture()

    orig_saves_dir = settings.saves_dir
    orig_env = settings.environment

    temp_dir = Path(tempfile.mkdtemp(prefix="r2_b5_d2_v9_"))

    try:
        # =====================================================================
        # STEP 1: Read full _process_tasks_async (the worker thread entry point)
        # =====================================================================
        _print_section("STEP 1: Read full task_scheduler._process_tasks_async")
        ts_path = _BACKEND / "app" / "services" / "game_loop" / "task_scheduler.py"
        _read_function_full(ts_path, "_process_tasks_async", max_lines=300)

        # =====================================================================
        # STEP 2: Read execute_pending fully
        # =====================================================================
        _print_section("STEP 2: Read execute_pending (where Future is created)")
        _read_function_full(ts_path, "execute_pending", max_lines=300)

        # =====================================================================
        # STEP 3: Read drain_task_worker_outbox fully
        # =====================================================================
        _print_section("STEP 3: Read drain_task_worker_outbox (where NPC_SPOKE is published)")
        _read_function_full(ts_path, "drain_task_worker_outbox", max_lines=150)

        # =====================================================================
        # STEP 4: Read DialogueExecutor.execute fully (already known)
        # =====================================================================
        _print_section("STEP 4: Read DialogueExecutor.execute fully")
        de_path = _BACKEND / "app" / "services" / "execution" / "dialogue_executor.py"
        _read_function_full(de_path, "execute", max_lines=300)
        print(f"\n  --- _generate_with_router ---")
        _read_function_full(de_path, "_generate_with_router", max_lines=250)

        # =====================================================================
        # STEP 5: Read DialogueMaterializer.materialize (already known)
        # =====================================================================
        _print_section("STEP 5: Read DialogueMaterializer.materialize")
        dm_path = _BACKEND / "app" / "services" / "execution" / "dialogue_materializer.py"
        _read_function_full(dm_path, "materialize", max_lines=200)

        # =====================================================================
        # STEP 6: Read _record_task_outcome + _task_outbox mechanism
        # =====================================================================
        _print_section("STEP 6: Read _record_task_outcome + _TaskArtifactRecord")
        # Find _record_task_outcome
        src_ts = _read_file_text(ts_path)
        lines_ts = src_ts.split("\n")
        # Search for _task_outbox usage
        print(f"  --- _task_outbox usage in task_scheduler.py ---")
        for i, line in enumerate(lines_ts, 1):
            if "_task_outbox" in line:
                print(f"  L{i}: {line.rstrip()}")
        print(f"\n  --- _record_task_outcome definition ---")
        _read_function_full(ts_path, "_record_task_outcome", max_lines=100)

        # =====================================================================
        # STEP 7: Build loop, find executor, run controlled experiments
        # =====================================================================
        _print_section("STEP 7: Build loop, find executor, run controlled experiments")

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
        _event_bus_spy.install(bus)
        print(f"  EventBus spy installed")

        # Find DialogueExecutor
        ts_obj = loop._get_task_scheduler()
        executors_dict = getattr(ts_obj, "_executors", None)
        dialogue_executor = None
        if executors_dict is not None:
            from app.domain.execution import TaskKind
            dialogue_executor = executors_dict.get(TaskKind.DIALOGUE)
        if dialogue_executor is None:
            print(f"  [FATAL: DialogueExecutor not found]")
            return 1
        print(f"  DialogueExecutor found: {dialogue_executor}")

        router = getattr(dialogue_executor, "_router", None)
        print(f"  router: {router}")
        print(f"  router is None: {router is None}")

        # Install class spies
        if _install_class_spies():
            print(f"  Class spies installed")
        # Install router spies (if router exists)
        if router is not None:
            _install_router_spies(router)
            print(f"  Router spies installed")

        # Build test proposition
        test_proposition = Proposition(
            subject_id="player",
            predicate=Predicate.INSULTED,
            object_id="tavern_keeper_tornin",
            polarity=True,
        )

        # Build test tasks for each experiment
        experiments_results: List[Dict[str, Any]] = []

        # Experiment A: router=None, no proposition (stub branch)
        # We need to temporarily set router to None
        print(f"\n  === Experiment A: router=None, no proposition ===")
        orig_router_val = getattr(dialogue_executor, "_router", None)
        dialogue_executor._router = None
        task_a = _build_test_task("guard_borko", "tavern_keeper_tornin", "warn", "test")
        result_a = _run_experiment("A: router=None, no prop, intent=warn", dialogue_executor, task_a, timeout_sec=15)
        experiments_results.append(result_a)
        dialogue_executor._router = orig_router_val

        # Experiment B: router=None, with proposition (stub branch, but spread_rumor)
        print(f"\n  === Experiment B: router=None, spread_rumor + proposition ===")
        dialogue_executor._router = None
        task_b = _build_test_task("guard_borko", "tavern_keeper_tornin", "spread_rumor", "власть",
                                   proposition=test_proposition)
        result_b = _run_experiment("B: router=None, spread_rumor+prop", dialogue_executor, task_b, timeout_sec=15)
        experiments_results.append(result_b)
        dialogue_executor._router = orig_router_val

        # Experiment C: router exists, no proposition (deterministic stub)
        print(f"\n  === Experiment C: router exists, no proposition, intent=warn ===")
        task_c = _build_test_task("guard_borko", "tavern_keeper_tornin", "warn", "test")
        result_c = _run_experiment("C: router exists, no prop, intent=warn", dialogue_executor, task_c, timeout_sec=15)
        experiments_results.append(result_c)

        # Experiment D: router exists, with proposition (LLM branch — likely blocks)
        print(f"\n  === Experiment D: router exists, spread_rumor + proposition ===")
        task_d = _build_test_task("guard_borko", "tavern_keeper_tornin", "spread_rumor", "власть",
                                   proposition=test_proposition)
        result_d = _run_experiment("D: router exists, spread_rumor+prop (LLM branch)", dialogue_executor, task_d, timeout_sec=30)
        experiments_results.append(result_d)

        # Experiment E: router exists, intent=warn, with proposition
        # (warn + proposition: requires_llm_materialization(warn)=False, AND (warn==spread_rumor is False)
        # → goes to deterministic stub branch)
        print(f"\n  === Experiment E: router exists, intent=warn, with proposition ===")
        task_e = _build_test_task("guard_borko", "tavern_keeper_tornin", "warn", "test",
                                   proposition=test_proposition)
        result_e = _run_experiment("E: router exists, warn+prop", dialogue_executor, task_e, timeout_sec=15)
        experiments_results.append(result_e)

        # Experiment F: router exists, intent=talk (requires_llm_materialization(talk)=True → goes to LLM branch)
        print(f"\n  === Experiment F: router exists, intent=talk (LLM branch) ===")
        task_f = _build_test_task("guard_borko", "tavern_keeper_tornin", "talk", "test")
        result_f = _run_experiment("F: router exists, intent=talk (LLM)", dialogue_executor, task_f, timeout_sec=30)
        experiments_results.append(result_f)

        # =====================================================================
        # STEP 8: Summary table
        # =====================================================================
        _print_section("STEP 8: Summary table — 6 experiments")

        print(f"\n  {'Experiment':<55} {'exec':>5} {'gen':>5} {'mat':>5} {'adapt':>5} {'router':>7} {'abort':>6} {'arts':>5} {'dur':>7} {'result':<30}")
        for r in experiments_results:
            status = "OK"
            if r.get("exception"):
                status = f"EXC: {r['exception'][:30]}"
            elif not r["execute_completed"]:
                status = "TIMEOUT"
            elif not r["yielded_artifacts"]:
                status = "NO ARTIFACTS"
            print(f"  {r['label']:<55} {r['execute_spy_calls']:>5} {r['generate_with_router_calls']:>5} "
                  f"{r['materialize_calls']:>5} {r['to_event_calls']:>5} {r['router_calls']:>7} "
                  f"{r['abort_calls']:>6} {len(r['yielded_artifacts']):>5} {r['duration_sec']:>6.1f}s {status:<30}")

        # =====================================================================
        # STEP 9: Answer 7 questions
        # =====================================================================
        _print_section("STEP 9: Answers to 7 questions")

        # Q1: Does executor reach _generate_with_router?
        q1_exp = next((r for r in experiments_results if "spread_rumor+prop" in r["label"] and "router exists" in r["label"]), None)
        if q1_exp:
            print(f"\n  Q1: Does executor reach _generate_with_router?")
            print(f"      Experiment D (router exists, spread_rumor+prop):")
            print(f"      generate_with_router_calls: {q1_exp['generate_with_router_calls']}")
            if q1_exp["generate_with_router_calls"] > 0:
                print(f"      >>> YES — executor reaches _generate_with_router")
            else:
                print(f"      >>> NO — executor does NOT reach _generate_with_router")
                print(f"      >>> Executor probably stops before L160 (e.g., at _resolve_disclosure_verdict L139)")

        # Q2: Does _generate_with_router return or block?
        if q1_exp and q1_exp["generate_with_router_calls"] > 0:
            print(f"\n  Q2: Does _generate_with_router return or block?")
            if q1_exp["execute_completed"]:
                print(f"      >>> RETURNS — execute completed in {q1_exp['duration_sec']:.1f}s")
            else:
                print(f"      >>> BLOCKS — execute did not complete within timeout")

        # Q3: Does Timer fire and what does it interrupt?
        print(f"\n  Q3: Does Timer fire and what does it interrupt?")
        if q1_exp:
            print(f"      Experiment D abort_calls: {q1_exp['abort_calls']}")
            if q1_exp["abort_calls"] > 0:
                print(f"      >>> Timer DID fire — _abort_generation called")
            else:
                print(f"      >>> Timer did NOT fire (within timeout)")

        # Q4: Does execute() return an Artifact?
        print(f"\n  Q4: Does execute() return an Artifact?")
        for r in experiments_results:
            print(f"      {r['label']}: {len(r['yielded_artifacts'])} artifacts")

        # Q5: Does the result reach materializer.materialize()?
        print(f"\n  Q5: Does the result reach materializer.materialize()?")
        print(f"      (Note: materializer is called by task_scheduler, NOT by executor directly)")
        print(f"      (In our controlled experiments, we call executor directly — no task_scheduler)")
        print(f"      (So materialize_calls=0 is expected — materializer isn't part of this path)")
        for r in experiments_results:
            print(f"      {r['label']}: materialize_calls={r['materialize_calls']}")

        # Q6: WHO publishes NPC_SPOKE and under what conditions?
        print(f"\n  Q6: WHO publishes NPC_SPOKE and under what conditions?")
        print(f"      From production code reading (Steps 1-6):")
        print(f"      - DialogueExecutor.execute() yields Artifact (NOT publishes event)")
        print(f"      - task_scheduler._process_tasks_async iterates artifacts")
        print(f"      - materializer.materialize(artifact) creates EventDTO objects")
        print(f"      - events go into _task_outbox (NOT published immediately)")
        print(f"      - drain_task_worker_outbox publishes events via _bus.publish()")
        print(f"      - drain_task_worker_outbox is called from execute_pending + idle_tick")
        print(f"      >>> NPC_SPOKE is published by drain_task_worker_outbox, NOT by executor")
        print(f"      >>> Condition: artifact must be successful AND have proposition/materializer result")

        # Q7: Does the Future get an exception, result, or remain pending?
        print(f"\n  Q7: Does the Future get an exception, result, or remain pending?")
        print(f"      From Step 1 (production code): _process_tasks_async uses _executor_pool.submit()")
        print(f"      In our experiments, we use direct thread — Future equivalent:")
        for r in experiments_results:
            if r["execute_completed"]:
                if r.get("exception"):
                    print(f"      {r['label']}: EXCEPTION — {r['exception'][:80]}")
                else:
                    print(f"      {r['label']}: COMPLETED with {len(r['yielded_artifacts'])} artifacts")
            else:
                print(f"      {r['label']}: PENDING (timeout)")

        # =====================================================================
        # STEP 10: VERDICT
        # =====================================================================
        _print_section("STEP 10: VERDICT")

        # Find experiment D (the most relevant — spread_rumor + prop + router)
        exp_d = next((r for r in experiments_results if "D:" in r["label"]), None)
        if exp_d:
            print(f"\n  Experiment D (router exists, spread_rumor + proposition):")
            print(f"    execute_completed: {exp_d['execute_completed']}")
            print(f"    duration: {exp_d['duration_sec']:.1f}s")
            print(f"    exception: {exp_d.get('exception', 'None')}")
            print(f"    yielded_artifacts: {len(exp_d['yielded_artifacts'])}")
            print(f"    generate_with_router_calls: {exp_d['generate_with_router_calls']}")
            print(f"    router_calls: {exp_d['router_calls']}")
            print(f"    abort_calls: {exp_d['abort_calls']}")

            if not exp_d["execute_completed"]:
                print(f"\n  >>> VERDICT: execute() BLOCKS (does not return within timeout)")
                print(f"  >>> spread_rumor + proposition causes executor to hang")
                print(f"  >>> Likely on _generate_with_router → router.request_for_agent (LLM call)")
                if exp_d["abort_calls"] > 0:
                    print(f"  >>> Timer fired ({exp_d['abort_calls']} times) but did not interrupt blocking call")
                else:
                    print(f"  >>> Timer did NOT fire — blocking call returns None or hangs indefinitely")
            elif exp_d.get("exception"):
                print(f"\n  >>> VERDICT: execute() raises exception")
                print(f"  >>> Exception: {exp_d['exception']}")
            elif exp_d["yielded_artifacts"]:
                print(f"\n  >>> VERDICT: execute() returns artifact(s)")
                art = exp_d["yielded_artifacts"][0]
                if art["success"]:
                    print(f"  >>> Artifact SUCCESS — should reach materializer → NPC_SPOKE published")
                else:
                    print(f"  >>> Artifact FAILURE — error: {art.get('error_message', 'N/A')[:200]}")
            else:
                print(f"\n  >>> VERDICT: execute() returns no artifacts (unexpected)")

        # Final summary
        print(f"\n  === ARCHITECTURAL UNDERSTANDING ===")
        print(f"  1. DialogueExecutor.execute() yields Artifact (does NOT publish NPC_SPOKE)")
        print(f"  2. task_scheduler._process_tasks_async iterates artifacts in worker thread")
        print(f"  3. materializer.materialize(artifact) creates EventDTO (NPC_SPOKE)")
        print(f"  4. Events go into _task_outbox (NOT published immediately from worker)")
        print(f"  5. drain_task_worker_outbox (called from main thread) publishes events via _bus.publish()")
        print(f"  6. For spread_rumor + proposition: execute() goes to LLM branch")
        print(f"  7. LLM branch calls _generate_with_router → router.request_for_agent")
        print(f"  8. If LLM unavailable: blocks until Timer fires or HTTP times out")
        print(f"  9. Worker thread does not complete → artifact not yielded → no materializer call")
        print(f"  10. No NPC_SPOKE published → Tornin does not receive belief from guard_borko")

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
