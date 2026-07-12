from __future__ import annotations

# backend/app/models/front.py
"""
Фаза 5.1 — Fronts: маска персонажа под давлением мира.

Принципы:
  - Front = защитная маска, которую персонаж носит чтобы соответствовать давлению.
  - Формируется ИЗВНЕ: репутация + слухи + фракционное давление → WorldPressure.
  - Поддержание Front стоит self_integrity (эрозия от маскировки).
  - Срыв Front → социальные последствия (потеря лица, разоблачение).
  - LLM получает описание Front, не числа.

  TODO:
  - Добавить "intensity" для Front, который влияет на стоимость поддержания и вероятность срыва.
  - Ввести "contextual modifiers" для более динамичного реагирования на давление (например, персонаж может выдержать больше давления в присутствии союзников).
  - Логирование принятия/срыва Front для анализа паттернов поведения персонажа и улучшения модели.
  - В будущем можно добавить "secondary fronts" для сложных персонажей, которые носят несколько масок в зависимости от ситуации (например, "tough" с друзьями, "compliant" с врагами).
  - Важно: FrontState — это часть runtime state персонажа, которая обновляется каждый тик на основе WorldPressure. Это позволяет динамически реагировать на изменения в мире и поддерживать консистентное поведение персонажа.
  - NPC с активным Front могут иметь определённые ограничения или бонусы в поведении (например, "tough" может быть менее склонен к бегству, но более агрессивен в бою).
"""


from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List


class FrontType(str, Enum):
    """Типы защитных масок персонажа."""

    NONE = "none"  # нет маски — персонаж искренен
    HUMBLE = "humble"  # смирение — низкая репутация → показная покорность
    TOUGH = "tough"  # жёсткость — страх → агрессивная защита
    COMPLIANT = "compliant"  # угодливость — долг/зависимость → согласие
    GUARDED = "guarded"  # закрытость — слухи/паранойя → минимальный контакт
    DECEPTIVE = "deceptive"  # обман — репутация ↔ истинные ценности


# Источники давления → какой Front они провоцируют
PRESSURE_FRONT_MAP: Dict[str, FrontType] = {
    "reputation_low": FrontType.HUMBLE,
    "fear_high": FrontType.TOUGH,
    "debt_high": FrontType.COMPLIANT,
    "rumors_negative": FrontType.GUARDED,
    "value_conflict": FrontType.DECEPTIVE,
}


@dataclass
class WorldPressure:
    """
    Сводное давление мира на персонажа.
    Вычисляется из ReputationEngine + SocialEngine + фракционных связей.
    НЕ хранится в персонаже — вычисляется каждый тик.
    """

    # Индивидуальные источники ∈ [0..1]
    reputation_pressure: float = 0.0  # низкая репутация в фракциях
    fear_pressure: float = 0.0  # угрозы от NPC/фракций
    debt_pressure: float = 0.0  # финансовые обязательства
    rumor_pressure: float = 0.0  # негативные слухи о персонаже
    value_conflict_pressure: float = 0.0  # конфликт ценностей с окружением

    # Итоговое давление ∈ [0..1]
    total_pressure: float = 0.0

    # Доминирующий источник (для выбора Front)
    dominant_source: str = "none"

    def compute_total(self) -> float:
        """Вычисляет итоговое давление. Вызывается после заполнения источников."""
        # Взвешенная сумма: разные источники имеют разный вес
        weights = {
            "reputation_pressure": 0.25,
            "fear_pressure": 0.30,
            "debt_pressure": 0.15,
            "rumor_pressure": 0.20,
            "value_conflict_pressure": 0.10,
        }
        total = 0.0
        max_contribution = 0.0
        dominant = "none"

        for attr, weight in weights.items():
            value = getattr(self, attr, 0.0)
            contribution = value * weight
            total += contribution
            if contribution > max_contribution:
                max_contribution = contribution
                dominant = attr

        self.total_pressure = min(total, 1.0)
        self.dominant_source = dominant
        return self.total_pressure


@dataclass
class FrontState:
    """
    Текущее состояние Front персонажа.
    Хранится в CharacterProfile как часть runtime state.
    """

    front_type: FrontType = FrontType.NONE
    intensity: float = 0.0  # сила маски ∈ [0..1]
    tick_adopted: int = 0  # тик когда Front был принят
    tick_age: int = 0  # тиков с принятия
    integrity_cost_per_tick: float = 0.0  # стоимость поддержания в self_integrity/тик

    # История срывов (для анализа паттернов)
    breaks: List[str] = field(default_factory=list)

    # Маппинг типа → стоимость поддержания за тик
    FRONT_MAINTENANCE_COST: Dict[FrontType, float] = field(
        default_factory=lambda: {
            FrontType.NONE: 0.0,
            FrontType.HUMBLE: 0.005,
            FrontType.TOUGH: 0.008,
            FrontType.COMPLIANT: 0.006,
            FrontType.GUARDED: 0.004,
            FrontType.DECEPTIVE: 0.010,  # самый дорогой — двойная жизнь
        }
    )

    @property
    def is_active(self) -> bool:
        """Есть ли активная маска."""
        return self.front_type != FrontType.NONE

    def adopt(self, front_type: FrontType, tick: int, intensity: float = 0.5) -> None:
        """Принять новую маску. Сбрасывает возраст предыдущей."""
        if front_type == self.front_type:
            # Усиление текущей маски
            self.intensity = min(1.0, self.intensity + intensity * 0.3)
            return
        self.front_type = front_type
        self.intensity = intensity
        self.tick_adopted = tick
        self.tick_age = 0
        self.integrity_cost_per_tick = self.FRONT_MAINTENANCE_COST.get(front_type, 0.0)

    def drop(self) -> None:
        """Сбросить маску (добровольно или срыв)."""
        self.front_type = FrontType.NONE
        self.intensity = 0.0
        self.tick_age = 0
        self.integrity_cost_per_tick = 0.0

    def age(self) -> float:
        """
        Инкрементировать возраст. Возвращает стоимость за этот тик.
        Стоимость растёт с возрастом (усталость от маскировки).
        """
        self.tick_age += 1
        # Стоимость растёт: base * (1 + age * 0.05)
        age_factor = 1.0 + self.tick_age * 0.05
        return self.integrity_cost_per_tick * age_factor
