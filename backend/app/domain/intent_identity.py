"""
path: backend/app/domain/intent_identity.py
Назначение: 4 поля IntentIdentity (R5.4 verified contract).
    Разделяет "кто инициировал" (intent_owner), "кто исполнил" (actor_id),
    "через какое тело" (body_id), "тип контроля" (control_source).
    Принцип: Player может управлять телом. Но управление телом не означает
    владение сознанием Avatar.
Зависимости: domain/control_source.py (ControlSource)
Основные сущности: IntentIdentity
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
from app.domain.control_source import ControlSource


@dataclass(frozen=True)
class IntentIdentity:
    """R5.4: 4 поля Identity для event attribution.
    
    intent_owner: кто инициировал (player name/id ИЛИ character_id для autonomous)
    actor_id: кто исполняет действие (npc_id в мире)
    body_id: тело, через которое действуют (= actor_id для single-body)
    control_source: PLAYER_INPUT | NPC_DECISION | AVATAR_INITIATIVE
    """
    intent_owner: str
    actor_id: str
    body_id: str
    control_source: ControlSource
    
    @classmethod
    def for_npc(cls, npc_id: str) -> "IntentIdentity":
        """NPC autonomous action — owner = actor = body = npc_id."""
        return cls(
            intent_owner=npc_id,
            actor_id=npc_id,
            body_id=npc_id,
            control_source=ControlSource.NPC_DECISION,
        )
    
    @classmethod
    def for_player_input(cls, player_name: str, character_id: str) -> "IntentIdentity":
        """Player commands Avatar body.
        
        intent_owner = player_name (who decided)
        actor_id = character_id (who executes in the world)
        body_id = character_id (the body)
        control_source = PLAYER_INPUT
        """
        return cls(
            intent_owner=player_name,
            actor_id=character_id,
            body_id=character_id,
            control_source=ControlSource.PLAYER_INPUT,
        )
    
    @classmethod
    def for_avatar_initiative(cls, character_id: str) -> "IntentIdentity":
        """Avatar acts autonomously (not Player command).
        
        intent_owner = character_id (Avatar itself decided)
        actor_id = character_id
        body_id = character_id
        control_source = AVATAR_INITIATIVE
        """
        return cls(
            intent_owner=character_id,
            actor_id=character_id,
            body_id=character_id,
            control_source=ControlSource.AVATAR_INITIATIVE,
        )
    
    @classmethod
    def unknown(cls) -> "IntentIdentity":
        """Unidentified control source — honest UNKNOWN, not guess."""
        return cls(
            intent_owner="",
            actor_id="",
            body_id="",
            control_source=ControlSource.UNKNOWN,
        )