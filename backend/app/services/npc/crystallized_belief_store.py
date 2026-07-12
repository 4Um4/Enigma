"""
path: backend/app/services/npc/crystallized_belief_store.py
Назначение: In-memory хранилище кристаллизованных убеждений NPC (L2.5).
Зависимости: backend/app/domain/identity_events.py
Основные сущности: CrystallizedBeliefStore
"""

from typing import Dict, List

from app.domain.identity_events import CrystallizedBelief


class CrystallizedBeliefStore:
    """
    Хранилище убеждений, кристаллизованных BeliefCrystallizationEngine.

    ADR-O-305: Разделено от BeliefState (R7/R8), чтобы избежать DOUBLE TRUTH.
    """

    def __init__(self):
        self._beliefs: Dict[str, List[CrystallizedBelief]] = {}

    def get_beliefs(self, npc_id: str) -> List[CrystallizedBelief]:
        """Чтение убеждений NPC для передачи в резолвер."""
        return self._beliefs.get(npc_id, [])

    def query_all(self, npc_id: str) -> List[CrystallizedBelief]:
        """SHI-FIX: Alias for get_beliefs for causal_validation test."""
        return self.get_beliefs(npc_id)

    def update_beliefs(self, npc_id: str, beliefs: List[CrystallizedBelief]) -> None:
        """Запись обновлённых убеждений после работы BeliefCrystallizationEngine."""
        self._beliefs[npc_id] = beliefs
