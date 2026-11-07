# backend/tests/sandbox/p5a_step_24_spatial_probe.py
"""
P5-A Step 2.4 — Spatial Membrane Forensics (v3).
v3 fix: без class-level patch (он вызывал hang в probe v2).
       instance-level wrap subscriber.on_claim_event, который читает _listeners ПОСЛЕ основного цикла.
Стратегия:
  1. build_game_loop (production, real campaign data)
  2. initialize_scene("Open_road", "tavern", "12:00") — ЯВНАЯ (как diag proved)
  3. Instance-level patch subscriber.on_claim_event — capture _listeners snapshot после каждого шага
  4. Instance-level patch _sq.distance (через provider wrapper) — capture distances
  5. publish PLAYER_INSULTS (production channel)
  6. Run TWICE for reproducibility check
"""
from __future__ import annotations

import os, sys, json, shutil, tempfile, traceback, math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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

SPY_LOG: List[Dict[str, Any]] = []
DISTANCE_CALLS: List[Dict[str, Any]] = []
CAN_OBSERVE_CALLS: List[Dict[str, Any]] = []
SQ_INSTANCES: List[Any] = []
_POS_SNAPSHOT: Dict[int, Dict[str, Any]] = {}

def _stamp(tag: str, **kw: Any) -> None:
    SPY_LOG.append({"tag": tag, **kw})
    print(f"[SPY] {tag}: " + json.dumps(kw, ensure_ascii=False, default=str))

# === Build production GameLoop ===
def build_test_loop() -> Tuple[Any, Path]:
    temp_dir = Path(tempfile.mkdtemp(prefix="p24_probe_"))
    real_data_dir = Path(settings.data_dir)
    settings.saves_dir = str(temp_dir)
    settings.environment = "development"
    loop = build_game_loop(data_dir=real_data_dir)
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

def _capture_sq_positions(sq: Any) -> None:
    sq_id = id(sq)
    if sq_id in _POS_SNAPSHOT: return
    pos = getattr(sq, "_npc_positions", {}) or {}
    snap = {}
    for nid, p in pos.items():
        if isinstance(p, dict):
            lp = p.get("local_position") or {}
            snap[nid] = {"x": lp.get("x"), "y": lp.get("y"),
                         "name": p.get("name"), "position_node": p.get("position")}
        else:
            snap[nid] = str(p)[:60]
    _POS_SNAPSHOT[sq_id] = snap

# === Patch provider to capture _sq + wrap distance ===
def patch_subscriber_for_capture(loop: Any) -> Dict[str, Any]:
    sub = getattr(loop, "_claim_event_subscriber", None)
    if sub is None:
        _stamp("PATCH", error="no subscriber")
        return {}
    orig_provider = sub._get_spatial_query  # bound method
    call_count = {"n": 0}
    def _spy_provider():
        call_count["n"] += 1
        sq = orig_provider()
        SQ_INSTANCES.append(sq)
        _capture_sq_positions(sq)
        _stamp("PROVIDER.call", call_n=call_count["n"],
               sq_id=id(sq), sq_type=type(sq).__name__,
               has_npc_positions=getattr(sq, "_npc_positions", None) is not None,
               npc_count=len(getattr(sq, "_npc_positions", {}) or {}),
               npc_ids=sorted(list((getattr(sq, "_npc_positions", {}) or {}).keys())),
               has_player="player" in (getattr(sq, "_npc_positions", {}) or {}),
               has_maid_lusya="maid_lusya" in (getattr(sq, "_npc_positions", {}) or {}),
               snapshot=_POS_SNAPSHOT.get(id(sq), {}))
        if not getattr(sq, "_distance_wrapped", False):
            orig_dist = sq.distance
            def _spy_distance(a, b, _orig=orig_dist, _sq_id=id(sq)):
                d = _orig(a, b)
                snap = _POS_SNAPSHOT.get(_sq_id, {})
                pa = snap.get(a, "?")
                pb = snap.get(b, "?")
                DISTANCE_CALLS.append({"a": a, "b": b, "pos_a": pa, "pos_b": pb, "dist": d})
                print(f"[DIST] {a} -> {b}: dist={d:.4f}")
                return d
            sq.distance = _spy_distance  # type: ignore
            sq._distance_wrapped = True
            _stamp("PATCH.distance", sq_id=id(sq), wrapped=True)
        return sq
    sub._get_spatial_query = _spy_provider  # type: ignore
    return {"sub": sub}

