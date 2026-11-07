# backend/tests/sandbox/p5a_step_25_track_b_probe.py
"""
P5-A Step 2.5 — Track B Production Verification.
Производит A/B: с/без PLAYER_INSULTS. Все звенья spy.
"""
from __future__ import annotations
import os, sys, json, shutil, tempfile, traceback, math, copy
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
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
from app.services.npc.epistemic_context_resolver import EpistemicContextResolver
from app.services.phases.post_decision import run_phase_6_post_decision
from app.services.execution.dialogue_executor import DialogueExecutor
from app.services.game_loop.task_scheduler import TaskScheduler
from app.domain.execution import TaskKind

SPY_LOG: List[Dict[str, Any]] = []

def _stamp(tag: str, **kw: Any) -> None:
    SPY_LOG.append({"tag": tag, **kw})
    print(f"[SPY] {tag}: " + json.dumps(kw, ensure_ascii=False, default=str))

# === Build production GameLoop ===
def build_test_loop() -> Tuple[Any, Path]:
    temp_dir = Path(tempfile.mkdtemp(prefix="p25_probe_"))
    real_data_dir = Path(settings.data_dir)
    settings.saves_dir = str(temp_dir)
    settings.environment = "development"
    loop = build_game_loop(data_dir=real_data_dir)
    # Mock LLM router (conftest pattern) — но с правильным путём
    try:
        ts = loop._get_task_scheduler()  # noqa: ENIGMA002
        for kind, ex in (getattr(ts, "_executors", {}) or {}).items():
            if hasattr(ex, "_router"):
                ex._router = MagicMock()
                if hasattr(ex._router, "route"):
                    ex._router.route.return_value = "[Test LLM Mock]"
                _stamp("HARNESS.mock_llm", kind=str(kind), where="executor._router")
    except Exception as e:
        _stamp("HARNESS.mock_llm", status="FAILED", error=str(e)[:200])
    return loop, temp_dir

def cleanup(loop: Any, temp_dir: Path) -> None:
    try:
        if hasattr(loop, "_task_scheduler"):
            ts = loop._task_scheduler
            if hasattr(ts, "_executor_pool"):
                try: ts._executor_pool.shutdown(wait=False, cancel_futures=True)
                except Exception: pass
    except Exception: pass
    shutil.rmtree(temp_dir, ignore_errors=True)

# === Init scene explicitly ===
def init_scene(loop: Any, campaign_id: str = "Open_road", location: str = "tavern") -> Dict[str, Any]:
    _stamp("INIT.scene:START", campaign=campaign_id, location=location)
    scene = loop.scene_manager.get_scene_state(campaign_id, location)
    if scene is None:
        scene = loop.scene_manager.initialize_scene(campaign_id, location, "12:00")
    pos = scene.get("npc_positions", {}) or {}
    _stamp("INIT.scene", npc_count=len(pos), npc_ids=sorted(list(pos.keys())),
           game_time=scene.get("game_time_seconds"), tick=scene.get("tick"))
    _stamp("INIT.player", pos=pos.get("player"))
    _stamp("INIT.maid_lusya", pos=pos.get("maid_lusya"))
    _stamp("INIT.pending_tasks", count=len(scene.get("pending_tasks", []) or []))
    # Epistemic pre-state
    sub = getattr(loop, "_claim_event_subscriber", None)
    if sub is not None:
        store = getattr(sub, "_store", None)
        if store is not None:
            try:
                recs = store.to_dict() if hasattr(store, "to_dict") else []
                _stamp("INIT.epistemic", total=len(recs) if isinstance(recs, list) else "?",
                       agents=sorted({r.get("agent_id") for r in recs}) if isinstance(recs, list) else [])
            except Exception as e:
                _stamp("INIT.epistemic", error=str(e)[:100])
    return scene

