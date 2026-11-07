# backend/tests/sandbox/p5a_step_22_spies.py
"""
P5-A Step 2.2 — Forensic spies для Track A.
НЕ изменяет production-код. monkey-patch через wrapper pattern.
EventDTO.create() — каноническая фабрика (Устав §2.1.1).
"""
from __future__ import annotations
import os, sys, json, traceback, dataclasses, types, uuid
from typing import Any, Dict, List, Optional
from pathlib import Path

_THIS = Path(__file__).resolve()
_BACKEND = _THIS.parent.parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.services.events.event_bus import EventBus
from app.services.events.event_types import EventType
from app.services.npc.belief_revision_engine import BeliefRevisionEngine
from app.services.npc.epistemic_store import EpistemicStore
from app.services.events.claim_event_subscriber import ClaimEventSubscriber
from app.services.npc.trust_based_reliability_provider import TrustBasedReliabilityProvider
from app.domain.epistemology import Proposition, Predicate, ClaimEvent, EpistemicRecord
from app.domain.sanity_membrane import can_address
from app.domain.events import EventDTO

SPY_LOG: List[Dict[str, Any]] = []

def _stamp(tag: str, **kw: Any) -> None:
    SPY_LOG.append({"tag": tag, **kw})
    print(f"[SPY] {tag}: " + json.dumps(kw, ensure_ascii=False, default=str))

def wrap(obj, method_name, tag):
    original = getattr(obj, method_name)
    def wrapper(*args, **kwargs):
        _stamp(f"{tag}:ENTER", args_len=len(args), kwargs_keys=list(kwargs.keys()))
        try:
            result = original(*args, **kwargs)
            _stamp(f"{tag}:EXIT", result_type=type(result).__name__, result_repr=repr(result)[:300])
            return result
        except Exception as e:
            _stamp(f"{tag}:ERROR", error=type(e).__name__, msg=str(e)[:200])
            raise
    setattr(obj, method_name, wrapper)

def build_harness():
    bus = EventBus()
    class _StubRelStore:
        def get_pair(self, cid, src, tgt): return {"trust": 50.0, "fear": 0.0, "affection": 0.0, "debt": 0.0, "respect": 0.0}
        def get_current(self, src, tgt):
            class _S: pass
            s = _S(); s.trust=50.0; s.fear=0.0; s.affection=0.0; s.debt=0.0; s.respect=0.0
            return s
    rel_store = _StubRelStore()
    rp = TrustBasedReliabilityProvider(rel_store, "test_campaign")
    engine = BeliefRevisionEngine(reliability_provider=rp)
    store = EpistemicStore.from_dict([])
    subscriber = ClaimEventSubscriber(engine=engine, store=store, spatial_query_provider=None)
    wrap(subscriber, "on_player_spoke", "A2.on_player_spoke")
    wrap(subscriber, "on_claim_event", "A3.on_claim_event")
    wrap(engine, "revise", "A4.belief_revision_engine.revise")
    wrap(store, "upsert", "A5.epistemic_store.upsert")
    wrap(store, "get", "A5.epistemic_store.get")
    bus.subscribe(EventType.PLAYER_INSULTS, subscriber.on_player_spoke)
    bus.subscribe(EventType.COMMUNICATION_CLAIM, subscriber.on_claim_event)
    return {"bus": bus, "subscriber": subscriber, "engine": engine, "store": store}

def make_player_insults_event(target_id="maid_lusya", source="player"):
    """Канонический EventDTO через EventDTO.create (Устав §2.1.1)."""
    payload = {
        "action_type": "player_insults",
        "target_id": target_id,
        "content": "оскорбление",
        "event_tick": 5,
        "visibility": "public",
        "radius": 10.0,
    }
    evt = EventDTO.create(
        event_type=EventType.PLAYER_INSULTS,
        source=source,
        payload=payload,
        persistence_level="working",
    )
    return evt