# === Patch subscriber.on_claim_event: wrap, run, capture _listeners afterwards ===
def patch_on_claim_event(loop: Any) -> Optional[Any]:
    sub = getattr(loop, "_claim_event_subscriber", None)
    if sub is None: return None
    orig = sub.on_claim_event
    def _spy_on_claim(event):
        _stamp("A3.on_claim_event:ENTER",
               event_type=getattr(event, "type", "?"),
               source=getattr(event, "source", "?"),
               target_id=(getattr(event, "payload", {}) or {}).get("target_id"))
        # Patch PerceptualKernel.can_observe AT INSTANCE LEVEL only for this call
        # (avoid class-level patches that caused hang in v2)
        from app.models.npc_state import PerceptualKernel
        orig_co = PerceptualKernel.can_observe
        def _spy_co(event_arg, distance, observer_id, target_id=None):
            result = orig_co(event_arg, distance, observer_id, target_id)
            CAN_OBSERVE_CALLS.append({
                "event_type": getattr(event_arg, "type", "?"),
                "visibility": getattr(event_arg, "visibility", "?"),
                "radius": getattr(event_arg, "radius", "?"),
                "observer_id": observer_id, "target_id": target_id,
                "distance": distance, "result": result,
            })
            print(f"[CO] event={getattr(event_arg, 'type', '?')} obs={observer_id} tgt={target_id} dist={distance:.4f} radius={getattr(event_arg, 'radius', '?')} -> {result}")
            return result
        PerceptualKernel.can_observe = staticmethod(_spy_co)  # type: ignore
        try:
            result = orig(event)
        finally:
            # Restore immediately after call
            PerceptualKernel.can_observe = orig_co  # type: ignore
        _stamp("A3.on_claim_event:EXIT", result_type=type(result).__name__)
        return result
    sub.on_claim_event = _spy_on_claim  # type: ignore
    return sub

# === Patch engine.revise at class level (safe — only called inside try/except in subscriber) ===
def patch_engine_revise():
    orig_revise = BeliefRevisionEngine.revise
    def _spy_revise(self_e, *args, **kwargs):
        listener_id = args[0] if args else kwargs.get("listener_id", "?")
        claim = args[1] if len(args) > 1 else kwargs.get("claim", None)
        prop_str = ""
        if claim is not None and getattr(claim, "proposition", None) is not None:
            p = claim.proposition
            prop_str = f"{p.subject_id}/{p.predicate.value}/{p.object_id}"
        _stamp("A4.revise:ENTER", listener=listener_id, prop=prop_str,
               speaker=getattr(claim, "speaker_id", "?"))
        result = orig_revise(self_e, *args, **kwargs)
        _stamp("A4.revise:EXIT", conf=getattr(result, "confidence", None))
        return result
    BeliefRevisionEngine.revise = _spy_revise  # type: ignore

# === Patch bus.publish for trace ===
def patch_bus():
    bus = get_event_bus()
    orig_pub = bus.publish
    def _spy_pub(evt):
        _stamp("BUS.publish", event_type=getattr(evt, "type", "?"),
               source=getattr(evt, "source", "?"),
               target_id=(getattr(evt, "payload", {}) or {}).get("target_id"))
        return orig_pub(evt)
    bus.publish = _spy_pub  # type: ignore

# === Initialize scene explicitly ===
def init_scene(loop: Any, campaign_id: str = "Open_road", location: str = "tavern") -> Dict[str, Any]:
    _stamp("INIT.scene:START", campaign=campaign_id, location=location)
    scene = loop.scene_manager.get_scene_state(campaign_id, location)
    if scene is None:
        scene = loop.scene_manager.initialize_scene(campaign_id, location, "12:00")
    pos = scene.get("npc_positions", {}) or {}
    _stamp("INIT.scene",
           npc_count=len(pos),
           npc_ids=sorted(list(pos.keys())))
    pl = pos.get("player", {})
    ml = pos.get("maid_lusya", {})
    _stamp("INIT.player_pos",
           local_pos=pl.get("local_position"),
           position=pl.get("position"))
    _stamp("INIT.maid_lusya_pos",
           local_pos=ml.get("local_position"),
           position=ml.get("position"))
    # Compute expected euclidean distance
    pl_lp = pl.get("local_position") or {}
    ml_lp = ml.get("local_position") or {}
    if pl_lp and ml_lp:
        try:
            dx = float(pl_lp.get("x", 0)) - float(ml_lp.get("x", 0))
            dy = float(pl_lp.get("y", 0)) - float(ml_lp.get("y", 0))
            d = math.sqrt(dx*dx + dy*dy)
            _stamp("INIT.expected_distance", dx=dx, dy=dy, euclidean=d, threshold=10.0,
                   exceeds_threshold=d > 10.0, by=d - 10.0)
        except Exception as e:
            _stamp("INIT.expected_distance", error=str(e)[:100])
    return scene

