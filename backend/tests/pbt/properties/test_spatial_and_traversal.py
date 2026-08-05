# backend/tests/pbt/properties/test_spatial_and_traversal.py
"""
Property-тесты для SC-1 (Spatial Coherence) и ADR-TRAV-FSM (Zombie Traversals).
"""
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import Any, Dict, List

# Добавляем backend в path для импортов
_BACKEND = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_BACKEND))

from hypothesis import given, strategies as st, settings as hyp_settings

@dataclass
class MockProbeContext:
    """Мок ProbeContext для тестирования проб без поднятия всего оркестратора."""
    tick_id: int
    scene_state: dict
    tick_state: Any = None
    tick_mutation: Any = None
    world_snapshot: Any = None
    interventions: list = None
    l1_events: list = None

# --- Стратегии генерации ---

@st.composite
def npc_positions_strategy(draw):
    """Генерирует словарь npc_positions. Иногда с (0.0, 0.0) для SC-1."""
    npc_id = draw(st.text(min_size=1, max_size=5, alphabet="abcdefghijklmnopqrstuvwxyz"))
    is_zero = draw(st.booleans())
    
    if is_zero:
        pos = {"x": 0.0, "y": 0.0}
    else:
        pos = {
            "x": draw(st.floats(min_value=1.0, max_value=50.0)),
            "y": draw(st.floats(min_value=1.0, max_value=50.0))
        }
        
    return {npc_id: {"local_position": pos, "name": "TestNPC"}}

@st.composite
def active_traversals_strategy(draw):
    """Генерирует active_traversals. Иногда с терминальными статусами для FSM."""
    npc_id = draw(st.text(min_size=1, max_size=5, alphabet="abcdefghijklmnopqrstuvwxyz"))
    status = draw(st.sampled_from(["PENDING", "MOVING", "COMPLETED", "CANCELLED"]))
    
    return {npc_id: {
        "status": status,
        "source_node": "node_A",
        "target_node": "node_B"
    }}

# --- Property Tests ---

@hyp_settings(max_examples=100)
@given(pos=npc_positions_strategy())
def test_sc1_rejects_zero_position(pos):
    """INV-SC-1: local_position не может быть (0.0, 0.0)."""
    from app.services.probes.probes.spatial_coherence_probe import SpatialCoherenceProbe
    
    ctx = MockProbeContext(tick_id=1, scene_state={"npc_positions": pos})
    probe = SpatialCoherenceProbe()
    result = probe.check(ctx)
    
    # Извлекаем координаты из сгенерированного словаря
    npc_data = list(pos.values())[0]
    is_zero = npc_data["local_position"] == {"x": 0.0, "y": 0.0}
    
    if is_zero:
        assert not result.passed, "Проба должна упасть на координатах (0.0, 0.0)"
    else:
        assert result.passed, "Проба не должна падать на валидных координатах"

@hyp_settings(max_examples=100)
@given(travs=active_traversals_strategy())
def test_trav_fsm_detects_zombies(travs):
    """INV-TRAV-ZOMBIE: Завершённые перемещения не должны зависать."""
    from app.services.probes.probes.traversal_fsm_probe import TraversalFSMProbe
    
    ctx = MockProbeContext(tick_id=1, scene_state={"active_traversals": travs})
    probe = TraversalFSMProbe()
    result = probe.check(ctx)
    
    # Извлекаем статус
    trav_data = list(travs.values())[0]
    status = trav_data["status"]
    
    if status in ["COMPLETED", "CANCELLED"]:
        assert not result.passed, f"Проба должна упасть на зомби-статусе {status}"
    else:
        assert result.passed, f"Проба не должна падать на активном статусе {status}"