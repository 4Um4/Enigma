"""
path: backend/tests/sandbox/movement/test_topology_gate.py
Назначение: S-143 Topology Gate Test. Доказывает, что компилятор графа падает
с INV-TOPOLOGY-WALL-CROSS, если ребро пересекает неразрезанную стену.
Зависимости: pytest, app.errors, graph_compiler
Основные сущности: SimulationIntegrityError

Запуск: cd backend; python -m pytest tests/sandbox/movement/test_topology_gate.py -v ; cd ..
"""
import pytest
from app.errors import SimulationIntegrityError
from app.services.spatial.graph_compiler import compile_graph


def _make_synthetic_map(wall_id_on_door: bool = False) -> dict:
    """Создаёт синтетическую карту 10x10 с двумя узлами и стеной между ними."""
    # Если door нет на стене, она не разрезает её (даже по координатам).
    # Если door на стене и имеет wall_id, она разрезает стену.
    door_pos = {"x": 0.0, "y": 0.0}
    door_obj = {
        "id": "door_1",
        "type": "door",
        "position": door_pos,
        "size": {"w": 1.0, "h": 1.0},
        "passability": {"walk": True},
    }
    if wall_id_on_door:
        door_obj["wall_id"] = "wall_1"
        door_obj["position"] = {"x": 5.0, "y": 5.0}

    return {
        "size": {"w": 10.0, "h": 10.0},
        "origin": {"x": 0, "y": 0},
        "walls": [
            {"id": "wall_1", "x1": 5.0, "y1": 0.0, "x2": 5.0, "y2": 10.0}
        ],
        "nodes": {
            "A": {"x": 2.0, "y": 5.0, "connections": ["B"]},
            "B": {"x": 8.0, "y": 5.0, "connections": ["A"]}
        },
        "objects": [door_obj],
        "portals": [],
        "npcs": []
    }


def test_topology_gate_blocks_uncut_wall():
    """S-143: Если ребро пересекает неразрезанную стену, ребро удаляется из графа (BUG-TOPO-001 FIX)."""
    # Карта без wall_id на двери (стена не разрезана)
    bad_map = _make_synthetic_map(wall_id_on_door=False)
    
    # BUG-TOPO-001 FIX: Компилятор логирует и удаляет ребро, не роняя SpatialService.
    graph, connections, _alias, _boundary, _rooms, _walls, _obstacles, _afford = compile_graph(bad_map, "test_location")
    
    # Проверяем, что ребро A-B отсутствует в графе
    _node_a = "test_location:A"
    _node_b = "test_location:B"
    assert _node_a in graph
    assert _node_b in graph
    # Проверяем, что нет связи A-B в connections (ключ "test_location:A" -> "test_location:B")
    # Формат connections: Dict[str, List[str]]
    assert _node_b not in connections.get(_node_a, [])
    assert _node_a not in connections.get(_node_b, [])


def test_topology_gate_allows_cut_wall():
    """S-143: Если дверь разрезает стену (wall_id), компиляция успешна."""
    # Карта с wall_id на двери (стена разрезана)
    good_map = _make_synthetic_map(wall_id_on_door=True)
    
    # Не должно выбросить исключение
    result = compile_graph(good_map, "test_location")
    assert result is not None