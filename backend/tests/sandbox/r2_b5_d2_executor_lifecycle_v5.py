# backend/tests/sandbox/r2_b5_d2_executor_lifecycle_v5.py
"""
R2-B5-D2 v5 — Fix spy wrapping (plain function, not class method).

v4 finding:
  - Class-level spy DID install correctly (verify True)
  - But spy captured exception: TypeError "missing 1 required positional argument: 'task'"
  - This is because _spy_execute is a METHOD of _InstanceSpy class, not a plain function
  - When assigned to DialogueExecutor.execute, Python doesn't trigger __get__ protocol
  - So 'self_instance' parameter receives the 'task' arg, not the DialogueExecutor instance

v5 fix:
  - Use PLAIN MODULE-LEVEL FUNCTION as spy (not method of a class)
  - Python's descriptor protocol will then trigger __get__ when accessing instance.execute
  - This will correctly pass DialogueExecutor instance as 'self' parameter

Other v4 findings (already confirmed):
  - Only ONE DialogueExecutor instance exists (router=<ModelRouter>)
  - Logs [DIALOGUE_EXEC] in v3 were STALE (came from previous run in same buffer)
  - Real idle_tick doesn't call execute() multiple times — it tries ONCE and crashes

  - This means: in v4, execute() WAS called, but spy crashed before original code ran
  - Need to re-test with FIXED spy to see actual executor behavior

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
OUT_FILE = OUT_FILE_DIR / "r2_b5_d2_executor_lifecycle_v5.txt"


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
    "app.services.execution.dialogue_materializer",
    "app.services.events.intent_event_adapter",
    "app.services.events.event_bus",
    "app.services.game_loop.task_scheduler",
    "app.services.game_loop.game_loop",
    "app.services.world.world_tick_engine",
    "app.services.npc.state_applicator",
    "app", "",
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
# PLAIN MODULE-LEVEL SPY FUNCTIONS (the v5 fix!)
# ============================================================================
# When assigned to a class attribute (DialogueExecutor.execute = _spy_execute_execute),
# Python's descriptor protocol makes instance.execute a bound method that passes
# instance as 'self' to the plain function.

_executor_calls: List[Dict[str, Any]] = []
_orig_execute: Optional[Callable] = None
_orig_gen: Optional[Callable] = None

_materializer_calls: List[Dict[str, Any]] = []
_orig_materialize: Optional[Callable] = None

_adapter_calls: List[Dict[str, Any]] = []
_orig_to_event: Optional[Callable] = None


def _spy_execute(self: Any, task: Any) -> Any:
    """Spy on DialogueExecutor.execute. PLAIN function — descriptor protocol passes self."""
    call_record: Dict[str, Any] = {
        "instance_id": id(self),
        "instance_type": type(self).__name__,
        "instance_router": repr(getattr(self, "_router", None))[:120],
        "task_repr": repr(task)[:300],
        "task_owner_id": getattr(task, "owner_id", None),
        "task_kind": str(getattr(task, "kind", None)),
        "task_payload_type": type(getattr(task, "payload", None)).__name__,
        "exception": None,
        "yielded_artifacts": [],
    }
    # Extract payload details
    payload = getattr(task, "payload", None)
    if payload is not None:
        call_record["payload_target_id"] = getattr(payload, "target_id", None)
        call_record["payload_intent_type"] = getattr(payload, "intent_type", None)
        call_record["payload_topic"] = getattr(payload, "topic", None)
        call_record["payload_proposition"] = str(getattr(payload, "proposition", None))[:200]
    try:
        result = _orig_execute(self, task)  # call ORIGINAL execute
        call_record["return_value"] = "generator/iterable returned"
        call_record["return_type"] = type(result).__name__
        # If it's a generator, try to iterate to capture yields
        if hasattr(result, "__iter__") or hasattr(result, "__next__"):
            call_record["is_generator"] = True
            artifacts = []
            # IMPORTANT: we need to consume the generator to capture artifacts
            # But if we consume it, production code won't get fresh generator
            # SOLUTION: re-create by calling original again
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
        # Return a fresh generator (we consumed the original)
        return _orig_execute(self, task)
    except Exception as e:
        call_record["exception"] = f"{type(e).__name__}: {e}"
        call_record["exception_traceback"] = traceback.format_exc()[:2000]
        _executor_calls.append(call_record)
        raise


def _spy_generate_with_router(self: Any, task: Any, req: Any, verdict: Any = None) -> str:
    """Spy on _generate_with_router."""
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
        _executor_calls.append(call_record)  # use same list
        return result
    except Exception as e:
        call_record["exception"] = f"{type(e).__name__}: {e}"
        call_record["exception_traceback"] = traceback.format_exc()[:1500]
        _executor_calls.append(call_record)
        raise


def _spy_materialize(self: Any, artifact: Any) -> Any:
    """Spy on DialogueMaterializer.materialize."""
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
    """Spy on IntentEventAdapter.to_event (staticmethod)."""
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
    """Install class-level spies using PLAIN FUNCTIONS (v5 fix)."""
    global _orig_execute, _orig_gen, _orig_materialize, _orig_to_event
    try:
        from app.services.execution.dialogue_executor import DialogueExecutor
        _orig_execute = DialogueExecutor.execute
        DialogueExecutor.execute = _spy_execute  # plain function — descriptor will pass self

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
# Find all DialogueExecutor instances via gc
# ============================================================================
def _find_all_dialogue_executors() -> List[Tuple[int, Any]]:
    """Find ALL DialogueExecutor instances via gc.get_objects()."""
    try:
        from app.services.execution.dialogue_executor import DialogueExecutor
    except Exception:
        return []
    instances = []
    for obj in gc.get_objects():
        try:
            if isinstance(obj, DialogueExecutor):
                instances.append((id(obj), obj))
        except Exception:
            continue
    return instances


# ============================================================================
# MAIN
# ============================================================================
def main() -> int:
    print("=" * 78)
    print("R2-B5-D2 v5 — Fix spy wrapping (plain function, descriptor protocol)")
    print(f"OUT_FILE: {OUT_FILE}")
    print("=" * 78)
    print()
    print("v5 FIX from v4:")
    print("  - Use PLAIN MODULE-LEVEL FUNCTION as spy (not class method)")
    print("  - Python descriptor protocol will pass instance as 'self'")
    print("  - This fixes the TypeError that crashed the spy in v4")
    print()
    print("v4 KEY FINDINGS (preserved):")
    print("  - Only ONE DialogueExecutor instance (router=<ModelRouter>)")
    print("  - Logs [DIALOGUE_EXEC] in v3 were STALE (from previous run)")
    print("  - Real idle_tick calls execute() ONCE")
    print()

    _install_log_capture()

    orig_saves_dir = settings.saves_dir
    orig_env = settings.environment

    temp_dir = Path(tempfile.mkdtemp(prefix="r2_b5_d2_v5_"))

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

        # =====================================================================
        # STEP 1: Find ALL DialogueExecutor instances BEFORE spy
        # =====================================================================
        _print_section("STEP 1: find ALL DialogueExecutor instances (before spy)")
        gc.collect()
        instances_before = _find_all_dialogue_executors()
        print(f"  Found {len(instances_before)} DialogueExecutor instance(s):")
        for inst_id, inst in instances_before:
            router = getattr(inst, "_router", None)
            print(f"    id={inst_id}, router={router}, router_type={type(router).__name__}")

        # =====================================================================
        # STEP 2: Install CLASS-LEVEL spies (PLAIN FUNCTIONS — v5 fix)
        # =====================================================================
        _print_section("STEP 2: install CLASS-LEVEL spies (PLAIN FUNCTIONS)")
        _event_bus_spy.install(bus)
        print(f"  EventBus spy installed")

        if _install_class_spies():
            print(f"  Class spies installed (plain functions)")

        # Verify
        from app.services.execution.dialogue_executor import DialogueExecutor
        from app.services.execution.dialogue_materializer import DialogueMaterializer
        from app.services.events.intent_event_adapter import IntentEventAdapter

        print(f"\n  Verify spy installation:")
        print(f"    DialogueExecutor.execute is _spy_execute: {DialogueExecutor.execute is _spy_execute}")
        print(f"    DialogueExecutor._generate_with_router is _spy_generate_with_router: "
              f"{DialogueExecutor._generate_with_router is _spy_generate_with_router}")
        print(f"    DialogueMaterializer.materialize is _spy_materialize: "
              f"{DialogueMaterializer.materialize is _spy_materialize}")
        print(f"    IntentEventAdapter.to_event is _spy_to_event: "
              f"{IntentEventAdapter.to_event is _spy_to_event.__func__ if hasattr(_spy_to_event, '__func__') else _spy_to_event}")

        # =====================================================================
        # STEP 3: capture PRE-EXISTING Tornin beliefs
        # =====================================================================
        _print_section("STEP 3: PRE-EXISTING Tornin beliefs")
        if store:
            tornin_pre = store.get_all_for_agent("tavern_keeper_tornin") or []
            print(f"  Tornin pre-existing records: {len(tornin_pre)}")
            for r in tornin_pre:
                print(f"    prop={str(getattr(r, 'proposition', None))[:80]} "
                      f"source_id={getattr(r, 'source_id', None)} "
                      f"orig={getattr(r, 'original_source_id', None)}")

        # =====================================================================
        # STEP 4: publish PLAYER_INSULTS
        # =====================================================================
        _print_section("STEP 4: publish PLAYER_INSULTS")
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
        # STEP 5: clear spies + run idle_tick
        # =====================================================================
        _print_section("STEP 5: clear spies + run idle_tick")
        _event_bus_spy.clear()
        _clear_spy_calls()
        _reset_log_capture()
        _install_log_capture()

        # Re-verify spies are still installed after reset
        print(f"  Re-verify spies after reset:")
        print(f"    DialogueExecutor.execute is _spy_execute: {DialogueExecutor.execute is _spy_execute}")

        try:
            result = loop.idle_tick("Open_road", "tavern")
            print(f"  idle_tick returned: {type(result).__name__}")
            if isinstance(result, dict):
                print(f"  status: {result.get('status')}")
        except Exception as e:
            print(f"  ERROR: {type(e).__name__}: {e}")
            traceback.print_exc()

        # =====================================================================
        # STEP 6: spy results
        # =====================================================================
        _print_section("STEP 6: spy results")

        # 6a. DialogueExecutor.execute() + _generate_with_router calls (combined)
        print(f"\n  === All executor spy calls (execute + _generate_with_router) ===")
        print(f"  Total: {len(_executor_calls)}")
        for i, call in enumerate(_executor_calls):
            print(f"\n  Call [{i}]:")
            print(f"    instance_id: {call.get('instance_id')}")
            print(f"    instance_type: {call.get('instance_type', 'N/A')}")
            print(f"    instance_router: {call.get('instance_router', 'N/A')[:100]}")
            if "task_owner_id" in call:
                print(f"    task_owner_id: {call.get('task_owner_id')}")
                print(f"    task_kind: {call.get('task_kind')}")
                print(f"    task_payload_type: {call.get('task_payload_type')}")
                print(f"    payload_target_id: {call.get('payload_target_id')}")
                print(f"    payload_intent_type: {call.get('payload_intent_type')}")
                print(f"    payload_topic: {call.get('payload_topic')}")
                print(f"    payload_proposition: {call.get('payload_proposition')}")
            if "req_target_id" in call:
                print(f"    req_target_id: {call.get('req_target_id')}")
                print(f"    req_intent_type: {call.get('req_intent_type')}")
                print(f"    req_proposition: {call.get('req_proposition')}")
            if call.get("exception"):
                print(f"    EXCEPTION: {call['exception']}")
                if "exception_traceback" in call:
                    print(f"    TRACEBACK:")
                    print(call["exception_traceback"][:1500])
            else:
                print(f"    return: {call.get('return_value', 'N/A')[:200]}")
                if call.get("yielded_artifacts"):
                    print(f"    yielded artifacts ({len(call['yielded_artifacts'])}):")
                    for art in call["yielded_artifacts"]:
                        print(f"      success={art.get('success')} result_type={art.get('result_type')}")
                        if art.get("error_message"):
                            print(f"        error: {art['error_message'][:200]}")
                        if art.get("data_text"):
                            print(f"        text: {art['data_text'][:200]}")
                        if art.get("data_proposition"):
                            print(f"        proposition: {art['data_proposition'][:200]}")
                if "iteration_exception" in call:
                    print(f"    ITERATION EXCEPTION: {call['iteration_exception']}")
                    if "iteration_traceback" in call:
                        print(call["iteration_traceback"][:800])

        # 6b. DialogueMaterializer.materialize calls
        print(f"\n  === DialogueMaterializer.materialize() calls ===")
        print(f"  Total: {len(_materializer_calls)}")
        for i, call in enumerate(_materializer_calls[:10]):
            print(f"  [{i}] artifact.success={call.get('artifact_success')} "
                  f"result_type={call.get('artifact_result_type')}")
            if call.get("artifact_error_message"):
                print(f"      error: {call['artifact_error_message'][:200]}")
            if call.get("exception"):
                print(f"      EXCEPTION: {call['exception']}")
                if "exception_traceback" in call:
                    print(call["exception_traceback"][:800])
            else:
                print(f"      return: {call.get('return_value', 'N/A')[:200]}")
                if "result_count" in call:
                    print(f"      result count: {call['result_count']}")

        # 6c. IntentEventAdapter calls
        print(f"\n  === IntentEventAdapter.to_event() calls ===")
        print(f"  Total: {len(_adapter_calls)}")
        for i, call in enumerate(_adapter_calls[:10]):
            print(f"  [{i}] speaker={call.get('intent_speaker')} "
                  f"target={call.get('intent_target')} type={call.get('intent_type')}")
            print(f"      proposition: {call.get('intent_proposition', 'N/A')[:120]}")
            if call.get("exception"):
                print(f"      EXCEPTION: {call['exception']}")
            else:
                print(f"      return_event_type: {call.get('return_event_type', 'N/A')}")

        # 6d. EventBus events
        print(f"\n  === EventBus.publish() calls ===")
        print(f"  Total events: {len(_event_bus_spy.published_events)}")
        ev_type_counter: Dict[str, int] = {}
        for ev_type, _ in _event_bus_spy.published_events:
            ev_type_counter[ev_type] = ev_type_counter.get(ev_type, 0) + 1
        for ev_type, count in sorted(ev_type_counter.items()):
            print(f"    {ev_type}: {count}")

        # Show all events with details
        print(f"\n  --- ALL events with details ---")
        for i, (ev_type, ev) in enumerate(_event_bus_spy.published_events):
            p = getattr(ev, "payload", {}) or {}
            print(f"    [{i}] type={ev_type} source={getattr(ev, 'source', '?')} "
                  f"target={p.get('target_id', '?')} intent={p.get('intent_type', '?')}")
            if p.get("proposition"):
                print(f"         proposition: {str(p.get('proposition'))[:200]}")

        # 6e. ALL DialogueExecutor logs
        print(f"\n  === ALL DialogueExecutor logs ===")
        all_logs = _log_capture.messages()
        de_logs = [l for l in all_logs if "dialogue_executor" in l.lower() or "DIALOGUE_EXEC" in l]
        print(f"  Total: {len(de_logs)}")
        for l in de_logs[:30]:
            print(f"    {l[:300]}")

        # 6f. ALL task_scheduler logs
        print(f"\n  === ALL task_scheduler logs (no filter) ===")
        ts_logs = [l for l in all_logs if "task_scheduler" in l.lower() or "TASK_SCHED" in l or "[SCHEDULER]" in l]
        print(f"  Total: {len(ts_logs)}")
        for l in ts_logs[:30]:
            print(f"    {l[:300]}")

        # 6g. DialogueMaterializer logs
        print(f"\n  === DialogueMaterializer logs ===")
        dm_logs = [l for l in all_logs if "dialogue_materializer" in l.lower() or "Materializer" in l]
        print(f"  Total: {len(dm_logs)}")
        for l in dm_logs[:30]:
            print(f"    {l[:300]}")

        # 6h. ERROR logs
        print(f"\n  === ALL ERROR level logs ===")
        err_logs = [l for l in all_logs if l.startswith("[ERROR]")]
        print(f"  Total: {len(err_logs)}")
        for l in err_logs[:30]:
            print(f"    {l[:300]}")

        # 6i. WARN logs
        print(f"\n  === ALL WARN level logs ===")
        warn_logs = [l for l in all_logs if l.startswith("[WARNING]")]
        print(f"  Total: {len(warn_logs)}")
        for l in warn_logs[:30]:
            print(f"    {l[:300]}")

        # =====================================================================
        # STEP 7: Tornin belief AFTER idle_tick
        # =====================================================================
        _print_section("STEP 7: Tornin belief AFTER idle_tick")
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
        # STEP 8: VERDICT
        # =====================================================================
        _print_section("STEP 8: VERDICT")

        # Separate execute calls from _generate_with_router calls
        execute_calls = [c for c in _executor_calls if "task_owner_id" in c]
        gen_calls = [c for c in _executor_calls if "req_target_id" in c]
        materializer_calls = len(_materializer_calls)
        adapter_calls = len(_adapter_calls)
        npc_spoke_count = sum(1 for t, _ in _event_bus_spy.published_events
                              if "npc_spoke" in t.lower() or "spread_rumor" in t.lower())

        print(f"  execute() calls: {len(execute_calls)}")
        print(f"  _generate_with_router calls: {len(gen_calls)}")
        print(f"  materialize() calls: {materializer_calls}")
        print(f"  to_event() calls: {adapter_calls}")
        print(f"  NPC_SPOKE/SPREAD_RUMOR published: {npc_spoke_count}")

        if new_borko_belief:
            print(f"\n  >>> VERDICT: B5-D2 NOT A DEFECT — chain completed")
        elif len(execute_calls) == 0:
            print(f"\n  >>> VERDICT: BREAK — execute() NOT called")
            print(f"  >>> Spy works, but executor was never invoked by task_scheduler")
        elif len(execute_calls) > 0 and execute_calls[0].get("exception"):
            print(f"\n  >>> VERDICT: BREAK — execute() raised exception")
            print(f"  >>> Exception: {execute_calls[0]['exception']}")
            print(f"  >>> TRACEBACK:")
            print(execute_calls[0].get("exception_traceback", "")[:1500])
        elif len(execute_calls) > 0 and execute_calls[0].get("iteration_exception"):
            print(f"\n  >>> VERDICT: BREAK — execute() generator iteration raised exception")
            print(f"  >>> Exception: {execute_calls[0]['iteration_exception']}")
            print(f"  >>> TRACEBACK:")
            print(execute_calls[0].get("iteration_traceback", "")[:1500])
        elif len(execute_calls) > 0:
            arts = execute_calls[0].get("yielded_artifacts", [])
            if not arts:
                print(f"\n  >>> VERDICT: BREAK — execute() yielded NO artifacts")
            else:
                first_art = arts[0]
                if not first_art.get("success"):
                    print(f"\n  >>> VERDICT: BREAK — execute() yielded error artifact")
                    print(f"  >>> error_message: {first_art.get('error_message', 'N/A')[:200]}")
                elif materializer_calls == 0:
                    print(f"\n  >>> VERDICT: BREAK — execute() succeeded but materializer NOT called")
                    print(f"  >>> Investigate task_scheduler materializer dispatch")
                elif adapter_calls == 0:
                    print(f"\n  >>> VERDICT: BREAK — materializer called but IntentEventAdapter NOT called")
                    print(f"  >>> Materializer creates events directly (not via IntentEventAdapter)")
                elif npc_spoke_count == 0:
                    print(f"\n  >>> VERDICT: BREAK — adapter called but NPC_SPOKE not published")
                else:
                    print(f"\n  >>> VERDICT: needs manual inspection")

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
