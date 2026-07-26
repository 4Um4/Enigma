"""
Файл: backend/app/models/world_continuity.py
Назначение: Единый доменный контракт режима персистентности мира.
Зависимости: enum
"""

from enum import Enum

class WorldContinuityMode(str, Enum):
    """Определяет, как новая кампания наследует состояние предыдущей."""
    ISOLATED = "isolated"       # Каждая игра начинается с чистого канона
    CONTINUOUS = "continuous"   # Последствия переносятся в новую игру