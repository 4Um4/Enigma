"""
app/services/player_cognition/spatial_layer.py
Spatial Layer — вычисляет расстояния и LOS от игрока до каждой сущности.
Чистые функции без состояния. Переиспользует spatial_runtime.

path: /backend/app/services/player_cognition/spatial_layer.py
Назначение: Вычисляет расстояния и LOS от игрока до каждой сущности — чистые вычисления, без состояния
Зависимости: app.services.spatial.spatial_runtime, types из этого пакета
Основные сущности: extract_spatial_data()
"""
import math
from typing import List, Tuple

from app.services.player_cognition.types import PerceivedEntity
from app.services.spatial.spatial_runtime import (
    is_line_of_sight_clear,
    is_blocked_by_wall,
    is_blocked_by_obstacle,
)


def _player_xy(scene_state: dict) -> Tuple[float, float]:
    """Извлекает координаты игрока из SceneState"""
    # ADR-048: Игрок читается из единого словаря npc_positions
    ps = scene_state.get("npc_positions", {}).get("player", {})
    lp = ps.get("local_position") or {}
    return float(lp.get("x", 0.0)), float(lp.get("y", 0.0))


def _entity_xy(entity_data: dict) -> Tuple[float, float]:
    """Извлекает координаты сущности — работает для NPC и объектов"""
    # NPC: local_position直接
    lp = entity_data.get("local_position")
    if lp:
        return float(lp.get("x", 0.0)), float(lp.get("y", 0.0))
    # Объекты: position.x, position.y
    pos = entity_data.get("position") or {}
    return float(pos.get("x", 0.0)), float(pos.get("y", 0.0))


# _euclidean удалён — используем math.hypot напрямую (точнее и без дублирования с perception_filter)


def compute_distance_and_los(
    player_x: float,
    player_y: float,
    entity_x: float,
    entity_y: float,
    scene_state: dict,
) -> Tuple[float, bool, str | None]:
    """
    Вычисляет расстояние и LOS от игрока до одной сущности.

    Returns:
        (distance_meters, los_clear, blocked_by_or_None)
    """
    distance = math.hypot(player_x - entity_x, player_y - entity_y)

    los_clear = is_line_of_sight_clear(
        player_x, player_y, entity_x, entity_y, scene_state
    )

    blocked_by = None
    if not los_clear:
        # Определяем ЧТО именно блокирует — для UI ("за стеной" vs "за объектом")
        if is_blocked_by_wall(player_x, player_y, entity_x, entity_y, scene_state):
            blocked_by = "wall"
        elif is_blocked_by_obstacle(player_x, player_y, entity_x, entity_y, scene_state):
            blocked_by = "obstacle"

    return distance, los_clear, blocked_by


def extract_spatial_data(
    scene_state: dict,
) -> List[PerceivedEntity]:
    """
    Создаёт PerceivedEntity для всех сущностей сцены с заполненным Spatial Layer.

    Returns:
        Список PerceivedEntity с заполненными: entity_id, entity_type, distance, los, los_blocked_by
    """
    player_x, player_y = _player_xy(scene_state)
    entities: List[PerceivedEntity] = []

    # NPC из npc_positions — могут быть внутри scene_state или на верхнем уровне campaign_state
    npc_positions = scene_state.get("npc_positions") or scene_state.get("_top_level_npc_positions") or {}
    for npc_id, npc_data in npc_positions.items():
        ex, ey = _entity_xy(npc_data)
        distance, los, blocked_by = compute_distance_and_los(
            player_x, player_y, ex, ey, scene_state
        )
        entities.append(PerceivedEntity(
            entity_id=npc_id,
            entity_type="npc",
            x=ex,
            y=ey,
            distance=distance,
            los=los,
            los_blocked_by=blocked_by,
            _raw_data=npc_data,
        ))

    # Объекты из objects
    for obj_id, obj_data in scene_state.get("objects", {}).items():
        ex, ey = _entity_xy(obj_data)
        distance, los, blocked_by = compute_distance_and_los(
            player_x, player_y, ex, ey, scene_state
        )
        entities.append(PerceivedEntity(
            entity_id=obj_id,
            entity_type="object",
            x=ex,
            y=ey,
            distance=distance,
            los=los,
            los_blocked_by=blocked_by,
            _raw_data=obj_data,
        ))

    return entities