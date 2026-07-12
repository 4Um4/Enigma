from __future__ import annotations
# backend/app/services/economy/need_engine.py
"""
NeedEngine — движок потребностей NPC.
Работает в фоне, независимо от игрока.

Назначение: Движок потребностей — обновляет urgency, авто-удовлетворение, генерация драйвов.
Зависимости: app.models.economy
Основные сущности: NeedEngine, NeedDrive

ОТВЕЧАЕТ ЗА:
1. Обновление neglected_ticks (каждый мирный тик)
2. Авто-удовлетворение (если есть ресурс в инвентаре)
3. Генерация драйвов для DecisionHub (urgency > 0.6)

НЕ ОТВЕЧАЕТ ЗА:
- Решения КАК удовлетворить потребность (DecisionHub)
- Транзакции (TransactionEngine)
"""


import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List

from app.models.economy import EconomicProfile, NeedType

logger = logging.getLogger(__name__)


class DriveType(Enum):
    """Драйвы, генерируемые NeedEngine для DecisionHub."""

    HUNGER = "hunger"  # Нужно еду
    THIRST = "thirst"  # Нужно воду (пока = FOOD)
    SHELTER_URGE = "shelter_urge"  # Нужно жильё
    INCOME_URGE = "income_urge"  # Нужны деньги
    SOCIAL_URGE = "social_urge"  # Нужно общение
    SECURITY_URGE = "security_urge"  # Чувствует угрозу
    CLEANLINESS_URGE = "cleanliness"  # Нужно навести порядок
    OBLIGATION_URGE = "obligation"  # Давление обязательства


# Маппинг: NeedType → DriveType
NEED_TO_DRIVE: Dict[NeedType, DriveType] = {
    NeedType.FOOD: DriveType.HUNGER,
    NeedType.SHELTER: DriveType.SHELTER_URGE,
    NeedType.INCOME: DriveType.INCOME_URGE,
    NeedType.SOCIAL: DriveType.SOCIAL_URGE,
    NeedType.SECURITY: DriveType.SECURITY_URGE,
    NeedType.CLEANLINESS: DriveType.CLEANLINESS_URGE,
    NeedType.TOOLS: DriveType.INCOME_URGE,  # инструменты → нужно заработать
    NeedType.INFORMATION: DriveType.SOCIAL_URGE,  # слухи → общение
}

# Ресурсы для авто-удовлетворения
NEED_AUTO_GOODS: Dict[NeedType, str] = {
    NeedType.FOOD: "food",
    # Другие потребности не авто-удовлетворяются предметами
}


@dataclass
class NeedDrive:
    """
    Сигнал от NeedEngine к DecisionHub.
    Содержит тип драйва и его силу (для модификации score).
    """

    drive_type: DriveType
    strength: float  # ∈ [0..1], based on urgency
    source_need: NeedType  # Какая потребность генерирует
    reason: str  # Для логирования

    @property
    def is_critical(self) -> bool:
        """Критический драйв (urgency > 0.85)."""
        return self.strength > 0.85


# Маппинг: Активность -> Потребность (для удовлетворения)
_ACTIVITY_TO_NEED: Dict[str, NeedType] = {
    "eating": NeedType.FOOD,
    "resting": NeedType.SHELTER,
    "socializing": NeedType.SOCIAL,
    "dwelling": NeedType.SHELTER,
    "drinking": NeedType.SOCIAL,
}


@dataclass
class NeedEngine:
    """
    Движок потребностей NPC.
    Вызывается каждый мирный тик для обновления состояния.
    """

    def tick(
        self, profile: EconomicProfile, current_activity: str = ""
    ) -> List[NeedDrive]:
        """
        Обрабатывает один тик для NPC.

        Args:
            profile: Экономический профиль NPC.
            current_activity: Текущая активность NPC (из routine).

        Returns: список активных драйвов (urgency > 0.6)
        """
        drives: List[NeedDrive] = []

        # 0. Удовлетворение потребностей через активность (ADR-S96.4)
        if current_activity:
            for activity, need_type in _ACTIVITY_TO_NEED.items():
                if activity in current_activity:
                    profile.satisfy_need(need_type)

        # 1. Обновляем neglected_ticks для всех потребностей
        profile.tick_needs()

        # 2. Авто-удовлетворение ОТКЛЮЧЕНО — еда/питьё — это РЕШЕНИЕ NPC, не рефлекс
        # Вызов вручную через ConsumptionResolver если NPC решает поесть

        # 3. Генерируем драйвы для срочных потребностей
        for need in profile.base_needs:
            if need.is_urgent:
                drive_type = NEED_TO_DRIVE.get(need.need_type, DriveType.INCOME_URGE)
                drive = NeedDrive(
                    drive_type=drive_type,
                    strength=need.effective_urgency,
                    source_need=need.need_type,
                    reason=f"{need.need_type.value} urgency={need.effective_urgency:.2f}",
                )
                drives.append(drive)

        # 4. Генерируем драйв от просроченных обязательств
        overdue = profile.get_overdue_obligations()
        if overdue:
            # Берём самое срочное обязательство
            most_urgent = max(overdue, key=lambda o: o.amount * o.penalty_per_tick)
            drives.append(
                NeedDrive(
                    drive_type=DriveType.OBLIGATION_URGE,
                    strength=1.0,  # просрочка = максимальный драйв
                    source_need=NeedType.INCOME,  # нужно деньги
                    reason=f"overdue {most_urgent.obligation_type}: {most_urgent.amount}G to {most_urgent.creditor_id}",
                )
            )

        return drives

    def _auto_satisfy(self, profile: EconomicProfile) -> List[NeedType]:
        """
        Авто-удовлетворение: если у NPC есть ресурс и потребность срочная.
        Пример: есть food в инвентаре + FOOD urgent → списать 1 food, сбросить neglect.

        Returns: список удовлетворённых потребностей.
        """
        satisfied: List[NeedType] = []

        for need in profile.base_needs:
            if not need.is_urgent:
                continue

            good_id = NEED_AUTO_GOODS.get(need.need_type)
            if not good_id:
                continue

            if profile.has_good(good_id, amount=1.0):
                profile.remove_good(good_id, amount=1.0)
                profile.satisfy_need(need.need_type)
                satisfied.append(need.need_type)
                logger.debug(
                    f"[NEED_ENGINE] {profile.npc_id}: auto-satisfied {need.need_type.value}"
                )

        return satisfied

    def get_wealth_stress(self, profile: EconomicProfile) -> float:
        """
        Рассчитывает стресс от бедности.
        Если wealth_level < 0.2 и нет дохода — +0.01 за тик.

        Returns: стресс-дельта ∈ [0..1]
        """
        if profile.wealth_level >= 0.2:
            return 0.0

        # Нет доходов = хуже
        has_income = any(v > 0 for v in profile.income_sources.values())
        if not has_income:
            # Бедность + безработица = максимальный стресс
            return 0.02
        else:
            # Бедность но есть работа = умеренный стресс
            return 0.01

    def get_obligation_stress(self, profile: EconomicProfile) -> float:
        """
        Рассчитывает стресс от просроченных обязательств.

        Returns: стресс-дельта ∈ [0..1]
        """
        overdue = profile.get_overdue_obligations()
        if not overdue:
            return 0.0

        # Суммируем штрафы от всех просрочек
        total_penalty = sum(o.penalty_per_tick for o in overdue)
        return min(total_penalty, 0.05)  # cap 0.05 за тик
