# backend/tests/sandbox/p5g_flee_positive_control.py
"""
P5-G Уточнение D — FLEE Positive Control.
Цель: доказать, что FLEE без active traversal создаёт физическое движение.
Стратегия: 10 idle_ticks, spy на каждый тик, искать natural occurrence.
"""
from __future__ import annotations
import os, sys, json, shutil, tempfile, traceback
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
from app.services.npc.decision_hub import DecisionHub
from app.services.phases.movement_bridge import process_movement_intents
from app.services.spatial.movement_engine import MovementEngine
from app.services.action.commitment_arbiter import CommitmentArbiter

SPY_LOG: List[Dict[str, Any]] = []

def _stamp(tag: str, **kw: Any) -> None:
    SPY_LOG.append({"tag": tag, **kw})
    print(f"[SPY] {tag}: " + json.dumps(kw, ensure_ascii=False, default=str))

def build_test_loop(data_dir, saves_dir):
    settings.saves_dir = str(saves_dir)
    settings.environment = "development"
    loop = build_game_loop(data_dir=data_dir)
    try:
        ts = loop._get_task_scheduler()
        for kind, ex in (getattr(ts, "_executors", {}) or {}).items():
            if hasattr(ex, "_router"):
                ex._router = MagicMock()
                if hasattr(ex._router, "route"):
                    ex._router.route.return_value = "[Mock LLM]"
    except Exception: pass
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

def attach_spies():
    orig_compute = DecisionHub.compute
    def _spy_compute(self_dh, *args, **kwargs):
        state_arg = args[0] if args else kwargs.get("state", None)
        npc_id = getattr(state_arg, "npc_id", "?") if state_arg is not None else "?"
        result = orig_compute(self_dh, *args, **kwargs)
        if npc_id == "maid_lusya":
            dec = getattr(result, "decision", None)
            if dec is not None:
                _stamp("DH.compute:EXIT maid_lusya",
                       intent=str(getattr(dec, "intent", "?")),
                       target=getattr(dec, "intent_target", None),
                       score=getattr(dec, "score", None))
        return result
    DecisionHub.compute = _spy_compute

    orig_pmi = process_movement_intents
    def _spy_pmi(movement_intents, ctx, orchestrator):
        ml_intents = []
        for i in (movement_intents or []):
            actor = getattr(i, "actor_id", getattr(i, "npc_id", "?"))
            if actor == "maid_lusya":
                ml_intents.append({"reason": getattr(i, "reason", "?"), "target": getattr(i, "target_node_id", "?")})
        scene_state = getattr(ctx, "scene_state", None)
        ml_trav = {}
        if scene_state and isinstance(scene_state, dict):
            _at = scene_state.get("active_traversals", {})
            if isinstance(_at, dict):
                _ml = _at.get("maid_lusya", {})
                if isinstance(_ml, dict):
                    ml_trav = {"status": _ml.get("status"), "target": _ml.get("target_node")}
        if ml_intents:
            _stamp("MB.process_movement_intents:ENTER maid_lusya",
                   intents=ml_intents, traversal_before_bridge=ml_trav,
                   has_traversal=bool(ml_trav), traversal_status=ml_trav.get("status"))
        return orig_pmi(movement_intents, ctx, orchestrator)
    import app.services.phases.movement_bridge as mb_mod
    mb_mod.process_movement_intents = _spy_pmi

    orig_efi = CommitmentArbiter.enforce_for_intent
    def _spy_efi(scene_state, intent, tick):
        actor = getattr(intent, "actor_id", "?")
        if actor != "maid_lusya":
            return orig_efi(scene_state, intent, tick)
        _at = scene_state.get("active_traversals", {}) or {}
        trav_before = _at.get("maid_lusya", {})
        _stamp("CA.enforce_for_intent:ENTER maid_lusya",
               reason=getattr(intent, "reason", "?"),
               has_traversal=bool(trav_before),
               traversal_status=trav_before.get("status") if isinstance(trav_before, dict) else None)
        result = orig_efi(scene_state, intent, tick)
        _at2 = scene_state.get("active_traversals", {}) or {}
        trav_after = _at2.get("maid_lusya", {})
        _stamp("CA.enforce_for_intent:EXIT maid_lusya",
               result=result,
               traversal_changed=bool(trav_before) != bool(trav_after))
        return result
    CommitmentArbiter.enforce_for_intent = _spy_efi

    orig_pi = MovementEngine.process_intents
    def _spy_pi(self_me, intents, **kwargs):
        scene_state = kwargs.get("scene_state")
        has_ml = any(getattr(i, "actor_id", "") == "maid_lusya" for i in (intents or []))
        if has_ml:
            pre_travs = {}
            if scene_state and isinstance(scene_state, dict):
                _at = scene_state.get("active_traversals", {})
                if isinstance(_at, dict):
                    _ml = _at.get("maid_lusya", {})
                    if isinstance(_ml, dict):
                        pre_travs = {"status": _ml.get("status"), "target": _ml.get("target_node")}
            ml_reasons = [getattr(i, "reason", "?") for i in (intents or []) if getattr(i, "actor_id", "") == "maid_lusya"]
            _stamp("ME.process_intents:ENTER maid_lusya",
                   ml_reasons=ml_reasons, traversal_before=pre_travs,
                   has_traversal=bool(pre_travs), traversal_status=pre_travs.get("status"))
        result = orig_pi(self_me, intents, **kwargs)
        if has_ml:
            ml_changes = [sc for sc in (result or []) if getattr(sc, "target", getattr(sc, "npc_id", "?")) == "maid_lusya"]
            _stamp("ME.process_intents:EXIT maid_lusya",
                   ml_changes_count=len(ml_changes),
                   FLEE_EXECUTED=len(ml_changes) > 0)
        return result
    MovementEngine.process_intents = _spy_pi

