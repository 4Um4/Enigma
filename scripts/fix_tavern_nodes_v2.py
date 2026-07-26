import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
file_path = ROOT / "frontend/map_editor/campaigns/Open_road/locations/tavern.json"

with open(file_path, "r", encoding="utf-8") as f:
    data = json.load(f)

# Сдвигаем узлы так, чтобы линии пути не пересекали стулья
data["nodes"]["entrance"]["x"] = 8.5
data["nodes"]["entrance"]["y"] = 11.0

data["nodes"]["main_hall_west"]["x"] = 5.0
data["nodes"]["main_hall_west"]["y"] = 8.5

data["nodes"]["main_hall"]["x"] = 6.5
data["nodes"]["main_hall"]["y"] = 5.5

data["nodes"]["bar_pass_north"]["x"] = 3.0
data["nodes"]["bar_pass_north"]["y"] = 4.5

with open(file_path, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

print("[FIXED] tavern.json nodes shifted to bypass chairs (obj_16, obj_14, obj_21).")