# === Publish PLAYER_INSULTS ===
def publish_insult(target_id: str = "maid_lusya"):
    _stamp("=== TRACK A: PLAYER_INSULTS ===", target=target_id)
    payload = {
        "action_type": "player_insults",
        "target_id": target_id,
        "content": "оскорбление",
        "event_tick": 1,
        "visibility": "public",
        "radius": 10.0,
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
    _stamp("A1.publish", event_id=str(evt.id), target_id=target_id,
           radius=evt.radius, visibility=evt.visibility)
    get_event_bus().publish(evt)

# === MAIN ===
def main() -> int:
    print("\n" + "=" * 78)
    print("P5-A Step 2.4 — Spatial Membrane Forensics (v3)")
    print("Baseline: 72cf47b0658ffe8cae6351213ddbfb3b48f2e6d2")
    print("=" * 78)
    print(f"DATA_DIR={settings.data_dir}")

    try: get_event_bus().clear()
    except Exception: pass

    loop = None
    temp_dir = None
    try:
        loop, temp_dir = build_test_loop()
        _stamp("HARNESS.built", temp_dir=str(temp_dir))

        # 1. Initialize scene explicitly
        scene = init_scene(loop, "Open_road", "tavern")
        if scene is None:
            _stamp("FATAL", reason="scene init failed")
            return 1

        # 2. Patch subscriber: capture _sq + wrap distance
        patch_info = patch_subscriber_for_capture(loop)
        sub = patch_info.get("sub")
        if sub is None:
            _stamp("FATAL", reason="no subscriber")
            return 1

        # 3. Patch on_claim_event for can_observe capture (instance-level)
        patch_on_claim_event(loop)
        # 4. Patch engine.revise at class level (safe, called only inside try/except)
        patch_engine_revise()
        # 5. Patch bus.publish
        patch_bus()

        # 6. Wrap store.upsert for trace
        store = getattr(sub, "_store", None)
        if store is not None:
            orig_up = store.upsert
            def _spy_upsert(record):
                _stamp("A5.upsert:ENTER",
                       agent=getattr(record, "agent_id", "?"),
                       conf=getattr(record, "confidence", None))
                return orig_up(record)
            store.upsert = _spy_upsert  # type: ignore

        _stamp("HARNESS.spies", all_attached=True)

        # 7. Run twice for reproducibility
        for run_i in [1, 2]:
            _stamp(f"=== RUN {run_i} ===")
            CAN_OBSERVE_CALLS.clear()
            DISTANCE_CALLS.clear()
            SQ_INSTANCES.clear()

            publish_insult(target_id="maid_lusya")

            _stamp(f"RUN{run_i}.can_observe.summary",
                   count=len(CAN_OBSERVE_CALLS),
                   calls=CAN_OBSERVE_CALLS)
            _stamp(f"RUN{run_i}.distance.summary",
                   count=len(DISTANCE_CALLS),
                   calls=DISTANCE_CALLS)

            # Verify belief
            if store is not None:
                prop = Proposition(subject_id="player", predicate=Predicate.INSULTED,
                                   object_id="maid_lusya", polarity=True)
                rec = store.get("maid_lusya", prop)
                _stamp(f"RUN{run_i}.belief",
                       present=rec is not None,
                       conf=getattr(rec, "confidence", None),
                       source=getattr(rec, "source_id", None))

        print("\n" + "=" * 78)
        print("FORENSIC REPORT — Step 2.4")
        print("=" * 78)
        print(f"\nTotal SPY entries: {len(SPY_LOG)}")
        return 0
    except Exception as e:
        print(f"\n[FATAL] {type(e).__name__}: {e}")
        traceback.print_exc()
        return 1
    finally:
        if loop is not None and temp_dir is not None:
            cleanup(loop, temp_dir)

if __name__ == "__main__":
    sys.exit(main())