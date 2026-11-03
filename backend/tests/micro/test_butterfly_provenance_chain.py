# backend/tests/micro/test_butterfly_provenance_chain.py
"""COGNITIVE-CONTINUITY-01: multi-hop provenance chain.

NPC-A (Lusya) hears from player -> tells NPC-B (Tornin) -> tells NPC-C (Borko).
original_source_id must remain "player" through all hops.
source_id changes to the immediate speaker.
"""
from app.domain.epistemology import ClaimEvent, Predicate, Proposition
from app.services.npc.belief_revision_engine import BeliefRevisionEngine
from app.services.npc.epistemic_store import EpistemicStore


class MockReliability:
    def get_reliability(self, observer, source, context=None):
        return 0.5


def _claim(speaker, listener, proposition, tick=1):
    return ClaimEvent(
        event_id=f"evt-{speaker}-{listener}-{tick}",
        claim_id=f"claim-{speaker}-{listener}-{tick}",
        speaker_id=speaker,
        listener_id=listener,
        proposition=proposition,
        tick=tick,
    )


def test_provenance_chain_three_hops():
    """Player -> Lusya -> Tornin -> Borko. original_source_id preserved through 3 hops."""
    store = EpistemicStore()
    engine = BeliefRevisionEngine(MockReliability())
    prop = Proposition(subject_id="player", predicate=Predicate.INSULTED, object_id="tavern_keeper_tornin")

    # Hop 1: Player tells Lusya
    claim1 = _claim("player", "maid_lusya", prop, tick=1)
    r1 = engine.revise("maid_lusya", claim1, store.get("maid_lusya", prop),
                        reliability_context={"source_type": "testimony"})
    store.upsert(r1)

    assert r1.source_id == "player"
    assert r1.original_source_id == "player"
    assert r1.source_type == "testimony"

    # Hop 2: Lusya tells Tornin
    claim2 = _claim("maid_lusya", "tavern_keeper_tornin", prop, tick=10)
    r2 = engine.revise("tavern_keeper_tornin", claim2, store.get("tavern_keeper_tornin", prop),
                        reliability_context={"source_type": "testimony", "original_source_id": "player"})
    store.upsert(r2)

    assert r2.source_id == "maid_lusya", f"Hop 2: source_id should be Lusya, got {r2.source_id}"
    assert r2.original_source_id == "player", f"Hop 2: original_source_id should be player, got {r2.original_source_id}"

    # Hop 3: Tornin tells Borko
    claim3 = _claim("tavern_keeper_tornin", "guard_borko", prop, tick=20)
    r3 = engine.revise("guard_borko", claim3, store.get("guard_borko", prop),
                        reliability_context={"source_type": "testimony", "original_source_id": "player"})
    store.upsert(r3)

    assert r3.source_id == "tavern_keeper_tornin", f"Hop 3: source_id should be Tornin, got {r3.source_id}"
    assert r3.original_source_id == "player", f"Hop 3: original still player after 3 hops, got {r3.original_source_id}"


def test_provenance_round_trip_after_chain():
    """Serialization round-trip preserves provenance after multi-hop chain."""
    store = EpistemicStore()
    engine = BeliefRevisionEngine(MockReliability())
    prop = Proposition(subject_id="player", predicate=Predicate.INSULTED, object_id="tavern_keeper_tornin")

    # Build chain: player -> Lusya -> Tornin -> Borko
    for speaker, listener, tick in [("player", "maid_lusya", 1), ("maid_lusya", "tavern_keeper_tornin", 10), ("tavern_keeper_tornin", "guard_borko", 20)]:
        claim = _claim(speaker, listener, prop, tick=tick)
        r = engine.revise(listener, claim, store.get(listener, prop),
                          reliability_context={"source_type": "testimony", "original_source_id": "player"})
        store.upsert(r)

    # Round-trip
    data = store.to_dict()
    store2 = EpistemicStore.from_dict(data)
    r_borko = store2.get("guard_borko", prop)

    assert r_borko is not None
    assert r_borko.source_id == "tavern_keeper_tornin"
    assert r_borko.original_source_id == "player"
    assert r_borko.source_type == "testimony"