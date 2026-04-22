"""
backend/app/services/economy/psycho_economy.py
Связь психологических drives с экономическим поведением NPC.

Научная база:
- Self-Determination Theory (Deci & Ryan, 1985)
- Теория привязанности (Bowlby, 1969)
- Теория импульсивности (Eysenck, 1993)

Механизм:
- Control → локус контроля, планирование → замедляет импульсивные потребности
- Significance → долгосрочные цели → перенаправляет фокус с базовых на социальные
- Fear → гипервигильность → ускоряет потребность в безопасности
- Desire → импульсивность "Тени" → ускоряет мгновенные удовольствия

Формула модификатора:
  modifier = 1.0 + (drive_value - 0.25) * weight
  
  drive=0.25 → modifier=1.0 (нейтрально, "средний" человек)
  drive=0.50 → modifier=1.125 (усилено на 12.5%)
  drive=0.00 → modifier=0.75 (ослаблено на 25%)

Назначение: Индивидуализация экономического поведения NPC
Зависимости: app.models.economy.NeedType
Основные сущности: PsychoEconomy, DECAY_WEIGHTS
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

from app.models.economy import Need, NeedType


# ── Весовые матрицы: как каждый drive влияет на каждую потребность ──
# Положительный вес → drive ускоряет рост потребности
# Отрицательный вес → drive замедляет рост потребности
# Ноль → нет влияния

DECAY_WEIGHTS: Dict[str, Dict[NeedType, float]] = {
    # Control (контроль): стратег, планирует, не отвлекается на сиюминутное
    "control": {
        NeedType.FOOD:      -0.30,  # планирует приёмы пищи, не забывает
        NeedType.SOCIAL:    -0.20,  # социальные контакты по расписанию
        NeedType.INCOME:     0.15,  # контролирует финансы, чувствителен к потере
        NeedType.SECURITY:  -0.10,  # сам создаёт безопасность, не параноит
        NeedType.SHELTER:   -0.15,  # обустроен заранее
    },
    
    # Significance (значимость): статус, признание, долгосрочные цели
    "significance": {
        NeedType.FOOD:      -0.15,  # может терпеть голод ради цели
        NeedType.SOCIAL:     0.25,  # нуждается в признании
        NeedType.INCOME:     0.20,  # деньги = статус
        NeedType.SECURITY:   0.05,  # статус требует защиты
        NeedType.SHELTER:    0.10,  # жильё отражает статус
    },
    
    # Fear (страх): гипервигильность, избегание риска
    "fear": {
        NeedType.FOOD:       0.05,  # лёгкая тревога по еде (не доминирует)
        NeedType.SOCIAL:    -0.20,  # избегает контактов из осторожности
        NeedType.INCOME:    -0.25,  # боится рисковать с деньгами
        NeedType.SECURITY:   0.40,  # гипервигильность к угрозам
        NeedType.SHELTER:    0.15,  # убежище = безопасность
    },
    
    # Desire (желание): импульсивность, "Тень", мгновенное удовольствие
    "desire": {
        NeedType.FOOD:       0.35,  # ест когда хочет, не когда нужно
        NeedType.SOCIAL:     0.20,  # ищет стимуляцию
        NeedType.INCOME:    -0.15,  # тратит impulsively, не копит
        NeedType.SECURITY:  -0.20,  # риск ради удовольствия
        NeedType.SHELTER:   -0.10,  # не привязан к месту
    },
}


@dataclass
class PsychoProfile:
    """Психологический профиль NPC для экономических расчётов."""
    control: float = 0.25
    significance: float = 0.25
    fear: float = 0.25
    desire: float = 0.25


class PsychoEconomy:
    """
    Вычисляет индивидуальные экономические параметры на основе психологии.
    """
    
    def __init__(self, profile: PsychoProfile) -> None:
        self.profile = profile
        self._modifiers: Optional[Dict[NeedType, float]] = None
    
    def get_decay_modifier(self, need_type: NeedType) -> float:
        """
        Возвращает модификатор скорости роста потребности.
        
        modifier > 1.0 → потребность растёт быстрее (хуже справляется)
        modifier < 1.0 → потребность растёт медленнее (лучше справляется)
        """
        if self._modifiers is None:
            self._modifiers = self._calculate_all_modifiers()
        return self._modifiers.get(need_type, 1.0)
    
    def apply_to_need(self, need: Need) -> Need:
        """
        Применяет психологический модификатор к потребности.
        Возвращает новую Need с изменённым decay_rate.
        """
        modifier = self.get_decay_modifier(need.need_type)
        base_decay = need.effective_decay_rate
        new_decay = round(base_decay * modifier, 4)
        
        return Need(
            need_type=need.need_type,
            base_urgency=need.base_urgency,
            budget_share=need.budget_share,
            skill_required=need.skill_required,
            neglected_ticks=need.neglected_ticks,
            decay_rate=new_decay,
        )
    
    def get_consumption_frequency(self) -> int:
        """
        Возвращает как часто NPC ест (в тиках).
        Высокий desire + низкий control → часто (каждые 4-5 действий)
        Высокий control + низкий desire → редко (каждые 8-10 действий)
        """
        # Базовое: каждые 6 действий
        base = 6
        
        # Desire ускоряет, Control замедляет
        desire_effect = (self.profile.desire - 0.25) * 8   # ±2 тика
        control_effect = (self.profile.control - 0.25) * -6  # ∓1.5 тика
        
        frequency = base + desire_effect + control_effect
        return max(3, min(12, int(frequency)))
    
    def get_savings_tendency(self) -> float:
        """
        Склонность к накоплению (0-1).
        High control + low desire → копит
        High desire + low control → тратит
        """
        control_effect = (self.profile.control - 0.25) * 1.5
        desire_effect = (self.profile.desire - 0.25) * -1.2
        fear_effect = (self.profile.fear - 0.25) * 0.5  # страх → накопление "на чёрный день"
        
        tendency = 0.5 + control_effect + desire_effect + fear_effect
        return max(0.0, min(1.0, tendency))
    
    def get_risk_tolerance(self) -> float:
        """
        Толерантность к риску (0-1).
        High fear + low control → избегает риска
        High desire + low fear → ищет риск
        """
        fear_effect = (self.profile.fear - 0.25) * -1.5
        control_effect = (self.profile.control - 0.25) * 0.5  # контроль → рассчитанный риск
        desire_effect = (self.profile.desire - 0.25) * 1.0
        
        tolerance = 0.5 + fear_effect + control_effect + desire_effect
        return max(0.0, min(1.0, tolerance))
    
    def _calculate_all_modifiers(self) -> Dict[NeedType, float]:
        """Вычисляет модификаторы для всех типов потребностей."""
        modifiers = {}
        
        for need_type in NeedType:
            total_weight = 0.0
            
            for drive_name, weights in DECAY_WEIGHTS.items():
                drive_value = getattr(self.profile, drive_name, 0.25)
                weight = weights.get(need_type, 0.0)
                # Формула: (drive - 0.25) * weight
                contribution = (drive_value - 0.25) * weight
                total_weight += contribution
            
            # Итоговый модификатор
            modifier = 1.0 + total_weight
            modifiers[need_type] = round(modifier, 3)
        
        return modifiers
    
    def debug_profile(self) -> str:
        """Отладочная строка с параметрами."""
        lines = [
            f"PsychoProfile: ctrl={self.profile.control:.2f} sig={self.profile.significance:.2f} "
            f"fear={self.profile.fear:.2f} des={self.profile.desire:.2f}",
            f"  Decay modifiers: {self._calculate_all_modifiers() if not self._modifiers else self._modifiers}",
            f"  Ест каждые {self.get_consumption_frequency()} тиков",
            f"  Склонность копить: {self.get_savings_tendency():.0%}",
            f"  Толерантность к риску: {self.get_risk_tolerance():.0%}",
        ]
        return "\n".join(lines)