# path: backend/app/domain/spatial_target.py
from enum import Enum
from typing import Optional, Tuple
from dataclasses import dataclass

class SpatialTargetType(Enum):
    NPC = "NPC"
    ANCHOR = "ANCHOR"
    REGION = "REGION"
    BOUNDARY = "BOUNDARY"
    POSITION = "POSITION"           # Используется только для FLEE/AVOID
    EMERGENT_PLACE = "EMERGENT"

class TargetResolutionStatus(Enum):
    RESOLVED = "RESOLVED"
    UNAVAILABLE = "UNAVAILABLE"     # Цель не существует или заблокирована
    STALE = "STALE"                 # Мир изменился, требуется перерасчёт
    BLOCKED = "BLOCKED"             # Путь невозможен

class SpatialResolutionMode(Enum):
    """Архитектурный режим разрешения цели (макро-узел или микро-позиция)."""
    NAV_NODE = "nav_node"
    LOCAL_POSITION = "local_position"

@dataclass(frozen=True)
class EmergentPlaceRef:
    """Provenance для эмерджентных мест из L1Chronicle."""
    place_id: str
    owner_id: str
    source: str
    confidence: float

@dataclass(frozen=True)
class SpatialTargetIntent:
    """
    Чистое семантическое желание NPC.
    Не содержит координат и узлов.
    """
    target_type: SpatialTargetType
    target_id: Optional[str]
    reason: str
    confidence: float
    emergent_ref: Optional[EmergentPlaceRef] = None
    context_ref: Optional[str] = None  # ADR-O-330: ID сущности, относительно которой вычисляется цель (FLEE threat)

@dataclass(frozen=True)
class ResolvedSpatialTarget:
    """
    Физический факт, вычисленный Spatial Kernel.
    """
    intent: SpatialTargetIntent
    resolution_status: TargetResolutionStatus
    mode: Optional[SpatialResolutionMode] = None  # None, если цель не разрешена (UNAVAILABLE)
    position: Optional[Tuple[float, float]] = None
    anchor_node_id: Optional[str] = None
    resolution_reason: str = ""