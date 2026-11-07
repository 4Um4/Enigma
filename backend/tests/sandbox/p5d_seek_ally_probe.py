# backend/tests/sandbox/p5d_seek_ally_probe.py
"""
P5-D — SEEK_ALLY EXECUTION FORENSICS.
Цель: доказать, что SEEK_ALLY — исполняемое намерение или только категория решения.
Spies на 10 точках + snapshot позиций maid_lusya / tavern_keeper_tornin до/после.
"""
from __future__ import annotations
import os, sys, json, shutil, tempfile, time, traceback
from pathlib import Path
from typing import Any, Dict, List, Tuple
from unittest.mock import MagicMock

_THIS = Path(__file__).resolve()
_BACKEND = _THIS.parent.parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.core.config import settings, BASE_DIR
from app.services.game_loop_builder import build_game_loop
from app.services.events.event_bus import get_event_bus
from app.services.events.event_types import EventType
from app.domain.events import EventDTO
from app.domain.epistemology import Proposition, Predicate
from app.services.npc.belief_revision_engine import BeliefRevisionEngine
from app.services.npc.decision_hub import DecisionHub
from app.services.phases.post_decision import run_phase_6_post_decision
from app.services.phases.movement_bridge import process_movement_intents

SPY_LOG: List[Dict[str, Any]] = []
NPC_SPOKE_EVENTS: List[Any] = []
MOVEMENT_INTENTS_CAPTURED: List[Dict[str, Any]] = []
SPATIAL_CHANGES_CAPTURED: List[Dict[str, Any]] = []

def _stamp(tag: str, **kw: Any) -> None:
    SPY_LOG.append({"tag": tag, **kw})
    print(f"[SPY] {tag}: " + json.dumps(kw, ensure_ascii=False, default=str))

def _safe_repr(obj, max_len=300):
    try:
        s = repr(obj)
        return s[:max_len] + ("..." if len(s) > max_len else "")
    except Exception as e:
        return f"<repr error: {e}>"

def build_test_loop(data_dir, saves_dir):
    settings.saves_dir = str(saves_dir)
    settings.environment = "development"
    loop = build_game_loop(data_dir=data_dir)
    # Mock LLM router (we investigate SEEK_ALLY movement, not LLM dialogue)
    try:
        ts = loop._get_task_scheduler()
        for kind, ex in (getattr(ts, "_executors", {}) or {}).items():
            if hasattr(ex, "_router"):
                ex._router = MagicMock()
                if hasattr(ex._router, "route"):
                    ex._router.route.return_value = "[Mock LLM]"
    except Exception as e:
        _stamp("HARNESS.mock_llm", error=str(e)[:200])
    return loop

def cleanup_loop(loop):
    try:
        if hasattr(loop, "_task_scheduler"):
            ts = loop._task_scheduler
            if hasattr(ts, "_executor_pool"):
                try: ts._executor_pool.shutdown(wait=False, cancel_futures=True)
                except Exception: pass
    except Exception: pass

def init_scene(loop):
    scene = loop.scene_manager.get_scene_state("Open_road", "tavern")
    if scene is None:
        scene = loop.scene_manager.initialize_scene("Open_road", "tavern", "12:00")
    return scene or {}

# === Snapshot positions ===
def snapshot_positions(loop, npc_ids=("maid_lusya", "tavern_keeper_tornin", "guard_borko")):
    scene = loop.scene_manager.get_scene_state("Open_road", "tavern")
    if scene is None:
        return {"error": "scene None"}
    pos = scene.get("npc_positions", {}) or {}
    result = {}
    for nid in npc_ids:
        e = pos.get(nid, {})
        lp = e.get("local_position", {}) if isinstance(e, dict) else {}
        result[nid] = {
            "position_node": e.get("position") if isinstance(e, dict) else None,
            "x": lp.get("x") if isinstance(lp, dict) else None,
            "y": lp.get("y") if isinstance(lp, dict) else None,
            "activity": e.get("activity") if isinstance(e, dict) else None,
        }
    result["_tick"] = scene.get("tick")
    result["_game_time"] = scene.get("game_time_seconds")
    result["_active_traversals"] = list((scene.get("active_traversals") or {}).keys())
    return result

