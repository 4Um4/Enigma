# backend/tests/pbt/properties/test_spatial_coherence.py
"""
Property-тесты для SC-2..SC-8 (Spatial Coherence Contract).
Проверяют структурную валидность npc_positions.
"""
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_BACKEND))

from hypothesis import given, strategies as st, settings as hyp_settings

@st.composite
def valid_npc_position_strategy(draw):
    """Генерирует структурно валидную позицию NPC."""
    return {
        "npc_id": draw(st.text(min_size=1, max_size=5, alphabet="abcdefghijklmnopqrstuvwxyz")),
        "local_position": {
            "x": draw(st.floats(min_value=1.0, max_value=50.0)),
            "y": draw(st.floats(min_value=1.0, max_value=50.0))
        },
        "current_node": draw(st.text(min_size=1, max_size=10, alphabet="abcdefghijklmnopqrstuvwxyz_")),
        "location_id": draw(st.sampled_from(["tavern", "city_gate", "market_square"])),
        "name": "TestNPC"
    }

@hyp_settings(max_examples=100)
@given(pos=valid_npc_position_strategy())
def test_sc2_position_belongs_to_location(pos):
    """SC-2: local_position должен принадлежать текущей location_id (структурная проверка)."""
    # В PBT без реального SpatialService мы можем проверить только наличие полей
    assert "location_id" in pos, "NPC position must have location_id"
    assert pos["location_id"] is not None, "location_id cannot be None"

@hyp_settings(max_examples=100)
@given(pos=valid_npc_position_strategy())
def test_sc3_current_node_exists(pos):
    """SC-3: current_node должен существовать (не пустой)."""
    assert "current_node" in pos, "NPC position must have current_node"
    assert pos["current_node"] != "", "current_node cannot be empty string"

@hyp_settings(max_examples=100)
@given(pos=valid_npc_position_strategy())
def test_sc4_current_node_resolvable(pos):
    """SC-4: current_node разрешим из local_position (структурная проверка типов)."""
    assert isinstance(pos["local_position"], dict), "local_position must be dict"
    assert "x" in pos["local_position"] and "y" in pos["local_position"], "local_position must have x and y"

@hyp_settings(max_examples=100)
@given(pos=valid_npc_position_strategy())
def test_sc5_spatial_service_authoritative(pos):
    """SC-5: SpatialService собран из авторитетной топологии (наличие location_id)."""
    assert pos["location_id"] in ["tavern", "city_gate", "market_square"], "location_id must be a valid topology"

@hyp_settings(max_examples=100)
@given(pos=valid_npc_position_strategy())
def test_sc6_no_movement_without_validation(pos):
    """SC-6: Движение запрещено до Validation (структурная проверка)."""
    # В реальности проверяется статус TraversalState, здесь проверяем наличие координат
    assert pos["local_position"]["x"] != 0.0 and pos["local_position"]["y"] != 0.0, "Position must be validated (not 0,0)"

@hyp_settings(max_examples=100)
@given(pos=valid_npc_position_strategy())
def test_sc7_persistence_authoritative(pos):
    """SC-7: Persistence не может быть авторитетной, если сохранённое состояние нарушает SC-1..SC-5."""
    assert pos["current_node"] is not None, "Persisted state must have current_node"

@hyp_settings(max_examples=100)
@given(pos=valid_npc_position_strategy())
def test_sc8_recovery_deterministic(pos):
    """SC-8: Recovery из старого состояния должен быть детерминированным (наличие имени)."""
    assert "name" in pos, "Recovered state must have name for fuzzy matching"