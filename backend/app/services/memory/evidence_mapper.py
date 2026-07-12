from __future__ import annotations

# backend/app/services/memory/evidence_mapper.py
"""
EvidenceMapper: EventMemory → Evidence.

ИНВАРИАНТ: не использует event_type напрямую.
Работает только с:
  - memory.tags (semantic tags от EventSemanticTagger)
  - memory.actor_id (кто совершил)
  - memory.importance, memory.confidence (вес)

Масштабируемость:
  Новый тип убеждения → добавить правило в _RULES.
  Новый маппер → реализовать EvidenceMapper Protocol.
"""


from dataclasses import dataclass
from typing import TYPE_CHECKING, List, Protocol

if TYPE_CHECKING:
    from app.models.npc_state import EventMemory

from app.models.npc.beliefs import BeliefType

# ============================================================================
# Evidence — единица доказательства
# ============================================================================


@dataclass
class Evidence:
    """
    Одно доказательство в пользу или против убеждения.

    direction: +1.0 = поддержка, -1.0 = противоречие.
    weight: importance × confidence (не нормирован, агрегатор суммирует).
    """

    belief_type: BeliefType
    direction: float  # +1.0 / -1.0
    weight: float  # importance × confidence
    actor_id: str  # о ком доказательство
    observer_npc_id: str  # кто наблюдал


# ============================================================================
# Protocol
# ============================================================================


class EvidenceMapper(Protocol):
    """
    Контракт: один метод, одна ответственность.
    Не знает про AggregatОр. Только извлекает.
    """

    def extract(self, memory: "EventMemory") -> List[Evidence]:
        """Извлечь доказательства из одной записи памяти."""
        ...


# ============================================================================
# Правила маппинга semantic tag → (BeliefType, direction)
# Единственное место где semantic tag знается для belief.
# ============================================================================

_RULES: List[tuple[frozenset[str], BeliefType, float]] = [
    # Агрессия игрока → поддержка PLAYER_HOSTILE
    (
        frozenset({"social:aggression", "social:player_actor"}),
        BeliefType.PLAYER_HOSTILE,
        +1.0,
    ),
    # Физический вред → поддержка DANGER
    (frozenset({"social:physical_harm"}), BeliefType.DANGER, +1.0),
    # Запугивание → умеренная поддержка DANGER
    (frozenset({"social:intimidation"}), BeliefType.DANGER, +0.6),
    # Доброжелательность игрока → противоречие PLAYER_HOSTILE
    (
        frozenset({"social:benevolence", "social:player_actor"}),
        BeliefType.PLAYER_HOSTILE,
        -0.5,
    ),
    # Экстремальный вред → сильная поддержка DANGER
    (frozenset({"social:extreme_harm"}), BeliefType.DANGER, +1.5),
]

# Множитель для высокой интенсивности
_HIGH_INTENSITY_TAG = "social:high_intensity"
_HIGH_INTENSITY_MULT = 1.5


# ============================================================================
# Первая реализация
# ============================================================================


class SemanticTagEvidenceMapper:
    """
    Извлекает Evidence на основе semantic tags и actor_id.
    Не знает event_type. Не знает BeliefAggregator.
    """

    def extract(self, memory: "EventMemory") -> List[Evidence]:
        """Применить правила к тегам памяти."""

        tag_set = frozenset(memory.tags)
        base_weight = memory.importance * memory.confidence
        intensity_mult = _HIGH_INTENSITY_MULT if _HIGH_INTENSITY_TAG in tag_set else 1.0

        results: List[Evidence] = []

        for required_tags, belief_type, direction in _RULES:
            # Правило срабатывает если все требуемые теги присутствуют
            if required_tags.issubset(tag_set):
                results.append(
                    Evidence(
                        belief_type=belief_type,
                        direction=direction,
                        weight=round(base_weight * intensity_mult, 4),
                        actor_id=memory.actor_id,
                        observer_npc_id=memory.npc_id,
                    )
                )

        return results
