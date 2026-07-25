# scripts/check_population_flow.py
"""
S137.3: Daily Cross-Location Flow Census.
Читает финальный scene_state.json после прогона DriftLaboratory
и выводит статистику миграции населения.

Запуск: python scripts/check_population_flow.py
"""
import json
from collections import defaultdict
from pathlib import Path


def main():
    saves_dir = Path("saves/Open_road")
    state_file = saves_dir / "scene_state.json"
    
    if not state_file.exists():
        print(f"❌ Файл состояния не найден: {state_file}")
        print("Сначала запустите DriftLaboratory: cd backend && python -m tests.sandbox.SUPERBOX.run drift mass_traversal")
        return

    data = json.loads(state_file.read_text(encoding="utf-8-sig"))
    
    # DriftLab может сохранять в формате {"scene_state": {...}} или напрямую {...}
    scene_state = data.get("scene_state", data)
    
    npc_positions = scene_state.get("npc_positions", {})
    
    location_map = defaultdict(list)
    
    print("\n" + "="*50)
    print(" 📊 CENSUS: Daily Cross-Location Flow")
    print("="*50 + "\n")
    
    for npc_id, npc_data in npc_positions.items():
        loc_id = npc_data.get("location_id", "UNKNOWN")
        position = npc_data.get("position", "UNKNOWN")
        location_map[loc_id].append(f"{npc_id} (at {position})")
        
    for loc_id, npcs in location_map.items():
        print(f"📍 Локация: {loc_id} ({len(npcs)} NPC)")
        for npc in npcs:
            print(f"   - {npc}")
        print()
            
    print("="*50)
    total_npcs = sum(len(n) for n in location_map.values())
    tavern_npcs = len(location_map.get("tavern_silver_wolf", []))
    migrated_npcs = total_npcs - tavern_npcs
    
    print(f"Всего NPC: {total_npcs}")
    print(f"Остались в таверне: {tavern_npcs}")
    print(f"Мигрировали: {migrated_npcs}")
    
    if migrated_npcs > 0:
        print("\n✅ Кросс-локационная миграция успешно состоялась!")
    else:
        print("\n⚠️ Ни один NPC не покинул таверну. Проверьте расписания и логи.")

if __name__ == "__main__":
    main()