# path: /project/backend/tests/gameplay/test_p5_production_save_load.py
# Назначение: P5 — полноценный production save/load через JsonPersistenceAdapter.
#   EpistemicStore → scene_state → JSON file → load → restore → verify.
#   + автономность Люси (canonical maid disposition).
# Зависимости: app.services.state.json_persistence_adapter, app.services.npc.epistemic_store
# Запуск: cd backend; python -m pytest tests/gameplay/test_p5_production_save_load.py -v -s

"""
P5: Production SQLite/JSON Save/Load — cognitive continuity after restart.

Tests the REAL production persistence path:
  EpistemicStore.to_dict() → scene_state["epistemic_records"]
  → JsonPersistenceAdapter.save_scene_at → JSON file
  → JsonPersistenceAdapter.load_scene_at → loaded scene_state
  → EpistemicStore.from_dict → restored store

L1: data exists and is correctly saved (JSON file)
L2: new process restores data in correct NPC
L3: CognitionContextResolver + DialogueExecutor receive restored data
"""
import json
import tempfile
from pathlib import Path

from app.domain.epistemology import EpistemicRecord, Predicate, Proposition
from app.domain.epistemic_dispositions import EPISTEMIC_DISPOSITIONS
from app.services.execution.dialogue_executor import DialogueExecutor
from app.services.npc.epistemic_store import EpistemicStore
from app.services.state.json_persistence_adapter import JsonPersistenceAdapter


def _rec(agent, subj, pred, obj, polarity=True, conf=0.5, source="maid_lusya"):
    return EpistemicRecord(
        agent_id=agent,
        proposition=Proposition(subject_id=subj, predicate=pred, object_id=obj, polarity=polarity),
        confidence=conf, source_id=source, source_claim_id=f"c-{agent}-{polarity}",
        first_observed_tick=1, last_updated_tick=3,
        source_type="testimony", original_source_id="player",
    )


def _make_scene_state(store, npc_states=None):
    """Build scene_state with epistemic_records + npc_states (causal_ledger)."""
    scene = {
        "location_id": "tavern",
        "tick": 3,
        "game_time_seconds": 30.0,
        "epistemic_records": store.to_dict(),
    }
    if npc_states:
        scene["npc_states"] = npc_states
    return scene