def run_scenario():
    h = build_harness()
    bus = h["bus"]; store = h["store"]
    print("\n" + "=" * 70)
    print("SCENARIO: PLAYER_INSULTS -> on_player_spoke -> Proposition -> ClaimEvent")
    print("                            -> BeliefRevisionEngine.revise -> EpistemicStore(maid_lusya)")
    print("=" * 70)
    event = make_player_insults_event(target_id="maid_lusya", source="player")
    _stamp("A1.publish_player_insults",
           event_type=event.type, source=event.source,
           target_id=event.payload.get("target_id"),
           action_type=event.payload.get("action_type"),
           event_id=str(event.id))
    _orig_publish = bus.publish
    def _spy_publish(evt):
        _stamp("A1.bus.publish",
               event_type=getattr(evt, "type", "?"),
               source=getattr(evt, "source", "?"),
               target_id=(getattr(evt, "payload", {}) or {}).get("target_id"))
        return _orig_publish(evt)
    bus.publish = _spy_publish
    bus.publish(event)
    prop_check = Proposition(subject_id="player", predicate=Predicate.INSULTED,
                              object_id="maid_lusya", polarity=True)
    record_for_lusya = store.get("maid_lusya", prop_check)
    _stamp("FINAL.store_check",
           listener="maid_lusya",
           proposition={"subject": "player", "predicate": "INSULTED", "object": "maid_lusya"},
           record_present=record_for_lusya is not None,
           record_conf=getattr(record_for_lusya, "confidence", None),
           record_source=getattr(record_for_lusya, "source_id", None),
           record_orig_src=getattr(record_for_lusya, "original_source_id", None))
    print("\n" + "=" * 70)
    print("SPY TRACE SUMMARY (Track A)")
    print("=" * 70)
    tags_seen = {e["tag"] for e in SPY_LOG}
    summary = {
        "A1.publish_player_insults": "A1.publish_player_insults" in tags_seen,
        "A1.bus.publish:ENTER": "A1.bus.publish:ENTER" in tags_seen,
        "A2.on_player_spoke:ENTER": "A2.on_player_spoke:ENTER" in tags_seen,
        "A2.on_player_spoke:EXIT": "A2.on_player_spoke:EXIT" in tags_seen,
        "A3.on_claim_event:ENTER": "A3.on_claim_event:ENTER" in tags_seen,
        "A3.on_claim_event:EXIT": "A3.on_claim_event:EXIT" in tags_seen,
        "A4.belief_revision_engine.revise:ENTER": "A4.belief_revision_engine.revise:ENTER" in tags_seen,
        "A4.belief_revision_engine.revise:EXIT": "A4.belief_revision_engine.revise:EXIT" in tags_seen,
        "A5.epistemic_store.upsert:ENTER": "A5.epistemic_store.upsert:ENTER" in tags_seen,
        "A5.epistemic_store.upsert:EXIT": "A5.epistemic_store.upsert:EXIT" in tags_seen,
    }
    for k, v in summary.items():
        mark = "OK" if v else "FAIL"
        print(f"  [{mark}] {k}: {v}")
    print("\n" + "=" * 70)
    print("HYPOTHESIS — FIRST POINT OF FAILURE (Track A)")
    print("=" * 70)
    if not summary["A2.on_player_spoke:ENTER"]:
        print("A2: on_player_spoke NOT CALLED. Reason: PLAYER_INSULTS subscription missing / event not dispatched.")
    elif not summary["A3.on_claim_event:ENTER"]:
        print("A3: on_claim_event NOT CALLED. Reason: player_insults branch did not reach on_claim_event")
        print("    (target_id empty in payload, or return on guard 'if _victim:' line 111).")
    elif not summary["A4.belief_revision_engine.revise:ENTER"]:
        print("A4: revise NOT CALLED. Reason: Proposition-guard rejected prop (sanity_membrane / empty fields),")
        print("    OR _listeners empty (spatial_query_provider=None, fallback target_id='maid_lusya' must be added).")
    elif not summary["A5.epistemic_store.upsert:ENTER"]:
        print("A5: upsert NOT CALLED. Reason: revise threw exception.")
    elif record_for_lusya is None:
        print("FINAL: store.get('maid_lusya') -> None. upsert was called, but for ANOTHER listener_id")
        print("       (likely target_id='maid_lusya' was filtered out of _listeners by membrane).")
    else:
        print(f"FULL CHAIN OK. maid_lusya belief: conf={record_for_lusya.confidence},")
        print(f"  source={record_for_lusya.source_id}, original={record_for_lusya.original_source_id}")
    return {"summary": summary, "record_for_lusya": record_for_lusya, "spy_log_count": len(SPY_LOG)}

if __name__ == "__main__":
    try:
        result = run_scenario()
        print(f"\n[DONE] spy_log_entries={result['spy_log_count']}")
        sys.exit(0)
    except Exception as e:
        print(f"\n[FATAL] {type(e).__name__}: {e}")
        traceback.print_exc()
        sys.exit(1)