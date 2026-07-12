import json
from pathlib import Path

# Маппинг: ID NPC -> Ориентация
ORIENTATIONS = {
    "tavern_keeper_tornin": "ruler",
    "guard_borko": "wealth_creator",
    "merchant_goran": "wealth_creator",
    "maid_lusya": "family_builder",
    "blacksmith_orm": "knowledge_seeker",
    "thief_shadow": "warrior",
}

# Папка с профилями
INDIVIDUALS_DIR = Path("config/npc/individuals")

def process_file(filepath: Path) -> bool:
    # Используем utf-8-sig для чтения, чтобы автоматически срезать BOM (если есть)
    with open(filepath, "r", encoding="utf-8-sig") as f:
        data = json.load(f)
    
    npc_id = data.get("id")
    if not npc_id or npc_id not in ORIENTATIONS:
        return False
        
    # Если поле уже есть и совпадает — пропускаем (идемпотентность)
    if data.get("core_orientation") == ORIENTATIONS[npc_id]:
        return False
        
    # Добавляем или обновляем поле
    data["core_orientation"] = ORIENTATIONS[npc_id]
    
    # Записываем обратно, сохраняя отступы и кириллицу
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return True

count = 0
for f in INDIVIDUALS_DIR.glob("*.json"):
    if process_file(f):
        count += 1
        print(f"Fixed: {f}")

print(f"Total files fixed: {count}")