class TestP5ProductionSaveLoad:
    """P5: Production save/load through JsonPersistenceAdapter."""

    def _setup_adapter(self):
        """Create temp dir + JsonPersistenceAdapter."""
        tmpdir = Path(tempfile.mkdtemp(prefix="p5_"))
        adapter = JsonPersistenceAdapter(data_dir=tmpdir, saves_dir=tmpdir / "saves")
        return adapter, tmpdir

    def test_L1_L2_epistemic_store_survives_json_persistence(self) -> None:
        """L1+L2: EpistemicStore → JSON → load → restore. Full production path."""
        store = EpistemicStore()
        store.upsert(_rec("tavern_keeper_tornin", "player", Predicate.INSULTED, "tornin", polarity=True, conf=0.5))
        store.upsert(_rec("tavern_keeper_tornin", "player", Predicate.INSULTED, "tornin", polarity=False, conf=0.3, source="guard_borko"))

        adapter, _ = self._setup_adapter()
        scene = _make_scene_state(store)
        adapter.save_scene_at("Open_road", "tavern", scene)

        # Verify JSON file exists
        campaign_file = adapter._saves_dir / "Open_road" / "campaign_state.json"
        assert campaign_file.exists(), "JSON file not created"

        # Load
        loaded = adapter.load_scene_at("Open_road", "tavern")
        assert loaded is not None, "load returned None"
        assert "epistemic_records" in loaded, "epistemic_records missing from loaded scene"

        # Restore
        store2 = EpistemicStore.from_dict(loaded["epistemic_records"])
        pos = store2.get("tavern_keeper_tornin", Proposition(
            "player", Predicate.INSULTED, "tornin", polarity=True))
        neg = store2.get("tavern_keeper_tornin", Proposition(
            "player", Predicate.INSULTED, "tornin", polarity=False))

        assert pos is not None, "positive record lost after production save/load"
        assert neg is not None, "negative record lost after production save/load"
        assert pos.confidence == 0.5, f"confidence changed: {pos.confidence}"
        assert neg.source_id == "guard_borko", f"source changed: {neg.source_id}"
        print("[L1+L2] EpistemicStore survived production save/load")

    def test_L1_causal_ledger_survives_json_persistence(self) -> None:
        """L1: causal_ledger in npc_states survives JSON persistence."""
        npc_states = {
            "tavern_keeper_tornin": {
                "npc_id": "tavern_keeper_tornin",
                "causal_ledger": [
                    {"npc_id": "tavern_keeper_tornin", "field": "trust", "delta": -5.0,
                     "source": "player_insults", "tick": 3, "persistence_time": 0,
                     "emotional_impact": 0.25, "cause": None},
                ],
            },
        }
        store = EpistemicStore()
        adapter, _ = self._setup_adapter()
        scene = _make_scene_state(store, npc_states)
        adapter.save_scene_at("Open_road", "tavern", scene)

        loaded = adapter.load_scene_at("Open_road", "tavern")
        loaded_npc = loaded.get("npc_states", {}).get("tavern_keeper_tornin", {})
        ledger = loaded_npc.get("causal_ledger", [])
        assert len(ledger) == 1, f"causal_ledger lost: {len(ledger)} entries"
        assert ledger[0]["field"] == "trust"
        assert ledger[0]["source"] == "player_insults"
        print("[L1] causal_ledger survived production save/load")

    def test_L3_restored_store_accessible_by_dialogue_executor(self) -> None:
        """L3: DialogueExecutor._format_contradictions works with restored store."""
        store = EpistemicStore()
        store.upsert(_rec("tornin", "player", Predicate.INSULTED, "tornin", polarity=True, conf=0.5))
        store.upsert(_rec("tornin", "player", Predicate.INSULTED, "tornin", polarity=False, conf=0.3, source="guard_borko"))

        adapter, _ = self._setup_adapter()
        scene = _make_scene_state(store)
        adapter.save_scene_at("Open_road", "tavern", scene)

        # Load + restore
        loaded = adapter.load_scene_at("Open_road", "tavern")
        store2 = EpistemicStore.from_dict(loaded["epistemic_records"])

        # L3: DialogueExecutor can use restored store
        de = DialogueExecutor(epistemic_store=store2)
        result = de._format_contradictions("tornin", "Open_road")
        print(f"[L3] Contradictions after load:\n{result}")
        assert "НЕ" in result, "negation not visible after production load"
        assert "guard_borko" in result, "source not visible after load"
        assert "0.30" in result, "confidence not visible after load"

    def test_L3_restored_causal_context_accessible(self) -> None:
        """L3: _format_causal_context works with restored causal_ledger."""
        npc_states = {
            "tornin": {
                "npc_id": "tornin",
                "causal_ledger": [
                    {"npc_id": "tornin", "field": "trust", "delta": -5.0,
                     "source": "player_insults", "tick": 3, "persistence_time": 0,
                     "emotional_impact": 0.25, "cause": None},
                ],
            },
        }
        store = EpistemicStore()
        adapter, _ = self._setup_adapter()
        scene = _make_scene_state(store, npc_states)
        adapter.save_scene_at("Open_road", "tavern", scene)

        loaded = adapter.load_scene_at("Open_road", "tavern")
        loaded_npc = loaded.get("npc_states", {}).get("tornin", {})
        ledger = loaded_npc.get("causal_ledger", [])

        de = DialogueExecutor()
        result = de._format_causal_context(ledger)
        print(f"[L3] Causal context after load:\n{result}")
        assert "доверие" in result, "trust field not in causal context after load"
        assert "player_insults" in result, "source not in causal context after load"

    def test_C_no_duplicates_after_production_load(self) -> None:
        """C: production save/load doesn't create duplicates."""
        store = EpistemicStore()
        store.upsert(_rec("tornin", "player", Predicate.INSULTED, "tornin", conf=0.5))
        adapter, _ = self._setup_adapter()
        scene = _make_scene_state(store)
        adapter.save_scene_at("Open_road", "tavern", scene)

        loaded = adapter.load_scene_at("Open_road", "tavern")
        store2 = EpistemicStore.from_dict(loaded["epistemic_records"])
        all_records = store2.get_all_for_agent("tornin")
        assert len(all_records) == 1, f"duplicates after load: {len(all_records)}"

    def test_C_contradiction_survives_production_save_load(self) -> None:
        """C: polarity=False survives full JSON persistence (not just to_dict)."""
        store = EpistemicStore()
        store.upsert(_rec("tornin", "player", Predicate.INSULTED, "tornin", polarity=True))
        store.upsert(_rec("tornin", "player", Predicate.INSULTED, "tornin", polarity=False, conf=0.3, source="guard_borko"))
        adapter, _ = self._setup_adapter()
        scene = _make_scene_state(store)
        adapter.save_scene_at("Open_road", "tavern", scene)

        loaded = adapter.load_scene_at("Open_road", "tavern")
        store2 = EpistemicStore.from_dict(loaded["epistemic_records"])
        all_records = store2.get_all_for_agent("tornin")
        assert len(all_records) == 2, f"lost records: {len(all_records)}"
        polarities = [r.proposition.polarity for r in all_records]
        assert True in polarities and False in polarities, "polarity lost"

    def test_C_unknown_agent_none_after_production_load(self) -> None:
        """C: unknown agent → None after production load (no fabrication)."""
        store = EpistemicStore()
        store.upsert(_rec("tornin", "player", Predicate.INSULTED, "tornin"))
        adapter, _ = self._setup_adapter()
        scene = _make_scene_state(store)
        adapter.save_scene_at("Open_road", "tavern", scene)

        loaded = adapter.load_scene_at("Open_road", "tavern")
        store2 = EpistemicStore.from_dict(loaded["epistemic_records"])
        record = store2.get("unknown_agent")
        assert record is None, "unknown agent fabricated after load"

    def test_C_provenance_survives_production_save_load(self) -> None:
        """C: source_type + original_source_id survive JSON persistence."""
        store = EpistemicStore()
        store.upsert(EpistemicRecord(
            agent_id="tornin",
            proposition=Proposition("player", Predicate.INSULTED, "tornin"),
            confidence=0.5, source_id="maid_lusya", source_claim_id="c1",
            first_observed_tick=3, last_updated_tick=7,
            source_type="testimony", original_source_id="player",
        ))
        adapter, _ = self._setup_adapter()
        scene = _make_scene_state(store)
        adapter.save_scene_at("Open_road", "tavern", scene)

        loaded = adapter.load_scene_at("Open_road", "tavern")
        store2 = EpistemicStore.from_dict(loaded["epistemic_records"])
        record = store2.get("tornin", Proposition("player", Predicate.INSULTED, "tornin"))
        assert record.source_type == "testimony", f"source_type: {record.source_type}"
        assert record.original_source_id == "player", f"original: {record.original_source_id}"
        assert record.first_observed_tick == 3
        assert record.last_updated_tick == 7
        print(f"[C] Provenance after load: source_type={record.source_type} original={record.original_source_id}")


