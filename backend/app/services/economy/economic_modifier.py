# backend/app/services/economy/economic_modifier.py
"""
EconomicModifier — модификатор score для DecisionHub.
Аналогично BehaviorMask, но на основе экономики.

Назначение: Модификатор score для DecisionHub на основе экономического состояния NPC.
Зависимости: app.models.economy, app.services.economy.need_engine
Основные сущности: EconomicModifier

ПРИНЦИП: Экономика не создаёт новые интенты, а усиливает/ослабляет существующие.
- Голодный NPC → TRADE score усилен (попытка купить/выменять еду)
- Бедный NPC → TRADE усилен (нужны деньги)
- Просроченное обязательство → TRADE сильно усилен (срочная потребность)

ИНТЕГРАЦИЯ: Вызывается в DecisionHub._score_all() после _score_components().
Формула: scores[intent] *= economic_modifier или scores[intent] += bonus
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

from app.models.economy import EconomicProfile, NeedType
from app.services.economy.need_engine import NeedDrive, DriveType

logger = logging.getLogger(__name__)


# Маппинг: DriveType → какие интенты усиливает и на сколько
# Формат: {intent: bonus_to_score}
DRIVE_INTENT_MAP: Dict[DriveType, Dict[str, float]] = {
    DriveType.HUNGER: {
        "trade": 0.35,      # попытка купить/выменять еду
        "talk": 0.15,       # попросить еду у игрока
        "help": -0.2,       # не будет помогать когда голоден
    },
    DriveType.INCOME_URGE: {
        "trade": 0.30,      # попытка заработать
        "talk": 0.20,       # попросить работу
    },
    DriveType.OBLIGATION_URGE: {
        "trade": 0.45,      # срочная необходимость в деньгах
        "talk": 0.25,       # попросить отсрочку/помощь
        "flee": 0.10,       # мысль сбежать от кредитора
    },
    DriveType.SHELTER_URGE: {
        "trade": 0.20,      # попытка найти жильё
        "talk": 0.15,       # попросить приют
    },
    DriveType.SOCIAL_URGE: {
        "talk": 0.25,       # поиск общения
        "observe": 0.10,    # пойти туда где люди
    },
    DriveType.SECURITY_URGE: {
        "flee": 0.30,       # убежать от угрозы
        "observe": 0.20,    # следить за обстановкой
        "talk": -0.10,      # меньше болтать когда страшно
    },
    DriveType.CLEANLINESS_URGE: {
        "idle": 0.20,       # заняться уборкой вместо активных действий
        "trade": -0.10,     # не до торговли когда грязно
    },
}


@dataclass
class EconomicModifierResult:
    """Результат расчёта экономического модификатора."""
    modifiers: Dict[str, float]        # intent → modifier (добавляется к score)
    active_drives: List[str]           # список активных драйвов (для логов)
    wealth_bonus: float                # бонус/штраф от богатства
    
    def to_dict(self) -> Dict:
        return {
            "modifiers": self.modifiers,
            "active_drives": self.active_drives,
            "wealth_bonus": self.wealth_bonus,
        }


@dataclass
class EconomicModifier:
    """
    Рассчитывает экономические модификаторы score для DecisionHub.
    Вызывается один раз на compute(), не имеет состояния.
    """
    
    def calculate(
        self,
        profile: Optional[EconomicProfile],
        drives: List[NeedDrive],
    ) -> EconomicModifierResult:
        """
        Рассчитывает модификаторы score на основе экономического состояния.
        
        Args:
            profile: Экономический профиль NPC (None = нет экономики, без модификаторов)
            drives: Активные драйвы от NeedEngine
        
        Returns:
            EconomicModifierResult с модификаторами по интентам
        """
        if not profile:
            return EconomicModifierResult(
                modifiers={},
                active_drives=[],
                wealth_bonus=0.0,
            )
        
        modifiers: Dict[str, float] = {}
        active_drive_names: List[str] = []
        
        # 1. Модификаторы от драйвов потребностей
        for drive in drives:
            drive_mods = DRIVE_INTENT_MAP.get(drive.drive_type, {})
            for intent, bonus in drive_mods.items():
                # Умножаем бонус на силу драйва (критический драйв = полный бонус)
                scaled_bonus = bonus * drive.strength
                modifiers[intent] = modifiers.get(intent, 0.0) + scaled_bonus
            active_drive_names.append(f"{drive.drive_type.value}({drive.strength:.2f})")
        
        # 2. Модификатор от богатства
        wealth_bonus = self._wealth_modifier(profile)
        # Богатый NPC менее мотивирован на TRADE
        if "trade" in modifiers:
            modifiers["trade"] += wealth_bonus * -0.15
        
        # 3. Clamp модификаторов (не давать больше +0.6 к одному интенту)
        for intent in modifiers:
            modifiers[intent] = max(-0.5, min(0.6, modifiers[intent]))
            modifiers[intent] = round(modifiers[intent], 4)
        
        return EconomicModifierResult(
            modifiers=modifiers,
            active_drives=active_drive_names,
            wealth_bonus=round(wealth_bonus, 4),
        )
    
    def _wealth_modifier(self, profile: EconomicProfile) -> float:
        """
        Модификатор от богатства.
        wealth_level 1.0 = +1.0 (комфорт, меньше мотивации)
        wealth_level 0.0 = 0.0 (бедность, нет бонуса)
        """
        return profile.wealth_level