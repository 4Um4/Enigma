"""
path: /project/backend/tests/sandbox/test_lod0_collision_avoidance.py
Назначение: Верификация ADR-056 Collision Avoidance для LOD0 микро-подхода. Доказывает, что MovementEngine избегает stacking-эффекта при подходе к одной цели.
Зависимости: MovementEngine, MovementIntent
Основные сущности: npc_positions, collision_radius

ЗАПУСК: python -m pytest backend/tests/sandbox/test_lod0_collision_avoidance.py -v --tb=short

TODO:
- Добавить тесты для разных радиусов коллизии и убедиться, что NPC корректно избегают друг друга.
- В будущем расширить тесты, чтобы покрыть edge cases, например, когда несколько NPC одновременно подходят к одной цели или когда NPC уже стоит в целевой точке.
"""

import pytest
from app.domain.movement import LocalSteeringGoal
from app.services.spatial.movement_engine import MovementEngine

class MockSpatialService:
    """LOD0 не требует графа, но движок требует сервис."""
    pass

@pytest.fixture
def engine():
    me = MovementEngine()
    me.set_spatial_service(MockSpatialService())
    return me

def test_lod0_collision_avoidance(engine):
    """ДОКАЗЫВАЕТ: NPC не встает друг в друга при микро-подходе.
    Если точка занята, MovementEngine ищет свободную в радиусе."""
    
    # NPC 1 уже стоит у игрока (целевая точка 5.0, 5.0)
    npc_positions = {
        "npc_1": {"local_position": {"x": 5.0, "y": 5.0}},
        "npc_2": {"local_position": {"x": 2.0, "y": 2.0}}
    }
    
    # NPC 2 подходит туда же (ADR-060: Чистый LOD0 интент)
    intent = LocalSteeringGoal(
        npc_id="npc_2",
        local_target_xy=(5.0, 5.0), # Цель - позиция игрока/NPC_1
        reason="approach",
        priority=10
    )
    
    changes = engine.process_intents([intent], tick=1, npc_positions=npc_positions)
    
    assert len(changes) == 1, "MovementIntent не сгенерировал SceneChange"
    change = changes[0]
    assert change.field == "local_position"
    
    new_x = change.value["x"]
    new_y = change.value["y"]
    
    # Проверяем, что новая позиция НЕ совпадает с NPC_1 (радиус 0.8)
    dist_to_npc1 = ((new_x - 5.0)**2 + (new_y - 5.0)**2)**0.5
    assert dist_to_npc1 >= 0.8, f"БАГ КОЛЛИЗИИ: NPC_2 встал в NPC_1! Дистанция: {dist_to_npc1:.2f}"
    
    # Проверяем, что новая позиция всё ещё рядом с целью (в радиусе 1.6 от изначальной цели)
    dist_to_target = ((new_x - 5.0)**2 + (new_y - 5.0)**2)**0.5
    assert dist_to_target <= 1.5, f"NPC_2 ушел слишком далеко от цели: {dist_to_target:.2f}"