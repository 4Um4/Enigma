# backend/tests/sandbox/r2_b5_d2_executor_lifecycle_v8.py
"""
R2-B5-D2 v8 — Capture STACK TRACE when [DIALOGUE_EXEC] log fires.

v7 finding:
  - [DIALOGUE_EXEC] log records: 1
  - Source: dialogue_executor.py:130, funcName=execute
  - execute() spy calls: 0
  - Spy verified installed (DialogueExecutor.execute is _spy_execute: True)

This means execute() IS being called (log on L130 fires),
but our spy on DialogueExecutor.execute doesn't intercept.

v8 strategy:
  - Capture inspect.stack() inside _log_capture.emit when [DIALOGUE_EXEC] log fires
  - Stack trace shows WHO called execute() — exact file+line+function
  - This bypasses the spy mystery entirely — we trace the actual call chain

ALSO: wrap logger.debug to add another stack capture point.

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
OUT_FILE = OUT_FILE_DIR / "r2_b5_d2_executor_lifecycle_v8.txt"


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
# Log capture with STACK TRACE for [DIALOGUE_EXEC]
# ============================================================================
class _LogCapture(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.DEBUG)
        self.records: List[logging.LogRecord] = []
        self.de_log_stack_traces: List[List[Dict[str, Any]]] = []  # stack traces for [DIALOGUE_EXEC] logs

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.records.append(record)
            # If this is a [DIALOGUE_EXEC] log, capture stack trace
            msg = record.getMessage()
            if "DIALOGUE_EXEC" in msg:
                stack = inspect.stack()
                stack_info = []
                for i, frame in enumerate(stack):
                    stack_info.append({
                        "index": i,
                        "filename": frame.filename,
                        "lineno": frame.lineno,
                        "function": frame.function,
                        "code_context": frame.code_context[0].strip() if frame.code_context else "",
                    })
                self.de_log_stack_traces.append(stack_info)
        except Exception:
            pass

    def messages(self) -> List[str]:
        return [f"[{r.levelname}] {r.name}: {r.getMessage()}" for r in self.records]


_log_capture = _LogCapture()


def _install_log_capture() -> None:
    """Install log capture on ROOT ONLY (avoid duplicate capture)."""
    root = logging.getLogger()
    root.handlers = [h for h in root.handlers if not isinstance(h, _LogCapture)]
    if not any(isinstance(h, _LogCapture) for h in root.handlers):
        root.addHandler(_log_capture)
    root.setLevel(logging.DEBUG)


def _reset_log_capture() -> None:
    _log_capture.records.clear()
    _log_capture.de_log_stack_traces.clear()


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
# MAIN
# ============================================================================
def main() -> int:
    print("=" * 78)
    print("R2-B5-D2 v8 — Stack trace when [DIALOGUE_EXEC] log fires")
    print(f"OUT_FILE: {OUT_FILE}")
    print("=" * 78)
    print()
    print("v8 STRATEGY:")
    print("  - Capture inspect.stack() inside _log_capture.emit")
    print("  - When [DIALOGUE_EXEC] log fires, capture full call stack")
    print("  - Stack shows WHO called execute() — bypassing spy mystery")
    print()

    _install_log_capture()

    orig_saves_dir = settings.saves_dir
    orig_env = settings.environment

    temp_dir = Path(tempfile.mkdtemp(prefix="r2_b5_d2_v8_"))

    try:
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

        # Publish PLAYER_INSULTS
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

        # Clear state
        _reset_log_capture()
        _event_bus_spy.clear()

        # =====================================================================
        # Run idle_tick
        # =====================================================================
        _print_section("Running idle_tick...")
        try:
            result = loop.idle_tick("Open_road", "tavern")
            print(f"  idle_tick returned: {type(result).__name__}")
            if isinstance(result, dict):
                print(f"  status: {result.get('status')}")
        except Exception as e:
            print(f"  ERROR: {type(e).__name__}: {e}")
            traceback.print_exc()

        # =====================================================================
        # STEP 1: Stack traces for [DIALOGUE_EXEC] logs
        # =====================================================================
        _print_section("STEP 1: Stack traces for [DIALOGUE_EXEC] logs")

        de_logs = [r for r in _log_capture.records if "DIALOGUE_EXEC" in r.getMessage()]
        print(f"  Total [DIALOGUE_EXEC] log records: {len(de_logs)}")
        print(f"  Total stack traces captured: {len(_log_capture.de_log_stack_traces)}")

        for i, stack in enumerate(_log_capture.de_log_stack_traces):
            print(f"\n  === Stack trace [{i}] ===")
            for frame_info in stack:
                # Filter: only show frames in backend/ (skip Python internals + logging)
                fname = frame_info["filename"]
                if not fname:
                    continue
                # Skip logging internals
                if "logging" in fname and "__init__" in fname:
                    continue
                # Show all frames
                print(f"    [{frame_info['index']:2d}] {fname}:{frame_info['lineno']} in {frame_info['function']}")
                if frame_info["code_context"]:
                    print(f"         code: {frame_info['code_context'][:200]}")

        # =====================================================================
        # STEP 2: Find execute() in stack
        # =====================================================================
        _print_section("STEP 2: Find execute() in stack")

        for i, stack in enumerate(_log_capture.de_log_stack_traces):
            print(f"\n  Stack [{i}] — looking for execute() in DialogueExecutor:")
            for frame_info in stack:
                fname = frame_info["filename"]
                func = frame_info["function"]
                line = frame_info["lineno"]
                if "dialogue_executor" in fname.lower() and func == "execute":
                    print(f"    FOUND execute(): {fname}:{line}")
                if "task_scheduler" in fname.lower():
                    print(f"    task_scheduler frame: {fname}:{line} in {func}")
                    if frame_info["code_context"]:
                        print(f"      code: {frame_info['code_context'][:200]}")
                if "npc_tick_pipeline" in fname.lower():
                    print(f"    npc_tick_pipeline frame: {fname}:{line} in {func}")
                    if frame_info["code_context"]:
                        print(f"      code: {frame_info['code_context'][:200]}")
                if "game_loop" in fname.lower():
                    print(f"    game_loop frame: {fname}:{line} in {func}")

        # =====================================================================
        # STEP 3: Tornin belief AFTER idle_tick
        # =====================================================================
        _print_section("STEP 3: Tornin belief AFTER idle_tick")
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
        # STEP 4: EventBus events
        # =====================================================================
        _print_section("STEP 4: EventBus events")
        print(f"  Total events: {len(_event_bus_spy.published_events)}")
        ev_type_counter: Dict[str, int] = {}
        for ev_type, _ in _event_bus_spy.published_events:
            ev_type_counter[ev_type] = ev_type_counter.get(ev_type, 0) + 1
        for ev_type, count in sorted(ev_type_counter.items()):
            print(f"    {ev_type}: {count}")

        # =====================================================================
        # STEP 5: ALL logs (filtered to relevant)
        # =====================================================================
        _print_section("STEP 5: ALL logs (key entries)")
        all_logs = _log_capture.messages()
        print(f"  Total log records: {len(all_logs)}")
        # Filter to relevant
        relevant_keywords = ["DIALOGUE_EXEC", "TASK_SCHED", "SCHEDULER", "materializer",
                             "Materializer", "intent_event_adapter", "INTENT_EVENT_ADAPTER",
                             "execute", "spread_rumor", "NPC_SPOKE", "npc_spoke"]
        relevant_logs = [l for l in all_logs if any(kw in l for kw in relevant_keywords)]
        print(f"  Relevant logs: {len(relevant_logs)}")
        for l in relevant_logs[:50]:
            print(f"    {l[:300]}")

        # =====================================================================
        # STEP 6: VERDICT
        # =====================================================================
        _print_section("STEP 6: VERDICT")

        if new_borko_belief:
            print(f"  >>> VERDICT: B5-D2 NOT A DEFECT — chain completed")
        elif not _log_capture.de_log_stack_traces:
            print(f"  >>> VERDICT: No [DIALOGUE_EXEC] log captured")
            print(f"  >>> execute() was NOT called during idle_tick")
        else:
            # Find caller of execute()
            stack = _log_capture.de_log_stack_traces[0]
            execute_frame = None
            caller_frame = None
            for j, frame in enumerate(stack):
                if "dialogue_executor" in frame["filename"].lower() and frame["function"] == "execute":
                    execute_frame = frame
                    # Caller is the next frame
                    if j + 1 < len(stack):
                        caller_frame = stack[j + 1]
                    break

            if execute_frame and caller_frame:
                print(f"  >>> execute() called at: {execute_frame['filename']}:{execute_frame['lineno']}")
                print(f"  >>> CALLED BY: {caller_frame['filename']}:{caller_frame['lineno']} in {caller_frame['function']}")
                if caller_frame["code_context"]:
                    print(f"  >>> Caller code: {caller_frame['code_context'][:300]}")
                print(f"\n  >>> This identifies WHO calls execute() — bypassing spy issue")
                print(f"  >>> Next: investigate why spy doesn't trigger from this call path")
            else:
                print(f"  >>> execute() not found in stack — see Step 2")
                print(f"  >>> Full stack shown in Step 1")

        # ---- Cleanup ----
        _event_bus_spy.restore()
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