def snapshot_belief(loop, agent_id):
    orch = getattr(loop, "_tick_orch", None)
    store = getattr(orch, "_epistemic_store", None) if orch else None
    if store is None:
        return {"error": "no store"}
    records = store.get_all_for_agent(agent_id)
    return {
        "agent_id": agent_id,
        "records_count": len(records),
        "records": [{
            "proposition": r.proposition.to_dict(),
            "confidence": r.confidence,
            "source_id": r.source_id,
            "source_type": r.source_type,
        } for r in records]
    }

# === Attach 10 spies ===
def attach_spies(loop):
    refs = {}

    # Spy 1: DecisionHub.compute — capture maid_lusya decision
    orig_compute = DecisionHub.compute
    def _spy_compute(self_dh, *args, **kwargs):
        state_arg = args[0] if args else kwargs.get("state", None)
        npc_id = getattr(state_arg, "npc_id", "?") if state_arg is not None else "?"
        if npc_id == "maid_lusya":
            ep_ctx = kwargs.get("epistemic_context", None)
            _stamp("1.DH.compute:ENTER maid_lusya",
                   has_epistemic_ctx=ep_ctx is not None,
                   claims_self=[p.to_dict() for p in (ep_ctx.claims_about_self or [])] if ep_ctx else [])
        result = orig_compute(self_dh, *args, **kwargs)
        if npc_id == "maid_lusya":
            dec = getattr(result, "decision", None)
            comm = getattr(result, "communication", None)
            dec_summary = {}
            if dec is not None:
                dec_summary = {
                    "intent": str(getattr(dec, "intent", "?")),
                    "intent_target": getattr(dec, "intent_target", None),
                    "score": getattr(dec, "score", None),
                    "scores_trace_top3": sorted(getattr(dec, "scores_trace", {}).items(),
                                                key=lambda x: -x[1])[:3] if hasattr(dec, "scores_trace") else []
                }
            _stamp("1.DH.compute:EXIT maid_lusya",
                   decision=dec_summary,
                   has_communication=comm is not None,
                   communication_intent_type=getattr(comm, "intent_type", None) if comm else None)
        return result
    DecisionHub.compute = _spy_compute

    # Spy 2: post_decision Phase 6
    orig_pd6 = run_phase_6_post_decision
    def _spy_pd6(ctx, orch):
        pre_count = len(getattr(ctx, "communication_intents", []) or [])
        comm_list = [{"speaker": getattr(c, "speaker", "?"),
                      "intent_type": getattr(c, "intent_type", "?"),
                      "target_id": getattr(c, "target_id", None)}
                     for c in (getattr(ctx, "communication_intents", []) or [])]
        _stamp("2.PD6.phase_6:ENTER", pre_communication_intents=pre_count, intents=comm_list)
        result = orig_pd6(ctx, orch)
        pending = ctx.scene_state.get("pending_tasks", []) if hasattr(ctx, "scene_state") else []
        _stamp("2.PD6.phase_6:EXIT",
               post_communication_intents=len(getattr(ctx, "communication_intents", []) or []),
               pending_tasks_count=len(pending))
        return result
    import app.services.phases.post_decision as pd_mod
    pd_mod.run_phase_6_post_decision = _spy_pd6

    # Spy 3 (movement_intent creation): We need to capture the movement_intents list
    # which is built inside npc_tick_pipeline.run() — we'll capture it post-hoc
    # via Phase 5 movement_bridge (Spy 4 wraps process_movement_intents)

    # Spy 4 + 5: process_movement_intents (movement_bridge) — captures movement_intents input
    orig_pmi = process_movement_intents
    def _spy_pmi(movement_intents, ctx, orchestrator):
        intents_summary = []
        for i in (movement_intents or []):
            intents_summary.append({
                "type": type(i).__name__,
                "actor_id": getattr(i, "actor_id", getattr(i, "npc_id", "?")),
                "target_node_id": getattr(i, "target_node_id", None),
                "reason": getattr(i, "reason", None),
                "target_intent": getattr(i, "target_intent", None),
            })
        MOVEMENT_INTENTS_CAPTURED.extend(intents_summary)
        _stamp("3-5.process_movement_intents:ENTER",
               intents_count=len(movement_intents or []),
               intents=intents_summary)
        result = orig_pmi(movement_intents, ctx, orchestrator)
        _stamp("3-5.process_movement_intents:EXIT")
        return result
    import app.services.phases.movement_bridge as mb_mod
    mb_mod.process_movement_intents = _spy_pmi

    # Spy 6: MovementEngine.process_intents — wrap instance-level via patching class method
    from app.services.spatial.movement_engine import MovementEngine
    orig_pi = MovementEngine.process_intents
    def _spy_pi(self_me, intents, **kwargs):
        actors = [getattr(i, "actor_id", getattr(i, "npc_id", "?")) for i in (intents or [])]
        _stamp("6.ME.process_intents:ENTER",
               intents_count=len(intents or []),
               actors=actors,
               has_spatial_service=self_me._spatial_service is not None if hasattr(self_me, "_spatial_service") else "?")
        result = orig_pi(self_me, intents, **kwargs)
        # result = spatial_changes (list of SceneChange)
        changes_summary = []
        for sc in (result or []):
            changes_summary.append({
                "type": type(sc).__name__,
                "target": getattr(sc, "target", getattr(sc, "npc_id", "?")),
                "field": getattr(sc, "field", None),
                "delta": _safe_repr(getattr(sc, "delta", None), 100),
                "value": _safe_repr(getattr(sc, "value", None), 100),
            })
        SPATIAL_CHANGES_CAPTURED.extend(changes_summary)
        _stamp("6.ME.process_intents:EXIT",
               spatial_changes_count=len(result or []),
               changes_preview=changes_summary[:5])
        return result
    MovementEngine.process_intents = _spy_pi

    # Spy 7: NPC interaction system — check if any NPC_CONTACT or similar event
    # (we'll capture via bus.publish below)
    # Spy 8: EventBus.publish — capture all events
    bus = get_event_bus()
    orig_pub = bus.publish
    def _spy_pub(evt):
        et = str(getattr(evt, "type", "?"))
        if "spoke" in et.lower() or "proximity" in et.lower() or "contact" in et.lower() or "interact" in et.lower() or "approach" in et.lower() or "ally" in et.lower() or "social" in et.lower():
            captured = {
                "event_type": et,
                "source": getattr(evt, "source", "?"),
                "target_id": (getattr(evt, "payload", {}) or {}).get("target_id"),
                "intent_type": (getattr(evt, "payload", {}) or {}).get("intent_type"),
                "payload_keys": sorted(list((getattr(evt, "payload", {}) or {}).keys()))
            }
            if "spoke" in et.lower():
                NPC_SPOKE_EVENTS.append(captured)
            _stamp("8.BUS.publish:EVENT", **captured)
        return orig_pub(evt)
    bus.publish = _spy_pub
    refs["bus"] = bus

    # Spy 9: NPC state — we'll snapshot positions before/after (no spy, just measurement)
    # Spy 10: Social state — check relationship_state changes via spy on save_scene_state
    sm = loop.scene_manager
    orig_sss = sm.save_scene_state
    def _spy_sss(campaign_id, scene_state):
        rel_state = scene_state.get("relationship_state", {}) if isinstance(scene_state, dict) else {}
        ml_rels = rel_state.get("maid_lusya", {}) if isinstance(rel_state, dict) else {}
        _stamp("10.SSS.save_scene_state:ENTER",
               campaign=campaign_id,
               relationship_state_maid_lusya_keys=sorted(list(ml_rels.keys())) if isinstance(ml_rels, dict) else [])
        return orig_sss(campaign_id, scene_state)
    sm.save_scene_state = _spy_sss
    return refs

