"""
Назначение: Интеграционный тест проверки маршрутизации NPC к местам сна (кроватям/палаткам) в ночное время через GameLoop.
Зависимости: backend/app/services/game_loop_builder.py, backend/app/services/game_loop/init.py
Основные сущности: GameLoop, SceneStateManager


Запуск: cd backend; python -m pytest tests/system/test_sleep_routing.py -v; cd ..
"""

import sys
import os
import shutil
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_BACKEND_ROOT = _PROJECT_ROOT / "backend"
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(_BACKEND_ROOT))

from app.services.game_loop_builder import build_game_loop

@pytest.fixture(scope="module")
def game_loop_setup():
    """Подготовка окружения: копирование карт и сборка GameLoop."""
    _src_campaign = _PROJECT_ROOT / "frontend" / "map_editor" / "campaigns" / "Open_road"
    _dst_saves = _PROJECT_ROOT / "saves" / "Open_road"
    if _dst_saves.exists():
        shutil.rmtree(_dst_saves)
    shutil.copytree(_src_campaign, _dst_saves)

    _src_templates = _PROJECT_ROOT / "backend" / "data" / "locations" / "location_templates.json"
    _dst_templates_dir = _PROJECT_ROOT / "saves" / "locations"
    _dst_templates_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(_src_templates, _dst_templates_dir / "location_templates.json")

    loop = build_game_loop(data_dir=(_PROJECT_ROOT / "saves"))
    if not loop:
        pytest.fail("GameLoop не собран.")
    
    campaign_id = "Open_road"
    scene_manager = loop.scene_manager
    scene_manager.reinit_campaign(campaign_id)
    
    yield loop, scene_manager, campaign_id

def test_npc_sleep_routing_at_night(game_loop_setup):
    """Тест: NPC должны доходить до своих спальных мест в 02:00."""
    loop, scene_manager, campaign_id = game_loop_setup
    
    # 1. Устанавливаем время 02:00 и обнуляем стресс/угрозы
    for loc_id in ["tavern", "city_gate"]:
        _loc_state = scene_manager.get_scene_state(campaign_id, loc_id)
        if not _loc_state:
            continue
        _env = _loc_state.setdefault("environment", {})
        _env["time_of_day"] = "02:00"
        _loc_state["game_time_seconds"] = 2 * 3600
        
        for _npc in _loc_state.get("npcs", []):
            _npc.setdefault("psyche", {})["stress"] = 0.0
            _pk = _npc.setdefault("perceptual_kernel", {})
            if isinstance(_pk, dict):
                _pk["threat_gradient"] = 0.0
                
        scene_manager.save_scene_state(campaign_id, _loc_state)

    # 2. Прогоняем 120 тиков симуляции
    for _ in range(120):
        loop.idle_tick(campaign_id, location_id="tavern")
        loop.idle_tick(campaign_id, location_id="city_gate")

    # 3. Проверяем финальные позиции NPC
    expected_positions = {
        "guard_borko": ("city_gate", "guard_bed"),
        "blacksmith_orm": ("city_gate", "tent_1"),
        "merchant_goran": ("city_gate", "tent_2"),
        "maid_lusya": ("tavern", "kitchen_bed_1"),
        "tavern_keeper_tornin": ("tavern", "kitchen_bed_2"),
    }

    errors = []
    for npc_id, (exp_loc, exp_node_prefix) in expected_positions.items():
        _loc_state = scene_manager.get_scene_state(campaign_id, exp_loc)
        _npc_positions = _loc_state.get("npc_positions", {})
        _npc_data = _npc_positions.get(npc_id, {})
        
        actual_loc = _npc_data.get("location_id", "")
        actual_node = _npc_data.get("position", "")
        
        # Отрезаем префикс локации (напр. "city_gate:guard_bed" -> "guard_bed") для проверки
        actual_node_short = actual_node.split(":")[-1]
        
        assert actual_loc == exp_loc, f"{npc_id}: Ожидается loc={exp_loc}, реально loc={actual_loc}"
        assert actual_node_short.startswith(exp_node_prefix), f"{npc_id}: Ожидается node={exp_node_prefix}*, реально node={actual_node}"