class TestAutonomyLusya:
    """Autonomy: Lusya can autonomously spread rumor (canonical disposition)."""

    def test_canonical_maid_disposition_supports_spread_rumor(self) -> None:
        """Autonomy: canonical maid has spread_rumor > 0 (no override needed)."""
        maid = EPISTEMIC_DISPOSITIONS.get("maid", {})
        assert maid.get("spread_rumor", 0) > 0, "maid has no spread_rumor"
        print(f"[Autonomy] maid disposition: {maid}")
        print(f"  spread_rumor={maid['spread_rumor']} (dominant intent)")

    def test_spread_rumor_is_dominant_for_maid(self) -> None:
        """Autonomy: spread_rumor is the highest-weight intent for maid."""
        maid = EPISTEMIC_DISPOSITIONS.get("maid", {})
        max_intent = max(maid, key=maid.get)
        assert max_intent == "spread_rumor", f"dominant intent is {max_intent}, not spread_rumor"
        print(f"[Autonomy] Dominant intent for maid: {max_intent}={maid[max_intent]}")

    def test_override_in_P1_was_unnecessary(self) -> None:
        """Autonomy: P1 override (1.4) vs canonical (1.3) — minimal difference."""
        maid = EPISTEMIC_DISPOSITIONS.get("maid", {})
        canonical = maid.get("spread_rumor", 0)
        override = 1.4  # from P1 _override_witness_disposition
        assert canonical > 0, "canonical spread_rumor is 0"
        assert canonical >= override * 0.9, f"canonical {canonical} << override {override}"
        print(f"[Autonomy] Canonical={canonical} vs P1 override={override} — override was unnecessary")