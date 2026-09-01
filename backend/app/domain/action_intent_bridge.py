from __future__ import annotations

# backend/app/domain/action_intent_bridge.py
"""
Мост между ActionType (из IntentCompressor) и Intent (из DecisionHub).
Единственная легальная точка маппинга (closed-world lattice).
"""

from enum import Enum
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class ActionType(str, Enum):
    MOVE = "MOVE"
    ATTACK = "ATTACK"
    THREATEN = "THREATEN"
    PERSUADE = "PERSUADE"
    OBSERVE = "OBSERVE"
    INTERACT = "INTERACT"
    UNCERTAIN = "UNCERTAIN"


_ACTION_TO_INTENT: dict[ActionType, str] = {
    ActionType.MOVE: "APPROACH",
    ActionType.ATTACK: "ATTACK",
    ActionType.THREATEN: "INTIMIDATE",
    ActionType.PERSUADE: "TALK",
    ActionType.OBSERVE: "OBSERVE",
    ActionType.INTERACT: "INTERACT",
}


def action_to_intent(action_type: Optional[str]) -> Optional[str]:
    if not action_type:
        return None
    try:
        return _ACTION_TO_INTENT.get(ActionType(action_type.upper()))
    except ValueError as e:
        logger.debug(f"ActionType not found, returning None: {e}")
        return None
