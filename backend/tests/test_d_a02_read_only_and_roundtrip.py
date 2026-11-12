"""D-A02 (A2): DecisionHub.compute() READ ONLY + pressure_accumulator round-trip.

WARA §12.2 (Устав): npc_state.pressure_accumulator → DEBT, organ=relationship,
terminal=decision (causality_manifest.py:141) — персистенция обязательна.

Тесты построены по §13.4 Устава (No Constructor Synthesis):
  - state создаётся через NPCStateAdapter.from_legacy (реальная фабрика),
  - personality — точный конструктор из test_contracts_stage6.py:201-208,
  - EffectiveDrives — _MOCK_DRIVES, буквально из test_contracts_stage6.py:27.

Прямая мутация state.pressure_accumulator запрещена гвардом NPCState.__setattr__
(_ALLOWED_WRITERS) — не тест, а архитектурный замок.
"""

import pytest
from unittest.mock import MagicMock
from app.domain.identity_events import EffectiveDrives
from app.models.npc_profile import NPCProfileL0, PsycheBase
from app.models.npc_state import Intent, NPCState, NPCStateAdapter
from app.models.state_delta import StateDeltas
from app.services.npc.decision_hub import DecisionHub, EventContext
from app.services.npc.state_applicator import StateApplicator


# Точный образец из test_contracts_stage6.py:27
_MOCK_DRIVES = EffectiveDrives.from_dict(
    {"control": 0.5, "significance": 0.5, "fear": 0.5, "desire": 0.5}
)


def _make_base_dict(**overrides):
    """Минимальный runtime-dict для from_legacy (реальная persistence)."""
    d = {
        "npc_id": "npc_test",
        "id": "npc_test",
        "psyche": {},
        "social_stats": {},
        "drives": {
            "control": 0.25,
            "significance": 0.25,
            "fear": 0.25,
            "desire": 0.25,
        },
    }
    d.update(overrides)
    return d


def _make_personality():
    """Точный конструктор из test_contracts_stage6.py:201-208."""
    return NPCProfileL0(
        id="npc_test",
        name="Тест",
        tier="mass",
        drives_base={
            "control": 0.5,
            "significance": 0.5,
            "fear": 0.5,
            "desire": 0.5,
        },
        psyche_base=PsycheBase(willpower=50, breakpoint=80),
        voice_profile="neutral",
    )


def _pressure_updates(result):
    """Извлекает pressure_accumulator_update из всех дельт result."""
    updates = {}
    for d in result.deltas or []:
        pu = getattr(d, "pressure_accumulator_update", None)
        if pu:
            updates.update(pu)
    return updates


# ── T1: WARA round-trip (to_persistence_dict ↔ from_legacy) ──
def test_pressure_accumulator_wara_roundtrip():
    real_dict = _make_base_dict(
        pressure_accumulator={"idle|flee": 0.4, "observe|approach": 0.9}
    )
    state = NPCStateAdapter.from_legacy(real_dict)
    assert state.pressure_accumulator == {
        ("idle", "flee"): 0.4,
        ("observe", "approach"): 0.9,
    }

    out = {}
    NPCState.to_persistence_dict(state, out)
    assert out["pressure_accumulator"] == {
        "idle|flee": 0.4,
        "observe|approach": 0.9,
    }

    restored = NPCStateAdapter.from_legacy(out)
    assert restored.pressure_accumulator == state.pressure_accumulator


# ── T2: apply_batch применяет pressure из дельты ──
def test_apply_batch_applies_pressure_update():
    app = StateApplicator(relationship_store=MagicMock())
    npc_dict = _make_base_dict()
    app.apply_batch(
        [
            StateDeltas(
                npc_id="npc_test",
                pressure_accumulator_update={("idle", "flee"): 0.7},
                source="test",
            )
        ],
        [npc_dict],
        "campaign_test",
    )
    assert npc_dict["pressure_accumulator"] == {"idle|flee": 0.7}


# ── T3: None pressure → no write ──
def test_apply_batch_skips_none_pressure():
    app = StateApplicator(relationship_store=MagicMock())
    npc_dict = _make_base_dict()
    app.apply_batch(
        [StateDeltas(npc_id="npc_test", intent=Intent.OBSERVE, source="test")],
        [npc_dict],
        "campaign_test",
    )
    assert npc_dict.get("pressure_accumulator", {}) == {}


# ── T4: StateDeltas accepts optional pressure field ──
def test_state_deltas_pressure_field_optional():
    d = StateDeltas(npc_id="x", pressure_accumulator_update={("a", "b"): 0.5})
    assert d.pressure_accumulator_update == {("a", "b"): 0.5}
    d2 = StateDeltas(npc_id="x")
    assert d2.pressure_accumulator_update is None


# ── T5: compute() does NOT mutate state.pressure_accumulator ──
def test_compute_does_not_mutate_pressure_accumulator():
    real_dict = _make_base_dict(
        intent=Intent.OBSERVE.value,
        pressure_accumulator={"observe|flee": 0.4},
    )
    state = NPCStateAdapter.from_legacy(real_dict)
    snapshot = dict(state.pressure_accumulator)

    hub = DecisionHub(seed=42)
    hub.compute(
        state=state,
        personality=_make_personality(),
        event=EventContext(event_type="player_interacts", actor_id="player"),
        effective_drives=_MOCK_DRIVES,
    )

    assert state.pressure_accumulator == snapshot, (
        "READ ONLY контракт нарушен: compute() мутировал state.pressure_accumulator"
    )


# ── T6: replay determinism ──
def test_compute_replay_deterministic():
    real_dict = _make_base_dict(
        intent=Intent.OBSERVE.value,
        pressure_accumulator={"observe|flee": 0.4},
    )
    personality = _make_personality()
    event = EventContext(event_type="player_interacts", actor_id="player")

    def run_once():
        state = NPCStateAdapter.from_legacy(dict(real_dict))
        hub = DecisionHub(seed=42)
        result = hub.compute(
            state=state,
            personality=personality,
            event=event,
            effective_drives=_MOCK_DRIVES,
        )
        return _pressure_updates(result)

    assert run_once() == run_once(), "replay-nondeterminism в pressure_updates"