# backend/tests/sandbox/r2_b5_d2_spread_rumor_execution.py
"""
R2-B5-D2 — Trace SPREAD_RUMOR execution on guard_borko (B5-E2 confirmed winner).

GOAL: Determine if ENIGMA can turn a selected SPREAD_RUMOR intent into a real
      social event that propagates the belief to tavern_keeper_tornin.

Subchains to verify (per Master):
  A. CommunicationIntent creation (where, what proposition, what target, where stored)
  B. Execution (dialogue_executor, intent_event_adapter, movement)
  C. NPC_SPOKE publication (when, by whom, with what proposition)
  D. Tornin belief reception (handler invoked, proposition, provenance chain)

STRATEGY:
  1. Build game loop, load NPCs, publish PLAYER_INSULTS
  2. Run idle_tick MULTIPLE times (10 ticks) — allow movement progression
  3. After each tick:
     - Inspect guard_borko.NPCState.intent, intent_target, position
     - Capture all EventBus events (NPC_SPOKE, COMMUNICATION_CLAIM, etc.)
     - Check tavern_keeper_tornin store for new belief
     - Capture all DecisionHub logs
  4. After all ticks: comprehensive report on chain completion

CONSTRAINTS:
  - No production code changes
  - No artificial NPC_SPOKE publishing
  - Do not assume comm_built=True proves communication happened
  - Multiple ticks: traversal requires ticks=2 (per v4 logs)

READ-ONLY. Production-код не менять.
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
OUT_FILE = OUT_FILE_DIR / "r2_b5_d2_spread_rumor_execution.txt"


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
# Log capture (from B5-E2.1 v2 — proven to work)
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
    "app.services.npc.break_progress_engine",
    "app.services.phases.decision",
    "app.services.npc.domain_phases",
    "app.services.npc.life_engine",
    "app.services.world.world_tick_engine",
    "app.services.game_loop.game_loop",
    "app.services.spatial.movement_engine",
    "app.services.event_compiler",
    "app.services.events.event_bus",
    "app.services.execution.dialogue_executor",
    "app.services.game_loop.task_scheduler",
    "app.services.npc.state_applicator",
    "app.services.events.intent_event_adapter",
    "app",  # catch-all
    "",    # root
]


def _install_log_capture() -> None:
    root = logging.getLogger()
    already_installed = any(isinstance(h, _LogCapture) for h in root.handlers)
    if not already_installed:
        root.addHandler(_log_capture)
    root.setLevel(logging.DEBUG)
    for name in _TARGET_LOGGERS:
        lg = logging.getLogger(name)
        lg.setLevel(logging.DEBUG)
        lg.propagate = True
        already = any(isinstance(h, _LogCapture) for h in lg.handlers)
        if not already:
            lg.addHandler(_log_capture)


def _reset_log_capture() -> None:
    _log_capture.records.clear()


# ============================================================================
# EventBus spy — capture all published events
# ============================================================================
class _EventBusSpy:
    """Wrap EventBus.publish to capture all published events."""
    def __init__(self):
        self.published_events: List[Tuple[str, Any]] = []  # (event_type, event)
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
        # Call original
        return self._orig_publish(event)

    def events_by_type(self, type_filter: str) -> List[Any]:
        return [e for t, e in self.published_events if type_filter.lower() in t.lower()]

    def clear(self) -> None:
        self.published_events.clear()


_event_bus_spy = _EventBusSpy()


# ============================================================================
# Helpers
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


def _inspect_obj(obj: Any, depth: int = 0, max_depth: int = 2) -> Any:
    if depth > max_depth:
        return {"_truncated": repr(obj)[:150]}
    if obj is None:
        return None
    if isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, (list, tuple, set)):
        return [_inspect_obj(x, depth + 1, max_depth) for x in list(obj)[:5]]
    if isinstance(obj, dict):
        return {str(k): _inspect_obj(v, depth + 1, max_depth) for k, v in list(obj.items())[:10]}
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


def _find_sub_and_store(bus) -> Tuple[Optional[Any], Optional[Any]]:
    """Find ClaimEventSubscriber + its store."""
    from app.services.events.claim_event_subscriber import ClaimEventSubscriber
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
    return sub, store


def _find_npc_state(loop, npc_id: str) -> Tuple[Optional[Any], str]:
    """Find NPC state via multiple strategies."""
    # Strategy 1: scene_state['npc_states']
    try:
        scene = loop.scene_manager.get_scene_state("Open_road", "tavern")
        if scene:
            npc_states = scene.get("npc_states", {}) or {}
            if npc_id in npc_states:
                return npc_states[npc_id], "scene['npc_states']"
    except Exception:
        pass
    # Strategy 2: _resolve_npcs_snapshot
    try:
        snap_fn = getattr(loop, "_resolve_npcs_snapshot", None)
        if snap_fn:
            snap = snap_fn("Open_road")
            if isinstance(snap, dict) and npc_id in snap:
                return snap[npc_id], "loop._resolve_npcs_snapshot (dict)"
            if isinstance(snap, list):
                for item in snap:
                    nid = getattr(item, "npc_id", None) or (item.get("npc_id") if isinstance(item, dict) else None)
                    if nid == npc_id:
                        return item, "loop._resolve_npcs_snapshot (list)"
    except Exception:
        pass
    # Strategy 3: npc_manager
    for nm_attr in ("_npc_manager", "npc_manager", "_npcs"):
        nm = getattr(loop, nm_attr, None)
        if nm is None:
            continue
        for method_name in ("get_npc_state", "get_state", "get", "get_npc"):
            method = getattr(nm, method_name, None)
            if method is None:
                continue
            for args in [(npc_id,), ("Open_road", npc_id),
                         ("Open_road", "tavern", npc_id)]:
                try:
                    result = method(*args)
                    if result is not None:
                        return result, f"loop.{nm_attr}.{method_name}({args})"
                except TypeError:
                    continue
                except Exception:
                    continue
        for method_name in ("snapshot", "all_states", "states"):
            method = getattr(nm, method_name, None)
            if method is None:
                continue
            try:
                result = method()
                if isinstance(result, dict) and npc_id in result:
                    return result[npc_id], f"loop.{nm_attr}.{method_name}()[dict]"
                if isinstance(result, list):
                    for item in result:
                        nid = getattr(item, "npc_id", None) or (item.get("npc_id") if isinstance(item, dict) else None)
                        if nid == npc_id:
                            return item, f"loop.{nm_attr}.{method_name}()[list]"
            except Exception:
                continue
    return None, "not_found"


# ============================================================================
# Production source readers — for understanding architecture
# ============================================================================
def _read_decision_hub_build_communication() -> None:
    """Read _build_communication method from decision_hub.py."""
    _print_section("PROD SOURCE: _build_communication in decision_hub.py")
    dh_path = _BACKEND / "app" / "services" / "npc" / "decision_hub.py"
    if not dh_path.exists():
        print(f"  [file not found: {dh_path}]")
        return
    src = _read_file_text(dh_path)
    lines = src.split("\n")
    bounds = _find_function_bounds(src, "_build_communication")
    if bounds:
        s, e = bounds
        print(f"  _build_communication at L{s+1}..L{e}:")
        for j in range(s, e):
            print(f"  L{j+1:4d}: {lines[j]}")
    else:
        print("  [_build_communication not found]")


def _read_dialogue_executor_spread_rumor() -> None:
    """Read dialogue_executor.py around spread_rumor handling."""
    _print_section("PROD SOURCE: dialogue_executor.py spread_rumor handling")
    de_path = _BACKEND / "app" / "services" / "execution" / "dialogue_executor.py"
    if not de_path.exists():
        print(f"  [file not found: {de_path}]")
        return
    src = _read_file_text(de_path)
    lines = src.split("\n")
    # Find spread_rumor references
    for i, line in enumerate(lines):
        if "spread_rumor" in line.lower():
            ctx_start = max(0, i - 5)
            ctx_end = min(len(lines), i + 10)
            print(f"\n  >>> L{i+1}: {line.rstrip()}")
            for j in range(ctx_start, ctx_end):
                marker = ">>>" if j + 1 == i + 1 else "   "
                print(f"  {marker} L{j+1:4d}: {lines[j]}")


def _read_task_scheduler_fast_path() -> None:
    """Read task_scheduler.py fast-path for spread_rumor."""
    _print_section("PROD SOURCE: task_scheduler.py fast-path for spread_rumor")
    ts_path = _BACKEND / "app" / "services" / "game_loop" / "task_scheduler.py"
    if not ts_path.exists():
        print(f"  [file not found: {ts_path}]")
        return
    src = _read_file_text(ts_path)
    lines = src.split("\n")
    # Find spread_rumor references
    for i, line in enumerate(lines):
        if "spread_rumor" in line.lower() or "fast-path" in line.lower() or "FAST" in line:
            ctx_start = max(0, i - 3)
            ctx_end = min(len(lines), i + 15)
            print(f"\n  >>> L{i+1}: {line.rstrip()}")
            for j in range(ctx_start, ctx_end):
                marker = ">>>" if j + 1 == i + 1 else "   "
                print(f"  {marker} L{j+1:4d}: {lines[j]}")


def _read_game_loop_fast_path_npc_spoke() -> None:
    """Read game_loop.py L1852 area (NPC_SPOKE synchronous publish)."""
    _print_section("PROD SOURCE: game_loop.py fast-path NPC_SPOKE publish")
    gl_path = _BACKEND / "app" / "services" / "game_loop" / "game_loop.py"
    if not gl_path.exists():
        print(f"  [file not found: {gl_path}]")
        return
    src = _read_file_text(gl_path)
    lines = src.split("\n")
    # Find NPC_SPOKE publish references (simple substring matching)
    matches: List[int] = []
    for i, line in enumerate(lines):
        low = line.lower()
        if "npc_spoke" in low and ("publish" in low or "spread_rumor" in low or "fast" in low):
            matches.append(i)
        elif "spread_rumor" in low and "fast" in low:
            matches.append(i)
    print(f"  Found {len(matches)} matching lines")
    seen_ranges = set()
    for i in matches[:15]:  # limit
        ctx_start = max(0, i - 5)
        ctx_end = min(len(lines), i + 15)
        # Skip if range overlaps with previous
        if any(r in seen_ranges for r in range(ctx_start, ctx_end)):
            continue
        for r in range(ctx_start, ctx_end):
            seen_ranges.add(r)
        print(f"\n  >>> L{i+1}: {lines[i].rstrip()}")
        for j in range(ctx_start, ctx_end):
            marker = ">>>" if j + 1 == i + 1 else "   "
            print(f"  {marker} L{j+1:4d}: {lines[j]}")


def _read_intent_event_adapter() -> None:
    """Read intent_event_adapter.py."""
    _print_section("PROD SOURCE: intent_event_adapter.py")
    iea_path = _BACKEND / "app" / "services" / "events" / "intent_event_adapter.py"
    if not iea_path.exists():
        print(f"  [file not found: {iea_path}]")
        return
    src = _read_file_text(iea_path)
    lines = src.split("\n")
    # Print all lines (it's small)
    for i, line in enumerate(lines[:80], 1):
        print(f"  L{i:4d}: {line}")


def _read_state_applicator_apply_intent() -> None:
    """Read _apply_intent from state_applicator.py."""
    _print_section("PROD SOURCE: state_applicator._apply_intent")
    sa_path = _BACKEND / "app" / "services" / "npc" / "state_applicator.py"
    if not sa_path.exists():
        print(f"  [file not found: {sa_path}]")
        return
    src = _read_file_text(sa_path)
    lines = src.split("\n")
    bounds = _find_function_bounds(src, "_apply_intent")
    if bounds:
        s, e = bounds
        print(f"  _apply_intent at L{s+1}..L{e}:")
        for j in range(s, e):
            print(f"  L{j+1:4d}: {lines[j]}")


# ============================================================================
# MAIN
# ============================================================================
def main() -> int:
    print("=" * 78)
    print("R2-B5-D2 — Trace SPREAD_RUMOR execution on guard_borko")
    print(f"OUT_FILE: {OUT_FILE}")
    print("=" * 78)
    print()
    print("GOAL: Determine if SPREAD_RUMOR selected by DecisionHub (B5-E2)")
    print("      actually reaches tavern_keeper_tornin as a belief.")
    print()
    print("STRATEGY:")
    print("  1. Read production source for execution path (no LLM required for spread_rumor)")
    print("  2. Publish PLAYER_INSULTS")
    print("  3. Run idle_tick multiple times (10) to allow movement progression")
    print("  4. After each tick: snapshot state + check EventBus + check Tornin store")
    print("  5. Final: did the chain complete?")
    print()

    _install_log_capture()

    orig_saves_dir = settings.saves_dir
    orig_env = settings.environment

    temp_dir = Path(tempfile.mkdtemp(prefix="r2_b5_d2_"))

    try:
        from app.services.game_loop_builder import build_game_loop
        from app.services.events.event_bus import get_event_bus
        from app.services.events.event_types import EventType
        from app.domain.events import EventDTO
        from app.services.events.claim_event_subscriber import ClaimEventSubscriber
        from app.services.npc.epistemic_context_resolver import EpistemicContextResolver
        from app.domain.epistemology import Proposition, Predicate  # type: ignore

        # Re-install after potential logging reconfiguration
        _install_log_capture()

        # =====================================================================
        # STEP 1: read production source for execution path
        # =====================================================================
        _print_section("STEP 1: read production source for execution path")
        _read_decision_hub_build_communication()
        _read_dialogue_executor_spread_rumor()
        _read_task_scheduler_fast_path()
        _read_game_loop_fast_path_npc_spoke()
        _read_intent_event_adapter()
        _read_state_applicator_apply_intent()

        # =====================================================================
        # STEP 2: build loop, load NPCs, install EventBus spy
        # =====================================================================
        _print_section("STEP 2: build loop, load NPCs, install EventBus spy")
        settings.saves_dir = str(temp_dir)
        settings.environment = "development"
        loop = build_game_loop(data_dir=Path(settings.data_dir))
        _install_log_capture()  # re-install after build

        scene = loop.scene_manager.get_scene_state("Open_road", "tavern")
        if scene is None:
            scene = loop.scene_manager.initialize_scene("Open_road", "tavern", "12:00")

        loaded = loop._load_npcs_with_runtime("Open_road")
        print(f"  loaded {len(loaded) if hasattr(loaded, '__len__') else '?'} NPCs")

        bus = get_event_bus()
        sub, store = _find_sub_and_store(bus)
        print(f"  sub: {sub}")
        print(f"  store: {store}")

        # Install EventBus spy
        _event_bus_spy.install(bus)
        print(f"  EventBus spy installed")

        # =====================================================================
        # STEP 3: publish PLAYER_INSULTS (B5-D1 chain confirmed)
        # =====================================================================
        _print_section("STEP 3: publish PLAYER_INSULTS")
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
        print(f"  published")

        expected_prop = Proposition(
            subject_id="player",
            predicate=Predicate.INSULTED,
            object_id="tavern_keeper_tornin",
            polarity=True,
        )
        rec_lusya = store.get("maid_lusya", expected_prop)
        rec_borko = store.get("guard_borko", expected_prop)
        rec_tornin_pre = store.get("tavern_keeper_tornin", expected_prop)
        print(f"  maid_lusya belief: confidence={getattr(rec_lusya, 'confidence', None)} source_id={getattr(rec_lusya, 'source_id', None)}")
        print(f"  guard_borko belief: confidence={getattr(rec_borko, 'confidence', None)} source_id={getattr(rec_borko, 'source_id', None)}")
        print(f"  tavern_keeper_tornin belief (pre-tick): {rec_tornin_pre}")

        # Clear log capture + EventBus spy for clean tick measurement
        _reset_log_capture()
        _event_bus_spy.clear()
        _install_log_capture()

        # =====================================================================
        # STEP 4: run multiple idle_ticks, snapshot after each
        # =====================================================================
        _print_section("STEP 4: run multiple idle_ticks, snapshot after each")

        NUM_TICKS = 10
        tick_snapshots: List[Dict[str, Any]] = []

        # Get initial guard_borko state
        borko_state_pre, _ = _find_npc_state(loop, "guard_borko")
        if borko_state_pre:
            print(f"  guard_borko pre-tick:")
            print(f"    intent: {getattr(borko_state_pre, 'intent', None)}")
            print(f"    intent_target: {getattr(borko_state_pre, 'intent_target', None)}")
            print(f"    position: {getattr(borko_state_pre, 'position', None)}")
            print(f"    local_position: {getattr(borko_state_pre, 'local_position', None)}")

        for tick_num in range(1, NUM_TICKS + 1):
            print(f"\n  === TICK {tick_num} ===")
            # Clear log capture for this tick
            _reset_log_capture()
            _event_bus_spy.clear()
            _install_log_capture()

            try:
                result = loop.idle_tick("Open_road", "tavern")
                if isinstance(result, dict):
                    events_count = len(result.get("events", [])) if isinstance(result.get("events"), list) else "N/A"
                    print(f"    idle_tick returned: status={result.get('status')}, events_count={events_count}")
            except Exception as e:
                print(f"    idle_tick ERROR: {type(e).__name__}: {e}")
                traceback.print_exc()

            # Capture logs
            tick_logs = _log_capture.messages()

            # Capture EventBus events
            tick_events = list(_event_bus_spy.published_events)

            # Get guard_borko state
            borko_state, _ = _find_npc_state(loop, "guard_borko")

            # Get Tornin belief
            tornin_rec = store.get("tavern_keeper_tornin", expected_prop) if store else None

            # Get all Tornin records (any predicate)
            tornin_all_records = []
            try:
                if store:
                    tornin_all_records = store.get_all_for_agent("tavern_keeper_tornin") or []
            except Exception as e:
                pass

            snapshot = {
                "tick": tick_num,
                "borko_intent": str(getattr(borko_state, "intent", None)) if borko_state else "N/A",
                "borko_intent_target": str(getattr(borko_state, "intent_target", None)) if borko_state else "N/A",
                "borko_position": str(getattr(borko_state, "position", None)) if borko_state else "N/A",
                "borko_local_position": str(getattr(borko_state, "local_position", None)) if borko_state else "N/A",
                "tornin_belief": str(tornin_rec) if tornin_rec else "None",
                "tornin_belief_confidence": getattr(tornin_rec, "confidence", None),
                "tornin_belief_source_id": getattr(tornin_rec, "source_id", None),
                "tornin_belief_original_source_id": getattr(tornin_rec, "original_source_id", None),
                "tornin_total_records": len(tornin_all_records),
                "event_count": len(tick_events),
                "event_types": list(set(t for t, _ in tick_events)),
                "log_count": len(tick_logs),
            }

            # Capture NPC_SPOKE events
            npc_spoke_events = [e for t, e in tick_events if "npc_spoke" in t.lower() or "NPC_SPOKE" in t]
            snapshot["npc_spoke_count"] = len(npc_spoke_events)
            if npc_spoke_events:
                snapshot["npc_spoke_details"] = []
                for nse in npc_spoke_events[:5]:
                    p = getattr(nse, "payload", {}) or {}
                    snapshot["npc_spoke_details"].append({
                        "source": getattr(nse, "source", "?"),
                        "target_id": p.get("target_id"),
                        "intent_type": p.get("intent_type"),
                        "content": str(p.get("content", ""))[:100],
                        "has_proposition": bool(p.get("proposition")),
                    })

            # Capture SPREAD_RUMOR events (EventType.SPREAD_RUMOR)
            spread_rumor_events = [e for t, e in tick_events if "spread_rumor" in t.lower()]
            snapshot["spread_rumor_event_count"] = len(spread_rumor_events)

            # Capture PROACTIVE_MOVE logs
            proactive_logs = [l for l in tick_logs if "PROACTIVE_MOVE" in l or "proactive" in l.lower()]
            snapshot["proactive_logs_count"] = len(proactive_logs)
            if proactive_logs:
                snapshot["proactive_logs"] = proactive_logs[:5]

            # Capture DECISION_HUB logs for guard_borko
            dh_borko_logs = [l for l in tick_logs if "guard_borko" in l and "DECISION_HUB" in l]
            snapshot["dh_borko_logs_count"] = len(dh_borko_logs)
            if dh_borko_logs:
                snapshot["dh_borko_logs"] = dh_borko_logs[:5]

            # Capture COMMUNICATION build logs
            comm_logs = [l for l in tick_logs if "comm" in l.lower() or "communication" in l.lower()]
            snapshot["comm_logs_count"] = len(comm_logs)
            if comm_logs:
                snapshot["comm_logs"] = comm_logs[:5]

            # Capture executor logs
            exec_logs = [l for l in tick_logs if "executor" in l.lower() or "execute" in l.lower() or "task_scheduler" in l.lower()]
            snapshot["exec_logs_count"] = len(exec_logs)
            if exec_logs:
                snapshot["exec_logs"] = exec_logs[:5]

            tick_snapshots.append(snapshot)

            # Print summary
            print(f"    borko_intent: {snapshot['borko_intent']}")
            print(f"    borko_intent_target: {snapshot['borko_intent_target']}")
            print(f"    borko_position: {snapshot['borko_position']}")
            print(f"    tornin_belief: {snapshot['tornin_belief'][:120]}")
            print(f"    tornin_total_records: {snapshot['tornin_total_records']}")
            print(f"    events: {snapshot['event_count']} types={snapshot['event_types']}")
            print(f"    npc_spoke_count: {snapshot['npc_spoke_count']}")
            print(f"    spread_rumor_event_count: {snapshot['spread_rumor_event_count']}")
            if "npc_spoke_details" in snapshot:
                print(f"    npc_spoke_details: {snapshot['npc_spoke_details']}")
            print(f"    proactive_logs: {snapshot['proactive_logs_count']}")
            if "proactive_logs" in snapshot:
                for pl in snapshot["proactive_logs"]:
                    print(f"      {pl[:200]}")
            if "dh_borko_logs" in snapshot:
                print(f"    dh_borko_logs:")
                for dl in snapshot["dh_borko_logs"]:
                    print(f"      {dl[:200]}")
            if "comm_logs" in snapshot:
                print(f"    comm_logs:")
                for cl in snapshot["comm_logs"]:
                    print(f"      {cl[:200]}")
            if "exec_logs" in snapshot:
                print(f"    exec_logs:")
                for el in snapshot["exec_logs"]:
                    print(f"      {el[:200]}")

            # If Tornin got belief, we can stop
            if tornin_rec is not None:
                print(f"\n    >>> TORNIN GOT BELIEF at tick {tick_num}!")
                break

        # =====================================================================
        # STEP 5: comprehensive final report
        # =====================================================================
        _print_section("STEP 5: comprehensive final report")

        # 5a. CommunicationIntent creation analysis
        print(f"\n  === A. CommunicationIntent creation ===")
        all_logs = []
        for snap in tick_snapshots:
            # Re-derive full logs from saved snapshots
            pass
        # Aggregate all logs from all ticks
        # Note: we already cleared log capture each tick — only saved summaries
        # Aggregate proactive logs across ticks
        all_proactive = []
        for snap in tick_snapshots:
            if "proactive_logs" in snap:
                all_proactive.extend(snap["proactive_logs"])
        print(f"  Total proactive logs across all ticks: {len(all_proactive)}")
        for pl in all_proactive[:10]:
            print(f"    {pl[:200]}")

        # 5b. Execution analysis
        print(f"\n  === B. Execution ===")
        all_exec = []
        for snap in tick_snapshots:
            if "exec_logs" in snap:
                all_exec.extend(snap["exec_logs"])
        print(f"  Total execution-related logs across all ticks: {len(all_exec)}")
        for el in all_exec[:15]:
            print(f"    {el[:200]}")

        # 5c. Publication analysis
        print(f"\n  === C. NPC_SPOKE publication ===")
        total_npc_spoke = sum(snap["npc_spoke_count"] for snap in tick_snapshots)
        total_spread_rumor_events = sum(snap["spread_rumor_event_count"] for snap in tick_snapshots)
        print(f"  Total NPC_SPOKE events across all ticks: {total_npc_spoke}")
        print(f"  Total SPREAD_RUMOR events across all ticks: {total_spread_rumor_events}")
        print(f"\n  NPC_SPOKE details per tick:")
        for snap in tick_snapshots:
            if snap["npc_spoke_count"] > 0:
                print(f"    tick {snap['tick']}: {snap['npc_spoke_count']} NPC_SPOKE events")
                if "npc_spoke_details" in snap:
                    for d in snap["npc_spoke_details"]:
                        print(f"      source={d['source']} target={d['target_id']} intent={d['intent_type']} has_prop={d['has_proposition']}")

        # 5d. Tornin belief reception
        print(f"\n  === D. Tornin belief reception ===")
        for snap in tick_snapshots:
            tornin_str = snap["tornin_belief"]
            if snap["tornin_belief_confidence"] is not None:
                print(f"    tick {snap['tick']}: Tornin belief! confidence={snap['tornin_belief_confidence']} "
                      f"source_id={snap['tornin_belief_source_id']} original={snap['tornin_belief_original_source_id']}")
            else:
                print(f"    tick {snap['tick']}: no belief (total records: {snap['tornin_total_records']})")

        # =====================================================================
        # STEP 6: VERDICT
        # =====================================================================
        _print_section("STEP 6: VERDICT — B5-D2 chain completion")

        # Check chain completion
        chain = {
            "A_intent_selected": any(snap["borko_intent"] and "spread_rumor" in snap["borko_intent"].lower()
                                     for snap in tick_snapshots),
            "B_proactive_move": any(snap["proactive_logs_count"] > 0 for snap in tick_snapshots),
            "C_npc_spoke_published": any(snap["npc_spoke_count"] > 0 for snap in tick_snapshots),
            "D_tornin_belief_created": any(snap["tornin_belief_confidence"] is not None
                                           for snap in tick_snapshots),
        }

        print(f"  Chain stage completion:")
        for stage, completed in chain.items():
            print(f"    {stage}: {'✓' if completed else '✗'}")

        print()
        if chain["D_tornin_belief_created"]:
            # Find first tick where Tornin got belief
            for snap in tick_snapshots:
                if snap["tornin_belief_confidence"] is not None:
                    print(f"  >>> VERDICT: B5-D2 NOT A DEFECT — chain completed at tick {snap['tick']}")
                    print(f"  >>> guard_borko's SPREAD_RUMOR reached tavern_keeper_tornin")
                    print(f"  >>> Tornin's belief:")
                    print(f"      confidence: {snap['tornin_belief_confidence']}")
                    print(f"      source_id: {snap['tornin_belief_source_id']}")
                    print(f"      original_source_id: {snap['tornin_belief_original_source_id']}")
                    provenance_ok = (snap['tornin_belief_source_id'] == 'guard_borko'
                                    and snap['tornin_belief_original_source_id'] == 'player')
                    print(f"  >>> Provenance chain preserved: {provenance_ok}")
                    break
        elif chain["C_npc_spoke_published"]:
            print("  >>> VERDICT: PARTIAL — NPC_SPOKE published but Tornin did not receive belief")
            print("  >>> Investigate why NPC_SPOKE handler did not create belief for Tornin")
        elif chain["B_proactive_move"]:
            print("  >>> VERDICT: PARTIAL — movement started but NPC_SPOKE not published")
            print("  >>> Investigate why movement did not complete or did not trigger NPC_SPOKE")
            # Check if borko reached target
            last_snap = tick_snapshots[-1] if tick_snapshots else {}
            print(f"  >>> Final guard_borko position: {last_snap.get('borko_position', 'N/A')}")
            print(f"  >>> Final guard_borko intent: {last_snap.get('borko_intent', 'N/A')}")
            print(f"  >>> Final guard_borko target: {last_snap.get('borko_intent_target', 'N/A')}")
        elif chain["A_intent_selected"]:
            print("  >>> VERDICT: DEFECT — SPREAD_RUMOR selected but no execution")
            print("  >>> guard_borko chose SPREAD_RUMOR but no movement/execution followed")
        else:
            print("  >>> VERDICT: DEFECT — SPREAD_RUMOR not selected by guard_borko")
            print("  >>> (unexpected — B5-E2 confirmed it was selected)")
            print(f"  >>> Borko intent progression:")
            for snap in tick_snapshots:
                print(f"    tick {snap['tick']}: {snap['borko_intent']}")

        # ---- Cleanup ----
        _event_bus_spy.restore()
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
