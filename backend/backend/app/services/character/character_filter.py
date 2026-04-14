# backend/app/services/character/character_filter.py
"""
CharacterFilter — психологический фильтр действий персонажа игрока.
Точка вставки: ПОСЛЕ DM Router, ДО DecisionHub.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

from app.models.character import CharacterProfile

logger = logging.getLogger(__name__)


class FilterOutcome(Enum):
    ACCEPT = "accept"
    MODIFY = "modify"
    RESIST = "resist"
    REFUSE = "refuse"


ACTION_VALUE_CONFLICTS: Dict[str, Dict[str, float]] = {
    "player_attacks": {"compassion": 0.6, "justice": 0.3},
    "player_kills": {"compassion": 0.9, "honour": 0.5},
    "player_threatens": {"honour": 0.4, "compassion": 0.5},
    "player_steals": {"honour": 0.7, "justice": 0.6},
    "player_betrayes": {"loyalty": 0.9, "honour": 0.8},
    "player_lies": {"honour": 0.5, "knowledge": 0.3},
    "player_helps": {},
    "player_defends": {},
}


@dataclass
class FilterResult:
    outcome: FilterOutcome
    resistance: float
    action_modifier: float
    erosion_applied: float
    hesitation_tags: List[str]
    modified_description: Optional[str]

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
    THRESHOLD_ACCEPT: float = 0.3
    THRESHOLD_MODIFY: float = 0.6
    THRESHOLD_RESIST: float = 0.9

    def compute_resistance(
        self,
        profile: CharacterProfile,
        event_type: str,
        intensity: float = 0.5,
    ) -> FilterResult:
        value_conflicts = ACTION_VALUE_CONFLICTS.get(event_type, {})
        base_resistance = profile.values.conflict_score(value_conflicts)
        
        if base_resistance == 0.0:
            return FilterResult(
                outcome=FilterOutcome.ACCEPT,
                resistance=0.0,
                action_modifier=1.0,
                erosion_applied=0.0,
                hesitation_tags=[],
                modified_description=None,
            )
        
        integrity_modifier = 0.5 + 0.5 * profile.self_integrity
        
        constraint_bonus = 0.0
        for weight in profile.social_constraints.values():
            if weight > 0.3:
                constraint_bonus += weight * 0.1
        constraint_modifier = 1.0 + min(constraint_bonus, 0.3)
        
        intensity_modifier = 0.5 + 0.5 * intensity
        
        resistance = base_resistance * integrity_modifier * constraint_modifier * intensity_modifier
        resistance = min(resistance, 1.0)
        
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
            erosion = 0.1 * resistance
            description = self._build_resist_description(hesitation_tags)
        else:
            outcome = FilterOutcome.REFUSE
            action_modifier = 0.0
            erosion = 0.0
            description = self._build_refuse_description(hesitation_tags)
        
        return FilterResult(
            outcome=outcome,
            resistance=resistance,
            action_modifier=action_modifier,
            erosion_applied=erosion,
            hesitation_tags=hesitation_tags,
            modified_description=description,
        )

    def _build_hesitation_tags(self, value_conflicts: Dict[str, float], profile: CharacterProfile) -> List[str]:
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
        if "eroded_integrity" in tags:
            return "персонаж выполняет действие неохотно, но уже не может сопротивляться"
        if any("strong_" in t for t in tags):
            return "персонаж колеблется, но преодолевает себя и действует"
        return "действие выполнено с лёгким замешательством"

    def _build_resist_description(self, tags: List[str]) -> str:
        if any("strong_" in t for t in tags):
            return "персонаж не может заставить себя это сделать"
        return "персонаж останавливается на полпути"

    def _build_refuse_description(self, tags: List[str]) -> str:
        return "персонаж категорически отказывается"
