# backend/app/services/state/persistence_port.py
"""
PersistencePort — абстракция сохранения состояния мира.

Принцип: persistence = инфраструктура, не доменная логика.
SceneStateManager использует порт для commit, но не знает КАК сохраняется.
"""

from __future__ import annotations
from abc import ABC, abstractmethod


class PersistencePort(ABC):
    """
    Порт сохранения состояния.
    
    Реализации:
    - JsonPersistenceAdapter — JSON файлы (текущий MVP)
    - (будущее) SqlitePersistenceAdapter — SQLite для Iron-Man режима
    """
    
    @abstractmethod
    def save_scene(self, campaign_id: str, scene_state: dict) -> None:
        """Сохраняет состояние сцены в campaign_state.json."""
        ...
    
    @abstractmethod
    def save_npcs(self, npc_dicts: list[dict]) -> None:
        """Сохраняет состояния NPC в major_npcs.json."""
        ...
