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


@dataclass(frozen=True)
class BeliefFragment:
    """Одно убеждение NPC о мире."""

    value: float  # 0.0–1.0, сила убеждения
    confidence: float  # 0.0–1.0, уверенность в нём
    source: str  # "perception" | "memory" | "rumor"
    timestamp: int  # тик, когда получено


@dataclass(frozen=True)
class BeliefDelta:
    """Delta для применения к BeliefState (SSOT epistemic)."""
    belief_type: BeliefType
    old_value: float
    new_value: float
    confidence: float
    source: str
    timestamp: int


class BeliefType(str, Enum):
    """
    Закрытый реестр типов убеждений.
    Расширять здесь — не строками в коде.
    """

    DANGER = "danger"
    PLAYER_HOSTILE = "player_hostile"
    # R8+: FOOD_SCARCE, GUARD_CORRUPT, RUMOR_BANDITS, ALLY_NEARBY — добавлять сюда при реализации


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

    # E2.0-c/D3 (ADR-SSOT-EPISTEMIC): guard единственной точки записи.
    # Экзамен доказал: beliefs.update открыт — прямая запись DANGER мимо
    # BeliefTransitionEngine/DeltaGate проходит молча. Легальные writer'ы
    # по цензусу E2.0-c: два R8-канала (BTE — тиковая ветка, генерирует
    # BeliefDelta; CoherenceBeliefAggregator — pattern-based) + загрузчик
    # персистенции + сам модуль. Тестовые исключения — по цензусу;
    # causal_state_test сюда НЕ вносить: его D3-атака обязана поднимать
    # ArchitecturalViolationError (замок экзамена).
    _UPDATE_ALLOWED_WRITERS = {
        "app.models.npc.beliefs",
        "app.models.npc_state",          # загрузка psyche["beliefs"] (npc_state:1022)
        # E2.0-c/D3: загрузка персистенции — _beliefs_from_persistence
        # (npc_loader:583, вызовы 561/661) строит BeliefState из psyche["beliefs"]
        # через update(). Прецедент: npc_loader в _ALLOWED_WRITERS NPCState-guard.
        # Поймано замком test_beliefs_round_trip_full_cycle (44/45).
        "app.services.npc.npc_loader",
        "app.services.npc.belief_transition_engine",
        "app.services.npc.state_applicator",
        "app.services.memory.belief_aggregator",
        # Тестовые исключения (цензус E2.0-c):
        "tests.sandbox.SUPERBOX.npc_sandbox",
        "tests.sandbox.SUPERBOX.scenarios.epistemic_runtime_closure_test",
        "tests.sandbox.SUPERBOX.scenarios.epistemic_scheduler_closure_test",
    }

    def update(self, key: BeliefType, fragment: BeliefFragment) -> None:
        """
        Записать убеждение.
        WRITE: два легальных канала (R8) + загрузка; см. _UPDATE_ALLOWED_WRITERS.
        """
        import sys

        _caller = sys._getframe(1).f_globals.get("__name__", "")
        if _caller not in self._UPDATE_ALLOWED_WRITERS:
            from app.errors import ArchitecturalViolationError

            raise ArchitecturalViolationError(f"beliefs.update({key.value})", _caller)
        self._beliefs[key] = fragment

    def all(self) -> Dict[BeliefType, BeliefFragment]:
        """Все убеждения — для отладки и CDS."""
        return dict(self._beliefs)
