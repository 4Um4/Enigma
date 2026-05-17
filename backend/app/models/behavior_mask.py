# path: backend/app/models/behavior_mask.py

"""
Поведенческая маска NPC — внешний слой поведения,
независимый от внутреннего WillState.

Файл: backend/app/models/behavior_mask.py
Назначение: Поведенческая маска NPC — внешний слой поведения
Зависимости: нет (только stdlib)
Основные сущности: BehaviorMask (Enum), BehaviorMaskState (dataclass)

WillState = что происходит внутри (broken, coerced...)
BehaviorMask = как NPC это показывает снаружи (или скрывает)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class BehaviorMask(str, Enum):
    """
    Поведенческая маска — внешний паттерн, скрывающий или искажающий
    истинное внутреннее состояние NPC.

    Не является заменой WillState. Накладывается поверх него.
    Один NPC может иметь только одну активную маску.

    str-миксин обеспечивает .value == строка — единообразно с WillState,
    EmotionTag, Intent. snapshot() сериализует без дополнительных преобразований.

    NONE            — маска отсутствует, поведение соответствует WillState
    FAKE_SUBMISSION — внешняя покорность при внутреннем сопротивлении
                      (декларирует согласие, но саботирует или выжидает)
    BETRAYAL        — скрытые действия против игрока при внешней лояльности
                      (активируется OpportunityEngine при низком риске)
    COLLAPSE        — функциональный паралич: NPC не способен действовать
                      нормально, реакции непредсказуемы или заморожены
    """

    NONE            = "none"
    FAKE_SUBMISSION = "fake_submission"
    BETRAYAL        = "betrayal"
    COLLAPSE        = "collapse"


@dataclass
class BehaviorMaskState:
    """
    Контейнер активной маски NPC.
    Хранится в NPCState как отдельное поле.

    Intensity определяет глубину маскировки:
    - 0.0–0.3: поверхностная (возможны оговорки, нервозность)
    - 0.4–0.7: устойчивая (NPC полностью контролирует внешний вид)
    - 0.8–1.0: кристаллизованная (маска срослась с поведением)

    applied_at_day нужен BreakProgressEngine для расчёта
    времени под давлением и точки возможного слома или отката.
    """

    mask: BehaviorMask = BehaviorMask.NONE

    # Глубина маскировки: 0.0 (поверхностная) — 1.0 (кристаллизованная)
    intensity: float = 0.0

    # Игровой день наложения маски (для decay и BreakProgressEngine)
    applied_at_day: Optional[int] = None

    def is_active(self) -> bool:
        """
        Маска считается активной только если она не NONE.
        Intensity = 0 при NONE — не ошибка, просто нет маски.
        """
        return self.mask is not BehaviorMask.NONE

    def is_concealment_mask(self) -> bool:
        """
        Маски скрытия (FAKE_SUBMISSION, BETRAYAL) требуют
        от EmotionalNuanceEngine показывать ложный эмоциональный слой.
        COLLAPSE — открытая маска, скрывать нечего.
        """
        return self.mask in (
            BehaviorMask.FAKE_SUBMISSION,
            BehaviorMask.BETRAYAL,
        )