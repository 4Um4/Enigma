# path: /project/backend/tests/gameplay/test_priority4_contradictions.py
# Назначение: Priority 4 — противоречия, save/load, отрицательные сценарии.
#   Part A: polarity=False visible in cognition block
#   Part B: EpistemicStore round-trip (polarity, provenance, confidence)
#   Part C: no fabrication, no duplicates, contradiction survives
# Зависимости: app.services.execution.dialogue_executor, app.services.npc.epistemic_store
# Запуск: cd backend; python -m pytest tests/gameplay/test_priority4_contradictions.py -v -s

"""
Priority 4: Contradictions, save/load, negative scenarios.

Part A: NPC sees BOTH positive (polarity=True) and negative (polarity=False) claims.
Part B: EpistemicStore.to_dict/from_dict preserves polarity, provenance, confidence.
Part C: No fabrication, no duplicates, contradiction survives round-trip.
"""
from app.domain.epistemology import EpistemicRecord, Predicate, Proposition
from app.services.execution.dialogue_executor import DialogueExecutor
from app.services.npc.epistemic_store import EpistemicStore


def _rec(agent, subj, pred, obj, polarity=True, conf=0.5, source="maid_lusya"):
    return EpistemicRecord(
        agent_id=agent,
        proposition=Proposition(subject_id=subj, predicate=pred, object_id=obj, polarity=polarity),
        confidence=conf, source_id=source, source_claim_id=f"c-{agent}-{polarity}",
        first_observed_tick=1, last_updated_tick=1,
        source_type="testimony", original_source_id="player",
    )


class TestPartAContradictions:
    """Part A: polarity=False visible in cognition block."""

    def test_negation_visible_with_source_and_confidence(self) -> None:
        """A: polarity=False → contradictions section with source + confidence."""
        store = EpistemicStore()
        store.upsert(_rec("tornin", "player", Predicate.INSULTED, "tornin", polarity=True, conf=0.5))
        store.upsert(_rec("tornin", "player", Predicate.INSULTED, "tornin", polarity=False, conf=0.3, source="guard_borko"))
        de = DialogueExecutor(epistemic_store=store)
        result = de._format_contradictions("tornin", "Open_road")
        print(f"[A] Contradictions:\n{result}")
        assert "НЕ" in result, "negation missing"
        assert "guard_borko" in result, "source missing"
        assert "0.30" in result, "confidence missing"

    def test_positive_only_no_contradictions(self) -> None:
        """A: only polarity=True → empty contradictions."""
        store = EpistemicStore()
        store.upsert(_rec("tornin", "player", Predicate.INSULTED, "tornin", polarity=True))
        de = DialogueExecutor(epistemic_store=store)
        result = de._format_contradictions("tornin", "Open_road")
        assert result == "", f"expected empty, got: {result!r}"

    def test_both_polarities_coexist_as_separate_records(self) -> None:
        """A: polarity=True and False are separate records (not merged)."""
        store = EpistemicStore()
        store.upsert(_rec("tornin", "player", Predicate.INSULTED, "tornin", polarity=True))
        store.upsert(_rec("tornin", "player", Predicate.INSULTED, "tornin", polarity=False))
        all_records = store.get_all_for_agent("tornin")
        assert len(all_records) == 2, f"expected 2 records, got {len(all_records)}"
        polarities = [r.proposition.polarity for r in all_records]
        assert True in polarities and False in polarities

    def test_cap_at_5_negations(self) -> None:
        """A: >5 negations → only last 5 shown."""
        store = EpistemicStore()
        for i in range(7):
            store.upsert(EpistemicRecord(
                agent_id="tornin",
                proposition=Proposition(subject_id=f"npc_{i}", predicate=Predicate.INSULTED, object_id="tornin", polarity=False),
                confidence=0.1 * i, source_id=f"src_{i}", source_claim_id=f"c_{i}",
                first_observed_tick=i, last_updated_tick=i,
                source_type="testimony", original_source_id=f"src_{i}",
            ))
        de = DialogueExecutor(epistemic_store=store)
        result = de._format_contradictions("tornin", "Open_road")
        assert result.count("•") == 5, f"expected 5 bullets, got {result.count('•')}"


