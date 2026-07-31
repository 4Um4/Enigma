"""
path: /project/scripts/test_sleep_routing.py
Назначение: Точечная проверка маршрутизации NPC к местам сна (кроватям/палаткам) в ночное время.
Зависимости: backend/app/services/game_loop_builder.py, backend/app/services/game_loop/__init__.py
Основные сущности: GameLoop, SceneStateManager

Запуск: python scripts/test_sleep_routing.py
"""

import sys
import os
import logging
import shutil
from pathlib import Path

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
_BACKEND_ROOT = os.path.join(_PROJECT_ROOT, 'backend')
sys.path.insert(0, _PROJECT_ROOT)
sys.path.insert(0, _BACKEND_ROOT)

from app.services.game_loop_builder import build_game_loop

# Копируем карты из map_editor в saves, чтобы SceneStateManager мог их прочитать
_src_campaign = Path("frontend/map_editor/campaigns/Open_road")
_dst_saves = Path("saves/Open_road")
if _dst_saves.exists():
    shutil.rmtree(_dst_saves)
shutil.copytree(_src_campaign, _dst_saves)

# S-142 FIX: Копируем location_templates.json в saves/locations/
_src_templates = Path("backend/data/locations/location_templates.json")
_dst_templates_dir = Path("saves/locations")
_dst_templates_dir.mkdir(parents=True, exist_ok=True)
shutil.copy2(_src_templates, _dst_templates_dir / "location_templates.json")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("SleepTest")

def run_sleep_test():
    logger.info("--- Инициализация теста сна ---")
    
    loop = build_game_loop(data_dir=Path("saves"))
    if not loop:
        logger.error("❌ GameLoop не собран.")
        return False

    scene_manager = loop.scene_manager
    campaign_id = "Open_road"
    
    # S-142 FIX: Принудительная переинициализация сцены
    scene_manager.reinit_campaign(campaign_id)
    
    scene_state = scene_manager.get_scene_state(campaign_id, "tavern")
    if not scene_state:
        logger.error("❌ SceneState не загружен после reinit_campaign.")
        return False

    logger.info("Устанавливаю время 02:00 (ночь)...")
    env = scene_state.setdefault("environment", {})
    env["time_of_day"] = "02:00"
    scene_state["game_time_seconds"] = 2 * 3600
    scene_manager.save_scene_state(campaign_id, scene_state)

    logger.info("Прогон 40 тиков симуляции...")
    for i in range(40):
        loop.idle_tick(campaign_id)
        # Сохраняем время 02:00, чтобы они точно уснули
        scene_state = scene_manager.get_scene_state(campaign_id, "tavern")
        env = scene_state.setdefault("environment", {})
        env["time_of_day"] = "02:00"
        scene_manager.save_scene_state(campaign_id, scene_state)

    logger.info("--- Проверка позиций NPC ---")
    
    # S-143 FIX: Проверяем глобальное состояние NPC через LifeEngine, 
    # так как NPC могут покинуть сцену tavern и перейти в city_gate.
    engine = loop._get_life_engine()
    all_npcs = engine.get_npc_states(campaign_id)
    
    if not all_npcs:
        logger.error("❌ LifeEngine не вернул состояния NPC.")
        return False
        
    npc_positions = {n.get("id"): n for n in all_npcs}
    
    all_passed = True
    
    expected_locations = {
        "guard_borko": ("city_gate", "guard_bed"),
        "blacksmith_orm": ("city_gate", "tent_"),
        "merchant_goran": ("city_gate", "tent_"),
        # thief_shadow спит днём (06:00-18:00), ночью он в tavern
        "maid_lusya": ("tavern", "kitchen_bed_"),
        "tavern_keeper_tornin": ("tavern", "kitchen_bed_")
    }

    for npc_id, (exp_loc, exp_node_prefix) in expected_locations.items():
        npc_data = npc_positions.get(npc_id, {})
        actual_loc = npc_data.get("location_id", npc_data.get("location", "N/A"))
        actual_node = npc_data.get("position", "N/A")
        
        # Нормализуем actual_loc, так как могут быть расхождения в именах
        if "tavern" in actual_loc:
            actual_loc = "tavern"
        elif "city_gate" in actual_loc:
            actual_loc = "city_gate"
            
        loc_ok = (actual_loc == exp_loc)
        # S-145 FIX: actual_node может содержать префикс локации (напр. "tavern:kitchen_bed_1").
        # Отрезаем префикс перед проверкой startswith.
        _pure_node = actual_node.split(":")[-1] if ":" in actual_node else actual_node
        node_ok = _pure_node.startswith(exp_node_prefix) if exp_node_prefix else True
        
        if loc_ok and node_ok:
            logger.info(f"✅ {npc_id}: loc={actual_loc}, node={actual_node}")
        else:
            logger.error(f"❌ {npc_id}: ОЖИДАНИЕ loc={exp_loc}, node={exp_node_prefix}* | РЕАЛЬНОСТЬ loc={actual_loc}, node={actual_node}")
            all_passed = False

    if all_passed:
        logger.info("🎉 ТЕСТ СНА УСПЕШНО ПРОЙДЕН!")
    else:
        logger.error("💥 ТЕСТ СНА ПРОВАЛЕН!")
        
    return all_passed

if __name__ == "__main__":
    success = run_sleep_test()
    sys.exit(0 if success else 1)