# === Attach spies on all звенья ===
def attach_all_spies(loop: Any) -> Dict[str, Any]:
    refs: Dict[str, Any] = {}

    # 1. ClaimEventSubscriber — instance wrap on_claim_event
    sub = getattr(loop, "_claim_event_subscriber", None)
    refs["sub"] = sub
    if sub is not None:
        orig_oc = sub.on_claim_event
        def _spy_oc(event):
            _stamp("A3.on_claim_event:ENTER",
                   event_type=getattr(event, "type", "?"),
                   source=getattr(event, "source", "?"),
                   target_id=(getattr(event, "payload", {}) or {}).get("target_id"))
            result = orig_oc(event)
            _stamp("A3.on_claim_event:EXIT")
            return result
        sub.on_claim_event = _spy_oc  # type: ignore

        # store
        store = getattr(sub, "_store", None)
        refs["store"] = store
        if store is not None:
            orig_up = store.upsert
            def _spy_up(record):
                _stamp("A5.upsert:ENTER",
                       agent=getattr(record, "agent_id", "?"),
                       conf=getattr(record, "confidence", None))
                return orig_up(record)
            store.upsert = _spy_up  # type: ignore

    # 2. BeliefRevisionEngine — class-level wrap revise
    orig_revise = BeliefRevisionEngine.revise
    def _spy_revise(self_e, *args, **kwargs):
        listener_id = args[0] if args else kwargs.get("listener_id", "?")
        claim = args[1] if len(args) > 1 else kwargs.get("claim", None)
        prop_str = ""
        if claim is not None and getattr(claim, "proposition", None) is not None:
            p = claim.proposition
            prop_str = f"{p.subject_id}/{p.predicate.value}/{p.object_id}"
        _stamp("A4.revise:ENTER", listener=listener_id, prop=prop_str)
        result = orig_revise(self_e, *args, **kwargs)
        _stamp("A4.revise:EXIT", conf=getattr(result, "confidence", None))
        return result
    BeliefRevisionEngine.revise = _spy_revise  # type: ignore

    # 3. DecisionHub.compute — class-level wrap (capture chosen intent for maid_lusya)
    orig_compute = DecisionHub.compute
    def _spy_compute(self_dh, *args, **kwargs):
        state_arg = args[0] if args else kwargs.get("state", None)
        npc_id = getattr(state_arg, "npc_id", "?") if state_arg is not None else "?"
        epistemic_ctx = kwargs.get("epistemic_context", None)
        if npc_id == "maid_lusya":
            # Capture epistemic_context threats/allies
            threats = sorted(list(getattr(epistemic_ctx, "perceived_threats", []) or [])) if epistemic_ctx else []
            allies = sorted(list(getattr(epistemic_ctx, "perceived_allies", []) or [])) if epistemic_ctx else []
            claims_self = []
            try:
                cs = getattr(epistemic_ctx, "claims_about_self", []) or []
                claims_self = [{"subject": getattr(c, "subject_id", "?"),
                                "predicate": getattr(getattr(c, "proposition", None), "predicate", "?"),
                                "object": getattr(getattr(c, "proposition", None), "object_id", "?")}
                               for c in cs]
            except Exception: pass
            _stamp("D.compute:ENTER maid_lusya",
                   threats=threats, allies=allies, claims_about_self=claims_self,
                   fear=getattr(state_arg, "fear", "?"),
                   affective_load=getattr(getattr(state_arg, "affective_load", None), "value", None))
        result = orig_compute(self_dh, *args, **kwargs)
        if npc_id == "maid_lusya":
            comm = getattr(result, "communication", None)
            intent_type = getattr(comm, "intent_type", None) if comm else None
            intent_target = getattr(comm, "target_id", None) if comm else None
            chosen_action = getattr(result, "action_type", "?")
            _stamp("D.compute:EXIT maid_lusya",
                   chosen_action=chosen_action,
                   has_communication=comm is not None,
                   intent_type=intent_type,
                   intent_target=intent_target,
                   comm_repr=repr(comm)[:200] if comm else None)
        return result
    DecisionHub.compute = _spy_compute  # type: ignore

    # 4. post_decision.run_phase_6_post_decision — module-level wrap
    orig_pd6 = run_phase_6_post_decision
    def _spy_pd6(ctx, orch):
        pre_count = len(getattr(ctx, "communication_intents", []) or [])
        _stamp("PD6.phase_6:ENTER", pre_communication_intents=pre_count,
               speakers=[getattr(c, "speaker", "?") for c in (getattr(ctx, "communication_intents", []) or [])])
        result = orig_pd6(ctx, orch)
        post_count = len(getattr(ctx, "communication_intents", []) or [])
        pending = ctx.scene_state.get("pending_tasks", []) if hasattr(ctx, "scene_state") else []
        _stamp("PD6.phase_6:EXIT", post_communication_intents=post_count,
               pending_tasks_count=len(pending))
        return result
    import app.services.phases.post_decision as pd_mod
    pd_mod.run_phase_6_post_decision = _spy_pd6  # type: ignore

    # 5. TaskScheduler.execute_pending — instance wrap
    try:
        ts = loop._get_task_scheduler()  # noqa: ENIGMA002
        refs["ts"] = ts
        orig_ep = ts.execute_pending
        def _spy_ep(scene_state, campaign_id):
            pre = len(scene_state.get("pending_tasks", []) or [])
            _stamp("B2.execute_pending:ENTER", campaign=campaign_id, pre_pending=pre)
            result = orig_ep(scene_state, campaign_id)
            post = len(scene_state.get("pending_tasks", []) or [])
            _stamp("B2.execute_pending:EXIT", post_pending=post)
            return result
        ts.execute_pending = _spy_ep  # type: ignore
    except Exception as e:
        _stamp("B2.attach", status="FAILED", error=str(e)[:200])

    # 6. DialogueExecutor.execute — instance wrap (all executors)
    try:
        ts = loop._get_task_scheduler()  # noqa: ENIGMA002
        for kind, ex in (getattr(ts, "_executors", {}) or {}).items():
            if hasattr(ex, "execute"):
                orig_exe = ex.execute
                def _make_spy(orig_exe, kind_name):
                    def _spy_exe(task):
                        _stamp("B4.execute:ENTER",
                               kind=str(kind_name),
                               owner=getattr(task, "owner_id", "?"),
                               target_ids=getattr(task, "target_ids", []),
                               task_id=getattr(task, "task_id", "?"))
                        try:
                            results = list(orig_exe(task))
                            _stamp("B4.execute:EXIT",
                                   kind=str(kind_name),
                                   results_count=len(results),
                                   success=results[0].success if results and hasattr(results[0], "success") else "?")
                            return iter(results)
                        except Exception as e:
                            _stamp("B4.execute:ERROR", error=str(e)[:200])
                            raise
                    return _spy_exe
                ex.execute = _make_spy(orig_exe, kind)  # type: ignore
    except Exception as e:
        _stamp("B4.attach", status="FAILED", error=str(e)[:200])

    # 7. EventBus — spy publish for NPC_SPOKE
    bus = get_event_bus()
    orig_pub = bus.publish
    def _spy_pub(evt):
        et = getattr(evt, "type", "?")
        if et in ("npc_spoke", "NPC_SPOKE") or "spoke" in str(et).lower():
            _stamp("B4.NPC_SPOKE:publish",
                   event_type=et,
                   source=getattr(evt, "source", "?"),
                   target_id=(getattr(evt, "payload", {}) or {}).get("target_id"),
                   intent_type=(getattr(evt, "payload", {}) or {}).get("intent_type"))
        return orig_pub(evt)
    bus.publish = _spy_pub  # type: ignore
    refs["bus"] = bus

    return refs

