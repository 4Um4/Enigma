"""
path: backend/app/services/avatar_character_registry.py
Назначение: Maps campaign_id → character_id (Avatar body npc_id).
    Заменяет player_name coupling в player_avatar_service.py:138.
    Позволяет Player управлять разными Avatar телами (body switching).
    Позволяет Avatar действовать автономно (AVATAR_INITIATIVE).
Зависимости: typing
Основные сущности: AvatarCharacterRegistry
"""

from __future__ import annotations
from typing import Dict, Optional
import threading


class AvatarCharacterRegistry:
    """Maps campaign_id → character_id (Avatar body identity).
    
    Thread-safe singleton. Populated at campaign start (player selects character).
    Replaces player_name as identity key in player_avatar_service.
    """
    
    _instance: Optional["AvatarCharacterRegistry"] = None
    _lock = threading.Lock()
    _campaign_to_character: Dict[str, str] = {}

    def __new__(cls) -> "AvatarCharacterRegistry":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._campaign_to_character = {}
        return cls._instance
    
    def register(self, campaign_id: str, character_id: str) -> None:
        """Register Avatar character_id for campaign."""
        with self._lock:
            self._campaign_to_character[campaign_id] = character_id
    
    def unregister(self, campaign_id: str) -> None:
        """Remove Avatar registration for campaign."""
        with self._lock:
            self._campaign_to_character.pop(campaign_id, None)
    
    def get_character_id(self, campaign_id: str) -> Optional[str]:
        """Get Avatar character_id for campaign."""
        with self._lock:
            return self._campaign_to_character.get(campaign_id)
    
    def is_avatar(self, npc_id: str, campaign_id: str) -> bool:
        """Check if npc_id is the Avatar body for this campaign."""
        char_id = self.get_character_id(campaign_id)
        return char_id is not None and char_id == npc_id
    
    def clear(self) -> None:
        """Clear all registrations (for testing)."""
        with self._lock:
            self._campaign_to_character.clear()

