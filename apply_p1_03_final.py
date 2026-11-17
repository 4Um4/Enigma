import json
import shutil
from pathlib import Path

file_path = Path("frontend/map_editor/campaigns/Open_road/locations/tavern.json")
if not file_path.exists():
    print(f"❌ Файл не найден: {file_path}")
else:
    # 1. Создаем бэкап
    backup_path = file_path.with_suffix(".json.bak.pre-p1-03-final")
    shutil.copy2(file_path, backup_path)
    print(f"✅ Бэкап создан: {backup_path}")

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    dx, dy = 25.0333, 5.018
    count = 0

    # 2. Сдвигаем player_spawn
    if "player_spawn" in data and isinstance(data["player_spawn"], dict):
        if "x" in data["player_spawn"]:
            data["player_spawn"]["x"] += dx
            count += 1
        if "y" in data["player_spawn"]:
            data["player_spawn"]["y"] += dy
            count += 1

    # 3. Сдвигаем rooms (origin и polygon)
    for room in data.get("rooms", []):
        if "origin" in room:
            if "x" in room["origin"]:
                room["origin"]["x"] += dx
                count += 1
            if "y" in room["origin"]:
                room["origin"]["y"] += dy
                count += 1
        for pt in room.get("polygon", []):
            if "x" in pt:
                pt["x"] += dx
                count += 1
            if "y" in pt:
                pt["y"] += dy
                count += 1

    # 4. Сдвигаем walls
    for wall in data.get("walls", []):
        if "x1" in wall:
            wall["x1"] += dx
            count += 1
        if "y1" in wall:
            wall["y1"] += dy
            count += 1
        if "x2" in wall:
            wall["x2"] += dx
            count += 1
        if "y2" in wall:
            wall["y2"] += dy
            count += 1

    # 5. Сдвигаем objects
    for obj in data.get("objects", []):
        if "position" in obj and isinstance(obj["position"], dict):
            if "x" in obj["position"]:
                obj["position"]["x"] += dx
                count += 1
            if "y" in obj["position"]:
                obj["position"]["y"] += dy
                count += 1

    # 6. Сдвигаем nodes
    for node in data.get("nodes", []):
        if "position" in node and isinstance(node["position"], dict):
            if "x" in node["position"]:
                node["position"]["x"] += dx
                count += 1
            if "y" in node["position"]:
                node["position"]["y"] += dy
                count += 1

    # 7. Сдвигаем npcs
    for npc in data.get("npcs", []):
        if "position" in npc and isinstance(npc["position"], dict):
            if "x" in npc["position"]:
                npc["position"]["x"] += dx
                count += 1
            if "y" in npc["position"]:
                npc["position"]["y"] += dy
                count += 1

    # 8. Сохраняем файл
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"✅ Миграция P1-03 завершена! Сдвинуто координатных полей: {count}")
