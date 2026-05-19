# backend/tests/sandbox/test_micro_macro_locomotion.py
# Назначение: Верификация каузального контура LOD0 (микро-сближение) в _resolve_reactive_movement
# Зависимости: pytest, app.services.npc.npc_tick_pipeline
# Основные сущности: MovementIntent (local_target_xy), _resolve_reactive_movement

import pytest
from app.services.npc.npc_tick_pipeline import _resolve_reactive_movement

# Фикстура: Игрок и Тень в одной зоне, но с разной нотацией узлов (баг ADR-045)
@pytest.fixture
def scene_state_same_zone_prefix_mismatch():
    return {
        "npc_positions": {
            "shadow": {"position": "main_hall", "local_position": {"x": 5.0, "y": 5.0}},
            "player": {"position": "tavern_silver_wolf:main_hall", "local_position": {"x": 10.0, "y": 10.0}}
        }
    }

# Фикстура: Игрок в той же зоне, без префикса (чистый кейс)
@pytest.fixture
def scene_state_same_zone_clean():
    return {
        "npc_positions": {
            "shadow": {"position": "main_hall", "local_position": {"x": 5.0, "y": 5.0}},
            "player": {"position": "main_hall", "local_position": {"x": 12.5, "y": 8.0}}
        }
    }

def test_micro_movement_with_prefix_mismatch(scene_state_same_zone_prefix_mismatch):
    """ДОКАЗЫВАЕТ: Строковое несовпадение 'main_hall' и 'tavern:main_hall' больше не убивает микро-подход."""
    result = _resolve_reactive_movement(
        npc_id="shadow",
        intent="approach",
        intent_target="player",
        scene_state=scene_state_same_zone_prefix_mismatch,
        location_id="tavern_silver_wolf",
        spatial_service=None
    )
    
    assert result is not None, "БАГ: Микро-движение заблокировано из-за несовпадения префиксов!"
    assert result.local_target_xy == (10.0, 10.0), f"ОШИБКА: local_target_xy не совпадает с позицией игрока: {result.local_target_xy}"
    assert "micro_snap" in result.reason, f"ОШИБКА: Причина должна быть micro_snap, а не {result.reason}"
    # ADR-060: Утверждение target_node_id удалено. LOD0 (LocalSteeringGoal) оперирует координатами, а не узлами графа.

def test_micro_movement_clean_case(scene_state_same_zone_clean):
    """ДОКАЗЫВАЕТ: Микро-движение работает в чистом случае (без префиксов)."""
    result = _resolve_reactive_movement(
        npc_id="shadow",
        intent="approach",
        intent_target="player",
        scene_state=scene_state_same_zone_clean,
        location_id="tavern_silver_wolf",
        spatial_service=None
    )
    
    assert result is not None, "БАГ: Микро-движение не создано в чистом случае!"
    assert result.local_target_xy == (12.5, 8.0)
    assert "micro_snap" in result.reason
