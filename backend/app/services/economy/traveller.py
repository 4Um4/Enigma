"""
backend/app/services/economy/traveller.py
Генерация визитов странников — события, не агенты.

Странник — это внешний шок для экономики локации:
- Привозит товары которых нет
- Покупает товары которые есть
- Уходит, оставляя деньги или забирая товар

Типы визитов определяют бюджет и цели:
- SOURCING: скупка сырья (ткань, инструменты) — большой бюджет
- LUXURY: редкие товары (шёлк) — средний бюджет
- URGENT: срочная закупка всего что есть — маленький бюджет

path: /backend/app/services/economy/traveller.py
Назначение: Генерация визитов странников
Зависимости: app.core.constants, market_state
Основные сущности: VisitType, TravellerVisit, TravellerGenerator
"""
from __future__ import annotations


import random
from dataclasses import dataclass
from enum import Enum
from typing import List, Any, Dict, Optional

from app.core.constants import GOODS_PRICES
from app.services.economy.market_state import MarketState


class VisitType(Enum):
    """Тип визита определяет бюджет и цель."""

    SOURCING = "sourcing"  # Скупка сырья (ткань, инструменты)
    LUXURY = "luxury"  # Редкие товары (шёлк, украшения)
    URGENT = "urgent"  # Срочная закупка всего что есть


# Что покупать у локальных NPC (зависит от типа)
WANT_TO_BUY: Dict[VisitType, Dict[str, tuple]] = {
    # VisitType: {good_id: (min_amount, max_amount)}
    VisitType.SOURCING: {
        "cloth": (3, 8),  # ткань — основной товар
        "tools": (1, 3),  # инструменты — ремесло
    },
    VisitType.LUXURY: {
        "silk": (1, 2),  # шёлк — если есть
    },
    VisitType.URGENT: {
        "food": (5, 10),  # еда — срочная закупка
        "ale": (5, 10),  # эль
    },
}

# Что привозит для продажи (зависит от типа)
BRINGS_TO_SELL: Dict[VisitType, Dict[str, tuple]] = {
    VisitType.SOURCING: {
        "iron": (2, 5),  # сырьё для кузнеца
        "lockpick": (1, 2),  # для вора
    },
    VisitType.LUXURY: {
        "silk": (2, 5),  # шёлк для перепродажи
    },
    VisitType.URGENT: {
        "food": (5, 10),  # привозит еду если дефицит
    },
}

# Бюджет привязан к типу и целям
BUDGET_RANGES: Dict[VisitType, tuple] = {
    VisitType.SOURCING: (15.0, 40.0),  # большой — закупает много сырья
    VisitType.LUXURY: (5.0, 15.0),  # средний — мало дорогого
    VisitType.URGENT: (2.0, 8.0),  # маленький — срочный минимум
}


@dataclass
class TravellerVisit:
    """
    Один визит странника — событие, не сущность.

    Содержит всё необходимое для торговли:
    - Сколько денег готов потратить
    - Что хочет купить у локальных NPC
    - Что привозит для продажи
    """

    tick: int
    visit_type: VisitType
    gold_budget: float
    wants_to_buy: Dict[str, float]  # good_id → amount
    brings_to_sell: Dict[str, float]  # good_id → amount

    def get_buy_cost(self, prices: Dict[str, float]) -> float:
        """Рассчитать стоимость покупок по ценам."""
        return sum(
            amount * prices.get(good_id, 0.1)
            for good_id, amount in self.wants_to_buy.items()
        )

    def __repr__(self) -> str:
        buys = "+".join(f"{k}×{v:.0f}" for k, v in self.wants_to_buy.items())
        sells = "+".join(f"{k}×{v:.0f}" for k, v in self.brings_to_sell.items())
        return f"Traveller(t={self.tick}, {self.visit_type.value}, {self.gold_budget:.1f}G, buy=[{buys}], sell=[{sells}])"


class TravellerGenerator:
    """
    Генерирует визиты странников на основе MarketState.

    Не хранит состояние — использует MarketState для вероятностей.
    """

    def __init__(
        self,
        market_state: MarketState,
        rng: Optional[random.Random] = None,
    ) -> None:
        self._market = market_state
        self._rng = rng or random.Random()

    # Минимальный тик до первого визита (24 = конец первого дня)
    FIRST_VISIT_MIN_TICK: int = 24

    def maybe_generate(self, tick: int) -> Optional[TravellerVisit]:
        """
        Проверяет вероятность и генерирует визит если повезло.

        Returns:
            TravellerVisit если странник приходит, иначе None
        """
        # Странник не приходит в первый день — локация ещё "прогревается"
        if tick < self.FIRST_VISIT_MIN_TICK:
            return None

        if self._rng.random() > self._market.get_visit_probability():
            return None

        return self._generate_visit(tick)

    def _generate_visit(self, tick: int) -> TravellerVisit:
        """Создаёт визит с конкретными параметрами."""
        # Тип визита: с учётом demand_bias если есть
        demand_bias = self._market.get_demand_bias()
        visit_type = self._pick_visit_type(demand_bias)

        # Бюджет в рамках типа
        min_budget, max_budget = BUDGET_RANGES[visit_type]
        budget = round(self._rng.uniform(min_budget, max_budget), 2)

        # Что хочет купить (в рамках бюджета)
        wants = self._pick_wants(visit_type, budget)

        # Что привозит
        brings = self._pick_brings(visit_type)

        return TravellerVisit(
            tick=tick,
            visit_type=visit_type,
            gold_budget=budget,
            wants_to_buy=wants,
            brings_to_sell=brings,
        )

    def _pick_visit_type(self, demand_bias: Optional[str]) -> VisitType:
        """Выбирает тип визита. Слой 1: случайный."""
        # Слой 2 здесь бы проверял demand_bias
        return self._rng.choice(list(VisitType))

    def _pick_wants(self, visit_type: VisitType, budget: float) -> Dict[str, float]:
        """Выбирает что купить, с учётом бюджета."""
        result = {}
        options = WANT_TO_BUY.get(visit_type, {})

        for good_id, (min_amt, max_amt) in options.items():
            amount = float(self._rng.randint(min_amt, max_amt))
            cost = amount * GOODS_PRICES.get(good_id, 0.1)

            # Не превышать бюджет
            if cost <= budget * 0.8:  # 80% бюджета на одну позицию максимум
                result[good_id] = amount
                budget -= cost
            elif budget >= cost * 0.5:
                # Берём сколько можем afford
                affordable = budget / GOODS_PRICES.get(good_id, 0.1)
                if affordable >= min_amt * 0.5:
                    result[good_id] = round(affordable, 1)
                    budget -= affordable * GOODS_PRICES.get(good_id, 0.1)

        return result

    def _pick_brings(self, visit_type: VisitType) -> Dict[str, float]:
        """Выбирает что привезти для продажи."""
        result = {}
        options = BRINGS_TO_SELL.get(visit_type, {})

        for good_id, (min_amt, max_amt) in options.items():
            amount = float(self._rng.randint(min_amt, max_amt))
            result[good_id] = amount

        return result
