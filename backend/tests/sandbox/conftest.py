"""
Файл: backend/tests/sandbox/conftest.py
Назначение: Фикстуры минимального валидного мира для каузальных тестов.
Зависимости: pytest, app.domain.cfrm, app.domain.intent_profile

TODO
"""

import pytest
from typing import Dict, Any
from app.models.cfrm import ClusterOccupancy, ClusterID

@pytest.fixture
def minimal_world() -> Dict[str, Any]:
    """Минимальный снимок мира, где игрок и Тень в одной локации."""
    return {
        "all_npcs_raw": [
            {"npc_id": "player", "name": "Венус", "position": {"node": "main_hall", "x": 5.0, "y": 5.0}},
            {"npc_id": "thief_shadow", "name": "Тень", "position": {"node": "bar_area", "x": 12.0, "y": 9.0}, "body_state": {"disabled": False, "shock_impulse": 0.0}}
        ],
        "npc_positions": {
            "player": {"npc_id": "player", "display_name": "Венус", "location_id": "tavern_silver_wolf:main_hall"},
            "thief_shadow": {"npc_id": "thief_shadow", "display_name": "Тень", "location_id": "tavern_silver_wolf:bar_area"}
        }
    }

@pytest.fixture
def cluster_occupancy(minimal_world) -> ClusterOccupancy:
    """Индекс присутствия: игрок и Тень в одном кластере."""
    co = ClusterOccupancy()
    co.update_entity("player", "tavern_silver_wolf:main_hall")
    co.update_entity("thief_shadow", "tavern_silver_wolf:bar_area") # Допустим, связь есть
    return co