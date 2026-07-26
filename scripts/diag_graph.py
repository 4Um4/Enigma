import json
from pathlib import Path
import sys
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.services.spatial.graph_compiler import compile_graph

tavern_path = ROOT / "frontend/map_editor/campaigns/Open_road/locations/tavern.json"
with open(tavern_path, "r", encoding="utf-8") as f:
    editor_data = json.load(f)

print("--- Compiling Graph ---")
result = compile_graph(editor_data, "tavern_silver_wolf")

print(f"\nReturn type: {type(result)}, length: {len(result)}")
graph = result[0]

print("\n--- Checking Isolated Nodes ---")
for node_id, node in graph.items():
    neighbors = getattr(node, "neighbors", getattr(node, "connections", None))
    if not neighbors:
        print(f"[ISOLATED] {node_id} at ({node.x}, {node.y})")
    else:
        print(f"[OK] {node_id} neighbors: {neighbors}")