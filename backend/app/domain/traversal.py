"""
Файл: backend/app/domain/traversal.py
Назначение: Контракт воплощённой навигации (Embodied Traversal). Определяет возможности тела и оценку проходимости.
Зависимости: stdlib
Основные сущности: BodyCapabilities, TraversalMode, TraversalAssessment
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple

class TraversalMode(Enum):
    WALK = "WALK"
    JUMP = "JUMP"
    NONE = "NONE"

@dataclass(frozen=True)
class Pose:
    x: float
    y: float
    z: float = 0.0

@dataclass(frozen=True)
class WallSegment:
    x1: float
    y1: float
    x2: float
    y2: float

@dataclass(frozen=True)
class Obstacle:
    id: str = "unknown"
    x: float = 0.0
    y: float = 0.0
    w: float = 0.0
    h: float = 0.0
    height: float = 1.0

@dataclass(frozen=True)
class TransitionCandidate:
    """Геометрическое описание локального перехода через границу препятствия.
    Не зависит от BodyCapabilities — это чистая физика пространства."""
    mode: TraversalMode
    obstacle_id: str
    entry_pose: Pose
    exit_pose: Pose
    horizontal_distance: float
    vertical_delta: float
    obstacle_height: float
    trajectory_clearance: float # Signed clearance of the original source-target trajectory relative to body's collision envelope. < 0 means penetration.

@dataclass(frozen=True)
class LocalGeometry:
    """Срез геометрии, доступный NPC в пределах его восприятия."""
    walls: Tuple[WallSegment, ...] = ()
    obstacles: Tuple[Obstacle, ...] = ()
    perception_radius: float = 15.0
    center_xy: Tuple[float, float] = (0.0, 0.0)

@dataclass(frozen=True)
class BodyCapabilities:
    radius: float = 0.35
    height: float = 1.8
    can_walk: bool = True
    # S131: Базовые гуманоиды могут перешагивать мебель (canonical baseline).
    can_jump: bool = True
    max_jump_height: float = 1.0
    max_jump_distance: float = 2.0
    movement_speed: float = 2.0

@dataclass(frozen=True)
class TraversalQuery:
    source_pose: Pose
    target_pose: Pose
    body: BodyCapabilities
    allowed_modes: Tuple[TraversalMode, ...] = (TraversalMode.WALK,)

@dataclass(frozen=True)
class TraversalFeasibility:
    possible: bool
    mode: TraversalMode
    reason: Optional[str] = None
    available_clearance: Optional[float] = None
    required_capability: Optional[str] = None

@dataclass(frozen=True)
class TraversalSegment:
    """Режимный сегмент плана (Level 1).
    Описывает смену режима движения (WALK, JUMP), а не кинематическую траекторию (Level 2)."""
    mode: TraversalMode
    start_pose: Pose
    end_pose: Pose
    obstacle_id: Optional[str] = None

@dataclass(frozen=True)
class TraversalPlan:
    """Скомпилированный план локального движения тела через физическую геометрию."""
    possible: bool
    segments: Tuple[TraversalSegment, ...] = ()
    reason: Optional[str] = None
    required_capability: Optional[str] = None
    available_clearance: Optional[float] = None