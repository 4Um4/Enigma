import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
file_path = ROOT / "frontend/map_editor/campaigns/Open_road/locations/tavern.json"

with open(file_path, "r", encoding="utf-8") as f:
    data = json.load(f)

# Восстанавливаем правильные двунаправленные связи
data["nodes"]["bar_west"]["connections"] = ["bar_area", "bar_pass_north"]
data["nodes"]["bar_pass_north"]["connections"] = ["bar_west", "bar_side"]
data["nodes"]["bar_side"]["connections"] = ["bar_pass_north", "bar_pass_south"]
data["nodes"]["bar_pass_south"]["connections"] = ["bar_side", "behind_bar"]
data["nodes"]["behind_bar"]["connections"] = ["bar_pass_south"]

data["nodes"]["door_kitchen"]["connections"] = ["main_hall", "kitchen", "fireplace"]
data["nodes"]["fireplace"]["connections"] = ["right_table", "door_kitchen"]
data["nodes"]["right_table"]["connections"] = ["main_hall", "fireplace", "corner_table"]
data["nodes"]["corner_table"]["connections"] = ["entrance", "right_table"]

# Сдвигаем fireplace для безопасности
data["nodes"]["fireplace"]["x"] = 10.5

with open(file_path, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

print("[FIXED] tavern.json connections restored to bidirectional.")