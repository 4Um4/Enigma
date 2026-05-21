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

import math
import pytest
from app.services.integration.world_snapshot_builder import WorldSnapshotBuilder

def test_traversal_state_packed_into_snapshot():
    """ДОКАЗЫВАЕТ: SceneStateManager → WorldSnapshotDTO.active_traversals труба не разорвана.
    Фронтенд получает path_waypoints, started_tick, duration_ticks для Lerp (ADR-059)."""
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
                "path_waypoints": [[1.0, 2.0], [5.0, 6.0]],
                "speed": 2.0,
                "started_tick": 1,
                "duration_ticks": 3,
                "locomotion": "WALK",
                "status": "MOVING"
            }
        }
    }
    
    # WHEN: Билдер собирает WorldSnapshotDTO
    snapshot = builder.build(scene_state, tick=1)
    
    # THEN: active_traversals содержит корректные данные для фронтенд-интерполяции
    assert len(snapshot.active_traversals) == 1, "Транзит потерян при сборке снапшота!"
    trav = snapshot.active_traversals[0]
    
    # Проверка контракта ADR-059 Dual-Time Ontology (поля для Lerp)
    assert trav["npc_id"] == "thief_shadow"
    assert trav["path_waypoints"][0] == [1.0, 2.0], "Неверная точка старта для Lerp"
    assert trav["path_waypoints"][-1] == [5.0, 6.0], "Неверная точка финиша для Lerp"
    assert trav["started_tick"] == 1, "Фронтенд не сможет синхронизировать тики без started_tick"
    assert trav["locomotion"] == "WALK"
    
    # ADR-059: Dual-Time Ontology. Длительность измеряется в тиках, а не секундах
    assert "duration_ticks" in trav
    assert trav["duration_ticks"] > 0, "Duration не вычислен"
    expected_duration = math.hypot(4, 4) / 2.0 # ~2.828
    assert abs(trav["duration_ticks"] - expected_duration) < 0.1


@pytest.mark.parametrize("speed, locomotion, expected_duration", [
    (2.0, "WALK", math.hypot(4, 4) / 2.0),  # ~2.828 ticks
    (4.0, "RUN", math.hypot(4, 4) / 4.0),   # ~1.414 ticks
    (1.0, "SNEAK", math.hypot(4, 4) / 1.0), # ~5.656 ticks
])
def test_locomotion_type_affects_duration_ticks(speed, locomotion, expected_duration):
    """ДОКАЗЫВАЕТ: Билдер корректно рассчитывает duration_ticks на основе типа локомоции (скорости)."""
    builder = WorldSnapshotBuilder()
    
    scene_state = {
        "tick": 1, "version": 1, "location_id": "tavern_silver_wolf",
        "npc_positions": {}, "visible_events": [], "available_actions": [],
        "weather": "clear", "time_of_day": "day", "game_time_seconds": 1000,
        "active_traversals": {
            "thief_shadow": {
                "npc_id": "thief_shadow",
                "from_node": "shadow_corner",
                "target_node": "bar_area",
                "path_waypoints": [[1.0, 2.0], [5.0, 6.0]], # Distance = sqrt(16+16) = 5.656
                "speed": speed,
                "started_tick": 1,
                "locomotion": locomotion,
                "status": "MOVING"
            }
        }
    }
    
    snapshot = builder.build(scene_state, tick=1)
    
    assert len(snapshot.active_traversals) == 1, "Транзит потерян при сборке снапшота!"
    trav = snapshot.active_traversals[0]
    
    assert trav["locomotion"] == locomotion
    assert "duration_ticks" in trav
    assert trav["duration_ticks"] > 0, "Duration не вычислен"
    assert abs(trav["duration_ticks"] - expected_duration) < 0.01, \
        f"Неверная длительность для {locomotion}. Ожидалось {expected_duration}, получено {trav['duration_ticks']}"


def test_zero_distance_traversal_duration():
    """ДОКАЗЫВАЕТ: При нулевой дистанции (from_xy == to_xy) duration_ticks = 0."""
    builder = WorldSnapshotBuilder()
    
    scene_state = {
        "tick": 1, "version": 1, "location_id": "tavern_silver_wolf",
        "npc_positions": {}, "visible_events": [], "available_actions": [],
        "weather": "clear", "time_of_day": "day", "game_time_seconds": 1000,
        "active_traversals": {
            "guard_idle": {
                "npc_id": "guard_idle",
                "from_node": "gate",
                "target_node": "gate",
                "path_waypoints": [[10.0, 10.0], [10.0, 10.0]], # Нулевая дистанция
                "speed": 2.0,
                "started_tick": 1,
                "locomotion": "WALK",
                "status": "MOVING"
            }
        }
    }
    
    snapshot = builder.build(scene_state, tick=1)
    assert len(snapshot.active_traversals) == 1
    trav = snapshot.active_traversals[0]
    assert trav["duration_ticks"] == 0.0, "При нулевой дистанции duration_ticks должен быть 0"


def test_extremely_long_path_duration():
    """ДОКАЗЫВАЕТ: Расчёт duration_ticks не переполняется и не ломается на длинных путях."""
    builder = WorldSnapshotBuilder()
    
    scene_state = {
        "tick": 1, "version": 1, "location_id": "city_streets",
        "npc_positions": {}, "visible_events": [], "available_actions": [],
        "weather": "clear", "time_of_day": "day", "game_time_seconds": 1000,
        "active_traversals": {
            "courier": {
                "npc_id": "courier",
                "from_node": "district_a",
                "target_node": "district_z",
                "path_waypoints": [[0.0, 0.0], [1000.0, 1000.0]], # Дистанция ~1414.21
                "speed": 2.0,
                "started_tick": 1,
                "locomotion": "RUN",
                "status": "MOVING"
            }
        }
    }
    
    snapshot = builder.build(scene_state, tick=1)
    
    assert len(snapshot.active_traversals) == 1
    trav = snapshot.active_traversals[0]
    expected_duration = math.hypot(1000, 1000) / 2.0 # ~707.1
    
    assert abs(trav["duration_ticks"] - expected_duration) < 0.1, "Неверный расчёт для длинного пути"