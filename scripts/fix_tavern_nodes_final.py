import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
file_path = ROOT / "frontend/map_editor/campaigns/Open_road/locations/tavern.json"

with open(file_path, "r", encoding="utf-8") as f:
    data = json.load(f)

data["nodes"] = {
    "entrance": {
      "x": 8.5, "y": 11.0, "label": "Вход", "role": "entrance",
      "connections": ["main_hall_west", "corner_table"]
    },
    "main_hall_west": {
      "x": 5.5, "y": 8.0, "label": "Западный проход", "role": "default",
      "connections": ["entrance", "main_hall_south", "bar_area"]
    },
    "main_hall_south": {
      "x": 5.5, "y": 6.0, "label": "Юго-запад зала", "role": "default",
      "connections": ["main_hall_west", "main_hall"]
    },
    "main_hall": {
      "x": 6.5, "y": 6.0, "label": "Центр зала", "role": "default",
      "connections": ["main_hall_south", "right_table"]
    },
    "door_kitchen": {
      "x": 13.5, "y": 3.75, "label": "Проём на кухню", "role": "passage",
      "connections": ["fireplace", "kitchen"]
    },
    "bar_area": {
      "x": 5.5, "y": 6.5, "label": "У стойки", "role": "bar",
      "connections": ["main_hall_west", "bar_west"]
    },
    "bar_west": {
      "x": 5.5, "y": 4.5, "label": "У южной стойки", "role": "default",
      "connections": ["bar_area", "bar_pass_north"]
    },
    "bar_pass_north": {
      "x": 2.5, "y": 4.5, "label": "Северный обход стойки", "role": "default",
      "connections": ["bar_west", "bar_side"]
    },
    "bar_side": {
      "x": 2.5, "y": 2.5, "label": "Обход стойки", "role": "default",
      "connections": ["bar_pass_north", "behind_bar"]
    },
    "behind_bar": {
      "x": 4.0, "y": 2.5, "label": "За стойкой", "role": "inn_desk",
      "tags": ["workplace:tavern_keeper", "inn_desk"],
      "connections": ["bar_side"]
    },
    "fireplace": {
      "x": 10.5, "y": 3.0, "label": "У камина", "role": "default",
      "connections": ["right_table", "door_kitchen"]
    },
    "corner_table": {
      "x": 11.0, "y": 10.0, "label": "В тёмном углу", "role": "dark_corner",
      "tags": ["workplace:thief", "dark_corner"],
      "connections": ["entrance", "right_table"]
    },
    "right_table": {
      "x": 10.5, "y": 6.5, "label": "За правым столом", "role": "table",
      "connections": ["main_hall", "fireplace", "corner_table"]
    },
    "kitchen": {
      "x": 17.0, "y": 5.5, "label": "Кухня", "role": "kitchen_counter",
      "tags": ["workplace:maid", "serving_station"],
      "connections": ["door_kitchen"]
    }
}

with open(file_path, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

print("[FIXED] tavern.json nodes fully overwritten with final safe topology.")