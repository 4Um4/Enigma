# backend/tests/test_break_progress_engine_r64.py
# $env:PYTHONPATH="."; pytest tests/test_break_progress_engine_r64.py -v
"""
Назначение: Unit-тесты R6.4 — BreakProgressEngine и BreakDeltas,
            включая тик-независимый расчёт pressure, identity_integrity_delta,
            pressure_resistance_delta, will_state_override и стадий слома
            (resistance → cracks → rationalization → adaptation → deformation).
            Полная интеграция с NPCState (fear, stress, identity_integrity, will_state,
            pressure_resistance).
Зависимости: pytest, break_progress_engine.py, npc_state.py
"""

import pytest
from app.models.npc_state import WillState
from app.services.npc.break_progress_engine import BreakDeltas, BreakProgressEngine

# ====================== Fixtures ======================


class MinimalNPCState:
    def __init__(self, npc_id: str = "test_npc", **kwargs):
        self.npc_id = npc_id
        self.fear = kwargs.get("fear", 0.0)
        self.stress = kwargs.get("stress", 0.0)
        self.identity_integrity = kwargs.get("identity_integrity", 1.0)
        self.pressure_resistance = kwargs.get("pressure_resistance", 0.0)
        self.will_state = kwargs.get("will_state", WillState.FREE)
        self.relationship_cache = kwargs.get("relationship_cache", {})
        self.state_modifiers = kwargs.get("state_modifiers", {})
        self.resentment = kwargs.get("resentment", 0.0)
        self.dependency = kwargs.get("dependency", 0.0)


@pytest.fixture
def npc_state():
    return MinimalNPCState()


# ====================== Core ======================


def test_calculate_returns_break_deltas(npc_state):
    deltas = BreakProgressEngine.calculate(npc_state)
    assert isinstance(deltas, BreakDeltas)


# ====================== Stage logic ======================


@pytest.mark.parametrize(
    "integrity, expected_stage",
    [
        (0.9, "resistance"),
        (0.7, "cracks"),
        (0.5, "rationalization"),
        (0.3, "adaptation"),
        (0.1, "deformation"),
    ],
)
def test_stages_by_integrity(npc_state, integrity, expected_stage):
    npc_state.identity_integrity = integrity
    deltas = BreakProgressEngine.calculate(npc_state)

    assert deltas.stage == expected_stage


def test_stage_monotonicity(npc_state):
    """Чем ниже integrity — тем сильнее или равно падение."""
    npc_state.fear = 0.6
    npc_state.stress = 40.0

    npc_state.identity_integrity = 0.9
    d1 = BreakProgressEngine.calculate(npc_state)

    npc_state.identity_integrity = 0.5
    d2 = BreakProgressEngine.calculate(npc_state)

    npc_state.identity_integrity = 0.1
    d3 = BreakProgressEngine.calculate(npc_state)

    assert d2.identity_integrity_delta <= d1.identity_integrity_delta
    assert d3.identity_integrity_delta <= d2.identity_integrity_delta


# ====================== Pressure effects ======================


def test_pressure_increases_damage(npc_state):
    npc_state.identity_integrity = 0.5

    npc_state.fear = 0.1
    npc_state.stress = 10
    low = BreakProgressEngine.calculate(npc_state)

    npc_state.fear = 0.9
    npc_state.stress = 80
    high = BreakProgressEngine.calculate(npc_state)

    assert high.identity_integrity_delta < low.identity_integrity_delta


def test_support_reduces_pressure(npc_state):
    npc_state.fear = 0.8
    npc_state.stress = 60

    no_support = BreakProgressEngine.calculate(npc_state, support_present=False)
    with_support = BreakProgressEngine.calculate(npc_state, support_present=True)

    assert with_support.identity_integrity_delta > no_support.identity_integrity_delta


def test_recent_failures_increase_pressure(npc_state):
    npc_state.identity_integrity = 0.5

    no_fail = BreakProgressEngine.calculate(npc_state, recent_failures=0)
    with_fail = BreakProgressEngine.calculate(npc_state, recent_failures=5)

    assert with_fail.identity_integrity_delta < no_fail.identity_integrity_delta


# ====================== Extreme states ======================


def test_high_pressure_can_break(npc_state):
    npc_state.identity_integrity = 0.1
    npc_state.fear = 1.0
    npc_state.stress = 100.0
    npc_state.will_state = WillState.COERCED

    deltas = BreakProgressEngine.calculate(npc_state, recent_failures=5)

    assert deltas.stage == "deformation"
    assert deltas.identity_integrity_delta < -0.05
    assert deltas.will_state_override in (None, WillState.BROKEN)


def test_integrity_always_decreases(npc_state):
    npc_state.identity_integrity = 1.0
    deltas = BreakProgressEngine.calculate(npc_state)

    assert deltas.identity_integrity_delta < 0


def test_integrity_near_zero(npc_state):
    npc_state.identity_integrity = 0.01
    npc_state.fear = 1.0
    npc_state.stress = 100.0

    deltas = BreakProgressEngine.calculate(npc_state)

    assert deltas.identity_integrity_delta < 0


# ====================== Resistance ======================


def test_pressure_resistance_behavior(npc_state):
    npc_state.fear = 0.1
    npc_state.stress = 10
    low = BreakProgressEngine.calculate(npc_state)

    npc_state.fear = 0.95
    npc_state.stress = 90
    high = BreakProgressEngine.calculate(npc_state)

    assert high.pressure_resistance_delta >= low.pressure_resistance_delta


# ====================== Defaults ======================


def test_default_values_when_state_empty():
    state = MinimalNPCState()

    deltas = BreakProgressEngine.calculate(state)

    assert deltas.stage == "resistance"
    assert deltas.identity_integrity_delta < 0
    assert deltas.will_state_override is None


# ====================== Immutability ======================


def test_break_deltas_immutability():
    deltas = BreakDeltas(
        identity_integrity_delta=-0.05, pressure_resistance_delta=0.01, stage="cracks", will_state_override=None
    )

    with pytest.raises(AttributeError):
        deltas.stage = "broken"
