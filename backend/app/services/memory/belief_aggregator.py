from __future__ import annotations
# backend/app/services/memory/belief_aggregator.py
"""
BeliefAggregator: Evidence[] → BeliefFragment[].

Инвариант:
  Убеждение рождается из накопленного паттерна доказательств,
  а не из отдельного события.

Protocol: интерфейс стабилен.
CoherenceBeliefAggregator: первая реализация (заменяема).
"""


from collections import defaultdict
from typing import Any, TYPE_CHECKING, Dict, List, Protocol, Tuple

from app.models.npc.beliefs import BeliefFragment, BeliefType

if TYPE_CHECKING:
    from app.services.memory.evidence_mapper import Evidence


# ============================================================================
# Protocol — архитектурный инвариант
# ============================================================================


class BeliefAggregator(Protocol):
    """
    Превращает накопленные доказательства в убеждения.
    Не знает про EventMemory, EventType или pipeline.
    """

    def assess(
        self,
        evidence_list: "List[Evidence]",
        current_tick: int,
    ) -> List[Tuple[BeliefType, BeliefFragment]]:
        """
        Оценить паттерн Evidence и вернуть убеждения.
        Пустой список = доказательств недостаточно.
        """
        ...


# ============================================================================
# CoherenceBeliefAggregator — первая реализация
# ============================================================================


# WRITE PATH 2/2: CoherenceBeliefAggregator → BeliefState
# Pattern-based (R8): обновляет убеждения из накопленных воспоминаний.
# Первый writer — BeliefTransitionEngine (R7).
# Без правила мёрджа между ними. См. BeliefState docstring.
class CoherenceBeliefAggregator:
    """
    belief_strength = support / (support + |contradiction|)
    Убеждение формируется когда:
      support > MINIMUM_SUPPORT
      belief_strength > COHERENCE_THRESHOLD
    """

    # Пороги (настраиваются, не архитектурный закон)
    MINIMUM_SUPPORT: float = 1.5  # минимальная сумма весов поддержки
    COHERENCE_THRESHOLD: float = 0.60  # минимальная согласованность

    def assess(
        self,
        evidence_list: "List[Evidence]",
        current_tick: int,
    ) -> List[Tuple[BeliefType, BeliefFragment]]:

        if not evidence_list:
            return []

        # Группируем по belief_type
        # actor_id — для будущей адресации (R9+)
        support_by: Dict[BeliefType, float] = defaultdict(float)
        contradiction_by: Dict[BeliefType, float] = defaultdict(float)
        actor_by: Dict[BeliefType, str] = {}

        for ev in evidence_list:
            if ev.direction > 0:
                support_by[ev.belief_type] += ev.weight * ev.direction
            else:
                contradiction_by[ev.belief_type] += ev.weight * abs(ev.direction)
            # Запоминаем самый частый актор (упрощение для R8)
            if ev.actor_id and ev.belief_type not in actor_by:
                actor_by[ev.belief_type] = ev.actor_id

        results: List[Tuple[BeliefType, BeliefFragment]] = []

        for belief_type in set(support_by) | set(contradiction_by):
            support = support_by[belief_type]
            contradiction = contradiction_by[belief_type]

            if support < self.MINIMUM_SUPPORT:
                continue  # недостаточно доказательств

            total = support + contradiction
            coherence = support / total if total > 0 else 0.0

            if coherence < self.COHERENCE_THRESHOLD:
                continue  # слишком много противоречий

            # Уверенность растёт с количеством доказательств (не более 1.0)
            confidence = min(1.0, support / (self.MINIMUM_SUPPORT * 4))

            results.append(
                (
                    belief_type,
                    BeliefFragment(
                        value=round(coherence, 4),
                        confidence=round(confidence, 4),
                        source="belief_aggregator",
                        timestamp=current_tick,
                    ),
                )
            )

        return results
