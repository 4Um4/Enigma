# backend/tests/sandbox/p5e_movement_arbitration_probe.py
"""
P5-E — Movement Arbitration Forensics.
Цель: доказать, почему MovementEngine.process_intents() не создаёт
spatial_changes для maid_lusya при SEEK_ALLY.
Подозреваемый: GATE B1.5 — Traversal Pre-emption Guard (movement_engine.py:202-229).
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
from app.services.npc.decision_hub import DecisionHub
from app.services.phases.post_decision import run_phase_6_post_decision
from app.services.phases.movement_bridge import process_movement_intents
from app.services.spatial.movement_engine import MovementEngine
from app.domain.movement import MacroMovementGoal

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

# === Spies on MovementEngine internals ===
def attach_movement_spies():
    """Spy на process_intents + _spatial_intent_gate + _process_single_intent."""

    # Spy 1: _spatial_intent_gate — capture какие intents проходят Stage 2
    orig_gate = MovementEngine._spatial_intent_gate
    def _spy_gate(self_me, intents, npc_positions):
        pre_count = len(intents)
        pre_actors = [getattr(i, "actor_id", "?") for i in intents]
        result = orig_gate(self_me, intents, npc_positions)
        post_count = len(result)
        post_actors = [getattr(i, "actor_id", "?") for i in result]
        # Check if maid_lusya was collapsed (already at target)
        ml_pre = any(a == "maid_lusya" for a in pre_actors)
        ml_post = any(a == "maid_lusya" for a in post_actors)
        # Get maid_lusya position and target
        ml_pos = (npc_positions or {}).get("maid_lusya", {})
        ml_current = ml_pos.get("position", "?") if isinstance(ml_pos, dict) else "?"
        ml_target = ""
        for i in intents:
            if getattr(i, "actor_id", "") == "maid_lusya":
                ml_target = getattr(i, "target_node_id", "?")
                break
        _stamp("STAGE2._spatial_intent_gate",
               pre_count=pre_count, post_count=post_count,
               pre_actors=pre_actors, post_actors=post_actors,
               maid_lusya_pre=ml_pre, maid_lusya_post=ml_post,
               ml_current_pos=ml_current, ml_target=ml_target,
               ml_collapsed=ml_pre and not ml_post)
        return result
    MovementEngine._spatial_intent_gate = _spy_gate

    # Spy 2: process_intents — capture active_traversals BEFORE processing + per-intent fate
    orig_pi = MovementEngine.process_intents
    def _spy_pi(self_me, intents, **kwargs):
        scene_state = kwargs.get("scene_state")
        npc_positions = kwargs.get("npc_positions")

        # Snapshot active_traversals for ALL actors BEFORE processing
        pre_travs = {}
        if scene_state and isinstance(scene_state, dict):
            _at = scene_state.get("active_traversals", {})
            if isinstance(_at, dict):
                for nid, trav in _at.items():
                    if isinstance(trav, dict):
                        pre_travs[nid] = {
                            "status": trav.get("status"),
                            "target_node": trav.get("target_node"),
                            "reason": trav.get("reason", ""),
                            "origin_node": trav.get("origin_node", ""),
                        }

        # Specifically snapshot maid_lusya
        ml_trav = pre_travs.get("maid_lusya", {})
        _stamp("STAGE0.pre_process_intents",
               intents_count=len(intents),
               actors=[getattr(i, "actor_id", "?") for i in intents],
               maid_lusya_active_traversal=ml_trav,
               all_active_traversals=pre_travs)

        # Check: does maid_lusya have a MOVING traversal?
        ml_is_moving = ml_trav.get("status") == "MOVING"
        # Check: does maid_lusya's intent reason contain "interrupt" or "+relocation"?
        ml_intent_reason = ""
        for i in intents:
            if getattr(i, "actor_id", "") == "maid_lusya":
                ml_intent_reason = getattr(i, "reason", "")
                break
        ml_has_interrupt = "interrupt" in ml_intent_reason
        ml_has_relocation = "+relocation" in ml_intent_reason
        _stamp("STAGE3.B1_5_PREDICTION maid_lusya",
               ml_is_moving=ml_is_moving,
               ml_intent_reason=ml_intent_reason,
               ml_has_interrupt=ml_has_interrupt,
               ml_has_relocation=ml_has_relocation,
               PREDICTED_REJECT=ml_is_moving and not ml_has_interrupt and not ml_has_relocation)

        result = orig_pi(self_me, intents, **kwargs)

        # Check result: did maid_lusya get spatial_changes?
        ml_changes = [sc for sc in (result or []) if getattr(sc, "target", getattr(sc, "npc_id", "?")) == "maid_lusya"]
        _stamp("STAGE_FINAL.process_intents:EXIT",
               spatial_changes_count=len(result or []),
               maid_lusya_changes_count=len(ml_changes),
               maid_lusya_changes=[{"field": getattr(sc, "field", "?"),
                                    "value": str(getattr(sc, "value", "?"))[:200]}
                                   for sc in ml_changes],
               ACTUAL_REJECT=len(ml_changes) == 0)
        return result
    MovementEngine.process_intents = _spy_pi

    # Spy 3: _process_single_intent — which actors reach this final stage?
    orig_psi = MovementEngine._process_single_intent
    def _spy_psi(self_me, intent, **kwargs):
        actor = getattr(intent, "actor_id", getattr(intent, "npc_id", "?"))
        reason = getattr(intent, "reason", "?")
        target = getattr(intent, "target_node_id", "?")
        _stamp("STAGE4._process_single_intent:ENTER",
               actor=actor, reason=reason, target=target)
        try:
            result = orig_psi(self_me, intent, **kwargs)
            changes_count = len(result) if isinstance(result, list) else 0
            _stamp("STAGE4._process_single_intent:EXIT",
                   actor=actor, changes_count=changes_count)
            return result
        except Exception as e:
            _stamp("STAGE4._process_single_intent:ERROR",
                   actor=actor, error=type(e).__name__, msg=str(e)[:200])
            raise
    MovementEngine._process_single_intent = _spy_psi

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

def run_scenario(label, with_insult, real_data_dir, saves_dir):
    print(f"\n{'#' * 78}\n# SCENARIO {label}\n{'#' * 78}")
    SPY_LOG.clear()
    try: get_event_bus().clear()
    except Exception: pass

    loop = build_test_loop(real_data_dir, saves_dir)
    init_scene(loop)
    attach_movement_spies()

    if with_insult:
        publish_insult("maid_lusya")

    _stamp(f"{label}.idle_tick:START")
    try:
        result = loop.idle_tick("Open_road")
        _stamp(f"{label}.idle_tick:EXIT", status=result.get("status", "?") if isinstance(result, dict) else "?")
    except Exception as e:
        _stamp(f"{label}.idle_tick:ERROR", error=type(e).__name__, msg=str(e)[:300])
        traceback.print_exc()

    cleanup_loop(loop)
    del loop
    import gc; gc.collect()
    return list(SPY_LOG)

def main():
    print("\n" + "=" * 78)
    print("P5-E — Movement Arbitration Forensics")
    print("Baseline: 72cf47b0658ffe8cae6351213ddbfb3b48f2e6d2")
    print("=" * 78)

    real_data_dir = Path(settings.data_dir)
    saves_a = Path(tempfile.mkdtemp(prefix="p5e_A_"))
    saves_b = Path(tempfile.mkdtemp(prefix="p5e_B_"))

    try:
        spy_a = run_scenario("A", with_insult=True, real_data_dir=real_data_dir, saves_dir=saves_a)
        spy_b = run_scenario("B", with_insult=False, real_data_dir=real_data_dir, saves_dir=saves_b)

        print("\n" + "=" * 78)
        print("FORENSIC REPORT — P5-E")
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