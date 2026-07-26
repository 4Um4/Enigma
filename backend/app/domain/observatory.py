# path: backend/app/domain/observatory.py
"""
Этот контракт полностью изолирован от внутренних NodeRef и SceneState. Он содержит только то, что нужно рисовать на экране.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Tuple

@dataclass(frozen=True)
class ObservatoryNodeDTO:
    """Проекция NodeRef для рендера в редакторе."""
    node_id: str
    position: Tuple[float, float]
    role: str
    zone_id: str
    is_boundary: bool

@dataclass(frozen=True)
class ObservatoryEdgeDTO:
    """Проекция ребра графа."""
    from_node_id: str
    to_node_id: str
    traversable: bool
    block_reason: Optional[str] = None

@dataclass(frozen=True)
class ObservatorySpatialIntentDTO:
    """Чистое желание NPC."""
    target_type: str
    target_id: Optional[str]
    reason: str
    confidence: float
    context_ref: Optional[str] = None

@dataclass(frozen=True)
class ObservatoryResolutionDTO:
    """Физический факт разрешения цели."""
    status: str
    mode: Optional[str]  # NAV_NODE или LOCAL_POSITION
    position: Optional[Tuple[float, float]]
    anchor_node_id: Optional[str]
    reason: str

@dataclass(frozen=True)
class ObservatoryPathDTO:
    """Список точек для рендера линии пути."""
    status: str
    points: Tuple[Tuple[float, float], ...]
    node_ids: Tuple[str, ...]
    failure_reason: Optional[str] = None

@dataclass(frozen=True)
class ObservatoryCausalDiagnosticDTO:
    """Каузальная ошибка (например, ANCHOR_NOT_FOUND)."""
    phase: str  # RESOLUTION, PATHFINDING, TOPOLOGY
    status: str # UNAVAILABLE, BLOCKED
    code: str   # ANCHOR_NOT_FOUND, EDGE_CROSSES_WALL
    message: str

@dataclass(frozen=True)
class ObservatoryAgentDTO:
    """Агрегированное состояние NPC для Observatory."""
    actor_id: str
    position: Tuple[float, float]
    intent: Optional[ObservatorySpatialIntentDTO] = None
    resolution: Optional[ObservatoryResolutionDTO] = None
    path: Optional[ObservatoryPathDTO] = None
    diagnostics: Tuple[ObservatoryCausalDiagnosticDTO, ...] = ()

@dataclass(frozen=True)
class ObservatoryTopologyDTO:
    """Топология локации для рендера графа."""
    nodes: Tuple[ObservatoryNodeDTO, ...]
    edges: Tuple[ObservatoryEdgeDTO, ...]

@dataclass(frozen=True)
class SpatialObservatoryDTO:
    """Главный DTO для Spatial Observatory API."""
    topology: ObservatoryTopologyDTO
    agents: Tuple[ObservatoryAgentDTO, ...]
    diagnostics: Tuple[ObservatoryCausalDiagnosticDTO, ...]