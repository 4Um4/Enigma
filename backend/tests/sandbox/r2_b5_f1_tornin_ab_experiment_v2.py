# backend/tests/sandbox/r2_b5_f1_tornin_ab_experiment_v2.py
"""
R2-B5-F1 v2 — A/B experiment with proper EventBus isolation.

v1 failed: Tornin had NO belief at all (source_id=None) in BOTH runs.
Root cause: EventBus is a singleton — subscribers from loop A persisted
into loop B, causing belief to be stored in loop A's store (which was deleted).

v2 fix: Clear EventBus between A and B runs.
  - After loop A is deleted, clear bus._handlers
  - build_game_loop for B re-registers all subscribers on fresh bus
  - Each run gets clean EventBus + fresh store
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
if not OUT_FILE_DIR.exists() or not OUT_FILE_DIR.is_dir():
    OUT_FILE_DIR = _BACKEND / "tests" / "sandbox"
    try:
        OUT_FILE_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        OUT_FILE_DIR = Path(os.getcwd())
OUT_FILE = OUT_FILE_DIR / "r2_b5_f1_tornin_ab_experiment_v2.txt"


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


class _SelectiveEventBusSpy:
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
            if self._block_borko and "communication_claim" in ev_type.lower():
                p = getattr(event, "payload", {}) or {}
                source = getattr(event, "source", "")
                target = p.get("target_id", "")
                if source == "guard_borko" and target == "tavern_keeper_tornin":
                    self.blocked_events.append((ev_type, event))
                    return  # DON'T publish
            self.published_events.append((ev_type, event))
        except: pass
        return self._orig_publish(event)

    def clear(self) -> None:
        self.published_events.clear()
        self.blocked_events.clear()


def _parse_why_decision(msg: str) -> Optional[Dict[str, Any]]:
    if "[WHY][DECISION]" not in msg: return None
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
            import ast; out["comps"] = ast.literal_eval(m.group(1))
        except: out["comps_raw"] = m.group(1)
    return out


def _parse_trace_decision_score(msg: str) -> Optional[Dict[str, Any]]:
    if "[TRACE][DECISION_SCORE]" not in msg: return None
    out: Dict[str, Any] = {}
    m = re.search(r"npc=(\S+?)\s", msg)
    if m: out["npc"] = m.group(1)
    m = re.search(r"winner=(\S+)", msg)
    if m: out["winner"] = m.group(1)
    m = re.search(r"top3=\[(.+)\]", msg)
    if m:
        try:
            import ast; out["top3"] = ast.literal_eval("[" + m.group(1) + "]")
        except: out["top3_raw"] = m.group(1)
    return out


def _collect_npc_decision_data(logs: List[str], npc_id: str) -> Dict[str, Any]:
    data: Dict[str, Any] = {"why_decision": None, "trace_decision_score": None, "dh_main": None}
    for msg in logs:
        if npc_id not in msg: continue
        for parser, key in [(_parse_why_decision, "why_decision"), (_parse_trace_decision_score, "trace_decision_score")]:
            parsed = parser(msg)
            if parsed and parsed.get("npc") == npc_id:
                data[key] = parsed
        if "[DECISION_HUB]" in msg and npc_id in msg and "DECISION_HUB_RETURN" not in msg:
            m = re.search(r"intent=(\S+)", msg)
            if m: data["dh_main"] = m.group(1)
            m = re.search(r"score=([\-\d.]+)", msg)
            if m: data["dh_score"] = float(m.group(1))
    return data


def _clear_event_bus() -> None:
    """Clear EventBus singleton between experiment runs."""
    from app.services.events.event_bus import get_event_bus
    bus = get_event_bus()
    for attr in ("_handlers", "_subscribers", "_callbacks", "_listeners"):
        if hasattr(bus, attr):
            val = getattr(bus, attr)
            if isinstance(val, dict):
                val.clear()
            elif isinstance(val, list):
                val.clear()
    # Also clear any other state
    if hasattr(bus, "_event_queue"):
        bus._event_queue.clear()
    if hasattr(bus, "_pending"):
        bus._pending.clear()


def _run_experiment(
    label: str,
    temp_dir: Path,
    block_borko: bool,
    num_ticks: int = 5,
) -> Dict[str, Any]:
    _print_section(f"EXPERIMENT {label} — {'BLOCK Borko' if block_borko else 'ALLOW Borko'}")

    # CRITICAL: Clear EventBus before each run
    _clear_event_bus()

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
    print(f"  loaded {len(loaded)} NPCs")

    bus = get_event_bus()

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

    resolver = None
    for parent_name in ("_tick_orch", "_svc"):
        parent = getattr(loop, parent_name, None)
        if parent is None: continue
        for attr_name in ("_resolver", "_epistemic_context_resolver"):
            val = getattr(parent, attr_name, None)
            if isinstance(val, EpistemicContextResolver):
                resolver = val; break
        if resolver: break

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

    ctx_pre = resolver.resolve("tavern_keeper_tornin") if resolver else None
    print(f"  Tornin ctx pre-tick: max_conf={getattr(ctx_pre, 'max_confidence', None)} "
          f"report_prop={getattr(ctx_pre, 'report_proposition', None)}")

    # Run ticks
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

        tornin_dh = _collect_npc_decision_data(all_logs, "tavern_keeper_tornin")
        borko_dh = _collect_npc_decision_data(all_logs, "guard_borko")

        npc_spoke_events = [e for t, e in spy.published_events if "npc_spoke" in t.lower()]
        comm_claim_events = [e for t, e in spy.published_events if "communication_claim" in t.lower()]

        ctx_after = resolver.resolve("tavern_keeper_tornin") if resolver else None
        tornin_rec = store.get("tavern_keeper_tornin", expected_prop) if store else None

        tick_info = {
            "tick": tick_num,
            "status": status,
            "tornin_winner": tornin_dh.get("why_decision", {}).get("winner", "N/A") if tornin_dh.get("why_decision") else "N/A",
            "tornin_score": tornin_dh.get("why_decision", {}).get("winner_score", "N/A") if tornin_dh.get("why_decision") else "N/A",
            "tornin_top3": tornin_dh.get("trace_decision_score", {}).get("top3", "N/A") if tornin_dh.get("trace_decision_score") else "N/A",
            "borko_intent": borko_dh.get("dh_main", "N/A"),
            "npc_spoke_count": len(npc_spoke_events),
            "comm_claim_count": len(comm_claim_events),
            "blocked_count": len(spy.blocked_events),
            "tornin_source_id": getattr(tornin_rec, "source_id", None) if tornin_rec else None,
            "tornin_confidence": getattr(tornin_rec, "confidence", None) if tornin_rec else None,
            "tornin_orig": getattr(tornin_rec, "original_source_id", None) if tornin_rec else None,
            "tornin_last_tick": getattr(tornin_rec, "last_updated_tick", None) if tornin_rec else None,
            "tornin_ctx_max_conf": getattr(ctx_after, "max_confidence", None) if ctx_after else None,
            "tornin_ctx_report_prop": str(getattr(ctx_after, "report_proposition", None))[:80] if ctx_after and getattr(ctx_after, "report_proposition", None) else None,
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
        for ev_type, ev in spy.blocked_events[:5]:
            p = getattr(ev, "payload", {}) or {}
            tick_info["blocked_details"].append({
                "source": getattr(ev, "source", "?"),
                "target": p.get("target_id"),
            })

        tick_data.append(tick_info)

        print(f"\n  Tick {tick_num}: status={status}")
        print(f"    Tornin: winner={tick_info['tornin_winner']} score={tick_info['tornin_score']}")
        if tick_info["tornin_top3"] != "N/A":
            print(f"    Tornin top3: {tick_info['tornin_top3']}")
        print(f"    Borko: {tick_info['borko_intent']}")
        print(f"    Events: NPC_SPOKE={tick_info['npc_spoke_count']} COMM_CLAIM={tick_info['comm_claim_count']} Blocked={tick_info['blocked_count']}")
        print(f"    Tornin belief: source={tick_info['tornin_source_id']} conf={tick_info['tornin_confidence']} tick={tick_info['tornin_last_tick']}")
        print(f"    Tornin ctx: max_conf={tick_info['tornin_ctx_max_conf']} report_prop={tick_info['tornin_ctx_report_prop']} claims_self={tick_info['tornin_ctx_claims_self']}")
        for d in tick_info["npc_spoke_details"]:
            print(f"      NPC_SPOKE: {d['source']}→{d['target']} intent={d['intent']} text={d['text'][:80]}")
        for d in tick_info["comm_claim_details"]:
            print(f"      COMM_CLAIM: {d['source']}→{d['target']}")
        for d in tick_info["blocked_details"]:
            print(f"      BLOCKED: {d['source']}→{d['target']}")

    # Final state
    ctx_final = resolver.resolve("tavern_keeper_tornin") if resolver else None
    tornin_final = store.get("tavern_keeper_tornin", expected_prop) if store else None

    result = {
        "label": label,
        "tick_data": tick_data,
        "tornin_pre": {
            "source_id": getattr(tornin_pre, "source_id", None) if tornin_pre else None,
            "confidence": getattr(tornin_pre, "confidence", None) if tornin_pre else None,
            "original_source_id": getattr(tornin_pre, "original_source_id", None) if tornin_pre else None,
        },
        "tornin_final": {
            "source_id": getattr(tornin_final, "source_id", None) if tornin_final else None,
            "confidence": getattr(tornin_final, "confidence", None) if tornin_final else None,
            "original_source_id": getattr(tornin_final, "original_source_id", None) if tornin_final else None,
            "last_updated_tick": getattr(tornin_final, "last_updated_tick", None) if tornin_final else None,
        },
        "ctx_pre": {
            "max_confidence": getattr(ctx_pre, "max_confidence", None) if ctx_pre else None,
            "report_proposition": str(getattr(ctx_pre, "report_proposition", None))[:80] if ctx_pre and getattr(ctx_pre, "report_proposition", None) else None,
        },
        "ctx_final": {
            "max_confidence": getattr(ctx_final, "max_confidence", None) if ctx_final else None,
            "report_proposition": str(getattr(ctx_final, "report_proposition", None))[:80] if ctx_final and getattr(ctx_final, "report_proposition", None) else None,
        },
    }

    spy.restore()
    try:
        ts = loop._get_task_scheduler()
        if hasattr(ts, "_executor_pool"):
            ts._executor_pool.shutdown(wait=False, cancel_futures=True)
    except: pass
    del loop
    import gc; gc.collect()

    return result


def main() -> int:
    print("=" * 78)
    print("R2-B5-F1 v2 — Tornin A/B experiment (EventBus isolation)")
    print(f"OUT_FILE: {OUT_FILE}")
    print("=" * 78)
    print()

    _install_log_capture()
    orig_saves_dir = settings.saves_dir
    orig_env = settings.environment

    temp_a = Path(tempfile.mkdtemp(prefix="r2_b5_f1_A_"))
    temp_b = Path(tempfile.mkdtemp(prefix="r2_b5_f1_B_"))

    data_A: Optional[Dict[str, Any]] = None
    data_B: Optional[Dict[str, Any]] = None

    try:
        data_A = _run_experiment("A (Control)", temp_a, block_borko=True, num_ticks=5)
        data_B = _run_experiment("B (Experiment)", temp_b, block_borko=False, num_ticks=5)

        # =====================================================================
        # COMPARE
        # =====================================================================
        _print_section("A vs B COMPARISON")

        print(f"\n  === Epistemic state ===")
        print(f"  {'Field':<30} {'Control A':<25} {'Experiment B':<25} {'Changed'}")
        fields = [
            ("pre source_id", data_A["tornin_pre"]["source_id"], data_B["tornin_pre"]["source_id"]),
            ("pre confidence", data_A["tornin_pre"]["confidence"], data_B["tornin_pre"]["confidence"]),
            ("final source_id", data_A["tornin_final"]["source_id"], data_B["tornin_final"]["source_id"]),
            ("final orig_source", data_A["tornin_final"]["original_source_id"], data_B["tornin_final"]["original_source_id"]),
            ("final confidence", data_A["tornin_final"]["confidence"], data_B["tornin_final"]["confidence"]),
            ("final last_tick", data_A["tornin_final"]["last_updated_tick"], data_B["tornin_final"]["last_updated_tick"]),
            ("ctx_pre max_conf", data_A["ctx_pre"]["max_confidence"], data_B["ctx_pre"]["max_confidence"]),
            ("ctx_final max_conf", data_A["ctx_final"]["max_confidence"], data_B["ctx_final"]["max_confidence"]),
            ("ctx_pre report_prop", data_A["ctx_pre"]["report_proposition"], data_B["ctx_pre"]["report_proposition"]),
            ("ctx_final report_prop", data_A["ctx_final"]["report_proposition"], data_B["ctx_final"]["report_proposition"]),
        ]
        for name, va, vb in fields:
            changed = "YES" if va != vb else "no"
            print(f"  {name:<30} {str(va):<25} {str(vb):<25} {changed}")

        print(f"\n  === DecisionHub per tick — Tornin ===")
        print(f"  {'Tick':<6} {'A winner':<20} {'A score':<10} {'B winner':<20} {'B score':<10} {'Changed'}")
        for i in range(min(len(data_A["tick_data"]), len(data_B["tick_data"]))):
            ta = data_A["tick_data"][i]
            tb = data_B["tick_data"][i]
            changed = "YES" if ta["tornin_winner"] != tb["tornin_winner"] else "no"
            print(f"  {i+1:<6} {str(ta['tornin_winner']):<20} {str(ta['tornin_score']):<10} "
                  f"{str(tb['tornin_winner']):<20} {str(tb['tornin_score']):<10} {changed}")

        print(f"\n  === NPC_SPOKE per tick ===")
        print(f"  {'Tick':<6} {'A count':<10} {'B count':<10} {'A details':<50} {'B details':<50}")
        for i in range(min(len(data_A["tick_data"]), len(data_B["tick_data"]))):
            ta = data_A["tick_data"][i]
            tb = data_B["tick_data"][i]
            a_det = "; ".join(f"{d['source']}→{d['target']}:{d['intent']}" for d in ta["npc_spoke_details"])
            b_det = "; ".join(f"{d['source']}→{d['target']}:{d['intent']}" for d in tb["npc_spoke_details"])
            print(f"  {i+1:<6} {ta['npc_spoke_count']:<10} {tb['npc_spoke_count']:<10} {a_det[:50]:<50} {b_det[:50]:<50}")

        print(f"\n  === Borko intent per tick ===")
        for i in range(min(len(data_A["tick_data"]), len(data_B["tick_data"]))):
            print(f"  Tick {i+1}: A={data_A['tick_data'][i]['borko_intent']}, B={data_B['tick_data'][i]['borko_intent']}")

        print(f"\n  === Blocked events in A ===")
        total_blocked = sum(ta["blocked_count"] for ta in data_A["tick_data"])
        print(f"  Total blocked: {total_blocked}")
        for ta in data_A["tick_data"]:
            for d in ta["blocked_details"]:
                print(f"    Tick {ta['tick']}: {d['source']}→{d['target']}")

        # =====================================================================
        # CAUSAL ANALYSIS
        # =====================================================================
        _print_section("CAUSAL ANALYSIS")

        conf_a = data_A["tornin_final"]["confidence"]
        conf_b = data_B["tornin_final"]["confidence"]
        source_a = data_A["tornin_final"]["source_id"]
        source_b = data_B["tornin_final"]["source_id"]

        print(f"\n  1. Epistemic state change?")
        print(f"     A: source={source_a}, conf={conf_a}")
        print(f"     B: source={source_b}, conf={conf_b}")
        if source_a != source_b or (conf_a != conf_b and conf_a is not None and conf_b is not None):
            print(f"     >>> YES — Borko's corroboration causally changed Tornin's belief")
        else:
            print(f"     >>> NO — epistemic state same")

        winners_a = [t["tornin_winner"] for t in data_A["tick_data"]]
        winners_b = [t["tornin_winner"] for t in data_B["tick_data"]]
        any_winner_change = any(a != b for a, b in zip(winners_a, winners_b))

        print(f"\n  2. DecisionHub winner change?")
        print(f"     A: {winners_a}")
        print(f"     B: {winners_b}")
        print(f"     {'YES' if any_winner_change else 'NO'}")

        scores_a = [t["tornin_score"] for t in data_A["tick_data"]]
        scores_b = [t["tornin_score"] for t in data_B["tick_data"]]
        any_score_change = any(a != b for a, b in zip(scores_a, scores_b) if a != "N/A" and b != "N/A")

        print(f"\n  3. Scores change?")
        print(f"     A: {scores_a}")
        print(f"     B: {scores_b}")
        print(f"     {'YES' if any_score_change else 'NO'}")

        # VERDICT
        _print_section("VERDICT")

        # Check if Borko transmitted in B
        comm_claim_b = sum(t["comm_claim_count"] for t in data_B["tick_data"])
        borko_sr_b = any("spread_rumor" in str(t["borko_intent"]).lower() for t in data_B["tick_data"])

        if source_a is None and source_b is None:
            print(f"  >>> Tornin has NO belief in either run")
            print(f"  >>> Borko chose SPREAD_RUMOR in B: {borko_sr_b}")
            print(f"  >>> COMMUNICATION_CLAIM in B: {comm_claim_b}")
            if comm_claim_b > 0:
                print(f"  >>> VERDICT: PARTIAL — Borko transmitted, but Tornin's belief wasn't created")
                print(f"  >>> (possible: materializer didn't verify proposition, or on_claim_event failed)")
            else:
                print(f"  >>> VERDICT: INCONCLUSIVE — Borko didn't transmit in this run")
        elif source_a == source_b and conf_a == conf_b:
            print(f"  >>> Epistemic state identical in A and B")
            if comm_claim_b > 0:
                print(f"  >>> VERDICT: PARTIAL — Borko transmitted, but Tornin's behavior didn't change")
                print(f"  >>> (additional corroboration didn't change DecisionHub output)")
            else:
                print(f"  >>> VERDICT: INCONCLUSIVE — Borko didn't transmit")
        elif source_b != source_a or conf_b != conf_a:
            print(f"  >>> Epistemic state DIFFERS between A and B")
            print(f"  >>> Borko's corroboration causally changed Tornin's belief!")
            if any_winner_change:
                print(f"  >>> VERDICT: PASS — full causal chain (belief → decision)")
            elif any_score_change:
                print(f"  >>> VERDICT: PARTIAL — belief changed, scores changed, decision didn't")
            else:
                print(f"  >>> VERDICT: PARTIAL — belief changed, but behavior didn't")

    except Exception as e:
        print(f"[FATAL: {e}]")
        traceback.print_exc()
    finally:
        settings.saves_dir = orig_saves_dir
        settings.environment = orig_env
        for td in (temp_a, temp_b):
            shutil.rmtree(td, ignore_errors=True)

    try:
        OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(OUT_FILE, "w", encoding="utf-8") as f:
            f.write(_stdout_buf.getvalue())
        size = OUT_FILE.stat().st_size
        print(f"\n>>> Output written to: {OUT_FILE}")
        print(f">>> File size: {size} bytes ({size / 1024:.1f} KB)")
    except Exception as e:
        print(f"\n[ERROR: {e}]")
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
