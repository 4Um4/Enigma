# test_spatial_service.py — критерии приёмки SpatialService v1.2
import sys
sys.path.insert(0, ".")

from app.models.spatial_contracts import NodeRole, Urgency, NodeRef, SpatialOverlay, NPCPathState
from app.services.spatial.role_resolver import resolve_role
from app.services.spatial.graph_compiler import compile_graph, load_editor_json, get_connections
from app.services.spatial.spatial_overlay import build_overlay_from_scene, try_reserve_node
from app.services.spatial.spatial_service import SpatialService

passed = 0
failed = 0

def check(name, condition):
    global passed, failed
    if condition:
        print(f"  PASS: {name}")
        passed += 1
    else:
        print(f"  FAIL: {name}")
        failed += 1

editor = load_editor_json("Open_road", "tavern_silver_wolf")
graph, alias_map = compile_graph(editor, "tavern_silver_wolf")
conns = get_connections("tavern_silver_wolf")
overlay = SpatialOverlay()
svc = SpatialService(graph, conns, alias_map, overlay)

print("=== test_role_resolver_priority ===")
check("BAR from label", resolve_role(node_label="У стойки") == NodeRole.BAR)
check("BAR from label za stoykoy", resolve_role(node_label="За стойкой") == NodeRole.BAR)
check("ENTRANCE from label", resolve_role(node_label="Вход") == NodeRole.ENTRANCE)
check("TRANSITION from editor_type", resolve_role(node_label="Дверь", editor_type="door") == NodeRole.TRANSITION)
check("TABLE from node_id", resolve_role(node_label="В тёмном углу", node_id="corner_table") == NodeRole.TABLE)
check("WORKBENCH from node_id", resolve_role(node_label="Кухня", node_id="kitchen") == NodeRole.WORKBENCH)
check("DEFAULT for unknown", resolve_role(node_label="Центр зала", node_id="main_hall") == NodeRole.DEFAULT)
check("manifest_override wins", resolve_role(node_label="У стойки", manifest_override=NodeRole.BED) == NodeRole.BED)

print("\n=== test_topology_filtering ===")
bar_in_zone = svc.resolve_node(NodeRole.BAR, origin_zone="tavern_silver_wolf")
bar_out_zone = svc.resolve_node(NodeRole.BAR, origin_zone="nonexistent_zone")
check("BAR found in correct zone", bar_in_zone is not None and "tavern_silver_wolf" in bar_in_zone.node_id)
check("BAR not found in wrong zone", bar_out_zone is None)

print("\n=== test_reservation_exclusion ===")
overlay1 = SpatialOverlay(reserved_nodes={"tavern_silver_wolf:bar_area": "npc_other"})
svc1 = SpatialService(graph, conns, alias_map, overlay1)
bar_reserved = svc1.resolve_node(NodeRole.BAR, origin_zone="tavern_silver_wolf", requesting_npc_id="npc_me")
check("Reserved node excluded for other NPC", bar_reserved is not None and bar_reserved.node_id != "tavern_silver_wolf:bar_area")
overlay2 = SpatialOverlay(reserved_nodes={"tavern_silver_wolf:bar_area": "npc_me"})
svc2 = SpatialService(graph, conns, alias_map, overlay2)
bar_own = svc2.resolve_node(NodeRole.BAR, origin_zone="tavern_silver_wolf", requesting_npc_id="npc_me")
check("Own reservation allowed", bar_own is not None and bar_own.node_id == "tavern_silver_wolf:bar_area")

print("\n=== test_urgency_weight_modification ===")
overlay3 = SpatialOverlay(reserved_nodes={"tavern_silver_wolf:bar_area": "npc_other"})
svc3 = SpatialService(graph, conns, alias_map, overlay3)
bar_urgent = svc3.resolve_node(NodeRole.BAR, origin_zone="tavern_silver_wolf", requesting_npc_id="npc_me", urgency=Urgency.URGENT)
check("URGENT allows reserved node", bar_urgent is not None)

print("\n=== test_path_computation_once ===")
path1 = svc.find_path((4.5, 5.0), svc.get_node("tavern_silver_wolf:kitchen"), Urgency.NORMAL)
path2 = svc.find_path((4.5, 5.0), svc.get_node("tavern_silver_wolf:kitchen"), Urgency.NORMAL)
check("Path found", len(path1) > 0)
check("Path is cached (same result)", path1 == path2)
check("Path ends at target", path1[-1].node_id == "tavern_silver_wolf:kitchen")

print("\n=== test_alias_normalization ===")
check("Legacy ID normalized", svc.normalize_id("bar_area") == "tavern_silver_wolf:bar_area")
check("Canonical ID passes through", svc.normalize_id("tavern_silver_wolf:bar_area") == "tavern_silver_wolf:bar_area")
check("Denormalize", svc.denormalize_id("tavern_silver_wolf:bar_area") == "bar_area")
check("get_node by legacy ID", svc.get_node("kitchen") is not None)
check("get_node by canonical ID", svc.get_node("tavern_silver_wolf:kitchen") is not None)

print("\n=== test_global_coordinates ===")
entrance = svc.get_node("tavern_silver_wolf:entrance")
check("Entrance x=8.0", entrance is not None and entrance.x == 8.0)
check("Entrance y=12.0", entrance is not None and entrance.y == 12.0)
check("Kitchen x=16.0", svc.get_node("kitchen").x == 16.0)
check("Bar y=4.0", svc.get_node("bar_area").y == 4.0)

print("\n=== test_flee_and_approach ===")
player_xy = (8.0, 12.0)
flee = svc.get_furthest("tavern_silver_wolf", player_xy)
approach = svc.get_nearest("tavern_silver_wolf", player_xy)
check("FLEE goes to kitchen (farthest from entrance)", flee is not None and "kitchen" in flee.node_id)
check("APPROACH goes to entrance (nearest to player)", approach is not None and "entrance" in approach.node_id)

print("\n=== test_world_distance ===")
d = SpatialService.world_distance((0.0, 0.0), (3.0, 4.0))
check("Euclidean 3-4-5 = 5.0", abs(d - 5.0) < 0.001)

print("\n" + "=" * 50)
print(f"RESULTS: {passed} passed, {failed} failed")
if failed > 0:
    sys.exit(1)
