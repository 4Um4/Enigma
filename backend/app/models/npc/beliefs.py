from __future__ import annotations

# backend/app/models/npc/beliefs.py
"""
Эпистемический слой NPC — убеждения о мире.

Отличие от PerceptualKernel:
  PerceptualKernel = непрерывное давление (геометрия выбора)
  BeliefState      = дискретные убеждения о фактах

Принцип владения:
  WRITE: только BeliefTransitionEngine
  READ:  BeliefModifierResolver → drive_modifiers → DecisionHub.compute()

BeliefState — тупой контейнер. Логика решений живёт снаружи.
"""


from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional


@dataclass
class BeliefFragment:
    """Одно убеждение NPC о мире."""

    value: float  # 0.0–1.0, сила убеждения
    confidence: float  # 0.0–1.0, уверенность в нём
    source: str  # "perception" | "memory" | "rumor"
    timestamp: int  # тик, когда получено


class BeliefType(str, Enum):
    """
    Закрытый реестр типов убеждений.
    Расширять здесь — не строками в коде.
    """

    DANGER = "danger"
    PLAYER_HOSTILE = "player_hostile"
    ALLY_NEARBY = "ally_nearby"
    # R8+: FOOD_SCARCE, GUARD_CORRUPT, RUMOR_BANDITS — добавлять сюда


class BeliefState:
    """
    Убеждения NPC — контейнер.

    # =========================================================================
    # BELIEF ARCHITECTURE WARNING (R8 checkpoint)
    #
    # Система содержит ДВА независимых writer'а:
    #
    #   1. BeliefTransitionEngine (R7) — реактивные episodic обновления
    #   2. CoherenceBeliefAggregator (R8) — pattern-derived semantic обновления
    #
    # Это НЕ одна и та же эпистемическая операция.
    # Сейчас: последний writer побеждает.
    #
    # Правильная архитектура (пока не реализована):
    #
    #   Observations → ObservationLayer → BeliefProjector → BeliefState
    #
    # Убеждение должно рождаться из вывода (inference),
    # а не из усреднения значений (weighted interpolation).
    #
    # НЕ вводить взвешенный merger здесь
    # без предварительного определения эпистемической семантики.
    #
    # Статус: осознанный компромисс (R8).
    # Пересмотреть после стабилизации SceneState ownership и CDS.
    # =========================================================================
    """

    def __init__(self) -> None:
        self._beliefs: Dict[BeliefType, BeliefFragment] = {}

    def get(self, key: BeliefType) -> Optional[BeliefFragment]:
        """Читать убеждение. None если отсутствует."""
        return self._beliefs.get(key)

    def update(self, key: BeliefType, fragment: BeliefFragment) -> None:
        """
        Записать убеждение.
        WRITE: вызывается только из BeliefTransitionEngine.
        """
        self._beliefs[key] = fragment

    def all(self) -> Dict[BeliefType, BeliefFragment]:
        """Все убеждения — для отладки и CDS."""
        return dict(self._beliefs)
