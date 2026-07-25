# scripts/run_census.py
"""
S137.3: Daily Cross-Location Flow Census.
Запускает симуляцию на 200 тиков и выводит, где оказались NPC.

Запуск: python scripts/run_census.py
"""

import shutil
import sys
from collections import defaultdict
from pathlib import Path

# Добавляем корень бэкенда в sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.core.config import settings


def main():
    settings.environment = "test"  # Отключаем LLM
    
    campaign_id = "Open_road"
    location_id = "tavern_silver_wolf"
    
    print(f"{'='*50}")
    print(f" 📊 CENSUS: Автономный запуск симуляции ({campaign_id})")
    print(f"{'='*50}\n")
    
    # 1. Сохраняем оригинальные настройки
    orig_saves = settings.saves_dir
    orig_data = settings.data_dir
    
    # 2. Создаём временную папку для изоляции
    temp_saves = Path("saves_census")
    if temp_saves.exists():
        shutil.rmtree(temp_saves)
    temp_saves.mkdir()
    
    try:
        # 3. Копируем статические данные (локации и NPC) во временную папку
        camp_dir = Path("frontend/map_editor/campaigns/Open_road")
        loc_src = camp_dir / "locations"
        npc_src = camp_dir / "npcs"
        
        dst_loc = temp_saves / "locations"
        dst_loc.mkdir(exist_ok=True)
        if loc_src.exists():
            for f in loc_src.glob("*.json"):
                shutil.copy2(f, dst_loc / f.name)
                
        dst_npc = temp_saves / "npcs"
        dst_npc.mkdir(exist_ok=True)
        if npc_src.exists():
            for f in npc_src.glob("*.json"):
                shutil.copy2(f, dst_npc / f.name)
                
        # 4. Копируем текущие сейвы во временную папку
        saves_src = Path(orig_saves) / campaign_id
        saves_dst = temp_saves / campaign_id
        if saves_src.exists():
            shutil.copytree(saves_src, saves_dst, dirs_exist_ok=True)
        else:
            saves_dst.mkdir(exist_ok=True)
            
        # 5. Переключаем настройки на временную папку
        settings.saves_dir = str(temp_saves)
        
        # 6. Инициализируем GameLoop
        from app.services.game_loop_builder import build_game_loop
        loop = build_game_loop(data_dir=Path(orig_data))
        
        # 7. Прогоняем 200 тиков (около 33 игровых часов)
        ticks_to_run = 200
        for i in range(1, ticks_to_run + 1):
            loop.idle_tick(campaign_id)
            if i % 50 == 0:
                print(f"  ...прогнано {i} тиков")
                
        print("\nСимуляция завершена. Сбор статистики...\n")
        
        # 8. Читаем финальное состояние
        scene_state = loop.scene_manager.get_scene_state_uncached(campaign_id, location_id)
        if not scene_state:
            # Если таверна пуста, ищем любую сцену
            scene_state = loop.scene_manager.get_scene_state_uncached(campaign_id, "")
            
        if not scene_state:
            print("❌ Не удалось получить scene_state после симуляции!")
            return
            
        npc_positions = scene_state.get("npc_positions", {})
        
        location_map = defaultdict(list)
        
        print(f"{'='*50}")
        print(" 📊 CENSUS: Финальное распределение NPC")
        print(f"{'='*50}\n")
        
        for npc_id, npc_data in npc_positions.items():
            loc_id = npc_data.get("location_id", "UNKNOWN")
            position = npc_data.get("position", "UNKNOWN")
            location_map[loc_id].append(f"{npc_id} (at {position})")
            
        for loc_id, npcs in location_map.items():
            print(f"📍 Локация: {loc_id} ({len(npcs)} NPC)")
            for npc in npcs:
                print(f"   - {npc}")
            print()
                
        print(f"{'='*50}")
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
            
    finally:
        # 9. Восстанавливаем настройки и удаляем временную папку
        settings.saves_dir = orig_saves
        settings.data_dir = orig_data
        if temp_saves.exists():
            shutil.rmtree(temp_saves, ignore_errors=True)
        print("\n[CLEANUP] Временная папка удалена, настройки восстановлены.")

if __name__ == "__main__":
    main()