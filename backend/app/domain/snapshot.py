"""
path: backend/app/domain/snapshot.py
Назначение: Снимок мира для frontend. Единственное, что видит клиент.
Зависимости: dataclasses, typing, uuid.UUID
Основные сущности: WorldSnapshotDTO, NPCPositionDTO, VisibleEventDTO
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple
from uuid import UUID


@dataclass(frozen=True)
class NPCPositionDTO:
    """Позиция одного NPC в мире. Readonly для frontend."""
    npc_id: str
    x: float
    y: float
    location_id: str
    facing: str          # 'north', 'south', 'east', 'west'
    action: str          # 'idle', 'walking', 'talking', 'working'
    display_name: str    # имя для UI


@dataclass(frozen=True)
class VisibleEventDTO:
    """Событие видимое frontend. Отфильтровано по visibility и радиусу."""
    event_id: str
    timestamp: float
    text: str
    actor_id: str
    visibility: str      # 'public', 'private', 'whisper'


@dataclass(frozen=True)
class WorldSnapshotDTO:
    """Снимок мира на конец тика.
    
    Единственное, что пересекает границу backend → frontend.
    Не содержит NPCState, trust, fear, secret_events — только визуальное.
    """
    tick: int
    version: int                 # инкремент SceneStateManager, защита от stale
    last_event_id: Optional[UUID]  # последнее обработанное событие
    player_position: Tuple[float, float]
    npc_positions: List[NPCPositionDTO]
    visible_events: List[VisibleEventDTO]
    available_actions: List[str]
    location_id: str
    weather: str
    time_of_day: str
    game_time_seconds: int = 0


def snapshot_npc_positions_to_dict(
    positions: List[NPCPositionDTO],
) -> dict:
    """Конвертирует List[NPCPositionDTO] в dict для обратной совместимости фронтенда.

    Фронтенд ожидает: {npc_id: {"local_position": {"x", "y"}, "activity", "name", ...}}
    WorldSnapshotDTO содержит: List[NPCPositionDTO] с плоскими x, y, action, display_name.
    """
    result: dict = {}
    for pos in positions:
        result[pos.npc_id] = {
            "npc_id": pos.npc_id,
            "x": pos.x,
            "y": pos.y,
            "local_position": {"x": pos.x, "y": pos.y},
            "activity": pos.action,
            "facing": pos.facing,
            "location_id": pos.location_id,
            "display_name": pos.display_name,
            "name": pos.display_name,
        }
    return result