def publish_insult(target_id="maid_lusya"):
    payload = {
        "action_type": "player_insults",
        "target_id": target_id,
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
    _stamp("0.EVENT.publish:PLAYER_INSULTS", event_id=str(evt.id), target_id=target_id)
    get_event_bus().publish(evt)

def run_scenario(label, with_insult, real_data_dir, saves_dir):
    print(f"\n{'#' * 78}\n# SCENARIO {label}: {'WITH' if with_insult else 'NO'} PLAYER_INSULTS\n# saves_dir={saves_dir}\n{'#' * 78}")
    SPY_LOG.clear()
    NPC_SPOKE_EVENTS.clear()
    MOVEMENT_INTENTS_CAPTURED.clear()
    SPATIAL_CHANGES_CAPTURED.clear()
    try: get_event_bus().clear()
    except Exception: pass

    _stamp(f"{label}.STARTUP", saves_dir=str(saves_dir))
    loop = build_test_loop(real_data_dir, saves_dir)
    init_scene(loop)
    attach_spies(loop)
    _stamp(f"{label}.PRE_positions", positions=snapshot_positions(loop))
    _stamp(f"{label}.PRE_belief_maid_lusya", belief=snapshot_belief(loop, "maid_lusya"))
    _stamp(f"{label}.PRE_belief_tornin", belief=snapshot_belief(loop, "tavern_keeper_tornin"))

    if with_insult:
        publish_insult("maid_lusya")
        _stamp(f"{label}.POST_INSULT_belief_maid_lusya", belief=snapshot_belief(loop, "maid_lusya"))

    _stamp(f"{label}.IDLE_TICK_START")
    try:
        result = loop.idle_tick("Open_road")
        _stamp(f"{label}.IDLE_TICK_EXIT",
               status=result.get("status", "?") if isinstance(result, dict) else type(result).__name__)
    except Exception as e:
        _stamp(f"{label}.IDLE_TICK_ERROR", error=type(e).__name__, msg=str(e)[:400])
        traceback.print_exc()
        cleanup_loop(loop)
        return list(SPY_LOG)

    _stamp(f"{label}.POST_positions", positions=snapshot_positions(loop))
    _stamp(f"{label}.POST_belief_maid_lusya", belief=snapshot_belief(loop, "maid_lusya"))
    _stamp(f"{label}.POST_belief_tornin", belief=snapshot_belief(loop, "tavern_keeper_tornin"))
    _stamp(f"{label}.MOVEMENT_INTENTS_CAPTURED", count=len(MOVEMENT_INTENTS_CAPTURED),
           intents=MOVEMENT_INTENTS_CAPTURED)
    _stamp(f"{label}.SPATIAL_CHANGES_CAPTURED", count=len(SPATIAL_CHANGES_CAPTURED),
           changes=SPATIAL_CHANGES_CAPTURED[:10])
    _stamp(f"{label}.NPC_SPOKE_CAPTURED", count=len(NPC_SPOKE_EVENTS), events=NPC_SPOKE_EVENTS)

    # Run 2 more idle_ticks to see if movement continues
    for tick_i in [2, 3]:
        _stamp(f"{label}.IDLE_TICK_{tick_i}_START")
        try:
            loop.idle_tick("Open_road")
            _stamp(f"{label}.POST_TICK_{tick_i}_positions", positions=snapshot_positions(loop))
        except Exception as e:
            _stamp(f"{label}.IDLE_TICK_{tick_i}_ERROR", error=str(e)[:200])

    cleanup_loop(loop)
    del loop
    import gc; gc.collect()
    return list(SPY_LOG)

def main():
    print("\n" + "=" * 78)
    print("P5-D — SEEK_ALLY EXECUTION FORENSICS")
    print("Baseline: 72cf47b0658ffe8cae6351213ddbfb3b48f2e6d2")
    print("=" * 78)

    real_data_dir = Path(settings.data_dir)
    saves_a = Path(tempfile.mkdtemp(prefix="p5d_A_"))
    saves_b = Path(tempfile.mkdtemp(prefix="p5d_B_"))

    try:
        spy_a = run_scenario("A", with_insult=True, real_data_dir=real_data_dir, saves_dir=saves_a)
        spy_b = run_scenario("B", with_insult=False, real_data_dir=real_data_dir, saves_dir=saves_b)

        print("\n" + "=" * 78)
        print("FORENSIC REPORT — P5-D")
        print("=" * 78)
        print("\n--- SCENARIO A (with PLAYER_INSULTS) ---")
        for e in spy_a:
            print(f"  {e}")
        print("\n--- SCENARIO B (control) ---")
        for e in spy_b:
            print(f"  {e}")
        return 0
    except Exception as e:
        print(f"\n[FATAL] {type(e).__name__}: {e}")
        traceback.print_exc()
        return 1
    finally:
        for d in [saves_a, saves_b]:
            try: shutil.rmtree(d, ignore_errors=True)
            except Exception: pass

if __name__ == "__main__":
    sys.exit(main())