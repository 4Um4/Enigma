"""
path: /project/backend/tests/sandbox/test_sandbox_lerp_cycle.py
Назначение: Верификация каузального контура поставки TraversalState во фронтенд (ADR-019). Доказывает, что WorldSnapshotBuilder корректно конвертирует внутренний транзит в DTO для визуального Lerp.
Зависимости: WorldSnapshotBuilder, WorldSnapshotDTO
Основные сущности: active_traversals, from_xy, to_xy, duration_seconds

ЗАПУСК: python -m pytest backend/tests/sandbox/test_sandbox_lerp_cycle.py -v --tb=short

TODO:
- Добавить тесты для разных типов locomotion (WALK, RUN, SNEAK) и убедиться, что duration_seconds корректно рассчитывается в зависимости от скорости.
- В будущем расширить тесты, чтобы покрыть edge cases, например, нулевое расстояние (from_xy == to_xy) или экстремально длинные пути.

"""

import pytest
from app.services.integration.world_snapshot_builder import WorldSnapshotBuilder

def test_traversal_state_packed_into_snapshot():
    """ДОКАЗЫВАЕТ: SceneStateManager → WorldSnapshotDTO.active_traversals труба не разорвана.
    Фронтенд получает from_xy, to_xy, duration_seconds для Lerp."""
    builder = WorldSnapshotBuilder()
    
    # Эмуляция scene_state после того, как SceneStateManager перехватил SceneChange(field="position")
    scene_state = {
        "tick": 1,
        "version": 1,
        "location_id": "tavern_silver_wolf",
        "npc_positions": {},
        "visible_events": [],
        "available_actions": [],
        "weather": "clear",
        "time_of_day": "day",
        "game_time_seconds": 1000,
        "active_traversals": {
            "thief_shadow": {
                "npc_id": "thief_shadow",
                "from_node": "shadow_corner",
                "target_node": "bar_area",
                "path_waypoints": [[1.0, 2.0], [5.0, 6.0]], # from_xy, to_xy
                "speed": 2.0,
                "started_tick": 1000,
                "locomotion": "WALK",
                "status": "MOVING"
            }
        }
    }
    
    # WHEN: Билдер собирает WorldSnapshotDTO
    snapshot = builder.build(scene_state, tick=1)
    
    # THEN: active_traversals содержит корректные данные для фронтенд-интерполяции
    assert len(snapshot.active_traversals) == 1, "Транзит потерян при сборке снапшота!"
    trav = snapshot.active_traversals["thief_shadow"]
    
    # Проверка контракта ADR-019 (поля для Lerp)
    assert trav["npc_id"] == "thief_shadow"
    assert trav["path_waypoints"][0] == [1.0, 2.0], "Неверная точка старта для Lerp"
    assert trav["path_waypoints"][-1] == [5.0, 6.0], "Неверная точка финиша для Lerp"
    assert trav["started_tick"] == 1000, "Фронтенд не сможет синхронизировать время без started_tick"
    assert trav["locomotion"] == "WALK"
    
    # ADR-059: Tick-based Dual Time. duration_ticks вычисляется в WorldSnapshotBuilder
    assert "duration_ticks" in trav
    assert trav["duration_ticks"] > 0, "Duration не вычислен"