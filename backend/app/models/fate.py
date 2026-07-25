"""
Файл: backend/app/models/fate.py
Назначение: Состояние судьбы NPC и судьбоносные события.
Зависимости: dataclasses, enum, typing
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class FateTrajectory(str, Enum):
    STABLE = "stable"
    DETERIORATING = "deteriorating"
    IMPROVING = "improving"
    CRITICAL = "critical"

class FateOutcome(str, Enum):
    ESCAPE = "escape"
    DEATH = "death"
    BROKEN = "broken"
    LIBERATED = "liberated"
    EMPOWERED = "empowered"
    IMPRISONED = "imprisoned"

@dataclass(frozen=True)
class FateState:
    """Судьба NPC — кумулятивный результат всех воздействий.
    Шкалы нормализованы: 0..1 (в отличие от 0..100 в SocialFabric).
    """
    npc_id: str
    stability: float          # 0..1
    threat_level: float       # 0..1
    fate_trajectory: FateTrajectory
    resolved_fate: Optional[FateOutcome] = None
    fate_tick: Optional[int] = None

@dataclass(frozen=True)
class FateEvent:
    """Судьбоносное событие, наступившее с NPC."""
    npc_id: str
    event_type: FateOutcome
    tick: int
    cause: str
    description: str
