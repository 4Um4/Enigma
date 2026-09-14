"""
path: /project/backend/tests/micro/test_intent_roundtrip.py
[GC-I01-E1] Lock: intent-block round-trip (DEBT-INTENT-SOURCE closure).
[GC-I01-E1b] Delta-route locks: applicator / aggregator / inertia / from_legacy.
v4 (fix2b): StateApplicator requires relationship_store (TypeError-fact);
mock calibrated to disk names (get_pair). Section marker unified: [GC-I01-E1b-tests].
"""
from __future__ import annotations

from unittest.mock import MagicMock

from app.models.npc_state import Intent, NPCState
from app.services.npc.npc_loader import load_l2_state_from_runtime_dict


def _raw_dict() -> dict:
    return {"id": "npc_test", "psyche": {}, "social_stats": {}}


def _state_with_block() -> NPCState:
    return NPCState(
        npc_id="npc_test",
        intent=Intent.FLEE,
        intent_target="player",
        intent_formed_at=41,
        intent_duration=7,
        intent_progress_ticks=5,
        last_intent_change=42,
    )


def _npc_dicts() -> list:
    return [{"npc_id": "npc_test", "id": "npc_test", "psyche": {}, "social_stats": {}}]


# ── E1: projection / round-trip ─────────────────────────────────────────────

def test_projection_writes_full_six_field_block():
    d: dict = {}
    NPCState.to_persistence_dict(_state_with_block(), d)
    assert d["intent"] == "flee"
    assert d["intent_target"] == "player"
    assert d["intent_formed_at"] == 41
    assert d["intent_duration"] == 7
    assert d["intent_progress_ticks"] == 5
    assert d["last_intent_change"] == 42


def test_projection_shape_is_flat_string():
    d: dict = {}
    NPCState.to_persistence_dict(_state_with_block(), d)
    assert isinstance(d["intent"], str)


def test_roundtrip_restores_full_block():
    d: dict = {}
    NPCState.to_persistence_dict(_state_with_block(), d)
    restored = load_l2_state_from_runtime_dict(d)
    assert restored.intent == Intent.FLEE
    assert restored.intent_target == "player"
    assert restored.intent_formed_at == 41
    assert restored.intent_duration == 7
    assert restored.intent_progress_ticks == 5
    assert restored.last_intent_change == 42


def test_prefix_save_without_block_yields_defaults():
    restored = load_l2_state_from_runtime_dict(_raw_dict())
    assert restored.intent is None
    assert restored.intent_target is None
    assert restored.intent_formed_at == 0
    assert restored.intent_duration == 0
    assert restored.intent_progress_ticks == 0
    assert restored.last_intent_change == 0


def test_garbage_intent_string_fails_soft():
    raw = _raw_dict()
    raw["intent"] = "definitely_not_an_intent"
    restored = load_l2_state_from_runtime_dict(raw)
    assert restored.intent is None


def test_none_intent_roundtrips_as_none():
    st = load_l2_state_from_runtime_dict(_raw_dict())
    assert st.intent is None
    d: dict = {}
    NPCState.to_persistence_dict(st, d)
    assert d["intent"] is None
    assert load_l2_state_from_runtime_dict(d).intent is None


# ── [GC-I01-E1b-tests] delta-route locks ───────────────────────────────────

from app.models.state_delta import StateDeltas
from app.services.npc.state_applicator import StateApplicator
from app.services.tick_utils import aggregate_deltas


def _applicator() -> StateApplicator:
    _store = MagicMock()
    _store.get_pair.return_value = {"trust": 0.0, "fear": 0.0}
    _store.update.return_value = None
    return StateApplicator(relationship_store=_store)


def test_intent_delta_writes_state_via_applicator():
    dicts = _npc_dicts()
    _applicator().apply_batch(
        [StateDeltas(npc_id="npc_test", intent=Intent.FLEE, target="player",
                     intent_tick=41, source="decision_hub")],
        dicts, "test",
    )
    assert dicts[0]["intent"] == "flee"
    assert dicts[0]["intent_target"] == "player"
    assert dicts[0]["intent_formed_at"] == 41


def test_intent_delta_merge_survives_aggregation():
    d1 = StateDeltas(npc_id="npc_test", intent=Intent.TALK, intent_tick=40, target="player")
    d2 = StateDeltas(npc_id="npc_test", stress_delta=0.1)
    merged = aggregate_deltas([d1, d2])
    assert any(getattr(m, "intent", None) == Intent.TALK for m in merged)


def test_intent_inertia_over_two_applications():
    dicts = _npc_dicts()
    app = _applicator()
    app.apply_batch([StateDeltas(npc_id="npc_test", intent=Intent.TALK, target="player", intent_tick=41)], dicts, "t")  # [GC-I01-E1b-fix4] TALK требует цель
    app.apply_batch([StateDeltas(npc_id="npc_test", intent=Intent.TALK, target="player", intent_tick=42)], dicts, "t")
    assert dicts[0]["intent"] == "talk"
    assert dicts[0]["intent_duration"] == 1


def test_from_legacy_restores_intent_block():
    d = dict(_raw_dict())
    d.update({"intent": "flee", "intent_target": "player", "intent_formed_at": 41,
              "intent_duration": 7, "intent_progress_ticks": 5, "last_intent_change": 42})
    from app.models.npc_state import NPCStateAdapter
    st = NPCStateAdapter.from_legacy(d)
    assert st.intent == Intent.FLEE
    assert st.intent_duration == 7
