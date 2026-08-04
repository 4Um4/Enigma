"""
path: /project/backend/app/domain/movement_contract.py
Назначение: Формальный контракт диагностики движения (S-141). 
Защищает систему от тихой деградации pipeline'а перемещений, предоставляя 
четкую таксономию ошибок (MovementFailure) и состояний пути (PathStatus).
Зависимости: стандартные типы данных.
Основные сущности: PathStatus, MovementFailure, MovementTrace.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, List, Optional, Tuple
# BUG-DOMAIN-PURITY FIX (§1.2): Убираем импорт из models, используем Any для аннотации типа


class PathStatus(Enum):
    """Чёткие состояния результата поиска пути."""
    NO_PATH = "NO_PATH"
    ALREADY_AT_TARGET = "ALREADY_AT_TARGET"
    VALID_PATH = "VALID_PATH"


class MovementFailure(Enum):
    """Таксономия ошибок движения для быстрой локализации разрыва контура."""
    NONE = "M000"
    INVALID_SOURCE_POSITION = "M001"
    SOURCE_NODE_NOT_FOUND = "M002"
    TARGET_NODE_NOT_FOUND = "M003"
    GRAPH_DISCONNECTED = "M004"
    NO_PATH = "M005"
    TRAVERSAL_CREATION_FAILED = "M006"
    TRAVERSAL_NOT_EXECUTED = "M007"
    POSITION_COMMIT_FAILED = "M008"


@dataclass
class MovementTrace:
    """Чёрный ящик движения (S-141). Фиксирует каждый шаг перемещения NPC."""
    actor_id: str
    
    source_position: Optional[Tuple[float, float]] = None
    source_node: Optional[Any] = None
    
    target_node: Optional[Any] = None
    
    path_status: PathStatus = PathStatus.NO_PATH
    path_nodes: List[Any] = field(default_factory=list)
    
    traversal_created: bool = False
    failure: MovementFailure = MovementFailure.NONE
    reason: str = ""

    def is_success(self) -> bool:
        return self.failure == MovementFailure.NONE and self.traversal_created