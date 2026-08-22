"""
Файл: backend/app/models/player_action.py
Назначение: Контракт действия игрока, влияющего на мир.
Зависимости: dataclasses, enum, typing
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple


class ActionType(str, Enum):
    DIALOGUE = "dialogue"
    EAVESDROP = "eavesdrop"
    BLACKMAIL = "blackmail"
    BRIBE = "bribe"
    ATTACK = "attack"
    HELP = "help"
    ACCUSE = "accuse"  # S211 (слой 4): публичное обвинение. Гейт — EpistemicStore[player] (§18)

@dataclass(frozen=True)
class PlayerAction:
    """Действие агента, инициирующее каузальные последствия."""
    action_id: str
    tick: int
    actor_id: str
    action_type: ActionType
    target_id: str
    secret_id: Optional[str] = None # Контекст действия, а не автоматически доказательство
    description: str = ""
