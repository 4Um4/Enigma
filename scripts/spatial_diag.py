"""
Запуск: python scripts/spatial_diag.py
"""

import sys, json
sys.path.insert(0, 'backend')
from app.services.spatial.graph_compiler import _build_spatial_data, _line_rect_intersect, _segments_intersect

with open('frontend/map_editor/campaigns/Open_road/locations/tavern.json', 'r', encoding='utf-8') as f:
    editor_data = json.load(f)

spatial_walls, spatial_obstacles = _build_spatial_data(editor_data)

nodes = editor_data['nodes']
edges = []
for nid, ndata in nodes.items():
    for conn in ndata.get('connections', []):
        if conn in nodes:
            edges.append((nid, conn))

print('=== SPATIAL DIAGNOSTICS ===')
for from_id, to_id in edges:
    from_node = nodes[from_id]
    to_node = nodes[to_id]
    x1, y1 = from_node['x'], from_node['y']
    x2, y2 = to_node['x'], to_node['y']
    
    for wall in spatial_walls:
        if _segments_intersect(x1, y1, x2, y2, wall['x1'], wall['y1'], wall['x2'], wall['y2']):
            print(f'BLOCKED: {from_id} -> {to_id} by WALL {wall.get("id")} ({wall["x1"]},{wall["y1"]} -> {wall["x2"]},{wall["y2"]})')
            
    for obs in spatial_obstacles:
        if not obs.get('passability', {}).get('walk', True):
            if _line_rect_intersect(x1, y1, x2, y2, obs['x'], obs['y'], obs['w'], obs['h']):
                print(f'BLOCKED: {from_id} -> {to_id} by OBSTACLE {obs.get("id")} (x={obs["x"]}, y={obs["y"]}, w={obs["w"]}, h={obs["h"]})')
print('=== DONE ===')