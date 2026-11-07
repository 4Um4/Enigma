# backend/tests/sandbox/p5g_flee_forensics.py
"""
P5-G Track A — FLEE Runtime Forensics.
Цель: доказать фактический production-path FLEE → CommitmentArbiter → B1.5 → spatial_changes.
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
from app.services.phases.post_decision import run_phase_6_post_decision
from app.services.phases.movement_bridge import process_movement_intents
from app.services.spatial.movement_engine import MovementEngine
from app.services.action.commitment_arbiter import CommitmentArbiter
from app.domain.action_priority import resolve_candidate_priority

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
    """Spy на ВСЕ этапы FLEE path."""
    
    # Spy 1: CommitmentArbiter.enforce_for_intent — capture verdict + enforcement
    orig_efi = CommitmentArbiter.enforce_for_intent
    def _spy_efi(scene_state, intent, tick):
        actor = getattr(intent, "actor_id", "?")
        reason = getattr(intent, "reason", "?")
        # Snapshot BEFORE
        _at = scene_state.get("active_traversals", {}) or {}
        _ac = scene_state.get("active_commitments", {}) or {}
        trav_before = _at.get(actor, {})
        comm_before = _ac.get(actor, {})
        
        # Compute candidate priority
        cp = resolve_candidate_priority(
            intent_type=getattr(intent, "intent_type", "") or "",
            intent_domain=getattr(intent, "domain", None),
        )
        
        _stamp("CA.enforce_for_intent:ENTER",
               actor=actor, reason=reason,
               candidate_priority=cp,
               traversal_before=trav_before,
               commitment_before=comm_before,
               has_traversal=bool(trav_before),
               has_commitment=bool(comm_before),
               traversal_status=trav_before.get("status") if isinstance(trav_before, dict) else None,
               commitment_status=comm_before.get("status") if isinstance(comm_before, dict) else None,
               intent_domain=str(getattr(intent, "domain", None)),
               intent_type_field=getattr(intent, "intent_type", "MISSING"))
        
        result = orig_efi(scene_state, intent, tick)
        
        # Snapshot AFTER
        _at2 = scene_state.get("active_traversals", {}) or {}
        _ac2 = scene_state.get("active_commitments", {}) or {}
        trav_after = _at2.get(actor, {})
        comm_after = _ac2.get(actor, {})
        
        _stamp("CA.enforce_for_intent:EXIT",
               actor=actor,
               result=result,
               traversal_after=trav_after,
               commitment_after=comm_after,
               traversal_changed=bool(trav_before) != bool(trav_after),
               commitment_changed=bool(comm_before) != bool(comm_after))
        return result
    CommitmentArbiter.enforce_for_intent = _spy_efi

    # Spy 2: MovementEngine.process_intents — capture B1.5 check
    orig_pi = MovementEngine.process_intents
    def _spy_pi(self_me, intents, **kwargs):
        scene_state = kwargs.get("scene_state")
        actors = [getattr(i, "actor_id", "?") for i in (intents or [])]
        
        # Snapshot traversals BEFORE
        pre_travs = {}
        if scene_state and isinstance(scene_state, dict):
            _at = scene_state.get("active_traversals", {})
            if isinstance(_at, dict):
                for nid, trav in _at.items():
                    if isinstance(trav, dict):
                        pre_travs[nid] = trav.get("status")
        
        _stamp("ME.process_intents:ENTER",
               intents_count=len(intents or []),
               actors=actors,
               active_traversals_before=pre_travs)
        
        result = orig_pi(self_me, intents, **kwargs)
        
        # Check which actors got spatial_changes
        changes_per_actor = {}
        for sc in (result or []):
            target = getattr(sc, "target", getattr(sc, "npc_id", "?"))
            changes_per_actor[target] = changes_per_actor.get(target, 0) + 1
        
        _stamp("ME.process_intents:EXIT",
               spatial_changes_count=len(result or []),
               changes_per_actor=changes_per_actor)
        return result
    MovementEngine.process_intents = _spy_pi

    # Spy 3: DecisionHub.compute — capture ALL NPC decisions
    orig_compute = DecisionHub.compute
    def _spy_compute(self_dh, *args, **kwargs):
        state_arg = args[0] if args else kwargs.get("state", None)
        npc_id = getattr(state_arg, "npc_id", "?") if state_arg is not None else "?"
        result = orig_compute(self_dh, *args, **kwargs)
        dec = getattr(result, "decision", None)
        if dec is not None:
            intent = str(getattr(dec, "intent", "?"))
            target = getattr(dec, "intent_target", None)
            score = getattr(dec, "score", None)
            _stamp("DH.compute:EXIT",
                   npc=npc_id, intent=intent, target=target, score=score)
        return result
    DecisionHub.compute = _spy_compute

    # Spy 4: process_movement_intents — capture what enters bridge
    orig_pmi = process_movement_intents
    def _spy_pmi(movement_intents, ctx, orchestrator):
        intents_info = []
        for i in (movement_intents or []):
            intents_info.append({
                "actor": getattr(i, "actor_id", getattr(i, "npc_id", "?")),
                "type": type(i).__name__,
                "reason": getattr(i, "reason", "?"),
                "target": getattr(i, "target_node_id", "?"),
                "has_target_intent": getattr(i, "target_intent", None) is not None,
                "priority": getattr(i, "priority", "?"),
                "domain": str(getattr(i, "domain", "?")),
            })
        _stamp("MB.process_movement_intents:ENTER",
               intents_count=len(movement_intents or []),
               intents=intents_info)
        result = orig_pmi(movement_intents, ctx, orchestrator)
        _stamp("MB.process_movement_intents:EXIT")
        return result
    import app.services.phases.movement_bridge as mb_mod
    mb_mod.process_movement_intents = _spy_pmi

def publish_insult(target_id="maid_lusya"):
    payload = {
        "action_type": "player_insults", "target_id": target_id,
        "content": "оскорбление", "event_tick": 1, "visibility": "public",
        "radius": 999.0, "location": "tavern", "campaign_id": "Open_road",
        "raw_input": "оскорбление",
    }
    evt = EventDTO.create(event_type=EventType.PLAYER_INSULTS, source="player",
                          payload=payload, persistence_level="working")
    get_event_bus().publish(evt)

def snapshot_positions(loop, npc_ids=("maid_lusya", "tavern_keeper_tornin")):
    scene = loop.scene_manager.get_scene_state("Open_road", "tavern")
    if scene is None:
        return {"error": "scene None"}
    pos = scene.get("npc_positions", {}) or {}
    result = {}
    for nid in npc_ids:
        e = pos.get(nid, {})
        lp = e.get("local_position", {}) if isinstance(e, dict) else {}
        result[nid] = {
            "position": e.get("position") if isinstance(e, dict) else None,
            "x": lp.get("x") if isinstance(lp, dict) else None,
            "y": lp.get("y") if isinstance(lp, dict) else None,
        }
    result["_active_traversals"] = {k: v.get("status") if isinstance(v, dict) else "?"
                                     for k, v in (scene.get("active_traversals") or {}).items()}
    result["_active_commitments"] = {k: v.get("status") if isinstance(v, dict) else "?"
                                      for k, v in (scene.get("active_commitments") or {}).items()}
    result["_tick"] = scene.get("tick")
    return result

def main():
    print("\n" + "=" * 78)
    print("P5-G Track A — FLEE Runtime Forensics")
    print("Baseline: 72cf47b0658ffe8cae6351213ddbfb3b48f2e6d2")
    print("=" * 78)

    real_data_dir = Path(settings.data_dir)
    saves = Path(tempfile.mkdtemp(prefix="p5g_flee_"))

    try:
        SPY_LOG.clear()
        get_event_bus().clear()
        
        loop = build_test_loop(real_data_dir, saves)
        init_scene(loop)
        attach_spies()
        
        _stamp("PRE_positions", positions=snapshot_positions(loop))
        publish_insult("maid_lusya")
        _stamp("POST_INSULT_positions", positions=snapshot_positions(loop))
        
        # Run 3 idle_ticks to see FLEE behavior
        for tick_i in [1, 2, 3]:
            _stamp(f"IDLE_TICK_{tick_i}:START")
            try:
                loop.idle_tick("Open_road")
                _stamp(f"IDLE_TICK_{tick_i}:EXIT", positions=snapshot_positions(loop))
            except Exception as e:
                _stamp(f"IDLE_TICK_{tick_i}:ERROR", error=str(e)[:300])
        
        cleanup_loop(loop)
        
        print("\n" + "=" * 78)
        print("FORENSIC REPORT — P5-G Track A")
        print("=" * 78)
        for e in SPY_LOG:
            print(f"  {e}")
        return 0
    except Exception as e:
        print(f"\n[FATAL] {type(e).__name__}: {e}")
        traceback.print_exc()
        return 1
    finally:
        try: shutil.rmtree(saves, ignore_errors=True)
        except Exception: pass

if __name__ == "__main__":
    sys.exit(main())