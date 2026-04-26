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
    perceived_scene: Optional[dict] = None  # TODO: удалить после миграции player_cognition