def snapshot_ml(loop):
    scene = loop.scene_manager.get_scene_state("Open_road", "tavern")
    if scene is None: return {"error": "scene None"}
    pos = scene.get("npc_positions", {}).get("maid_lusya", {})
    lp = pos.get("local_position", {}) if isinstance(pos, dict) else {}
    trav = (scene.get("active_traversals") or {}).get("maid_lusya", {})
    return {
        "position": pos.get("position") if isinstance(pos, dict) else None,
        "x": lp.get("x") if isinstance(lp, dict) else None,
        "y": lp.get("y") if isinstance(lp, dict) else None,
        "traversal_status": trav.get("status") if isinstance(trav, dict) else None,
        "traversal_target": trav.get("target_node") if isinstance(trav, dict) else None,
        "tick": scene.get("tick"),
    }

def publish_insult(target_id="maid_lusya"):
    payload = {"action_type": "player_insults", "target_id": target_id, "content": "оскорбление",
               "event_tick": 1, "visibility": "public", "radius": 999.0, "location": "tavern",
               "campaign_id": "Open_road", "raw_input": "оскорбление"}
    evt = EventDTO.create(event_type=EventType.PLAYER_INSULTS, source="player", payload=payload, persistence_level="working")
    get_event_bus().publish(evt)

def run_scenario(label, with_insult, real_data_dir, saves_dir, num_ticks=10):
    print(f"\n{'#'*78}\n# SCENARIO {label}: {'WITH' if with_insult else 'NO'} PLAYER_INSULTS, {num_ticks} ticks\n{'#'*78}")
    SPY_LOG.clear()
    try: get_event_bus().clear()
    except Exception: pass
    loop = build_test_loop(real_data_dir, saves_dir)
    init_scene(loop)
    attach_spies()
    _stamp(f"{label}.PRE", **snapshot_ml(loop))
    if with_insult: publish_insult("maid_lusya")
    for tick_i in range(1, num_ticks + 1):
        _stamp(f"{label}.TICK_{tick_i}:START", **snapshot_ml(loop))
        try: loop.idle_tick("Open_road")
        except Exception as e:
            _stamp(f"{label}.TICK_{tick_i}:ERROR", error=str(e)[:300]); break
        _stamp(f"{label}.TICK_{tick_i}:EXIT", **snapshot_ml(loop))
    cleanup_loop(loop); del loop; import gc; gc.collect()
    return list(SPY_LOG)

def main():
    print("\n"+"="*78+"\nP5-G Уточнение D — FLEE Positive Control\nBaseline: 72cf47b0658ffe8cae6351213ddbfb3b48f2e6d2\n"+"="*78)
    real_data_dir = Path(settings.data_dir)
    saves_a = Path(tempfile.mkdtemp(prefix="p5g_dA_")); saves_b = Path(tempfile.mkdtemp(prefix="p5g_dB_"))
    try:
        spy_a = run_scenario("A", True, real_data_dir, saves_a, 10)
        spy_b = run_scenario("B", False, real_data_dir, saves_b, 10)
        print("\n"+"="*78+"\nFORENSIC REPORT — P5-G Уточнение D\n"+"="*78)
        print("\n--- SCENARIO A ---")
        for e in spy_a: print(f"  {e}")
        print("\n--- SCENARIO B ---")
        for e in spy_b: print(f"  {e}")
        # Summary
        print("\n--- SUMMARY ---")
        for label, spy in [("A", spy_a), ("B", spy_b)]:
            flee_decisions = [e for e in spy if e.get("tag") == "DH.compute:EXIT maid_lusya" and "FLEE" in e.get("intent", "")]
            flee_enter = [e for e in spy if e.get("tag") == "ME.process_intents:ENTER maid_lusya" and any("flee" in r for r in e.get("ml_reasons", []))]
            flee_executed = [e for e in spy if e.get("tag") == "ME.process_intents:EXIT maid_lusya" and e.get("FLEE_EXECUTED") == True]
            flee_blocked = [e for e in spy if e.get("tag") == "ME.process_intents:EXIT maid_lusya" and e.get("FLEE_EXECUTED") == False]
            no_traversal_flee = [e for e in flee_enter if not e.get("has_traversal", True)]
            print(f"  {label}: FLEE decisions={len(flee_decisions)}, intents={len(flee_enter)}, executed={len(flee_executed)}, blocked={len(flee_blocked)}, without_traversal={len(no_traversal_flee)}")
            for e in no_traversal_flee:
                print(f"    POSITIVE CONTROL FOUND: {e}")
        return 0
    except Exception as e:
        print(f"\n[FATAL] {type(e).__name__}: {e}"); traceback.print_exc(); return 1
    finally:
        for d in [saves_a, saves_b]:
            try: shutil.rmtree(d, ignore_errors=True)
            except Exception: pass

if __name__ == "__main__": sys.exit(main())