# === Publish PLAYER_INSULTS ===
def publish_insult(target_id: str = "maid_lusya"):
    _stamp("=== A: PLAYER_INSULTS ===", target=target_id)
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
    _stamp("A1.publish", event_id=str(evt.id), target_id=target_id)
    get_event_bus().publish(evt)

# === Snapshot state before idle ===
def snapshot_state(loop: Any, campaign_id: str = "Open_road") -> Dict[str, Any]:
    snap: Dict[str, Any] = {}
    try:
        scene = loop.scene_manager.get_scene_state(campaign_id, "tavern")
        if scene is not None:
            snap["pending_tasks"] = len(scene.get("pending_tasks", []) or [])
            snap["game_time"] = scene.get("game_time_seconds")
            snap["tick"] = scene.get("tick")
            pos = scene.get("npc_positions", {}) or {}
            ml = pos.get("maid_lusya", {})
            snap["maid_lusya_pos"] = ml.get("local_position") if isinstance(ml, dict) else None
    except Exception as e:
        snap["error"] = str(e)[:100]
    sub = getattr(loop, "_claim_event_subscriber", None)
    if sub is not None:
        store = getattr(sub, "_store", None)
        if store is not None:
            try:
                prop = Proposition(subject_id="player", predicate=Predicate.INSULTED,
                                   object_id="maid_lusya", polarity=True)
                rec = store.get("maid_lusya", prop)
                snap["maid_lusya_belief"] = {
                    "present": rec is not None,
                    "conf": getattr(rec, "confidence", None),
                    "source": getattr(rec, "source_id", None),
                } if rec else {"present": False}
            except Exception as e:
                snap["maid_lusya_belief_error"] = str(e)[:100]
    return snap

# === Run idle_tick ===
def run_idle_tick(loop: Any, campaign_id: str = "Open_road") -> Dict[str, Any]:
    _stamp("=== B: idle_tick ===", campaign=campaign_id)
    try:
        result = loop.idle_tick(campaign_id)
        _stamp("B.idle_tick:EXIT",
               status=result.get("status", "?") if isinstance(result, dict) else type(result).__name__)
        return result if isinstance(result, dict) else {"raw": str(result)[:200]}
    except Exception as e:
        _stamp("B.idle_tick:ERROR", error=type(e).__name__, msg=str(e)[:300])
        traceback.print_exc()
        return {"error": str(e)[:200]}

