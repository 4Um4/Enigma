"""
path: backend/tests/sandbox/micro/test_boundary_nodes.py
Назначение: Верификация ДОЛГ 6.2 — Boundary Nodes + Graph Stitching
Зависимости: app.services.spatial.graph_compiler, app.models.spatial_contracts
Основные сущности: compile_graph, NodeRole.BOUNDARY, boundary_map

Запуск: cd backend; python -m pytest tests/sandbox/micro/test_boundary_nodes.py -v --tb=short; cd ..
"""

from app.domain.identity_events import EffectiveDrives

_MOCK_DRIVES = EffectiveDrives.from_dict({"control": 0.5, "significance": 0.5, "fear": 0.5, "desire": 0.5})

from app.models.spatial_contracts import NodeRole
from app.services.spatial.graph_compiler import compile_graph


def test_boundary_nodes_created_from_adjacency():
    """ДОКАЗЫВАЕТ: compile_graph создаёт boundary nodes при наличии adjacency.

    Без этого NPC не может планировать путь выхода из чанка.
    """
    editor_data = {
        "nodes": {
            "center": {"x": 5.0, "y": 5.0, "connections": []},
        },
        "adjacency": {
            "east": "other_chunk",
            "south": "another_chunk",
        },
    }
    graph, connections, alias_map, boundary_map, _rooms_geometry = compile_graph(editor_data, location_id="test_loc")

    # Boundary nodes созданы
    assert "test_loc:exit_east" in graph, "Boundary exit_east не создан"
    assert "test_loc:exit_south" in graph, "Boundary exit_south не создан"
    assert len(boundary_map) == 2, "boundary_map должна содержать 2 записи"

    # Boundary nodes имеют роль BOUNDARY
    assert graph["test_loc:exit_east"].role == NodeRole.BOUNDARY
    assert graph["test_loc:exit_south"].role == NodeRole.BOUNDARY


def test_boundary_nodes_connected_to_internal():
    """ДОКАЗЫВАЕТ: Boundary nodes связаны с ближайшими внутренними узлами.

    Без этого NPC не может дойти до boundary node.
    """
    editor_data = {
        "nodes": {
            "center": {"x": 5.0, "y": 5.0, "connections": []},
        },
        "adjacency": {
            "east": "other_chunk",
        },
    }
    graph, connections, alias_map, boundary_map, _rooms_geometry = compile_graph(editor_data, location_id="test_loc")

    # exit_east связан с center
    east_conns = connections.get("test_loc:exit_east", set())
    assert "test_loc:center" in east_conns, "Boundary exit_east не связан с center"

    # Обратная связь тоже
    center_conns = connections.get("test_loc:center", set())
    assert "test_loc:exit_east" in center_conns, "center не связан с boundary exit_east"


def test_boundary_map_contains_neighbor_info():
    """ДОКАЗЫВАЕТ: boundary_map содержит информацию о соседнем чанке для навигации.

    Без этого MovementEngine не знает куда вести NPC при достижении boundary.
    """
    editor_data = {
        "nodes": {
            "center": {"x": 5.0, "y": 5.0, "connections": []},
        },
        "adjacency": {
            "east": "city_gate",
        },
    }
    graph, connections, alias_map, boundary_map, _rooms_geometry = compile_graph(editor_data, location_id="tavern")

    binfo = boundary_map.get("tavern:exit_east")
    assert binfo is not None, "boundary_map не содержит exit_east"
    assert binfo["neighbor_chunk"] == "city_gate", "Неверный neighbor_chunk"
    assert binfo["direction"] == "east", "Неверное direction"
    assert binfo["entry_direction"] == "west", "Неверное entry_direction (противоположное)"
    assert binfo["entry_node_hint"] == "city_gate:exit_west", (
        "entry_node_hint должен указывать на exit-узел соседа (двусторонняя топология)"
    )


def test_no_adjacency_no_boundary_nodes():
    """ДОКАЗЫВАЕТ: Без adjacency boundary nodes не создаются.

    Изолированные чанки остаются изолированными — это корректное поведение.
    """
    editor_data = {
        "nodes": {
            "center": {"x": 5.0, "y": 5.0, "connections": []},
        },
    }
    graph, connections, alias_map, boundary_map, _rooms_geometry = compile_graph(editor_data, location_id="isolated")

    assert len(boundary_map) == 0, "Без adjacency не должно быть boundary nodes"
    boundaries = [nid for nid, nref in graph.items() if nref.role == NodeRole.BOUNDARY]
    assert len(boundaries) == 0, "Не должно быть узлов с ролью BOUNDARY"


def test_boundary_node_is_not_a_place():
    """ОНТОЛОГИЧЕСКИЙ ИНВАРИАНТ: Boundary node не является местом.

    Boundary node — это интерфейс графа, а не локация.
    NPC может проходить через него, но не может выбирать его как цель.
    """
    editor_data = {
        "nodes": {
            "center": {"x": 5.0, "y": 5.0, "connections": []},
        },
        "adjacency": {
            "east": "other_chunk",
        },
    }
    graph, connections, alias_map, boundary_map, _rooms_geometry = compile_graph(editor_data, location_id="test_loc")

    boundary_node = graph["test_loc:exit_east"]

    # Boundary node помечен тегами, отличающими его от мест
    assert "boundary:exit" in boundary_node.tags, "Boundary node должен иметь тег boundary:exit"
    assert boundary_node.role == NodeRole.BOUNDARY, "Роль должна быть BOUNDARY, не DEFAULT"

    # Boundary node НЕ имеет ролей, свойственных местам (BED, BAR, TABLE)
    place_roles = {NodeRole.BED, NodeRole.BAR, NodeRole.TABLE, NodeRole.MARKET, NodeRole.WORKBENCH}
    assert boundary_node.role not in place_roles, "Boundary node не должен иметь роль места"


def test_opposite_directions_resolved():
    """ДОКАЗЫВАЕТ: Противоположные направления корректно резолвятся.

    east → west, north → south и т.д. Это нужно для entry_node_hint.
    """
    editor_data = {
        "nodes": {
            "center": {"x": 5.0, "y": 5.0, "connections": []},
        },
        "adjacency": {
            "north": "northern_chunk",
            "south": "southern_chunk",
            "east": "eastern_chunk",
            "west": "western_chunk",
        },
    }
    graph, connections, alias_map, boundary_map, _rooms_geometry = compile_graph(editor_data, location_id="crossroads")

    assert boundary_map["crossroads:exit_north"]["entry_direction"] == "south"
    assert boundary_map["crossroads:exit_south"]["entry_direction"] == "north"
    assert boundary_map["crossroads:exit_east"]["entry_direction"] == "west"
    assert boundary_map["crossroads:exit_west"]["entry_direction"] == "east"
