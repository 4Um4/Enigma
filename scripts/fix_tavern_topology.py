import json
from pathlib import Path

FILE = Path("frontend/map_editor/campaigns/Open_road/locations/tavern.json")

def main():
    if not FILE.exists():
        print(f"[ERROR] File not found: {FILE}")
        return

    data = json.loads(FILE.read_text(encoding="utf-8"))

    # 1. Добавляем adjacency, если отсутствует
    if "adjacency" not in data:
        data["adjacency"] = {
            "east": "city_gate",
            "south": "market_square"
        }
        print("[FIX] Added adjacency section.")

    # 2. Обновляем координаты узлов, чтобы избежать блокировки рёбер мебелью
    # Стул №11 (obj_21) находится на (2.45, 4.3). Линия bar_side -> bar_pass_north пересекает его.
    # Сдвигаем узлы графа подальше от стен и мебели.
    if "nodes" in data:
        nodes = data["nodes"]
        
        # Сдвигаем обходные узлы бара влево, чтобы обойти стулья
        if "bar_pass_north" in nodes:
            nodes["bar_pass_north"]["x"] = 2.2
            nodes["bar_pass_north"]["y"] = 6.0
            
        if "bar_side" in nodes:
            nodes["bar_side"]["x"] = 2.2
            nodes["bar_side"]["y"] = 3.5
            
        if "bar_pass_south" in nodes:
            nodes["bar_pass_south"]["x"] = 2.2
            nodes["bar_pass_south"]["y"] = 3.0
            
        if "behind_bar" in nodes:
            nodes["behind_bar"]["x"] = 4.0
            nodes["behind_bar"]["y"] = 3.0

        # Сдвигаем вход, чтобы не пересекал декорации
        if "entrance" in nodes:
            nodes["entrance"]["x"] = 8.0
            nodes["entrance"]["y"] = 11.5

        # Сдвигаем main_hall_west для чистого пути
        if "main_hall_west" in nodes:
            nodes["main_hall_west"]["x"] = 6.0
            nodes["main_hall_west"]["y"] = 8.0

        # Добавляем door_kitchen, если его нет
        if "door_kitchen" not in nodes:
            nodes["door_kitchen"] = {
                "x": 13.5,
                "y": 4.5,
                "label": "Проём на кухню",
                "role": "passage",
                "connections": ["main_hall", "kitchen", "fireplace"]
            }
            print("[FIX] Added door_kitchen node.")

        # Гарантируем, что kitchen имеет связь
        if "kitchen" in nodes:
            nodes["kitchen"]["connections"] = ["door_kitchen"]
            nodes["kitchen"]["x"] = 17.0
            nodes["kitchen"]["y"] = 5.5

        print("[FIX] Updated node coordinates to avoid obstacles.")

    FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[SUCCESS] Updated {FILE}")

if __name__ == "__main__":
    main()