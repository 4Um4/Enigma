"""
backend/app/services/economy/market_state.py
Состояние рынка для генерации визитов странников.

Архитектура:
- MarketState — абстрактный интерфейс (слой 1 и 2 реализуют по-разному)
- RandomMarketState — бимодальный автомат (quiet/active)
- ReactiveMarketState (будущее) — реагирует на цены и игроков

Принципы:
- "Тихо" = базовое состояние, визиты редки
- "Активно" = волна спроса, визиты часты
- Переход по визитам, не по времени (наблюдаемость)
- get_demand_bias() — хук для слоя 2, сейчас None

path: /backend/app/services/economy/market_state.py
Назначение: Генерация вероятности визитов странников
Зависимости: нет (чистая логика)
Основные сущности: MarketPhase, MarketState, RandomMarketState
"""
from __future__ import annotations


import random
from abc import ABC, abstractmethod
from enum import Enum
from typing import List, Dict, Any, Optional


class MarketPhase(Enum):
    """Фазы рыночного цикла."""

    QUIET = "quiet"  # Базовое состояние, визиты редки
    ACTIVE = "active"  # Волна спроса, визиты часты


class MarketState(ABC):
    """
    Абстрактный интерфейс состояния рынка.

    Слой 1 (RandomMarketState): бимодальный random
    Слой 2 (ReactiveMarketState): реакция на цены + игроков

    Код использующий MarketState не знает КАК принимается решение.
    """

    @abstractmethod
    def tick(self) -> None:
        """Обновить состояние рынка (вызывать каждый тик)."""
        ...

    @abstractmethod
    def get_visit_probability(self) -> float:
        """Вероятность визита странника в этом тике ∈ [0..1]."""
        ...

    @abstractmethod
    def get_demand_bias(self) -> Optional[str]:
        """
        Смещение спроса к конкретному товару.

        None = агрегатный спрос (тип визита случайный)
        'cloth'/'tools'/etc = специфический спрос (слой 2)

        Слой 1 всегда возвращает None.
        """
        ...

    @property
    @abstractmethod
    def phase(self) -> MarketPhase:
        """Текущая фаза рынка."""
        ...


class RandomMarketState(MarketState):
    """
    Бимодальный генератор визитов (слой 1).

    Логика:
    - quiet → active: 10%/день (внешний слух)
    - active: P(визит) = 80%/день, но не более max_visits за волну
    - active → quiet: после 2-4 визитов (рынок насытился)
    - quiet: P(визит) = 5%/день (редкие проезжие)

    Результат: ~2 визита/неделю в среднем, но кластеризованными волнами.
    """

    # Параметры переходов
    QUIET_TO_ACTIVE_CHANCE: float = 0.10  # 10% за тик (=10%/день при 24 тиках/день)
    ACTIVE_VISIT_PROBABILITY: float = 0.80  # 80% за тик в активной фазе
    QUIET_VISIT_PROBABILITY: float = 0.05  # 5% за тик в тихой фазе

    # Параметры волны
    MIN_VISITS_PER_WAVE: int = 2
    MAX_VISITS_PER_WAVE: int = 4

    def __init__(self, rng: Optional[random.Random] = None) -> None:
        self._rng = rng or random.Random()
        self._phase: MarketPhase = MarketPhase.QUIET
        self._visits_this_wave: int = 0
        self._max_visits_this_wave: int = self._rng.randint(
            self.MIN_VISITS_PER_WAVE, self.MAX_VISITS_PER_WAVE
        )

    def tick(self) -> None:
        """Обновить состояние (вызывать каждый тик)."""
        if self._phase == MarketPhase.QUIET:
            # Шанс перехода к активной фазе (слух пришёл)
            if self._rng.random() < self.QUIET_TO_ACTIVE_CHANCE:
                self._phase = MarketPhase.ACTIVE
                self._visits_this_wave = 0
                self._max_visits_this_wave = self._rng.randint(
                    self.MIN_VISITS_PER_WAVE, self.MAX_VISITS_PER_WAVE
                )

    def record_visit(self) -> None:
        """Зарегистрировать состоявшийся визит (вызывать после торговли)."""
        if self._phase == MarketPhase.ACTIVE:
            self._visits_this_wave += 1
            # Проверяем насыщение
            if self._visits_this_wave >= self._max_visits_this_wave:
                self._phase = MarketPhase.QUIET

    def get_visit_probability(self) -> float:
        """Вероятность визита в этом тике."""
        if self._phase == MarketPhase.ACTIVE:
            return self.ACTIVE_VISIT_PROBABILITY
        return self.QUIET_VISIT_PROBABILITY

    def get_demand_bias(self) -> Optional[str]:
        """Слой 1: нет смещения спроса."""
        return None

    @property
    def phase(self) -> MarketPhase:
        return self._phase

    def __repr__(self) -> str:
        return (
            f"RandomMarketState(phase={self._phase.value}, "
            f"visits={self._visits_this_wave}/{self._max_visits_this_wave})"
        )
