# backend/tests/sandbox/r2_b5_d2_executor_lifecycle_v6.py
"""
R2-B5-D2 v6 — Determine WHERE [DIALOGUE_EXEC] logs come from.

v5 finding:
  - Class spy installed (verify True)
  - But spy calls = 0 after idle_tick
  - Yet [DIALOGUE_EXEC] logs × 3 visible

This is impossible IF logs come from execute() during our idle_tick.
Hypothesis: logs come from build_game_loop() or _load_npcs_with_runtime(),
which may run their own idle_tick internally.

v6 strategy:
  1. Install spies BEFORE build_game_loop
  2. Reset log capture AFTER build_game_loop + _load_npcs_with_runtime
  3. Check 4 checkpoints for [DIALOGUE_EXEC] logs:
     - After build_game_loop (init)
     - After _load_npcs_with_runtime
     - After publish PLAYER_INSULTS
     - After idle_tick
  4. At each checkpoint, also check spy calls count
  5. If logs appear BEFORE our idle_tick, they come from initialization

ALSO: try alternative spy mechanism — patch the logger itself to track
which function called logger.debug("[DIALOGUE_EXEC]...").

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
OUT_FILE = OUT_FILE_DIR / "r2_b5_d2_executor_lifecycle_v6.txt"


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


def _count_de_logs() -> Tuple[int, List[str]]:
    """Return count and list of [DIALOGUE_EXEC] messages."""
    msgs = _log_capture.messages()
    de_logs = [m for m in msgs if "DIALOGUE_EXEC" in m or "dialogue_executor" in m.lower()]
    return len(de_logs), de_logs


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


def _spy_execute(self: Any, task: Any) -> Any:
    """Spy on DialogueExecutor.execute."""
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
    payload = getattr(task, "payload", None)
    if payload is not None:
        call_record["payload_target_id"] = getattr(payload, "target_id", None)
        call_record["payload_intent_type"] = getattr(payload, "intent_type", None)
        call_record["payload_topic"] = getattr(payload, "topic", None)
        call_record["payload_proposition"] = str(getattr(payload, "proposition", None))[:200]
    try:
        result = _orig_execute(self, task)
        call_record["return_value"] = "generator/iterable returned"
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


def _checkpoint(label: str) -> Dict[str, Any]:
    """Take a checkpoint: count spy calls + count [DIALOGUE_EXEC] logs."""
    de_count, de_logs = _count_de_logs()
    return {
        "label": label,
        "execute_calls": len(_executor_calls),
        "materialize_calls": len(_materializer_calls),
        "to_event_calls": len(_adapter_calls),
        "dialogue_exec_logs": de_count,
        "dialogue_exec_logs_sample": de_logs[:5],
    }


# ============================================================================
# MAIN
# ============================================================================
def main() -> int:
    print("=" * 78)
    print("R2-B5-D2 v6 — Where do [DIALOGUE_EXEC] logs come from?")
    print(f"OUT_FILE: {OUT_FILE}")
    print("=" * 78)
    print()
    print("v6 STRATEGY:")
    print("  - Install spies BEFORE build_game_loop")
    print("  - Take 4 checkpoints:")
    print("    1. After build_game_loop")
    print("    2. After _load_npcs_with_runtime")
    print("    3. After publish PLAYER_INSULTS")
    print("    4. After idle_tick")
    print("  - At each checkpoint, count spy calls + [DIALOGUE_EXEC] logs")
    print("  - Determine WHERE the executor is actually invoked")
    print()

    _install_log_capture()

    orig_saves_dir = settings.saves_dir
    orig_env = settings.environment

    temp_dir = Path(tempfile.mkdtemp(prefix="r2_b5_d2_v6_"))

    checkpoints: List[Dict[str, Any]] = []

    try:
        # =====================================================================
        # STEP 1: Install spies BEFORE build_game_loop
        # =====================================================================
        _print_section("STEP 1: install spies BEFORE build_game_loop")
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

        # Clear spy state
        _clear_spy_calls()
        _reset_log_capture()

        # =====================================================================
        # STEP 2: build_game_loop
        # =====================================================================
        _print_section("STEP 2: build_game_loop")
        from app.services.game_loop_builder import build_game_loop
        settings.saves_dir = str(temp_dir)
        settings.environment = "development"
        loop = build_game_loop(data_dir=Path(settings.data_dir))

        # Checkpoint 1
        cp1 = _checkpoint("after build_game_loop")
        checkpoints.append(cp1)
        print(f"\n  Checkpoint 1 (after build_game_loop):")
        print(f"    execute_calls: {cp1['execute_calls']}")
        print(f"    materialize_calls: {cp1['materialize_calls']}")
        print(f"    to_event_calls: {cp1['to_event_calls']}")
        print(f"    [DIALOGUE_EXEC] logs: {cp1['dialogue_exec_logs']}")
        if cp1["dialogue_exec_logs_sample"]:
            print(f"    Sample logs:")
            for l in cp1["dialogue_exec_logs_sample"]:
                print(f"      {l[:200]}")

        # =====================================================================
        # STEP 3: _load_npcs_with_runtime
        # =====================================================================
        _print_section("STEP 3: _load_npcs_with_runtime")
        scene = loop.scene_manager.get_scene_state("Open_road", "tavern")
        if scene is None:
            scene = loop.scene_manager.initialize_scene("Open_road", "tavern", "12:00")
        loaded = loop._load_npcs_with_runtime("Open_road")
        print(f"  loaded {len(loaded) if hasattr(loaded, '__len__') else '?'} NPCs")

        # Checkpoint 2
        cp2 = _checkpoint("after _load_npcs_with_runtime")
        checkpoints.append(cp2)
        print(f"\n  Checkpoint 2 (after _load_npcs_with_runtime):")
        print(f"    execute_calls: {cp2['execute_calls']}")
        print(f"    materialize_calls: {cp2['materialize_calls']}")
        print(f"    to_event_calls: {cp2['to_event_calls']}")
        print(f"    [DIALOGUE_EXEC] logs: {cp2['dialogue_exec_logs']}")
        if cp2["dialogue_exec_logs_sample"]:
            print(f"    Sample logs:")
            for l in cp2["dialogue_exec_logs_sample"]:
                print(f"      {l[:200]}")

        # =====================================================================
        # STEP 4: install EventBus spy + publish PLAYER_INSULTS
        # =====================================================================
        _print_section("STEP 4: install EventBus spy + publish PLAYER_INSULTS")
        from app.services.events.event_bus import get_event_bus
        from app.services.events.event_types import EventType
        from app.domain.events import EventDTO
        from app.services.events.claim_event_subscriber import ClaimEventSubscriber
        from app.domain.epistemology import Proposition, Predicate  # type: ignore

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
        print(f"  sub: {sub}")
        print(f"  store: {store}")

        _event_bus_spy.install(bus)
        print(f"  EventBus spy installed")

        # Capture pre-existing Tornin beliefs
        if store:
            tornin_pre = store.get_all_for_agent("tavern_keeper_tornin") or []
            print(f"  Tornin pre-existing records: {len(tornin_pre)}")

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

        # Checkpoint 3
        cp3 = _checkpoint("after publish PLAYER_INSULTS")
        checkpoints.append(cp3)
        print(f"\n  Checkpoint 3 (after publish):")
        print(f"    execute_calls: {cp3['execute_calls']}")
        print(f"    materialize_calls: {cp3['materialize_calls']}")
        print(f"    to_event_calls: {cp3['to_event_calls']}")
        print(f"    [DIALOGUE_EXEC] logs: {cp3['dialogue_exec_logs']}")
        if cp3["dialogue_exec_logs_sample"]:
            print(f"    Sample logs:")
            for l in cp3["dialogue_exec_logs_sample"]:
                print(f"      {l[:200]}")

        # =====================================================================
        # STEP 5: clear all spy state + run idle_tick
        # =====================================================================
        _print_section("STEP 5: clear spy state + run idle_tick")
        _clear_spy_calls()
        _reset_log_capture()
        _event_bus_spy.clear()

        # CRITICAL: re-install spies in case build_game_loop reset them
        # Re-verify
        print(f"  Re-verify spies before idle_tick:")
        from app.services.execution.dialogue_executor import DialogueExecutor as DE2
        print(f"    DialogueExecutor.execute is _spy_execute: {DE2.execute is _spy_execute}")
        # If spies were reset, reinstall
        if DE2.execute is not _spy_execute:
            print(f"  >>> Spies were reset! Reinstalling...")
            _install_class_spies()
            print(f"    After reinstall: DialogueExecutor.execute is _spy_execute: {DE2.execute is _spy_execute}")

        try:
            result = loop.idle_tick("Open_road", "tavern")
            print(f"  idle_tick returned: {type(result).__name__}")
            if isinstance(result, dict):
                print(f"  status: {result.get('status')}")
        except Exception as e:
            print(f"  ERROR: {type(e).__name__}: {e}")
            traceback.print_exc()

        # Checkpoint 4
        cp4 = _checkpoint("after idle_tick")
        checkpoints.append(cp4)
        print(f"\n  Checkpoint 4 (after idle_tick):")
        print(f"    execute_calls: {cp4['execute_calls']}")
        print(f"    materialize_calls: {cp4['materialize_calls']}")
        print(f"    to_event_calls: {cp4['to_event_calls']}")
        print(f"    [DIALOGUE_EXEC] logs: {cp4['dialogue_exec_logs']}")
        if cp4["dialogue_exec_logs_sample"]:
            print(f"    Sample logs:")
            for l in cp4["dialogue_exec_logs_sample"]:
                print(f"      {l[:200]}")

        # =====================================================================
        # STEP 6: spy details if any calls captured
        # =====================================================================
        _print_section("STEP 6: spy details")

        if _executor_calls:
            print(f"\n  === DialogueExecutor.execute() calls ===")
            for i, call in enumerate(_executor_calls):
                print(f"\n  Call [{i}]:")
                print(f"    instance_id: {call.get('instance_id')}")
                print(f"    instance_type: {call.get('instance_type')}")
                print(f"    instance_router: {call.get('instance_router', 'N/A')[:100]}")
                if "task_owner_id" in call:
                    print(f"    task_owner_id: {call.get('task_owner_id')}")
                    print(f"    payload_target_id: {call.get('payload_target_id')}")
                    print(f"    payload_intent_type: {call.get('payload_intent_type')}")
                    print(f"    payload_topic: {call.get('payload_topic')}")
                    print(f"    payload_proposition: {call.get('payload_proposition')}")
                if call.get("exception"):
                    print(f"    EXCEPTION: {call['exception']}")
                    if "exception_traceback" in call:
                        print(f"    TRACEBACK:")
                        print(call["exception_traceback"][:1500])
                else:
                    print(f"    return: {call.get('return_value', 'N/A')[:200]}")
                    if call.get("yielded_artifacts"):
                        print(f"    yielded artifacts:")
                        for art in call["yielded_artifacts"]:
                            print(f"      success={art.get('success')} result_type={art.get('result_type')}")
                            if art.get("error_message"):
                                print(f"        error: {art['error_message'][:200]}")
                            if art.get("data_text"):
                                print(f"        text: {art['data_text'][:200]}")
        else:
            print(f"  No execute() calls captured")

        if _materializer_calls:
            print(f"\n  === DialogueMaterializer.materialize() calls ===")
            for i, call in enumerate(_materializer_calls):
                print(f"  [{i}] artifact.success={call.get('artifact_success')}")
                if call.get("exception"):
                    print(f"      EXCEPTION: {call['exception']}")
        else:
            print(f"  No materialize() calls captured")

        # EventBus events
        print(f"\n  === EventBus events after reset ===")
        print(f"  Total: {len(_event_bus_spy.published_events)}")
        ev_type_counter: Dict[str, int] = {}
        for ev_type, _ in _event_bus_spy.published_events:
            ev_type_counter[ev_type] = ev_type_counter.get(ev_type, 0) + 1
        for ev_type, count in sorted(ev_type_counter.items()):
            print(f"    {ev_type}: {count}")

        # =====================================================================
        # STEP 7: Check Tornin belief AFTER idle_tick
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
        # STEP 8: Summary + VERDICT
        # =====================================================================
        _print_section("STEP 8: Summary + VERDICT")

        print(f"\n  === Checkpoint summary ===")
        print(f"  {'Checkpoint':<35} {'exec':>6} {'mat':>6} {'adapter':>8} {'DE_logs':>8}")
        for cp in checkpoints:
            print(f"  {cp['label']:<35} {cp['execute_calls']:>6} {cp['materialize_calls']:>6} "
                  f"{cp['to_event_calls']:>8} {cp['dialogue_exec_logs']:>8}")

        # Analysis
        print(f"\n  === Analysis ===")
        if checkpoints[0]["execute_calls"] > 0:
            print(f"  >>> execute() called DURING build_game_loop")
            print(f"  >>> This means build_game_loop runs its own tick internally")
            print(f"  >>> Our idle_tick happens AFTER this initial tick")
        if checkpoints[1]["dialogue_exec_logs"] > checkpoints[0]["dialogue_exec_logs"]:
            print(f"  >>> [DIALOGUE_EXEC] logs appeared during _load_npcs_with_runtime")
        if checkpoints[2]["dialogue_exec_logs"] > checkpoints[1]["dialogue_exec_logs"]:
            print(f"  >>> [DIALOGUE_EXEC] logs appeared during publish PLAYER_INSULTS")
        if checkpoints[3]["dialogue_exec_logs"] > checkpoints[2]["dialogue_exec_logs"]:
            print(f"  >>> [DIALOGUE_EXEC] logs appeared during idle_tick")
            print(f"  >>> But spy calls = {checkpoints[3]['execute_calls']}")
            print(f"  >>> This means execute() called but spy NOT triggered")
            print(f"  >>> Hypothesis: spy was reset by build_game_loop or _load_npcs_with_runtime")
        else:
            print(f"  >>> No new [DIALOGUE_EXEC] logs during idle_tick")
            print(f"  >>> All [DIALOGUE_EXEC] logs came from build_game_loop/init")

        # Final verdict
        if new_borko_belief:
            print(f"\n  >>> VERDICT: B5-D2 NOT A DEFECT — chain completed")
        elif checkpoints[3]["execute_calls"] == 0 and checkpoints[3]["dialogue_exec_logs"] == 0:
            print(f"\n  >>> VERDICT: idle_tick does NOT call DialogueExecutor.execute()")
            print(f"  >>> Task scheduler is not dispatching tasks during idle_tick")
            print(f"  >>> Need to investigate: why does idle_tick not enqueue dialogue tasks?")
        elif checkpoints[3]["execute_calls"] == 0 and checkpoints[3]["dialogue_exec_logs"] > 0:
            print(f"\n  >>> VERDICT: execute() called but spy NOT triggered")
            print(f"  >>> Spy is bypassed — possibly via _orig_execute direct reference")
        else:
            print(f"\n  >>> VERDICT: needs manual inspection of checkpoints above")

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
