# backend\app\services\character\character_filter.py
"""
CharacterFilter — психологический фильтр действий персонажа игрока.
Точка вставки: ПОСЛЕ DM Router, ДО DecisionHub.

Файл: backend/app/services/character/character_filter.py
Зависимости: app.models.character, typing
Основные сущности: CharacterFilter, FilterResult, ActionClassification

ПРИНЦИП: Персонаж ≠ аватар. Персонаж имеет ценности и может сопротивляться
решениям игрока, если они противоречат его природе.

КЛАССИФИКАЦИЯ ДЕЙСТВИЙ:
Router определяет ЧТО делает игрок (action_mode, event_type).
CharacterFilter определяет МОЖЕТ ЛИ персонаж это сделать (resistance).

ФОРМУЛА СОПРОТИВЛЕНИЯ:
  resistance = base_resistance * integrity_modifier * constraint_modifier
  
  base_resistance = value_conflict (из ValueSet.conflict_score)
  integrity_modifier = 0.5 + 0.5 * self_integrity (при 1.0 = 1.0, при 0.0 = 0.5)
  constraint_modifier = 1.0 + social_constraint_bonus (нормы усиливают сопротивление)

РЕЗУЛЬТАТ:
  resistance < 0.3 → ACCEPT (действие выполнено как есть)
  resistance 0.3-0.6 → MODIFY (действие ослаблено, hesitation)
  resistance 0.6-0.9 → RESIST (действие отклонено, последствия для integrity)
  resistance > 0.9 → REFUSE (редко, раздражает — используется осторожно)

КОНТРАКТ:
- НЕ использует LLM — чистый Python scorer
- НЕ меняет состояние напрямую — возвращает FilterResult
- StateApplicator для персонажа вызывается отдельно (пока не реализован)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from app.models.character import CharacterProfile

logger = logging.getLogger(__name__)


class FilterOutcome(Enum):
    """Результат фильтрации действия персонажа."""
    ACCEPT = "accept"           # Действие выполнено полностью
    MODIFY = "modify"           # Действие выполнено с ограничениями
    RESIST = "resist"           # Действие отклонено, эрозия integrity
    REFUSE = "refuse"           # Действие заблокировано (редко)


# Классификация действий: какие ценности нарушает действие
# Используется как lookup из event_type (Router) → value_conflicts
# violation_strength ∈ [0..1]: насколько сильно действие нарушает ценность
ACTION_VALUE_CONFLICTS: Dict[str, Dict[str, float]] = {
    # Насилие
    "player_attacks": {
        "compassion": 0.6,      # нападение — против сострадания
        "justice": 0.3,         # может быть справедливым (самооборона)
    },
    "player_kills": {
        "compassion": 0.9,      # убийство — сильное нарушение
        "honour": 0.5,          # если не честный бой
    },
    # Угрозы
    "player_threatens": {
        "honour": 0.4,          # угрозы — не благородно
        "compassion": 0.5,      # запугивание — против сострадания
    },
    # Воровство
    "player_steals": {
        "honour": 0.7,          # воровство — нарушает честь
        "justice": 0.6,         # нарушение закона
    },
    # Предательство
    "player_betrayes": {
        "loyalty": 0.9,         # максимальное нарушение
        "honour": 0.8,
    },
    # Ложь
    "player_lies": {
        "honour": 0.5,
        "knowledge": 0.3,       # сокрытие правды
    },
    # Позитивные действия — не генерируют конфликт
    "player_helps": {},         # пустой dict = нет конфликта
    "player_defends": {},
}


@dataclass
class FilterResult:
    """
    Результат фильтрации действия персонажа.
    Содержит решение и метаданные для下游 потребителей.
    """
    outcome: FilterOutcome
    resistance: float                    # Рассчитанное сопротивление ∈ [0..1]
    action_modifier: float               # Модификатор силы действия (1.0 = полный, 0.5 = ослаблен)
    erosion_applied: float               # Сколько эрозии применено к integrity
    hesitation_tags: List[str]           # Теги для вербализации (DM видит почему)
    modified_description: Optional[str]  # Описание модифицированного действия для DM
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "outcome": self.outcome.value,
            "resistance": round(self.resistance, 4),
            "action_modifier": round(self.action_modifier, 4),
            "erosion_applied": round(self.erosion_applied, 4),
            "hesitation_tags": self.hesitation_tags,
            "modified_description": self.modified_description,
        }


@dataclass
class CharacterFilter:
    """
    Фильтр действий персонажа.
    Получает профиль и классификацию действия → возвращает FilterResult.
    """
    # Пороги сопротивления для принятия решения
    THRESHOLD_ACCEPT: float = 0.3
    THRESHOLD_MODIFY: float = 0.6
    THRESHOLD_RESIST: float = 0.9
    
    def compute_resistance(
        self,
        profile: CharacterProfile,
        event_type: str,
        intensity: float = 0.5,
    ) -> FilterResult:
        """
        Рассчитывает сопротивление персонажа действию.
        
        Args:
            profile: Психологический профиль персонажа
            event_type: Тип события из Router (player_attacks, player_threatens и т.д.)
            intensity: Сила действия ∈ [0..1] (из Router)
        
        Returns:
            FilterResult с решением и метаданными
        """
        # 1. Определяем конфликт ценностей
        value_conflicts = ACTION_VALUE_CONFLICTS.get(event_type, {})
        base_resistance = profile.values.conflict_score(value_conflicts)
        
        # Если нет конфликта ценностей — сразу ACCEPT
        if base_resistance == 0.0:
            return FilterResult(
                outcome=FilterOutcome.ACCEPT,
                resistance=0.0,
                action_modifier=1.0,
                erosion_applied=0.0,
                hesitation_tags=[],
                modified_description=None,
            )
        
        # 2. Модификатор целостности (eroded персонаж сопротивляется слабее)
        integrity_modifier = 0.5 + 0.5 * profile.self_integrity
        
        # 3. Модификатор социальных ограничений
        constraint_bonus = 0.0
        for constraint_id, weight in profile.social_constraints.items():
            # Социальные нормы усиливают сопротивление если есть конфликт
            if weight > 0.3:
                constraint_bonus += weight * 0.1
        constraint_modifier = 1.0 + min(constraint_bonus, 0.3)  # cap +0.3
        
        # 4. Модификатор интенсивности (сильное действие → больше сопротивление)
        intensity_modifier = 0.5 + 0.5 * intensity
        
        # 5. Итоговое сопротивление
        resistance = base_resistance * integrity_modifier * constraint_modifier * intensity_modifier
        resistance = min(resistance, 1.0)  # hard cap
        
        # 6. Принятие решения
        hesitation_tags = self._build_hesitation_tags(value_conflicts, profile)
        
        if resistance < self.THRESHOLD_ACCEPT:
            outcome = FilterOutcome.ACCEPT
            action_modifier = 1.0
            erosion = 0.0
            description = None
        elif resistance < self.THRESHOLD_MODIFY:
            outcome = FilterOutcome.MODIFY
            action_modifier = 1.0 - (resistance - self.THRESHOLD_ACCEPT) * 0.5
            erosion = 0.0
            description = self._build_modify_description(hesitation_tags)
        elif resistance < self.THRESHOLD_RESIST:
            outcome = FilterOutcome.RESIST
            action_modifier = 0.0
            erosion = 0.1 * resistance  # эрозия пропорциональна сопротивлению
            description = self._build_resist_description(hesitation_tags)
        else:
            outcome = FilterOutcome.REFUSE
            action_modifier = 0.0
            erosion = 0.0  # отказ — нет эрозии, персонаж устоял
            description = self._build_refuse_description(hesitation_tags)
        
        return FilterResult(
            outcome=outcome,
            resistance=resistance,
            action_modifier=action_modifier,
            erosion_applied=erosion,
            hesitation_tags=hesitation_tags,
            modified_description=description,
        )
    
    def _build_hesitation_tags(
        self,
        value_conflicts: Dict[str, float],
        profile: CharacterProfile,
    ) -> List[str]:
        """Строит теги для вербализации колебаний персонажа."""
        tags = []
        for value_id, violation in value_conflicts.items():
            weight = profile.values.get(value_id)
            if weight > 0 and violation > 0.3:
                if weight > 0.7:
                    tags.append(f"strong_{value_id}_conflict")
                else:
                    tags.append(f"mild_{value_id}_conflict")
        
        if profile.self_integrity < 0.5:
            tags.append("eroded_integrity")
        
        return tags
    
    def _build_modify_description(self, tags: List[str]) -> str:
        """Генерирует описание модифицированного действия для DM."""
        if "eroded_integrity" in tags:
            return "персонаж выполняет действие неохотно, но уже не может сопротивляться"
        if any("strong_" in t for t in tags):
            return "персонаж колеблется, но преодолевает себя и действует"
        return "действие выполнено с лёгким замешательством"
    
    def _build_resist_description(self, tags: List[str]) -> str:
        """Генерирует описание сопротивления для DM."""
        if any("strong_" in t for t in tags):
            return "персонаж не может заставить себя это сделать — внутренний барьер слишком силён"
        return "персонаж останавливается на полпути — что-то мешает"
    
    def _build_refuse_description(self, tags: List[str]) -> str:
        """Генерирует описание отказа для DM."""
        return "персонаж категорически отказывается — это противоречит его сути"