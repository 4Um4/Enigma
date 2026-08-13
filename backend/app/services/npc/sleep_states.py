"""
Назначение: Единый источник истины для состояний сна NPC.
Зависимости: enum
Основные сущности: SleepState, is_sleeping
"""

from enum import Enum

class SleepState(str, Enum):
    AWAKE = "awake"
    SLEEPING = "sleeping"
    RESTING = "resting"
    DROWSY = "drowsy"

def is_sleeping(activity: str) -> bool:
    """Проверяет, находится ли NPC в состоянии сна или отдыха."""
    if not activity:
        return False
    return SleepState.SLEEPING.value in activity or SleepState.RESTING.value in activity