class TestPartBSaveLoad:
    """Part B: EpistemicStore round-trip (to_dict/from_dict)."""

    def test_polarity_preserved_round_trip(self) -> None:
        """B: polarity=False survives to_dict → from_dict."""
        store = EpistemicStore()
        store.upsert(_rec("tornin", "player", Predicate.INSULTED, "tornin", polarity=False, conf=0.3))
        data = store.to_dict()
        store2 = EpistemicStore.from_dict(data)
        record = store2.get("tornin", Proposition(
            subject_id="player", predicate=Predicate.INSULTED, object_id="tornin", polarity=False))
        assert record is not None, "record not found after round-trip"
        assert record.proposition.polarity is False, f"polarity changed: {record.proposition.polarity}"

    def test_provenance_preserved_round_trip(self) -> None:
        """B: source_type, original_source_id, ticks survive round-trip."""
        store = EpistemicStore()
        store.upsert(EpistemicRecord(
            agent_id="tornin",
            proposition=Proposition(subject_id="player", predicate=Predicate.INSULTED, object_id="tornin"),
            confidence=0.5, source_id="maid_lusya", source_claim_id="c1",
            first_observed_tick=3, last_updated_tick=7,
            source_type="testimony", original_source_id="player",
        ))
        data = store.to_dict()
        store2 = EpistemicStore.from_dict(data)
        record = store2.get("tornin", Proposition(
            subject_id="player", predicate=Predicate.INSULTED, object_id="tornin"))
        assert record.source_type == "testimony", f"source_type: {record.source_type}"
        assert record.original_source_id == "player", f"original: {record.original_source_id}"
        assert record.first_observed_tick == 3
        assert record.last_updated_tick == 7

    def test_confidence_preserved_round_trip(self) -> None:
        """B: confidence value survives round-trip."""
        store = EpistemicStore()
        store.upsert(_rec("tornin", "player", Predicate.INSULTED, "tornin", conf=0.42))
        data = store.to_dict()
        store2 = EpistemicStore.from_dict(data)
        record = store2.get("tornin", Proposition(
            subject_id="player", predicate=Predicate.INSULTED, object_id="tornin"))
        assert abs(record.confidence - 0.42) < 0.001, f"confidence: {record.confidence}"

    def test_both_polarities_survive_round_trip(self) -> None:
        """B: both polarity=True and False survive to_dict/from_dict."""
        store = EpistemicStore()
        store.upsert(_rec("tornin", "player", Predicate.INSULTED, "tornin", polarity=True, conf=0.5))
        store.upsert(_rec("tornin", "player", Predicate.INSULTED, "tornin", polarity=False, conf=0.3, source="guard_borko"))
        data = store.to_dict()
        assert len(data) == 2, f"expected 2 serialized, got {len(data)}"
        store2 = EpistemicStore.from_dict(data)
        all_records = store2.get_all_for_agent("tornin")
        assert len(all_records) == 2, f"expected 2 restored, got {len(all_records)}"
        # Contradiction visible after round-trip
        de = DialogueExecutor(epistemic_store=store2)
        result = de._format_contradictions("tornin", "Open_road")
        assert "НЕ" in result, "negation lost after round-trip"


class TestPartCNegativeScenarios:
    """Part C: no fabrication, no duplicates, contradiction survives."""

    def test_empty_store_no_fabrication(self) -> None:
        """C: empty EpistemicStore → empty contradictions (no fabrication)."""
        store = EpistemicStore()
        de = DialogueExecutor(epistemic_store=store)
        result = de._format_contradictions("tornin", "Open_road")
        assert result == "", f"fabricated: {result!r}"

    def test_agent_without_records_no_fabrication(self) -> None:
        """C: agent has no records → no fabricated contradictions."""
        store = EpistemicStore()
        store.upsert(_rec("lusya", "player", Predicate.INSULTED, "tornin"))
        de = DialogueExecutor(epistemic_store=store)
        result = de._format_contradictions("tornin", "Open_road")
        assert result == "", f"fabricated for agent without records: {result!r}"

    def test_no_duplicates_after_round_trip(self) -> None:
        """C: round-trip doesn't create duplicate records."""
        store = EpistemicStore()
        store.upsert(_rec("tornin", "player", Predicate.INSULTED, "tornin", conf=0.5))
        data = store.to_dict()
        store2 = EpistemicStore.from_dict(data)
        all_records = store2.get_all_for_agent("tornin")
        assert len(all_records) == 1, f"duplicates: {len(all_records)}"

    def test_contradiction_survives_round_trip(self) -> None:
        """C: polarity=False survives round-trip (contradiction not lost)."""
        store = EpistemicStore()
        store.upsert(_rec("tornin", "player", Predicate.INSULTED, "tornin", polarity=True))
        store.upsert(_rec("tornin", "player", Predicate.INSULTED, "tornin", polarity=False, conf=0.3, source="guard_borko"))
        data = store.to_dict()
        store2 = EpistemicStore.from_dict(data)
        pos = store2.get("tornin", Proposition(
            subject_id="player", predicate=Predicate.INSULTED, object_id="tornin", polarity=True))
        neg = store2.get("tornin", Proposition(
            subject_id="player", predicate=Predicate.INSULTED, object_id="tornin", polarity=False))
        assert pos is not None and pos.proposition.polarity is True
        assert neg is not None and neg.proposition.polarity is False

    def test_unknown_not_converted_to_confidence_one(self) -> None:
        """C: unknown agent → None (not fabricated as confidence=1.0)."""
        store = EpistemicStore()
        record = store.get("unknown_agent")
        assert record is None, "unknown agent should return None, not fabricated record"