# backend/tests/sandbox/r2_b5_e2_1_ab_control_v2.py
"""
R2-B5-E2.1 v2 — Paired A/B control experiment with robust log capture.

v1 failed: captured 0 log entries despite idle_tick running.
Root cause: build_game_loop reconfigures logging and removes root handler.
Fixes:
  1. Re-install log capture AFTER each build_game_loop call
  2. Attach handler to specific loggers (decision_hub, npc_tick_pipeline, etc.)
  3. Force propagate=True on those loggers
  4. Use logging.basicConfig(level=DEBUG) as belt-and-suspenders
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
OUT_FILE = OUT_FILE_DIR / "r2_b5_e2_1_ab_control_v2.txt"


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
# Log capture — robust version that survives build_game_loop reconfiguration
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

# Specific loggers we want to capture from
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
    "app",  # catch-all
    "",    # root
]


def _install_log_capture() -> None:
    """Install log capture on root AND specific loggers."""
    # Reset to clean state
    root = logging.getLogger()
    # Don't clear existing handlers, just add ours (idempotent)
    already_installed = any(isinstance(h, _LogCapture) for h in root.handlers)
    if not already_installed:
        root.addHandler(_log_capture)
    root.setLevel(logging.DEBUG)

    # Also attach to specific loggers and force propagate
    for name in _TARGET_LOGGERS:
        lg = logging.getLogger(name)
        lg.setLevel(logging.DEBUG)
        lg.propagate = True
        # Ensure our handler is on this logger too
        already = any(isinstance(h, _LogCapture) for h in lg.handlers)
        if not already:
            lg.addHandler(_log_capture)


def _reset_log_capture() -> None:
    """Clear captured records (call between A and B runs)."""
    _log_capture.records.clear()


def _reinstall_log_capture() -> None:
    """Re-install after build_game_loop may have reset logging config."""
    _install_log_capture()


# ============================================================================
# Log parsing helpers
# ============================================================================
def _parse_why_decision(msg: str) -> Optional[Dict[str, Any]]:
    if "[WHY][DECISION]" not in msg:
        return None
    out: Dict[str, Any] = {}
    m = re.search(r"npc=(\S+?)\s*\|", msg)
    if m:
        out["npc"] = m.group(1)
    m = re.search(r"winner=(\S+)\s+\(([\-\d.]+)\)", msg)
    if m:
        out["winner"] = m.group(1)
        out["winner_score"] = float(m.group(2))
    m = re.search(r"threat=([\-\d.]+)", msg)
    if m:
        out["threat"] = float(m.group(1))
    m = re.search(r"comps=(\{[^}]+\})", msg)
    if m:
        try:
            import ast
            out["comps"] = ast.literal_eval(m.group(1))
        except Exception:
            out["comps_raw"] = m.group(1)
    m = re.search(r"threshold=([\-\d.]+)", msg)
    if m:
        out["threshold"] = float(m.group(1))
    m = re.search(r"pressure=([\-\d.]+)", msg)
    if m:
        out["pressure"] = float(m.group(1))
    m = re.search(r"accumulated=([\-\d.]+)", msg)
    if m:
        out["accumulated"] = float(m.group(1))
    m = re.search(r"force_switch=(\w+)", msg)
    if m:
        out["force_switch"] = m.group(1) == "True"
    return out


def _parse_trace_decision_score(msg: str) -> Optional[Dict[str, Any]]:
    if "[TRACE][DECISION_SCORE]" not in msg:
        return None
    out: Dict[str, Any] = {}
    m = re.search(r"npc=(\S+?)\s", msg)
    if m:
        out["npc"] = m.group(1)
    m = re.search(r"winner=(\S+)", msg)
    if m:
        out["winner"] = m.group(1)
    m = re.search(r"top3=\[(.+)\]", msg)
    if m:
        try:
            import ast
            out["top3"] = ast.literal_eval("[" + m.group(1) + "]")
        except Exception:
            out["top3_raw"] = m.group(1)
    return out


def _parse_decision_hub_return(msg: str) -> Optional[Dict[str, Any]]:
    if "[DECISION_HUB_RETURN]" not in msg:
        return None
    out: Dict[str, Any] = {}
    m = re.search(r"npc=(\S+)", msg)
    if m:
        out["npc"] = m.group(1)
    m = re.search(r"intent=(\S+)", msg)
    if m:
        out["intent"] = m.group(1)
    m = re.search(r"comm_built=(\w+)", msg)
    if m:
        out["comm_built"] = m.group(1) == "True"
    m = re.search(r"epistemic_context=(\w+)", msg)
    if m:
        out["epistemic_context"] = m.group(1)
    return out


def _parse_decision_hub_main(msg: str) -> Optional[Dict[str, Any]]:
    """[DECISION_HUB] X: intent=Intent.Y score=Z event=EventType.W"""
    if "[DECISION_HUB]" not in msg or "[DECISION_HUB_RETURN]" in msg:
        return None
    out: Dict[str, Any] = {}
    m = re.search(r"\[DECISION_HUB\]\s+(\S+?):", msg)
    if m:
        out["npc"] = m.group(1)
    m = re.search(r"intent=(\S+)", msg)
    if m:
        out["intent"] = m.group(1)
    m = re.search(r"score=([\-\d.]+)", msg)
    if m:
        out["score"] = float(m.group(1))
    return out


def _parse_break_progress(msg: str) -> Optional[Dict[str, Any]]:
    if "[BREAK_PROGRESS]" not in msg:
        return None
    out: Dict[str, Any] = {}
    m = re.search(r"npc=(\S+)", msg)
    if m:
        out["npc"] = m.group(1)
    for field in ("trust_min", "fear_max", "social_pressure"):
        m = re.search(rf"{field}=([\-\d.]+)", msg)
        if m:
            out[field] = float(m.group(1))
    return out


def _parse_emotion_emergent(msg: str) -> Optional[Dict[str, Any]]:
    if "[EMOTION_EMERGENT]" not in msg:
        return None
    out: Dict[str, Any] = {}
    m = re.search(r"npc=(\S+)", msg)
    if m:
        out["npc"] = m.group(1)
    m = re.search(r"emotion=(\S+)", msg)
    if m:
        out["emotion"] = m.group(1)
    m = re.search(r"social_pressure=([\-\d.]+)", msg)
    if m:
        out["social_pressure"] = float(m.group(1))
    return out


def _parse_break(msg: str) -> Optional[Dict[str, Any]]:
    if "[BREAK]" not in msg or "stage=" not in msg:
        return None
    out: Dict[str, Any] = {}
    m = re.search(r"npc=(\S+)", msg)
    if m:
        out["npc"] = m.group(1)
    m = re.search(r"stage=(\S+)", msg)
    if m:
        out["stage"] = m.group(1)
    m = re.search(r"integrity=([\-\d.]+)", msg)
    if m:
        out["integrity"] = float(m.group(1))
    m = re.search(r"integrity_delta=([\-\d.]+)", msg)
    if m:
        out["integrity_delta"] = float(m.group(1))
    m = re.search(r"pressure=([\-\d.]+)", msg)
    if m:
        out["pressure"] = float(m.group(1))
    return out


def _parse_diag_score_all(msg: str) -> Optional[Dict[str, Any]]:
    if "[DIAG_SCORE_ALL]" not in msg:
        return None
    out: Dict[str, Any] = {}
    m = re.search(r"npc=(\S+)", msg)
    if m:
        out["npc"] = m.group(1)
    m = re.search(r"fear_drive=([\-\d.]+)", msg)
    if m:
        out["fear_drive"] = float(m.group(1))
    m = re.search(r"skip_aggro=(\w+)", msg)
    if m:
        out["skip_aggro"] = m.group(1) == "True"
    m = re.search(r"possible=\[([^\]]+)\]", msg)
    if m:
        out["possible"] = [s.strip().strip("'\"") for s in m.group(1).split(",")]
    return out


def _parse_diag_risk_atk(msg: str) -> Optional[Dict[str, Any]]:
    if "[DIAG_RISK_ATK]" not in msg:
        return None
    out: Dict[str, Any] = {}
    m = re.search(r"npc=(\S+)", msg)
    if m:
        out["npc"] = m.group(1)
    m = re.search(r"fear=([\-\d.]+)", msg)
    if m:
        out["fear"] = float(m.group(1))
    m = re.search(r"risk=([\-\d.]+)", msg)
    if m:
        out["risk"] = float(m.group(1))
    m = re.search(r"perceived_threat=([\-\d.]+)", msg)
    if m:
        out["perceived_threat"] = float(m.group(1))
    return out


def _parse_causal_slice_grievance(msg: str) -> Optional[Dict[str, Any]]:
    if "[CAUSAL_SLICE_GRIEVANCE]" not in msg:
        return None
    out: Dict[str, Any] = {}
    m = re.search(r"npc=(\S+)", msg)
    if m:
        out["npc"] = m.group(1)
    m = re.search(r"desired_change=(\S+)", msg)
    if m:
        out["desired_change"] = m.group(1)
    m = re.search(r"methods=(\{[^}]+\})", msg)
    if m:
        try:
            import ast
            out["methods"] = ast.literal_eval(m.group(1))
        except Exception:
            out["methods_raw"] = m.group(1)
    return out


def _parse_epistemic_report_target(msg: str) -> Optional[Dict[str, Any]]:
    if "[EPISTEMIC_REPORT_TARGET]" not in msg:
        return None
    out: Dict[str, Any] = {}
    m = re.search(r"npc=(\S+)", msg)
    if m:
        out["npc"] = m.group(1)
    m = re.search(r"intent=(\S+)", msg)
    if m:
        out["intent"] = m.group(1)
    m = re.search(r"target=(\S+)", msg)
    if m:
        out["target"] = m.group(1)
    m = re.search(r"predicate=(\S+)", msg)
    if m:
        out["predicate"] = m.group(1)
    return out


_PARSERS = [
    (_parse_why_decision, "why_decision"),
    (_parse_trace_decision_score, "trace_decision_score"),
    (_parse_decision_hub_return, "decision_hub_return"),
    (_parse_decision_hub_main, "decision_hub_main"),
    (_parse_break_progress, "break_progress"),
    (_parse_emotion_emergent, "emotion_emergent"),
    (_parse_break, "break_records"),
    (_parse_diag_score_all, "diag_score_all"),
    (_parse_diag_risk_atk, "diag_risk_atk_records"),
    (_parse_causal_slice_grievance, "causal_slice_grievance"),
    (_parse_epistemic_report_target, "epistemic_report_target"),
]


def _collect_npc_data(logs: List[str], target_npc: str = "maid_lusya") -> Dict[str, Any]:
    """Extract all data for target_npc from logs."""
    data: Dict[str, Any] = {
        "why_decision": None,
        "trace_decision_score": None,
        "decision_hub_return": None,
        "decision_hub_main": None,
        "break_progress": None,
        "emotion_emergent": None,
        "break_records": [],
        "diag_score_all": None,
        "diag_risk_atk_records": [],
        "causal_slice_grievance": None,
        "epistemic_report_target": None,
    }
    for msg in logs:
        # Quick filter — must contain target npc name
        if target_npc not in msg:
            continue
        for parser, key in _PARSERS:
            parsed = parser(msg)
            if parsed is None:
                continue
            npc = parsed.get("npc", "")
            if npc != target_npc:
                continue
            if key in ("break_records", "diag_risk_atk_records"):
                data[key].append(parsed)
            else:
                data[key] = parsed
    return data


def _build_fresh_loop(temp_dir: Path):
    """Build a fresh game loop using the given temp dir as saves_dir."""
    from app.services.game_loop_builder import build_game_loop
    settings.saves_dir = str(temp_dir)
    settings.environment = "development"
    loop = build_game_loop(data_dir=Path(settings.data_dir))
    # IMPORTANT: re-install log capture AFTER build_game_loop
    # (build_game_loop may reset logging config)
    _reinstall_log_capture()
    return loop


# ============================================================================
# MAIN
# ============================================================================
def main() -> int:
    print("=" * 78)
    print("R2-B5-E2.1 v2 — Paired A/B control experiment (robust log capture)")
    print(f"OUT_FILE: {OUT_FILE}")
    print("=" * 78)
    print()
    print("DESIGN:")
    print("  Control A:    fresh build, NO PLAYER_INSULTS, run idle_tick")
    print("  Experiment B: fresh build, WITH PLAYER_INSULTS, run idle_tick")
    print("  Compare maid_lusya DecisionHub outputs")
    print()
    print("v2 FIXES from v1:")
    print("  - Re-install log capture AFTER each build_game_loop")
    print("  - Attach handler to specific loggers (not just root)")
    print("  - Force propagate=True")
    print()

    # Pre-install
    _install_log_capture()

    orig_saves_dir = settings.saves_dir
    orig_env = settings.environment

    temp_a = Path(tempfile.mkdtemp(prefix="r2_b5_e2_1_A_"))
    temp_b = Path(tempfile.mkdtemp(prefix="r2_b5_e2_1_B_"))

    data_A: Optional[Dict[str, Any]] = None
    data_B: Optional[Dict[str, Any]] = None
    logs_A: List[str] = []
    logs_B: List[str] = []

    try:
        # =====================================================================
        # RUN A: CONTROL
        # =====================================================================
        _print_section("RUN A — CONTROL (no PLAYER_INSULTS)")
        print(f"  temp dir: {temp_a}")
        _reset_log_capture()

        try:
            from app.services.events.event_bus import get_event_bus
            from app.services.events.claim_event_subscriber import ClaimEventSubscriber
            from app.services.npc.epistemic_context_resolver import EpistemicContextResolver
            from app.domain.epistemology import Proposition, Predicate  # type: ignore

            loop_a = _build_fresh_loop(temp_a)
            scene_a = loop_a.scene_manager.get_scene_state("Open_road", "tavern")
            if scene_a is None:
                scene_a = loop_a.scene_manager.initialize_scene("Open_road", "tavern", "12:00")

            loaded_a = loop_a._load_npcs_with_runtime("Open_road")
            print(f"  A: loaded {len(loaded_a) if hasattr(loaded_a, '__len__') else '?'} NPCs")

            # Verify A pre-tick
            expected_prop = Proposition(
                subject_id="player",
                predicate=Predicate.INSULTED,
                object_id="tavern_keeper_tornin",
                polarity=True,
            )
            bus = get_event_bus()
            sub_a: Optional[ClaimEventSubscriber] = None
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
                            sub_a = target_obj
                            break
                    if sub_a:
                        break
                if sub_a:
                    break
            store_a = getattr(sub_a, "_store", None) if sub_a else None

            if store_a is not None:
                rec_a = store_a.get("maid_lusya", expected_prop)
                print(f"  A: store.get('maid_lusya', expected_prop) = {rec_a}")

            resolver_a: Optional[EpistemicContextResolver] = None
            for parent_name in ("_tick_orch", "_svc"):
                parent = getattr(loop_a, parent_name, None)
                if parent is None:
                    continue
                for attr_name in ("_resolver", "_epistemic_context_resolver"):
                    val = getattr(parent, attr_name, None)
                    if isinstance(val, EpistemicContextResolver):
                        resolver_a = val
                        break
                if resolver_a:
                    break

            if resolver_a is not None:
                ctx_a = resolver_a.resolve("maid_lusya")
                print(f"  A: ctx.report_proposition (pre-tick) = {getattr(ctx_a, 'report_proposition', None)}")
                print(f"  A: ctx.max_confidence (pre-tick) = {getattr(ctx_a, 'max_confidence', None)}")

            # IMPORTANT: re-install before tick (in case anything reset logging)
            _reinstall_log_capture()
            _reset_log_capture()

            print(f"\n  A: calling loop.idle_tick('Open_road', 'tavern') ...")
            try:
                result_a = loop_a.idle_tick("Open_road", "tavern")
                print(f"  A: idle_tick returned type={type(result_a).__name__}")
            except Exception as e:
                print(f"  A: idle_tick ERROR: {type(e).__name__}: {e}")
                traceback.print_exc()

            logs_A = _log_capture.messages()
            print(f"  A: captured {len(logs_A)} log entries")
            # Show first 20 for sanity
            if logs_A:
                print(f"  A: first 10 log entries:")
                for l in logs_A[:10]:
                    print(f"    {l[:200]}")
            else:
                print(f"  A: WARNING — 0 logs captured! Checking logger config...")
                for name in _TARGET_LOGGERS[:5]:
                    lg = logging.getLogger(name)
                    print(f"    logger '{name}' level={lg.level} handlers={[type(h).__name__ for h in lg.handlers]} propagate={lg.propagate}")

            data_A = _collect_npc_data(logs_A, "maid_lusya")
            print(f"  A: parsed maid_lusya data: {[(k, type(v).__name__) for k, v in data_A.items() if v is not None and v != []]}")

            try:
                ts = loop_a._get_task_scheduler()
                if hasattr(ts, "_executor_pool"):
                    ts._executor_pool.shutdown(wait=False, cancel_futures=True)
            except Exception:
                pass
            del loop_a
            import gc
            gc.collect()
        except Exception as e:
            print(f"  A FATAL: {e}")
            traceback.print_exc()

        # =====================================================================
        # RUN B: EXPERIMENT
        # =====================================================================
        _print_section("RUN B — EXPERIMENT (WITH PLAYER_INSULTS)")
        print(f"  temp dir: {temp_b}")
        _reset_log_capture()

        try:
            from app.services.events.event_bus import get_event_bus
            from app.services.events.event_types import EventType
            from app.domain.events import EventDTO
            from app.services.events.claim_event_subscriber import ClaimEventSubscriber
            from app.services.npc.epistemic_context_resolver import EpistemicContextResolver
            from app.domain.epistemology import Proposition, Predicate  # type: ignore

            loop_b = _build_fresh_loop(temp_b)
            scene_b = loop_b.scene_manager.get_scene_state("Open_road", "tavern")
            if scene_b is None:
                scene_b = loop_b.scene_manager.initialize_scene("Open_road", "tavern", "12:00")

            loaded_b = loop_b._load_npcs_with_runtime("Open_road")
            print(f"  B: loaded {len(loaded_b) if hasattr(loaded_b, '__len__') else '?'} NPCs")

            bus = get_event_bus()
            sub_b: Optional[ClaimEventSubscriber] = None
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
                            sub_b = target_obj
                            break
                    if sub_b:
                        break
                if sub_b:
                    break
            store_b = getattr(sub_b, "_store", None) if sub_b else None

            expected_prop = Proposition(
                subject_id="player",
                predicate=Predicate.INSULTED,
                object_id="tavern_keeper_tornin",
                polarity=True,
            )
            if store_b is not None:
                rec_b_pre = store_b.get("maid_lusya", expected_prop)
                print(f"  B (pre-publish): store.get('maid_lusya', expected_prop) = {rec_b_pre}")

            resolver_b: Optional[EpistemicContextResolver] = None
            for parent_name in ("_tick_orch", "_svc"):
                parent = getattr(loop_b, parent_name, None)
                if parent is None:
                    continue
                for attr_name in ("_resolver", "_epistemic_context_resolver"):
                    val = getattr(parent, attr_name, None)
                    if isinstance(val, EpistemicContextResolver):
                        resolver_b = val
                        break
                if resolver_b:
                    break

            if resolver_b is not None:
                ctx_b_pre = resolver_b.resolve("maid_lusya")
                print(f"  B (pre-publish): ctx.report_proposition = {getattr(ctx_b_pre, 'report_proposition', None)}")

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
            print(f"  B: PLAYER_INSULTS published")

            if store_b is not None:
                rec_b_post = store_b.get("maid_lusya", expected_prop)
                print(f"  B (post-publish): store.get('maid_lusya', expected_prop).confidence = {getattr(rec_b_post, 'confidence', None)}")

            if resolver_b is not None:
                ctx_b_post = resolver_b.resolve("maid_lusya")
                print(f"  B (post-publish): ctx.report_proposition = {getattr(ctx_b_post, 'report_proposition', None)}")
                print(f"  B (post-publish): ctx.max_confidence = {getattr(ctx_b_post, 'max_confidence', None)}")

            # Re-install before tick
            _reinstall_log_capture()
            _reset_log_capture()

            print(f"\n  B: calling loop.idle_tick('Open_road', 'tavern') ...")
            try:
                result_b = loop_b.idle_tick("Open_road", "tavern")
                print(f"  B: idle_tick returned type={type(result_b).__name__}")
            except Exception as e:
                print(f"  B: idle_tick ERROR: {type(e).__name__}: {e}")
                traceback.print_exc()

            logs_B = _log_capture.messages()
            print(f"  B: captured {len(logs_B)} log entries")
            if logs_B:
                print(f"  B: first 10 log entries:")
                for l in logs_B[:10]:
                    print(f"    {l[:200]}")
            else:
                print(f"  B: WARNING — 0 logs captured!")

            data_B = _collect_npc_data(logs_B, "maid_lusya")
            print(f"  B: parsed maid_lusya data: {[(k, type(v).__name__) for k, v in data_B.items() if v is not None and v != []]}")

            try:
                ts = loop_b._get_task_scheduler()
                if hasattr(ts, "_executor_pool"):
                    ts._executor_pool.shutdown(wait=False, cancel_futures=True)
            except Exception:
                pass
            del loop_b
            import gc
            gc.collect()
        except Exception as e:
            print(f"  B FATAL: {e}")
            traceback.print_exc()

        # =====================================================================
        # ALSO collect data for ALL NPCs (not just maid_lusya) for completeness
        # =====================================================================
        _print_section("Sanity check: data for ALL NPCs (B only)")
        if logs_B:
            all_npcs_data: Dict[str, Dict[str, Any]] = {}
            for npc_id in ("maid_lusya", "guard_borko", "merchant_goran", "blacksmith_orm", "thief_shadow", "tavern_keeper_tornin"):
                all_npcs_data[npc_id] = _collect_npc_data(logs_B, npc_id)
            for npc_id, d in all_npcs_data.items():
                wd = d.get("why_decision") or {}
                tr = d.get("trace_decision_score") or {}
                dh = d.get("decision_hub_main") or {}
                dhret = d.get("decision_hub_return") or {}
                print(f"  {npc_id}:")
                print(f"    winner: {wd.get('winner', 'N/A')} ({wd.get('winner_score', 'N/A')})")
                print(f"    top3: {tr.get('top3', 'N/A')}")
                print(f"    [DECISION_HUB]: intent={dh.get('intent', 'N/A')} score={dh.get('score', 'N/A')}")
                print(f"    [DECISION_HUB_RETURN]: intent={dhret.get('intent', 'N/A')} comm_built={dhret.get('comm_built', 'N/A')} epistemic_context={dhret.get('epistemic_context', 'N/A')}")

        # =====================================================================
        # COMPARE A vs B
        # =====================================================================
        _print_section("A vs B COMPARISON — maid_lusya")

        if data_A is None or data_B is None:
            print("  [cannot compare — one or both runs failed]")
        else:
            print(f"\n  === DecisionHub winner ===")
            winner_a = data_A.get("why_decision") or {}
            winner_b = data_B.get("why_decision") or {}
            print(f"  A winner: {winner_a.get('winner', 'N/A')} (score={winner_a.get('winner_score', 'N/A')})")
            print(f"  B winner: {winner_b.get('winner', 'N/A')} (score={winner_b.get('winner_score', 'N/A')})")
            print(f"  winner changed: {winner_a.get('winner') != winner_b.get('winner')}")

            print(f"\n  === Top 3 intents (with scores) ===")
            top3_a = (data_A.get("trace_decision_score") or {}).get("top3", [])
            top3_b = (data_B.get("trace_decision_score") or {}).get("top3", [])
            print(f"  A top3: {top3_a}")
            print(f"  B top3: {top3_b}")

            sr_a = next((s for n, s in top3_a if "spread_rumor" in str(n).lower()), None)
            sr_b = next((s for n, s in top3_b if "spread_rumor" in str(n).lower()), None)
            print(f"\n  SPREAD_RUMOR score:")
            print(f"    A: {sr_a if sr_a is not None else 'NOT IN TOP3'}")
            print(f"    B: {sr_b if sr_b is not None else 'NOT IN TOP3'}")
            if sr_a is not None and sr_b is not None:
                delta = sr_b - sr_a
                print(f"    delta: {delta:+.4f}")
            elif sr_a is None and sr_b is not None:
                print(f"    >>> SPREAD_RUMOR entered top3 in B (was absent in A)")
            elif sr_a is not None and sr_b is None:
                print(f"    >>> SPREAD_RUMOR dropped from top3 in B (was present in A)")

            sa_a = next((s for n, s in top3_a if "seek_ally" in str(n).lower()), None)
            sa_b = next((s for n, s in top3_b if "seek_ally" in str(n).lower()), None)
            print(f"\n  SEEK_ALLY score:")
            print(f"    A: {sa_a if sa_a is not None else 'NOT IN TOP3'}")
            print(f"    B: {sa_b if sa_b is not None else 'NOT IN TOP3'}")
            if sa_a is not None and sa_b is not None:
                delta = sa_b - sa_a
                print(f"    delta: {delta:+.4f}")

            print(f"\n  === fear_drive ===")
            dsa = data_A.get("diag_score_all") or {}
            dsb = data_B.get("diag_score_all") or {}
            print(f"  A fear_drive: {dsa.get('fear_drive', 'N/A')}")
            print(f"  B fear_drive: {dsb.get('fear_drive', 'N/A')}")
            fd_a = dsa.get("fear_drive")
            fd_b = dsb.get("fear_drive")
            if fd_a is not None and fd_b is not None:
                print(f"  delta: {fd_b - fd_a:+.4f}")

            print(f"\n  === social_pressure (BREAK_PROGRESS) ===")
            bp_a = data_A.get("break_progress") or {}
            bp_b = data_B.get("break_progress") or {}
            print(f"  A: trust_min={bp_a.get('trust_min', 'N/A')} fear_max={bp_a.get('fear_max', 'N/A')} social_pressure={bp_a.get('social_pressure', 'N/A')}")
            print(f"  B: trust_min={bp_b.get('trust_min', 'N/A')} fear_max={bp_b.get('fear_max', 'N/A')} social_pressure={bp_b.get('social_pressure', 'N/A')}")

            print(f"\n  === emotion_emergent ===")
            ee_a = data_A.get("emotion_emergent") or {}
            ee_b = data_B.get("emotion_emergent") or {}
            print(f"  A: emotion={ee_a.get('emotion', 'N/A')} social_pressure={ee_a.get('social_pressure', 'N/A')}")
            print(f"  B: emotion={ee_b.get('emotion', 'N/A')} social_pressure={ee_b.get('social_pressure', 'N/A')}")

            print(f"\n  === grievance (CAUSAL_SLICE_GRIEVANCE) ===")
            cg_a = data_A.get("causal_slice_grievance") or {}
            cg_b = data_B.get("causal_slice_grievance") or {}
            print(f"  A: desired_change={cg_a.get('desired_change', 'N/A')} methods={cg_a.get('methods', 'N/A')}")
            print(f"  B: desired_change={cg_b.get('desired_change', 'N/A')} methods={cg_b.get('methods', 'N/A')}")

            print(f"\n  === [BREAK] records (resistance progression) ===")
            br_a = data_A.get("break_records", [])
            br_b = data_B.get("break_records", [])
            print(f"  A: {len(br_a)} BREAK records")
            for r in br_a[:3]:
                print(f"    {r}")
            print(f"  B: {len(br_b)} BREAK records")
            for r in br_b[:3]:
                print(f"    {r}")

            print(f"\n  === [DIAG_RISK_ATK] records ===")
            ra_a = data_A.get("diag_risk_atk_records", [])
            ra_b = data_B.get("diag_risk_atk_records", [])
            print(f"  A: {len(ra_a)} records")
            for r in ra_a[:5]:
                print(f"    {r}")
            print(f"  B: {len(ra_b)} records")
            for r in ra_b[:5]:
                print(f"    {r}")

            print(f"\n  === WHY/DECISION components (winner's components) ===")
            comps_a = winner_a.get("comps", {})
            comps_b = winner_b.get("comps", {})
            print(f"  A comps: {comps_a}")
            print(f"  B comps: {comps_b}")
            all_keys = set(comps_a.keys()) | set(comps_b.keys())
            print(f"\n  component delta (B - A):")
            for k in sorted(all_keys):
                va = comps_a.get(k, 0.0)
                vb = comps_b.get(k, 0.0)
                delta = vb - va if isinstance(va, (int, float)) and isinstance(vb, (int, float)) else "?"
                print(f"    {k:20s} A={va:+.4f}  B={vb:+.4f}  delta={delta if isinstance(delta, str) else f'{delta:+.4f}'}")

            print(f"\n  === threshold, pressure, accumulated ===")
            print(f"  A: threshold={winner_a.get('threshold', 'N/A')} pressure={winner_a.get('pressure', 'N/A')} accumulated={winner_a.get('accumulated', 'N/A')}")
            print(f"  B: threshold={winner_b.get('threshold', 'N/A')} pressure={winner_b.get('pressure', 'N/A')} accumulated={winner_b.get('accumulated', 'N/A')}")

            print(f"\n  === [DECISION_HUB_RETURN] ===")
            dh_a = data_A.get("decision_hub_return") or {}
            dh_b = data_B.get("decision_hub_return") or {}
            print(f"  A: intent={dh_a.get('intent', 'N/A')} comm_built={dh_a.get('comm_built', 'N/A')} epistemic_context={dh_a.get('epistemic_context', 'N/A')}")
            print(f"  B: intent={dh_b.get('intent', 'N/A')} comm_built={dh_b.get('comm_built', 'N/A')} epistemic_context={dh_b.get('epistemic_context', 'N/A')}")

            print(f"\n  === [EPISTEMIC_REPORT_TARGET] ===")
            ert_a = data_A.get("epistemic_report_target")
            ert_b = data_B.get("epistemic_report_target")
            print(f"  A: {ert_a}")
            print(f"  B: {ert_b}")

        # =====================================================================
        # VERDICT
        # =====================================================================
        _print_section("VERDICT — B5-E2.1 paired A/B")

        if data_A is None or data_B is None:
            print("  >>> VERDICT: INCONCLUSIVE — one or both runs failed")
        elif not data_A.get("why_decision") or not data_B.get("why_decision"):
            print("  >>> VERDICT: INCONCLUSIVE — DecisionHub log capture failed")
            print("  >>> Check 'first 10 log entries' above to see what was captured")
            print(f"  >>> Total logs A: {len(logs_A)}, B: {len(logs_B)}")
            print(f"  >>> maid_lusya-specific data A: {[(k, type(v).__name__) for k, v in data_A.items() if v is not None and v != []]}")
            print(f"  >>> maid_lusya-specific data B: {[(k, type(v).__name__) for k, v in data_B.items() if v is not None and v != []]}")
        else:
            winner_a = (data_A.get("why_decision") or {}).get("winner", "N/A")
            winner_b = (data_B.get("why_decision") or {}).get("winner", "N/A")
            score_a = (data_A.get("why_decision") or {}).get("winner_score", 0.0)
            score_b = (data_B.get("why_decision") or {}).get("winner_score", 0.0)

            top3_a = (data_A.get("trace_decision_score") or {}).get("top3", [])
            top3_b = (data_B.get("trace_decision_score") or {}).get("top3", [])
            sr_a = next((s for n, s in top3_a if "spread_rumor" in str(n).lower()), None)
            sr_b = next((s for n, s in top3_b if "spread_rumor" in str(n).lower()), None)

            print(f"  A winner: {winner_a} ({score_a})")
            print(f"  B winner: {winner_b} ({score_b})")
            print(f"  A SPREAD_RUMOR score: {sr_a}")
            print(f"  B SPREAD_RUMOR score: {sr_b}")
            print()

            if winner_a == winner_b and sr_a is not None and sr_b is not None and abs(sr_b - sr_a) < 0.01:
                print("  >>> VERDICT: PLAYER_INSULTS had NO measurable causal effect on Lusya's decision")
                print("  >>> A and B chose same intent, scores nearly identical")
                print("  >>> The social event did not causally change Lusya's behavior")
            elif winner_a == "seek_ally" and winner_b == "spread_rumor":
                print("  >>> VERDICT: PLAYER_INSULTS CAUSALLY changed Lusya's behavior")
                print("  >>> A: SEEK_ALLY → B: SPREAD_RUMOR")
                print("  >>> B5-E2 is NOT a defect — information causally drove the SPREAD_RUMOR choice")
            elif winner_a == winner_b and sr_b is not None and sr_a is not None and sr_b > sr_a + 0.05:
                print("  >>> VERDICT: PARTIAL — information influences scoring but insufficient to change decision")
                print(f"  >>> SPREAD_RUMOR score grew by {sr_b - sr_a:+.4f} but {winner_a} still wins")
            elif sr_b is not None and sr_a is not None and sr_b < sr_a:
                print("  >>> VERDICT: ANOMALY — SPREAD_RUMOR score DROPPED in B")
                print(f"  >>> drop of {sr_b - sr_a:+.4f} — investigate negative influence mechanism")
            elif winner_a != winner_b:
                print(f"  >>> VERDICT: WINNER CHANGED ({winner_a} → {winner_b})")
                if winner_b == "spread_rumor":
                    print("  >>> B5-E2 NOT A DEFECT — PLAYER_INSULTS causally drove SPREAD_RUMOR")
                else:
                    print(f"  >>> Investigate: did PLAYER_INSULTS push Lusya to {winner_b} (not SPREAD_RUMOR)?")
            else:
                print(f"  >>> VERDICT: needs manual inspection of comparison above")

    finally:
        settings.saves_dir = orig_saves_dir
        settings.environment = orig_env

        for td in (temp_a, temp_b):
            shutil.rmtree(td, ignore_errors=True)

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
