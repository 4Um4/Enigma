"""
Файл: backend/app/services/social/fate_tracker.py
Назначение: Вычисление судеб и триггеринг событий.
Зависимости: typing, app.models.fate, app.models.social_fabric
"""

from typing import Dict, List, Optional

from app.models.fate import FateEvent, FateOutcome, FateState, FateTrajectory
from app.models.social_fabric import RelationshipSnapshot


class FateTracker:
    """Отслеживает судьбинные траектории всех NPC."""

    def __init__(self) -> None:
        self._states: Dict[str, FateState] = {}
        self._events: List[FateEvent] = []

    def update_state(self, npc_id: str, stability: float, threat: float) -> FateState:
        """Обновляет стабильность и угрозу NPC. Вычисляет траекторию."""
        if not (0.0 <= stability <= 1.0):
            raise ValueError("stability must be in [0, 1]")
        if not (0.0 <= threat <= 1.0):
            raise ValueError("threat must be in [0, 1]")

        current = self._states.get(npc_id)

        # Определение траектории (STABLE имеет приоритет над IMPROVING для 0.8/0.1)
        if threat > 0.8 and stability < 0.2:
            trajectory = FateTrajectory.CRITICAL
        elif threat > 0.5 or stability < 0.4:
            trajectory = FateTrajectory.DETERIORATING
        elif stability > 0.9 and threat < 0.1:
            trajectory = FateTrajectory.IMPROVING
        else:
            trajectory = FateTrajectory.STABLE

        new_state = FateState(
            npc_id=npc_id,
            stability=stability,
            threat_level=threat,
            fate_trajectory=trajectory,
            resolved_fate=current.resolved_fate if current else None,
            fate_tick=current.fate_tick if current else None
        )
        self._states[npc_id] = new_state
        return new_state

    def trigger_fate(self, npc_id: str, outcome: FateOutcome, tick: int, cause: str, description: str) -> FateEvent:
        """Принудительно вызывает судьбоносное событие. Судьба необратима."""
        current = self._states.get(npc_id)
        if not current:
            raise ValueError(f"Cannot trigger fate for unknown NPC {npc_id}")

        # P7-05.2: Судьба необратима. Нельзя триггерить повторно.
        if current.resolved_fate is not None:
            raise ValueError(f"Fate for {npc_id} already resolved to {current.resolved_fate}")

        if current.fate_trajectory != FateTrajectory.CRITICAL and outcome == FateOutcome.DEATH:
            raise ValueError(f"Cannot trigger DEATH for {npc_id} in non-CRITICAL state")

        event = FateEvent(
            npc_id=npc_id,
            event_type=outcome,
            tick=tick,
            cause=cause,
            description=description
        )
        self._events.append(event)

        # Помечаем судьбу как свершившуюся (resolved)
        self._states[npc_id] = FateState(
            npc_id=npc_id,
            stability=current.stability,
            threat_level=current.threat_level,
            fate_trajectory=FateTrajectory.CRITICAL,
            resolved_fate=outcome,
            fate_tick=tick
        )
        return event

    def get_state(self, npc_id: str) -> Optional[FateState]:
        return self._states.get(npc_id)

    def get_all_states(self) -> List[FateState]:
        return list(self._states.values())

    def get_all_events(self) -> List[FateEvent]:
        return list(self._events)
