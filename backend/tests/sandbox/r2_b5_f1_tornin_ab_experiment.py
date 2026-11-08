# backend/tests/sandbox/r2_b5_f1_tornin_ab_experiment.py
"""
R2-B5-F1 — Tornin behavioral response to NPC corroboration.

A/B control experiment:
  Control A: PLAYER_INSULTS published, but Borko's SPREAD_RUMOR BLOCKED
  Experiment B: PLAYER_INSULTS published, Borko's SPREAD_RUMOR ALLOWED

Both run same number of idle_ticks. Compare Tornin's:
  - EpistemicContext (report_proposition, claims_about_self, max_confidence)
  - DecisionHub winner/scores/components
  - NPC_SPOKE publications
  - Actual actions (movement, speech)

How to block Borko in Control A:
  - After PLAYER_INSULTS, spy on DecisionHub.compute
  - When guard_borko selects SPREAD_RUMOR, override to IDLE (or OBSERVE)
  - This prevents CommunicationIntent creation → no NPC_SPOKE → no belief update for Tornin

Actually, simpler approach: prevent COMMUNICATION_CLAIM from reaching Tornin.
  - Spy on EventBus.publish
  - In Control A: intercept COMMUNICATION_CLAIM events where source=guard_borko
    and target=tavern_keeper_tornin, and DON'T publish them
  - This blocks belief update for Tornin without changing DecisionHub

This preserves production code integrity — we only intercept EventBus events.

READ-ONLY on production. Uses EventBus spy to selectively block events.
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
from typing import Any, Dict, List, Optional, Tuple

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
if not OUT_FILE_DIR.exists() or not OUT_file_DIR.is_dir():
    OUT_FILE_DIR = _BACKEND / "tests" / "sandbox"
    try:
        OUT_FILE_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        OUT_FILE_DIR = Path(os.getcwd())
OUT_FILE = OUT_FILE_DIR / "r2_b5_f1_tornin_ab_experiment.txt"


class TeeStream:
    def __init__(self, *streams):
        self.streams = streams

    def write(self, data):
        for s in self.streams:
            try: s.write(data)
            except: pass

    def flush(self):
        for s in self.streams:
            try: s.flush()
            except: pass


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
        try: self.records.append(record)
        except: pass

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
# Selective EventBus spy — can BLOCK specific events
# ============================================================================
class _SelectiveEventBusSpy:
    """EventBus spy that can selectively block COMMUNICATION_CLAIM events."""
    def __init__(self, block_communication_claim_from_borko: bool = False):
        self.published_events: List[Tuple[str, Any]] = []
        self.blocked_events: List[Tuple[str, Any]] = []
        self._block_borko = block_communication_claim_from_borko
        self._installed = False
        self._orig_publish = None
        self._bus = None

    def install(self, bus) -> bool:
        if self._installed: return True
        self._bus = bus
        self._orig_publish = bus.publish
        bus.publish = self._spy_publish
        self._installed = True
        return True

    def restore(self) -> None:
        if self._installed and self._bus and self._orig_publish:
            self._bus.publish = self._orig_publish
            self._installed = False

    def _spy_publish(self, event) -> None:
        try:
            ev_type = str(getattr(event, "type", "?"))
            # Check if this is a COMMUNICATION_CLAIM from guard_borko to tavern_keeper_tornin
            if self._block_borko and "communication_claim" in ev_type.lower():
                p = getattr(event, "payload", {}) or {}
                source = getattr(event, "source", "")
                target = p.get("target_id", "")
                if source == "guard_borko" and target == "tavern_keeper_tornin":
                    self.blocked_events.append((ev_type, event))
                    # DON'T call original publish — block this event
                    return
            self.published_events.append((ev_type, event))
        except: pass
        return self._orig_publish(event)

    def clear(self) -> None:
        self.published_events.clear()
        self.blocked_events.clear()


# ============================================================================
# Parsing helpers
# ============================================================================
def _parse_why_decision(msg: str) -> Optional[Dict[str, Any]]:
    if "[WHY][DECISION]" not in msg:
        return None
    out: Dict[str, Any] = {}
    m = re.search(r"npc=(\S+?)\s*\|", msg)
    if m: out["npc"] = m.group(1)
    m = re.search(r"winner=(\S+)\s+\(([\-\d.]+)\)", msg)
    if m:
        out["winner"] = m.group(1)
        out["winner_score"] = float(m.group(2))
    m = re.search(r"comps=(\{[^}]+\})", msg)
    if m:
        try:
            import ast
            out["comps"] = ast.literal_eval(m.group(1))
        except: out["comps_raw"] = m.group(1)
    return out


def _parse_trace_decision_score(msg: str) -> Optional[Dict[str, Any]]:
    if "[TRACE][DECISION_SCORE]" not in msg:
        return None
    out: Dict[str, Any] = {}
    m = re.search(r"npc=(\S+?)\s", msg)
    if m: out["npc"] = m.group(1)
    m = re.search(r"winner=(\S+)", msg)
    if m: out["winner"] = m.group(1)
    m = re.search(r"top3=\[(.+)\]", msg)
    if m:
        try:
            import ast
            out["top3"] = ast.literal_eval("[" + m.group(1) + "]")
        except: out["top3_raw"] = m.group(1)
    return out


def _collect_npc_decision_data(logs: List[str], npc_id: str) -> Dict[str, Any]:
    """Extract DecisionHub data for a specific NPC."""
    data: Dict[str, Any] = {
        "why_decision": None,
        "trace_decision_score": None,
        "epistemic_report_target": None,
        "dh_main": None,
    }
    for msg in logs:
        if npc_id not in msg:
            continue
        for parser, key in [
            (_parse_why_decision, "why_decision"),
            (_parse_trace_decision_score, "trace_decision_score"),
        ]:
            parsed = parser(msg)
            if parsed and parsed.get("npc") == npc_id:
                data[key] = parsed
        if "EPISTEMIC_REPORT_TARGET" in msg and npc_id in msg:
            m = re.search(r"target=(\S+)", msg)
            if m: data["epistemic_report_target"] = m.group(1)
        if "[DECISION_HUB]" in msg and npc_id in msg and "DECISION_HUB_RETURN" not in msg:
            m = re.search(r"intent=(\S+)", msg)
            if m: data["dh_main"] = m.group(1)
            m = re.search(r"score=([\-\d.]+)", msg)
            if m: data["dh_score"] = float(m.group(1))
    return data


# ============================================================================
# Build game loop with separate temp dir
# ============================================================================
def _build_fresh_loop(temp_dir: Path):
    from app.services.game_loop_builder import build_game_loop
    settings.saves_dir = str(temp_dir)
    settings.environment = "development"
    loop = build_game_loop(data_dir=Path(settings.data_dir))
    _install_log_capture()
    return loop


# ============================================================================
# Run one experiment (Control or Experiment)
# ============================================================================
def _run_experiment(
    label: str,
    temp_dir: Path,
    block_borko: bool,
    num_ticks: int = 5,
) -> Dict[str, Any]:
    """Run one A/B experiment and return all captured data."""
    _print_section(f"EXPERIMENT {label} — {'BLOCK Borko transmission' if block_borko else 'ALLOW Borko transmission'}")

    from app.services.events.event_bus import get_event_bus
    from app.services.events.event_types import EventType
    from app.domain.events import EventDTO
    from app.services.events.claim_event_subscriber import ClaimEventSubscriber
    from app.services.npc.epistemic_context_resolver import EpistemicContextResolver
    from app.domain.epistemology import Proposition, Predicate  # type: ignore

    loop = _build_fresh_loop(temp_dir)

    scene = loop.scene_manager.get_scene_state("Open_road", "tavern")
    if scene is None:
        scene = loop.scene_manager.initialize_scene("Open_road", "tavern", "12:00")
    loaded = loop._load_npcs_with_runtime("Open_road")
    print(f"  loaded {len(loaded)} NPCs")

    bus = get_event_bus()
    # Reset event bus for fresh experiment
    try:
        bus._handlers = {}
        bus._subscribers = {}
    except: pass

    # Re-register subscribers by rebuilding loop
    # Actually, build_game_loop already registers subscribers
    # But we need a fresh bus — let's just use the existing one

    sub = None
    for attr in ("_subscribers", "_handlers", "_callbacks"):
        if not hasattr(bus, attr): continue
        container = getattr(bus, attr)
        if not isinstance(container, dict): continue
        for ev_type, cbs in container.items():
            if cbs is None: continue
            try: iter_cbs = list(cbs)
            except TypeError: iter_cbs = [cbs]
            for cb in iter_cbs:
                target_obj = getattr(cb, "__self__", None)
                if target_obj and isinstance(target_obj, ClaimEventSubscriber):
                    sub = target_obj; break
                if sub: break
            if sub: break
        if sub: break
    store = getattr(sub, "_store", None) if sub else None

    # Find resolver
    resolver = None
    for parent_name in ("_tick_orch", "_svc"):
        parent = getattr(loop, parent_name, None)
        if parent is None: continue
        for attr_name in ("_resolver", "_epistemic_context_resolver"):
            val = getattr(parent, attr_name, None)
            if isinstance(val, EpistemicContextResolver):
                resolver = val; break
        if resolver: break

    # Install selective EventBus spy
    spy = _SelectiveEventBusSpy(block_communication_claim_from_borko=block_borko)
    spy.install(bus)

    expected_prop = Proposition(
        subject_id="player",
        predicate=Predicate.INSULTED,
        object_id="tavern_keeper_tornin",
        polarity=True,
    )

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

    # Verify Tornin has initial belief
    tornin_pre = store.get("tavern_keeper_tornin", expected_prop) if store else None
    print(f"  Tornin initial belief: source_id={getattr(tornin_pre, 'source_id', None)} "
          f"conf={getattr(tornin_pre, 'confidence', None)} "
          f"orig={getattr(tornin_pre, 'original_source_id', None)}")

    # Capture Tornin's EpistemicContext BEFORE ticks
    ctx_pre = resolver.resolve("tavern_keeper_tornin") if resolver else None
    print(f"  Tornin EpistemicContext (pre-tick):")
    if ctx_pre:
        print(f"    max_confidence: {getattr(ctx_pre, 'max_confidence', None)}")
        print(f"    report_proposition: {getattr(ctx_pre, 'report_proposition', None)}")
        print(f"    claims_about_self: {len(getattr(ctx_pre, 'claims_about_self', ()) or [])}")
        print(f"    trigger_proposition: {getattr(ctx_pre, 'trigger_proposition', None)}")

    # Run ticks and capture per-tick data
    tick_data: List[Dict[str, Any]] = []

    for tick_num in range(1, num_ticks + 1):
        spy.clear()
        _reset_log_capture()

        try:
            result = loop.idle_tick("Open_road", "tavern")
            status = result.get("status") if isinstance(result, dict) else "N/A"
        except Exception as e:
            status = f"ERROR: {e}"

        all_logs = _log_capture.messages()

        # Tornin's DecisionHub data for this tick
        tornin_dh = _collect_npc_decision_data(all_logs, "tavern_keeper_tornin")

        # Borko's DecisionHub data (to track SPREAD_RUMOR selection)
        borko_dh = _collect_npc_decision_data(all_logs, "guard_borko")

        # Events
        npc_spoke_events = [e for t, e in spy.published_events if "npc_spoke" in t.lower()]
        comm_claim_events = [e for t, e in spy.published_events if "communication_claim" in t.lower()]
        blocked_events = list(spy.blocked_events)

        # Tornin's EpistemicContext after this tick
        ctx_after = resolver.resolve("tavern_keeper_tornin") if resolver else None

        # Tornin's belief record after this tick
        tornin_rec = store.get("tavern_keeper_tornin", expected_prop) if store else None

        tick_info = {
            "tick": tick_num,
            "status": status,
            "tornin_dh": tornin_dh,
            "borko_dh": borko_dh,
            "npc_spoke_count": len(npc_spoke_events),
            "comm_claim_count": len(comm_claim_events),
            "blocked_count": len(blocked_events),
            "tornin_source_id": getattr(tornin_rec, "source_id", None) if tornin_rec else None,
            "tornin_orig_source": getattr(tornin_rec, "original_source_id", None) if tornin_rec else None,
            "tornin_confidence": getattr(tornin_rec, "confidence", None) if tornin_rec else None,
            "tornin_last_tick": getattr(tornin_rec, "last_updated_tick", None) if tornin_rec else None,
            "tornin_ctx_max_conf": getattr(ctx_after, "max_confidence", None) if ctx_after else None,
            "tornin_ctx_report_prop": str(getattr(ctx_after, "report_proposition", None))[:100] if ctx_after else None,
            "tornin_ctx_claims_self": len(getattr(ctx_after, "claims_about_self", ()) or []) if ctx_after else 0,
            "npc_spoke_details": [],
            "comm_claim_details": [],
            "blocked_details": [],
        }

        for ev in npc_spoke_events[:5]:
            p = getattr(ev, "payload", {}) or {}
            tick_info["npc_spoke_details"].append({
                "source": getattr(ev, "source", "?"),
                "target": p.get("target_id"),
                "intent": p.get("intent_type"),
                "text": str(p.get("text", ""))[:100],
            })

        for ev in comm_claim_events[:5]:
            p = getattr(ev, "payload", {}) or {}
            tick_info["comm_claim_details"].append({
                "source": getattr(ev, "source", "?"),
                "target": p.get("target_id"),
            })

        for ev_type, ev in blocked_events[:5]:
            p = getattr(ev, "payload", {}) or {}
            tick_info["blocked_details"].append({
                "type": ev_type,
                "source": getattr(ev, "source", "?"),
                "target": p.get("target_id"),
            })

        tick_data.append(tick_info)

        # Print summary
        print(f"\n  Tick {tick_num}: status={status}")
        print(f"    Tornin DH: winner={tornin_dh.get('why_decision', {}).get('winner', 'N/A')} "
              f"score={tornin_dh.get('why_decision', {}).get('winner_score', 'N/A')}")
        if tornin_dh.get('trace_decision_score'):
            print(f"    Tornin top3: {tornin_dh['trace_decision_score'].get('top3', 'N/A')}")
        print(f"    Borko DH: winner={borko_dh.get('dh_main', 'N/A')}")
        print(f"    NPC_SPOKE: {len(npc_spoke_events)}, COMM_CLAIM: {len(comm_claim_events)}, Blocked: {len(blocked_events)}")
        print(f"    Tornin belief: source={tick_info['tornin_source_id']} "
              f"conf={tick_info['tornin_confidence']} tick={tick_info['tornin_last_tick']}")
        print(f"    Tornin ctx: max_conf={tick_info['tornin_ctx_max_conf']} "
              f"report_prop={tick_info['tornin_ctx_report_prop']} "
              f"claims_self={tick_info['tornin_ctx_claims_self']}")
        for d in tick_info["npc_spoke_details"]:
            print(f"      NPC_SPOKE: {d['source']}→{d['target']} intent={d['intent']} text={d['text'][:80]}")
        for d in tick_info["blocked_details"]:
            print(f"      BLOCKED: {d['source']}→{d['target']}")

    # Final EpistemicContext
    ctx_final = resolver.resolve("tavern_keeper_tornin") if resolver else None
    tornin_final = store.get("tavern_keeper_tornin", expected_prop) if store else None

    result = {
        "label": label,
        "block_borko": block_borko,
        "tick_data": tick_data,
        "tornin_pre_tick": {
            "source_id": getattr(tornin_pre, "source_id", None) if tornin_pre else None,
            "original_source_id": getattr(tornin_pre, "original_source_id", None) if tornin_pre else None,
            "confidence": getattr(tornin_pre, "confidence", None) if tornin_pre else None,
        },
        "tornin_final": {
            "source_id": getattr(tornin_final, "source_id", None) if tornin_final else None,
            "original_source_id": getattr(tornin_final, "original_source_id", None) if tornin_final else None,
            "confidence": getattr(tornin_final, "confidence", None) if tornin_final else None,
            "last_updated_tick": getattr(tornin_final, "last_updated_tick", None) if tornin_final else None,
        },
        "tornin_ctx_pre": {
            "max_confidence": getattr(ctx_pre, "max_confidence", None) if ctx_pre else None,
            "report_proposition": str(getattr(ctx_pre, "report_proposition", None))[:100] if ctx_pre else None,
        },
        "tornin_ctx_final": {
            "max_confidence": getattr(ctx_final, "max_confidence", None) if ctx_final else None,
            "report_proposition": str(getattr(ctx_final, "report_proposition", None))[:100] if ctx_final else None,
        },
    }

    # Cleanup
    spy.restore()
    try:
        ts = loop._get_task_scheduler()
        if hasattr(ts, "_executor_pool"):
            ts._executor_pool.shutdown(wait=False, cancel_futures=True)
    except: pass
    del loop
    import gc; gc.collect()

    return result


# ============================================================================
# MAIN
# ============================================================================
def main() -> int:
    print("=" * 78)
    print("R2-B5-F1 — Tornin behavioral response to NPC corroboration (A/B)")
    print(f"OUT_FILE: {OUT_FILE}")
    print("=" * 78)
    print()
    print("Control A: PLAYER_INSULTS + BLOCK Borko's COMMUNICATION_CLAIM")
    print("Experiment B: PLAYER_INSULTS + ALLOW Borko's COMMUNICATION_CLAIM")
    print()

    _install_log_capture()

    orig_saves_dir = settings.saves_dir
    orig_env = settings.environment

    temp_a = Path(tempfile.mkdtemp(prefix="r2_b5_f1_A_"))
    temp_b = Path(tempfile.mkdtemp(prefix="r2_b5_f1_B_"))

    data_A: Optional[Dict[str, Any]] = None
    data_B: Optional[Dict[str, Any]] = None

    try:
        # =====================================================================
        # RUN A — Control (block Borko's transmission)
        # =====================================================================
        data_A = _run_experiment("A (Control)", temp_a, block_borko=True, num_ticks=5)

        # =====================================================================
        # RUN B — Experiment (allow Borko's transmission)
        # =====================================================================
        data_B = _run_experiment("B (Experiment)", temp_b, block_borko=False, num_ticks=5)

        # =====================================================================
        # COMPARE A vs B
        # =====================================================================
        _print_section("A vs B COMPARISON")

        # Epistemic state comparison
        print(f"\n  === Epistemic state ===")
        print(f"  {'Field':<30} {'Control A':<25} {'Experiment B':<25} {'Changed':<10}")
        fields = [
            ("tornin_pre source_id", data_A["tornin_pre_tick"]["source_id"], data_B["tornin_pre_tick"]["source_id"]),
            ("tornin_pre confidence", data_A["tornin_pre_tick"]["confidence"], data_B["tornin_pre_tick"]["confidence"]),
            ("tornin_final source_id", data_A["tornin_final"]["source_id"], data_B["tornin_final"]["source_id"]),
            ("tornin_final orig_source", data_A["tornin_final"]["original_source_id"], data_B["tornin_final"]["original_source_id"]),
            ("tornin_final confidence", data_A["tornin_final"]["confidence"], data_B["tornin_final"]["confidence"]),
            ("tornin_final last_tick", data_A["tornin_final"]["last_updated_tick"], data_B["tornin_final"]["last_updated_tick"]),
            ("ctx_pre max_confidence", data_A["tornin_ctx_pre"]["max_confidence"], data_B["tornin_ctx_pre"]["max_confidence"]),
            ("ctx_final max_confidence", data_A["tornin_ctx_final"]["max_confidence"], data_B["tornin_ctx_final"]["max_confidence"]),
        ]
        for name, val_a, val_b in fields:
            changed = "YES" if val_a != val_b else "no"
            print(f"  {name:<30} {str(val_a):<25} {str(val_b):<25} {changed:<10}")

        # DecisionHub comparison per tick
        print(f"\n  === DecisionHub per tick — Tornin ===")
        print(f"  {'Tick':<6} {'A winner':<20} {'A score':<10} {'B winner':<20} {'B score':<10} {'Changed':<10}")
        for i in range(min(len(data_A["tick_data"]), len(data_B["tick_data"]))):
            ta = data_A["tick_data"][i]
            tb = data_B["tick_data"][i]
            a_w = ta["tornin_dh"].get("why_decision", {}).get("winner", "N/A") if ta["tornin_dh"] else "N/A"
            a_s = ta["tornin_dh"].get("why_decision", {}).get("winner_score", "N/A") if ta["tornin_dh"] else "N/A"
            b_w = tb["tornin_dh"].get("why_decision", {}).get("winner", "N/A") if tb["tornin_dh"] else "N/A"
            b_s = tb["tornin_dh"].get("why_decision", {}).get("winner_score", "N/A") if tb["tornin_dh"] else "N/A"
            changed = "YES" if a_w != b_w else "no"
            print(f"  {i+1:<6} {str(a_w):<20} {str(a_s):<10} {str(b_w):<20} {str(b_s):<10} {changed:<10}")

        # NPC_SPOKE comparison
        print(f"\n  === NPC_SPOKE events per tick ===")
        print(f"  {'Tick':<6} {'A count':<10} {'B count':<10} {'A details':<40} {'B details':<40}")
        for i in range(min(len(data_A["tick_data"]), len(data_B["tick_data"]))):
            ta = data_A["tick_data"][i]
            tb = data_B["tick_data"][i]
            a_details = "; ".join(f"{d['source']}→{d['target']}:{d['intent']}" for d in ta["npc_spoke_details"])
            b_details = "; ".join(f"{d['source']}→{d['target']}:{d['intent']}" for d in tb["npc_spoke_details"])
            print(f"  {i+1:<6} {ta['npc_spoke_count']:<10} {tb['npc_spoke_count']:<10} {a_details[:40]:<40} {b_details[:40]:<40}")

        # Borko's SPREAD_RUMOR selection
        print(f"\n  === Borko SPREAD_RUMOR selection per tick ===")
        for i in range(min(len(data_A["tick_data"]), len(data_B["tick_data"]))):
            ta = data_A["tick_data"][i]
            tb = data_B["tick_data"][i]
            a_borko = ta["borko_dh"].get("dh_main", "N/A") if ta["borko_dh"] else "N/A"
            b_borko = tb["borko_dh"].get("dh_main", "N/A") if tb["borko_dh"] else "N/A"
            print(f"  Tick {i+1}: A={a_borko}, B={b_borko}")

        # Blocked events in Control A
        print(f"\n  === Blocked events in Control A ===")
        total_blocked = sum(ta["blocked_count"] for ta in data_A["tick_data"])
        print(f"  Total blocked: {total_blocked}")
        for ta in data_A["tick_data"]:
            for d in ta["blocked_details"]:
                print(f"    Tick {ta['tick']}: {d['source']}→{d['target']}")

        # =====================================================================
        # CAUSAL ANALYSIS
        # =====================================================================
        _print_section("CAUSAL ANALYSIS")

        # Check: did Tornin's epistemic state change differently?
        conf_a = data_A["tornin_final"]["confidence"]
        conf_b = data_B["tornin_final"]["confidence"]
        source_a = data_A["tornin_final"]["source_id"]
        source_b = data_B["tornin_final"]["source_id"]

        print(f"\n  1. Did epistemic state change?")
        print(f"     Control A: source_id={source_a}, confidence={conf_a}")
        print(f"     Experiment B: source_id={source_b}, confidence={conf_b}")
        if source_a != source_b or conf_a != conf_b:
            print(f"     >>> YES — epistemic state differs between A and B")
            print(f"     >>> Borko's transmission causally changed Tornin's belief")
        else:
            print(f"     >>> NO — epistemic state is the same (Borko may not have transmitted)")

        # Check: did DecisionHub winner change?
        winners_a = [t["tornin_dh"].get("why_decision", {}).get("winner", "N/A")
                     if t["tornin_dh"] else "N/A" for t in data_A["tick_data"]]
        winners_b = [t["tornin_dh"].get("why_decision", {}).get("winner", "N/A")
                     if t["tornin_dh"] else "N/A" for t in data_B["tick_data"]]
        any_winner_change = any(a != b for a, b in zip(winners_a, winners_b))

        print(f"\n  2. Did DecisionHub winner change?")
        print(f"     A winners: {winners_a}")
        print(f"     B winners: {winners_b}")
        if any_winner_change:
            print(f"     >>> YES — Tornin's decisions differ between A and B")
            # Find which tick changed
            for i, (a, b) in enumerate(zip(winners_a, winners_b)):
                if a != b:
                    print(f"     >>> Tick {i+1}: A={a} → B={b}")
        else:
            print(f"     >>> NO — Tornin chose the same intent in all ticks")

        # Check: did scores change?
        scores_a = [t["tornin_dh"].get("why_decision", {}).get("winner_score", 0)
                    if t["tornin_dh"] else 0 for t in data_A["tick_data"]]
        scores_b = [t["tornin_dh"].get("why_decision", {}).get("winner_score", 0)
                    if t["tornin_dh"] else 0 for t in data_B["tick_data"]]
        any_score_change = any(abs(a - b) > 0.01 for a, b in zip(scores_a, scores_b) if isinstance(a, (int, float)) and isinstance(b, (int, float)))

        print(f"\n  3. Did scores change?")
        print(f"     A scores: {scores_a}")
        print(f"     B scores: {scores_b}")
        if any_score_change:
            print(f"     >>> YES — scoring changed (even if winner didn't)")
        else:
            print(f"     >>> NO — scores are the same")

        # Check: did NPC_SPOKE from Tornin change?
        tornin_speech_a = sum(1 for t in data_A["tick_data"]
                              for d in t["npc_spoke_details"] if d["source"] == "tavern_keeper_tornin")
        tornin_speech_b = sum(1 for t in data_B["tick_data"]
                              for d in t["npc_spoke_details"] if d["source"] == "tavern_keeper_tornin")
        print(f"\n  4. Did Tornin's speech change?")
        print(f"     A: {tornin_speech_a} NPC_SPOKE from Tornin")
        print(f"     B: {tornin_speech_b} NPC_SPOKE from Tornin")

        # =====================================================================
        # VERDICT
        # =====================================================================
        _print_section("VERDICT")

        if source_a != source_b and conf_b > conf_a:
            print(f"  >>> Epistemic state causally changed by Borko's corroboration")
            print(f"  >>> source_id: {source_a} → {source_b}")
            print(f"  >>> confidence: {conf_a} → {conf_b}")
            if any_winner_change:
                print(f"  >>> DecisionHub winner ALSO changed — full causal chain")
                print(f"  >>> VERDICT: PASS — Borko's testimony causally influenced Tornin's behavior")
            elif any_score_change:
                print(f"  >>> DecisionHub winner same, but scores changed")
                print(f"  >>> VERDICT: PARTIAL — epistemic state changed, scores changed, but decision didn't")
            else:
                print(f"  >>> DecisionHub winner and scores same")
                print(f"  >>> VERDICT: PARTIAL — epistemic state changed, but behavior didn't")
        elif source_a == source_b:
            # Check if Borko actually transmitted in B
            borko_sr_in_b = any(t["borko_dh"].get("dh_main", "").lower() == "spread_rumor"
                               for t in data_B["tick_data"] if t["borko_dh"])
            comm_claim_in_b = sum(t["comm_claim_count"] for t in data_B["tick_data"])
            print(f"  >>> Epistemic state same in A and B")
            print(f"  >>> Borko chose SPREAD_RUMOR in B: {borko_sr_in_b}")
            print(f"  >>> COMMUNICATION_CLAIM events in B: {comm_claim_in_b}")
            if comm_claim_in_b == 0:
                print(f"  >>> VERDICT: INCONCLUSIVE — Borko didn't transmit in this run")
                print(f"  >>> (game state variability — Borko may not have reached Tornin)")
            else:
                print(f"  >>> VERDICT: PARTIAL — Borko transmitted, but Tornin's epistemic state didn't change")
                print(f"  >>> (possibly Tornin already had belief from PLAYER_INSULTS, and revise didn't update)")
        else:
            print(f"  >>> VERDICT: needs manual inspection")

    except Exception as e:
        print(f"[FATAL: {e}]")
        traceback.print_exc()
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
    try: rc = main()
    except Exception as e:
        print(f"\n[FATAL] {type(e).__name__}: {e}")
        traceback.print_exc()
        rc = 1
    finally: sys.stdout = _orig_stdout
    sys.exit(rc)
