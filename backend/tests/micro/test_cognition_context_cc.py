# backend/tests/micro/test_cognition_context_cc.py
"""COGNITIVE-CONTINUITY-01 CC-core: CognitionContextResolver reads EpistemicStore."""
from app.domain.epistemology import EpistemicRecord, Predicate, Proposition
from app.services.npc.cognition_context import CognitionContextResolver
from app.services.npc.epistemic_store import EpistemicStore


class MockMemory:
    """Mock memory_manager — returns empty session (no STM claims)."""
    def get_dialogue_session(self, campaign_id, npc_id, partner_id="player"):
        from types import SimpleNamespace
        return SimpleNamespace(claims=[], open_questions=[])


def _record(agent, subj, pred, obj, conf=0.5, source="player", source_type="testimony", original="player"):
    return EpistemicRecord(
        agent_id=agent,
        proposition=Proposition(subject_id=subj, predicate=pred, object_id=obj),
        confidence=conf,
        source_id=source,
        source_claim_id="test-claim",
        first_observed_tick=1,
        last_updated_tick=1,
        source_type=source_type,
        original_source_id=original,
    )


def _name_resolver(npc_id):
    names = {"player": "Игрок", "maid_lusya": "Люся", "tavern_keeper_tornin": "Торнин", "guard_borko": "Боро"}
    return {"name": names.get(npc_id, npc_id)}


def test_cognition_reads_epistemic_beliefs():
    """CognitionContextResolver с epistemic_store → блок «Что NPC знает»."""
    store = EpistemicStore()
    store.upsert(_record("maid_lusya", "player", Predicate.INSULTED, "tavern_keeper_tornin"))
    resolver = CognitionContextResolver(MockMemory(), epistemic_store=store, context_provider=_name_resolver)

    block = resolver.resolve_block("maid_lusya")

    assert "Что NPC знает" in block, f"Epistemic block missing: {block}"
    assert "оскорбил" in block, f"Predicate text missing: {block}"
    assert "Торнин" in block, f"Object name not resolved: {block}"
    assert "Игрок" in block, f"Subject name not resolved: {block}"
    assert "testimony" not in block  # source_type is rendered as Russian, not raw


def test_cognition_provenance_testimony():
    """Provenance: testimony → «тебе сообщил(а)»."""
    store = EpistemicStore()
    store.upsert(_record("tavern_keeper_tornin", "player", Predicate.INSULTED, "tavern_keeper_tornin",
                          source="maid_lusya", original="player"))
    resolver = CognitionContextResolver(MockMemory(), epistemic_store=store, context_provider=_name_resolver)

    block = resolver.resolve_block("tavern_keeper_tornin")

    assert "тебе сообщил(а) Люся" in block, f"Source provenance missing: {block}"
    assert "исходный источник — Игрок" in block, f"Original source missing: {block}"


def test_cognition_provenance_direct_observation():
    """Provenance: direct_observation → «ты видел это сам»."""
    store = EpistemicStore()
    store.upsert(_record("maid_lusya", "guard_borko", Predicate.STOLE, "merchant_goran",
                          source="maid_lusya", source_type="direct_observation", original="maid_lusya"))
    resolver = CognitionContextResolver(MockMemory(), epistemic_store=store, context_provider=_name_resolver)

    block = resolver.resolve_block("maid_lusya")

    assert "ты видел это сам" in block, f"Direct observation provenance missing: {block}"
    assert "Боро" in block, f"Subject name not resolved: {block}"


def test_cognition_backward_compatible_no_store():
    """Без epistemic_store → только STM (текущее поведение)."""
    resolver = CognitionContextResolver(MockMemory())
    block = resolver.resolve_block("maid_lusya")
    # No epistemic block, no crash, empty (no STM claims either)
    assert "Что NPC знает" not in block
    assert block == ""  # empty STM + no epistemic