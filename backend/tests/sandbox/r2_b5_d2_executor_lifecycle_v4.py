# backend/tests/sandbox/r2_b5_d2_executor_lifecycle_v4.py
"""
R2-B5-D2 v4 — Find ALL DialogueExecutor instances and spy on each.

v3 finding:
  - Spy attached to task_scheduler._executors[TaskKind.DIALOGUE]
  - But execute() calls = 0 in spy
  - Yet logs show [DIALOGUE_EXEC] Executing task for guard_borko × 3

This is impossible IF there's only one DialogueExecutor.
Conclusion: there may be MULTIPLE DialogueExecutor instances, OR
the method dispatch path differs from what we expected.

v4 strategy:
  1. Use gc.get_objects() to find ALL DialogueExecutor instances in runtime
  2. Spy on EACH found instance (capture id + call count per executor)
  3. Track which executor is actually called by task_scheduler
  4. ALSO spy on DialogueMaterializer.materialize (if there's a different path)
  5. Trace exactly where [DIALOGUE_EXEC] log comes from

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
OUT_FILE = OUT_FILE_DIR / "r2_b5_d2_executor_lifecycle_v4.txt"


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
# Per-instance spy — wraps BOTH class method AND instance attribute
# ============================================================================
class _InstanceSpy:
    """Spy on DialogueExecutor via CLASS method replacement (not instance attr).
    This catches ALL instances, regardless of how they're accessed.

    Strategy:
      - Replace DialogueExecutor.execute at the class level
      - Each call to ANY instance will go through our spy
      - Spy captures instance id + call details
    """
    def __init__(self):
        self.calls: List[Dict[str, Any]] = []
        self._installed = False
        self._orig_execute = None
        self._orig_gen = None
        self._class = None

    def install(self) -> bool:
        if self._installed:
            return True
        try:
            from app.services.execution.dialogue_executor import DialogueExecutor
            self._class = DialogueExecutor
            # Save original class method
            self._orig_execute = DialogueExecutor.execute
            # Replace at class level
            DialogueExecutor.execute = self._spy_execute
            # Also spy on _generate_with_router
            self._orig_gen = DialogueExecutor._generate_with_router
            DialogueExecutor._generate_with_router = self._spy_gen
            self._installed = True
            return True
        except Exception as e:
            print(f"  [_InstanceSpy install failed: {e}]")
            traceback.print_exc()
            return False

    def restore(self) -> None:
        if self._installed and self._class is not None:
            if self._orig_execute is not None:
                self._class.execute = self._orig_execute
            if self._orig_gen is not None:
                self._class._generate_with_router = self._orig_gen
            self._installed = False

    def _spy_execute(self, self_instance: Any, *args, **kwargs) -> Any:
        call_record: Dict[str, Any] = {
            "instance_id": id(self_instance),
            "instance_router": repr(getattr(self_instance, "_router", None))[:80],
            "args_repr": [repr(a)[:200] for a in args],
            "kwargs_repr": {k: repr(v)[:200] for k, v in kwargs.items()},
            "exception": None,
            "return_value": None,
        }
        try:
            result = self._orig_execute(self_instance, *args, **kwargs)
            call_record["return_value"] = "generator/iterable returned"
            # Check if iterable
            if hasattr(result, "__iter__") or hasattr(result, "__next__"):
                call_record["is_generator"] = True
            else:
                call_record["is_generator"] = False
                call_record["return_value"] = repr(result)[:300]
            self.calls.append(call_record)
            return result
        except Exception as e:
            call_record["exception"] = f"{type(e).__name__}: {e}"
            call_record["exception_traceback"] = traceback.format_exc()[:1500]
            self.calls.append(call_record)
            raise

    def _spy_gen(self, self_instance: Any, *args, **kwargs) -> Any:
        gen_record: Dict[str, Any] = {
            "instance_id": id(self_instance),
            "args_repr": [repr(a)[:200] for a in args],
            "exception": None,
            "return_value": None,
        }
        try:
            result = self._orig_gen(self_instance, *args, **kwargs)
            gen_record["return_value"] = repr(result)[:300] if result is not None else None
            self.calls.append(gen_record)
            return result
        except Exception as e:
            gen_record["exception"] = f"{type(e).__name__}: {e}"
            gen_record["exception_traceback"] = traceback.format_exc()[:1500]
            self.calls.append(gen_record)
            raise

    def clear(self) -> None:
        self.calls.clear()


_instance_spy = _InstanceSpy()


# ============================================================================
# Materializer spy — also at class level
# ============================================================================
class _MaterializerSpy:
    def __init__(self):
        self.calls: List[Dict[str, Any]] = []
        self._installed = False
        self._orig = None
        self._class = None

    def install(self) -> bool:
        if self._installed:
            return True
        try:
            from app.services.execution.dialogue_materializer import DialogueMaterializer
            self._class = DialogueMaterializer
            self._orig = DialogueMaterializer.materialize
            DialogueMaterializer.materialize = self._spy
            self._installed = True
            return True
        except Exception as e:
            print(f"  [_MaterializerSpy install failed: {e}]")
            return False

    def restore(self) -> None:
        if self._installed and self._class is not None and self._orig is not None:
            self._class.materialize = self._orig
            self._installed = False

    def _spy(self, self_instance: Any, *args, **kwargs) -> Any:
        call_record: Dict[str, Any] = {
            "instance_id": id(self_instance),
            "args_repr": [repr(a)[:200] for a in args],
            "exception": None,
            "return_value": None,
        }
        try:
            result = self._orig(self_instance, *args, **kwargs)
            call_record["return_value"] = repr(result)[:300] if result is not None else None
            # If it's a list/iterable, count items
            if hasattr(result, "__len__"):
                call_record["result_count"] = len(result)
            self.calls.append(call_record)
            return result
        except Exception as e:
            call_record["exception"] = f"{type(e).__name__}: {e}"
            call_record["exception_traceback"] = traceback.format_exc()[:1500]
            self.calls.append(call_record)
            raise

    def clear(self) -> None:
        self.calls.clear()


_materializer_spy = _MaterializerSpy()


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
            "intent_speaker": getattr(intent, "speaker", None),
            "intent_target": getattr(intent, "target_id", None) or getattr(intent, "audience", None),
            "intent_type": getattr(intent, "intent_type", None),
            "intent_proposition": str(getattr(intent, "proposition", None))[:200],
            "exception": None,
        }
        try:
            result = self._orig_to_event(intent)
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
# Find all DialogueExecutor instances via gc
# ============================================================================
def _find_all_dialogue_executors() -> List[Tuple[int, Any]]:
    """Find ALL DialogueExecutor instances via gc.get_objects()."""
    import gc as _gc
    try:
        from app.services.execution.dialogue_executor import DialogueExecutor
    except Exception:
        return []
    instances = []
    for obj in _gc.get_objects():
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
    print("R2-B5-D2 v4 — Find ALL DialogueExecutor instances, spy at CLASS level")
    print(f"OUT_FILE: {OUT_FILE}")
    print("=" * 78)
    print()
    print("v4 FIXES from v3:")
    print("  - Spy at CLASS level (DialogueExecutor.execute), not instance")
    print("  - Captures ALL calls regardless of which instance is used")
    print("  - gc.get_objects() to find ALL DialogueExecutor instances")
    print("  - Also spy on DialogueMaterializer.materialize at class level")
    print()

    _install_log_capture()

    import gc  # explicit import at function scope

    orig_saves_dir = settings.saves_dir
    orig_env = settings.environment

    temp_dir = Path(tempfile.mkdtemp(prefix="r2_b5_d2_v4_"))

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
        print(f"  Found {len(instances_before)} DialogueExecutor instance(s) BEFORE spy:")
        for inst_id, inst in instances_before:
            router = getattr(inst, "_router", None)
            print(f"    id={inst_id}, router={router}, router_type={type(router).__name__}")

        # Also find DialogueMaterializer instances
        print(f"\n  --- Find ALL DialogueMaterializer instances ---")
        try:
            from app.services.execution.dialogue_materializer import DialogueMaterializer
            mat_instances = []
            for obj in gc.get_objects():
                try:
                    if isinstance(obj, DialogueMaterializer):
                        mat_instances.append((id(obj), obj))
                except Exception:
                    continue
            print(f"  Found {len(mat_instances)} DialogueMaterializer instance(s):")
            for mid, m in mat_instances:
                print(f"    id={mid}")
        except Exception as e:
            print(f"  materializer search error: {e}")

        # =====================================================================
        # STEP 2: Install CLASS-LEVEL spies
        # =====================================================================
        _print_section("STEP 2: install CLASS-LEVEL spies")
        _event_bus_spy.install(bus)
        print(f"  EventBus spy installed")

        _instance_spy.install()
        print(f"  DialogueExecutor CLASS spy installed")

        _materializer_spy.install()
        print(f"  DialogueMaterializer CLASS spy installed")

        _adapter_spy.install()
        print(f"  IntentEventAdapter CLASS spy installed")

        # Verify class-level replacement worked
        from app.services.execution.dialogue_executor import DialogueExecutor
        print(f"\n  Verify class-level replacement:")
        print(f"    DialogueExecutor.execute is _instance_spy._spy_execute: "
              f"{DialogueExecutor.execute == _instance_spy._spy_execute}")
        print(f"    DialogueExecutor._generate_with_router is _instance_spy._spy_gen: "
              f"{DialogueExecutor._generate_with_router == _instance_spy._spy_gen}")

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
        _instance_spy.clear()
        _materializer_spy.clear()
        _adapter_spy.clear()
        _reset_log_capture()
        _install_log_capture()

        # Re-verify spies are still installed
        print(f"  Re-verify spies after reset:")
        print(f"    DialogueExecutor.execute is _spy_execute: "
              f"{DialogueExecutor.execute == _instance_spy._spy_execute}")
        print(f"    DialogueMaterializer.materialize is _spy: "
              f"{DialogueMaterializer.materialize == _materializer_spy._spy}")

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

        # 6a. ALL DialogueExecutor.execute() calls (with instance_id)
        print(f"\n  === DialogueExecutor.execute() calls ===")
        print(f"  Total calls: {len(_instance_spy.calls)}")
        # Group by instance_id
        by_instance: Dict[int, List[Dict]] = {}
        for call in _instance_spy.calls:
            inst_id = call.get("instance_id")
            by_instance.setdefault(inst_id, []).append(call)
        print(f"  Calls by instance:")
        for inst_id, calls in by_instance.items():
            print(f"    instance id={inst_id}: {len(calls)} call(s)")
            for i, c in enumerate(calls[:3]):
                print(f"      [{i}] router={c.get('instance_router', 'N/A')[:60]}")
                if c.get("exception"):
                    print(f"          EXCEPTION: {c['exception']}")
                    if "exception_traceback" in c:
                        print(f"          TRACEBACK: {c['exception_traceback'][:800]}")
                else:
                    print(f"          return: {c.get('return_value', 'N/A')[:120]}")

        # 6b. _generate_with_router calls (in same _instance_spy.calls)
        # Already captured above

        # 6c. DialogueMaterializer.materialize calls
        print(f"\n  === DialogueMaterializer.materialize() calls ===")
        print(f"  Total calls: {len(_materializer_spy.calls)}")
        for i, call in enumerate(_materializer_spy.calls[:10]):
            print(f"  [{i}] instance_id={call.get('instance_id')}")
            print(f"      args: {call.get('args_repr')}")
            if call.get("exception"):
                print(f"      EXCEPTION: {call['exception']}")
            else:
                print(f"      return: {call.get('return_value', 'N/A')[:200]}")
                if "result_count" in call:
                    print(f"      result count: {call['result_count']}")

        # 6d. IntentEventAdapter.to_event calls
        print(f"\n  === IntentEventAdapter.to_event() calls ===")
        print(f"  Total calls: {len(_adapter_spy.calls)}")
        for i, call in enumerate(_adapter_spy.calls[:10]):
            print(f"  [{i}] speaker={call.get('intent_speaker')} target={call.get('intent_target')} "
                  f"type={call.get('intent_type')}")
            print(f"      proposition: {call.get('intent_proposition', 'N/A')[:120]}")
            if call.get("exception"):
                print(f"      EXCEPTION: {call['exception']}")
            else:
                print(f"      return_event_type: {call.get('return_event_type', 'N/A')}")

        # 6e. EventBus events
        print(f"\n  === EventBus.publish() calls ===")
        print(f"  Total events: {len(_event_bus_spy.published_events)}")
        ev_type_counter: Dict[str, int] = {}
        for ev_type, _ in _event_bus_spy.published_events:
            ev_type_counter[ev_type] = ev_type_counter.get(ev_type, 0) + 1
        for ev_type, count in sorted(ev_type_counter.items()):
            print(f"    {ev_type}: {count}")

        # Show all events with their details
        print(f"\n  --- ALL events with details ---")
        for i, (ev_type, ev) in enumerate(_event_bus_spy.published_events):
            p = getattr(ev, "payload", {}) or {}
            print(f"    [{i}] type={ev_type} source={getattr(ev, 'source', '?')} "
                  f"target={p.get('target_id', '?')} intent={p.get('intent_type', '?')}")
            if p.get("proposition"):
                print(f"         proposition: {str(p.get('proposition'))[:200]}")

        # 6f. ALL DialogueExecutor logs
        print(f"\n  === ALL DialogueExecutor logs ===")
        all_logs = _log_capture.messages()
        de_logs = [l for l in all_logs if "dialogue_executor" in l.lower() or "DIALOGUE_EXEC" in l]
        print(f"  Total: {len(de_logs)}")
        for l in de_logs[:30]:
            print(f"    {l[:300]}")

        # 6g. ALL task_scheduler logs
        print(f"\n  === ALL task_scheduler logs (no filter) ===")
        ts_logs = [l for l in all_logs if "task_scheduler" in l.lower() or "TASK_SCHED" in l or "[SCHEDULER]" in l]
        print(f"  Total: {len(ts_logs)}")
        for l in ts_logs[:30]:
            print(f"    {l[:300]}")

        # 6h. ALL DialogueMaterializer logs
        print(f"\n  === ALL DialogueMaterializer logs ===")
        dm_logs = [l for l in all_logs if "dialogue_materializer" in l.lower() or "Materializer" in l]
        print(f"  Total: {len(dm_logs)}")
        for l in dm_logs[:30]:
            print(f"    {l[:300]}")

        # 6i. ERROR logs
        print(f"\n  === ALL ERROR level logs ===")
        err_logs = [l for l in all_logs if l.startswith("[ERROR]")]
        print(f"  Total: {len(err_logs)}")
        for l in err_logs[:30]:
            print(f"    {l[:300]}")

        # 6j. WARN logs
        print(f"\n  === ALL WARN level logs ===")
        warn_logs = [l for l in all_logs if l.startswith("[WARNING]")]
        print(f"  Total: {len(warn_logs)}")
        for l in warn_logs[:30]:
            print(f"    {l[:300]}")

        # 6k. ALL DialogueExecutor instances AFTER spy
        print(f"\n  === ALL DialogueExecutor instances AFTER spy ===")
        gc.collect()
        instances_after = _find_all_dialogue_executors()
        print(f"  Found {len(instances_after)} DialogueExecutor instance(s) AFTER:")
        for inst_id, inst in instances_after:
            router = getattr(inst, "_router", None)
            print(f"    id={inst_id}, router={router}, router_type={type(router).__name__}")

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
        # STEP 8: VERDICT
        # =====================================================================
        _print_section("STEP 8: VERDICT")

        executor_calls = len(_instance_spy.calls)
        materializer_calls = len(_materializer_spy.calls)
        adapter_calls = len(_adapter_spy.calls)
        npc_spoke_count = sum(1 for t, _ in _event_bus_spy.published_events
                              if "npc_spoke" in t.lower() or "spread_rumor" in t.lower())

        print(f"  DialogueExecutor.execute() called (CLASS spy): {executor_calls}")
        print(f"  DialogueMaterializer.materialize() called: {materializer_calls}")
        print(f"  IntentEventAdapter.to_event() called: {adapter_calls}")
        print(f"  NPC_SPOKE/SPREAD_RUMOR published: {npc_spoke_count}")

        if new_borko_belief:
            print(f"\n  >>> VERDICT: B5-D2 NOT A DEFECT — chain completed")
        elif executor_calls == 0:
            print(f"\n  >>> VERDICT: BREAK — execute() still NOT captured by class-level spy")
            print(f"  >>> This means [DIALOGUE_EXEC] log comes from somewhere else")
            print(f"  >>> Check if logs are from PREVIOUS runs (stale log capture)")
            print(f"  >>> OR: execute() is called via a different code path")
        elif executor_calls > 0 and materializer_calls == 0:
            print(f"\n  >>> VERDICT: BREAK — execute() called, materializer NOT called")
            print(f"  >>> Likely: artifact.success=False (error branch)")
            if _instance_spy.calls:
                last = _instance_spy.calls[-1]
                if last.get("exception"):
                    print(f"  >>> Last exception: {last['exception']}")
        elif materializer_calls > 0 and adapter_calls == 0:
            print(f"\n  >>> VERDICT: BREAK — materializer called, adapter NOT called")
            print(f"  >>> Materializer creates events directly, not via IntentEventAdapter")
            print(f"  >>> Check materializer result count")
        elif adapter_calls > 0 and npc_spoke_count == 0:
            print(f"\n  >>> VERDICT: BREAK — adapter called, NPC_SPOKE not published")
        else:
            print(f"\n  >>> VERDICT: INCONCLUSIVE — needs manual inspection")

        # ---- Cleanup ----
        _event_bus_spy.restore()
        _instance_spy.restore()
        _materializer_spy.restore()
        _adapter_spy.restore()
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
        _instance_spy.restore()
        _materializer_spy.restore()
        _adapter_spy.restore()
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
