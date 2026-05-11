"""
path: backend/app/domain/snapshot.py
Назначение: Снимок мира для frontend. Единственное, что видит клиент.
Зависимости: dataclasses, typing, uuid.UUID
Основные сущности: WorldSnapshotDTO, NPCPositionDTO, VisibleEventDTO
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple
from uuid import UUID


class PhysicalPresentationState(str, Enum):
    """Визуальное физическое состояние аватара для рендера."""
    HEALTHY = "healthy"
    WOUNDED = "wounded"
    BLEEDING = "bleeding"
    CRIPPLED = "crippled"
    DYING = "dying"


class MentalPresentationState(str, Enum):
    """Визуальное ментальное состояние аватара для рендера."""
    CALM = "calm"
    STRESSED = "stressed"
    PANICKED = "panicked"
    DISSOCIATING = "dissociating"
    BROKEN = "broken"


@dataclass(frozen=True)
class AvatarStateDTO:
    """Феноменологическая проекция состояния аватара (ADR-035, ADR-037).
    Фронтенд не знает о HP, pain или identity_integrity.
    Он знает только как ИСКРИВЛЯТЬ восприятие игрока."""
    physical_state: PhysicalPresentationState = PhysicalPresentationState.HEALTHY
    mental_state: MentalPresentationState = MentalPresentationState.CALM

    # Феноменологические скаляры (Бэкенд вычисляет давление, Фронтенд генерирует кино)
    perceptual_stability: float = 1.0    # 0.0-1.0 (1.0 = кристально чистое восприятие)
    cognitive_coherence: float = 1.0     # 0.0-1.0 (0.0 = диссоциация, потеря связи "я-здесь")
    sensory_noise: float = 0.0           # 0.0-1.0 (звон, пятна, глушение)
    motor_disruption: float = 0.0        # 0.0-1.0 (тремор, замедление моторики аватара)
    perceptual_latency: float = 0.0      # 0.0-1.0, задержка сборки реальности (шок, диссоциация)
    reality_reconciliation_rate: float = 1.0 # 0.0-1.0, скорость восстановления когерентности

    # Аудио и моторные маркеры для рендера
    blood_visibility: float = 0.0        # 0.0-1.0, кровь на экране/персонаже
    breathing_profile: str = "calm"      # calm, heavy, gasping, hyperventilating
    posture_state: str = "upright"       # upright, hunched, collapsed


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
    available_actions: List[str]
    location_id: str
    weather: str
    time_of_day: str
    visible_events: List[VisibleEventDTO] = field(default_factory=list)
    game_time_seconds: int = 0
    active_traversals: List[Dict] = field(default_factory=list) # ADR-019
    avatar_state: Optional[AvatarStateDTO] = None # ADR-035: Феноменологическая проекция
    ambient_phenomenology: Optional[Dict[str, float]] = None # ADR-037: Средовое давление (температура, плотность)


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