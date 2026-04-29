# path: backend/app/domain/tick.py
"""
Назначение: DTO результата тика — пересекает границу orchestrator → API → frontend
Зависимости: dataclasses, typing, domain.snapshot
Основные сущности: TickResultDTO
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional

from app.domain.snapshot import WorldSnapshotDTO


@dataclass(frozen=True)
class TickResultDTO:
    """Результат одного тика мира.
    
    Пересекает границу TickOrchestrator → API layer.
    Содержит только то, что нужно API для ответа клиенту.
    """
    status: str                           # "ok" | "no_scene" | "error"
    changes_count: int = 0
    significant_events: List[dict] = field(default_factory=list)
    world_snapshot: Optional[WorldSnapshotDTO] = None
    error: Optional[str] = None

    # TODO: удалить после A1 — npc_positions уже внутри world_snapshot
    npc_positions: dict = field(default_factory=dict)