from app.services.spatial.location_graph import (
    LocationNode,
    load_graph,
    local_xy_distance,
    validate_graph,
)


def test_load_graph_from_json_templates() -> None:
    graph = load_graph("tavern_silver_wolf", data_dir="data")
    assert graph.get_node("main_hall") is not None
    assert graph.get_distance("behind_bar", "main_hall") > 0


def test_validate_graph_detects_asymmetric_and_orphan_links() -> None:
    nodes = {
        "a": LocationNode(node_id="a", x=0, y=0, connections=("b",)),
        "b": LocationNode(node_id="b", x=1, y=0, connections=tuple()),
        "c": LocationNode(node_id="c", x=2, y=0, parent="ghost", connections=("none",)),
    }
    errors = validate_graph("test_loc", nodes)
    assert any("asymmetric" in e for e in errors)
    assert any("parent" in e for e in errors)
    assert any("unknown connection" in e for e in errors)


def test_local_xy_distance_adds_local_offsets() -> None:
    graph = load_graph("market_square", data_dir="data")
    base = graph.get_distance("center", "stall_1")
    d = local_xy_distance(graph, "center", "stall_1", (0.0, 0.0), (1.0, 0.0))
    assert d > base