# === MAIN ===
def main() -> int:
    print("\n" + "=" * 78)
    print("P5-A Step 2.5 — Track B Production Verification")
    print("Baseline: 72cf47b0658ffe8cae6351213ddbfb3b48f2e6d2")
    print("=" * 78)

    try: get_event_bus().clear()
    except Exception: pass

    loop = None
    temp_dir = None
    try:
        loop, temp_dir = build_test_loop()
        _stamp("HARNESS.built", temp_dir=str(temp_dir))

        # Init scene ONCE
        scene = init_scene(loop, "Open_road", "tavern")
        if scene is None:
            _stamp("FATAL", reason="scene init failed")
            return 1

        # Attach spies
        refs = attach_all_spies(loop)
        _stamp("HARNESS.spies",
               has_sub=refs.get("sub") is not None,
               has_store=refs.get("store") is not None,
               has_ts=refs.get("ts") is not None,
               has_bus=refs.get("bus") is not None)

        # === SCENARIO A: with PLAYER_INSULTS ===
        print("\n" + "#" * 78)
        print("# SCENARIO A: PLAYER_INSULTS published, then idle_tick")
        print("#" * 78)
        SPY_LOG.clear()
        pre_a = snapshot_state(loop, "Open_road")
        _stamp("A.PRE", **pre_a)
        publish_insult(target_id="maid_lusya")
        post_insult_a = snapshot_state(loop, "Open_road")
        _stamp("A.POST_INSULT", **post_insult_a)
        idle_result_a = run_idle_tick(loop, "Open_road")
        post_idle_a = snapshot_state(loop, "Open_road")
        _stamp("A.POST_IDLE", **post_idle_a)
        spy_a = list(SPY_LOG)  # save

        # === SCENARIO B: without PLAYER_INSULTS (clean state) ===
        print("\n" + "#" * 78)
        print("# SCENARIO B: NO PLAYER_INSULTS, only idle_tick (fresh state)")
        print("#" * 78)
        # Need fresh state — rebuild loop
        try:
            cleanup(loop, temp_dir)
        except Exception: pass
        loop, temp_dir = build_test_loop()
        scene = init_scene(loop, "Open_road", "tavern")
        if scene is None:
            _stamp("FATAL_B", reason="scene init failed in B")
            return 1
        refs = attach_all_spies(loop)
        SPY_LOG.clear()
        pre_b = snapshot_state(loop, "Open_road")
        _stamp("B.PRE", **pre_b)
        # NO publish_insult — control
        _stamp("B.SKIP_INSULT", reason="control scenario")
        idle_result_b = run_idle_tick(loop, "Open_road")
        post_idle_b = snapshot_state(loop, "Open_road")
        _stamp("B.POST_IDLE", **post_idle_b)
        spy_b = list(SPY_LOG)

        # === REPORT ===
        print("\n" + "=" * 78)
        print("FORENSIC REPORT — Step 2.5")
        print("=" * 78)
        print("\n--- SCENARIO A (with PLAYER_INSULTS) ---")
        print(f"SPY entries: {len(spy_a)}")
        for e in spy_a:
            print(f"  {e}")
        print("\n--- SCENARIO B (without PLAYER_INSULTS) ---")
        print(f"SPY entries: {len(spy_b)}")
        for e in spy_b:
            print(f"  {e}")

        print("\n--- A/B COMPARISON ---")
        print(f"A.pre.belief: {pre_a.get('maid_lusya_belief')}")
        print(f"A.post_insult.belief: {post_insult_a.get('maid_lusya_belief')}")
        print(f"A.post_idle.belief: {post_idle_a.get('maid_lusya_belief')}")
        print(f"A.pre.pending_tasks: {pre_a.get('pending_tasks')}")
        print(f"A.post_idle.pending_tasks: {post_idle_a.get('pending_tasks')}")
        print(f"B.pre.belief: {pre_b.get('maid_lusya_belief')}")
        print(f"B.post_idle.belief: {post_idle_b.get('maid_lusya_belief')}")
        print(f"B.pre.pending_tasks: {pre_b.get('pending_tasks')}")
        print(f"B.post_idle.pending_tasks: {post_idle_b.get('pending_tasks')}")
        return 0
    except Exception as e:
        print(f"\n[FATAL] {type(e).__name__}: {e}")
        traceback.print_exc()
        return 1
    finally:
        if loop is not None and temp_dir is not None:
            try: cleanup(loop, temp_dir)
            except Exception: pass

if __name__ == "__main__":
    sys.exit(main())