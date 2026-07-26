import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.services.spatial.spatial_factory import SpatialFactory
from app.services.spatial.graph_compiler import _line_rect_intersect, _segments_intersect

scene_state = {
    "location_id": "tavern_silver_wolf",
    "campaign_id": "Open_road"
}

svc = SpatialFactory.build_for_campaign("Open_road", "tavern_silver_wolf", scene_state)
if not svc:
    print("Failed to build SpatialService")
    exit(1)

print("--- Checking Blocked Edges ---")
for from_id, neighbors in svc._connections.items():
    from_node = svc._graph.get(from_id)
    if not from_node:
        continue
    for to_id in neighbors:
        to_node = svc._graph.get(to_id)
        if not to_node:
            continue
        
        is_blocked = False
        blocker = ""
        
        # Проверка стен
        for wall in svc._spatial_walls:
            if _segments_intersect(from_node.x, from_node.y, to_node.x, to_node.y, wall["x1"], wall["y1"], wall["x2"], wall["y2"]):
                is_blocked = True
                blocker = f"WALL {wall.get('id')}"
                break
                
        # Проверка препятствий (столы, стулья)
        if not is_blocked:
            for obs in svc._spatial_obstacles:
                if not obs.get("passability", {}).get("walk", True):
                    if _line_rect_intersect(from_node.x, from_node.y, to_node.x, to_node.y, obs["x"], obs["y"], obs["w"], obs["h"]):
                        is_blocked = True
                        blocker = f"OBS {obs.get('id')} ({obs.get('name')}) at ({obs['x']},{obs['y']}) size ({obs['w']},{obs['h']})"
                        break
        
        if is_blocked:
            print(f"[BLOCKED] {from_id} ({from_node.x},{from_node.y}) -> {to_id} ({to_node.x},{to_node.y}) by {blocker}")