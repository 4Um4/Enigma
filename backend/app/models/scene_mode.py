"""
path: backend/app/models/scene_mode.py
Назначение: Режимы сцены для динамической фильтрации контекста
Зависимости: Нет
Основные сущности: SceneMode, determine_scene_mode
"""

from enum import Enum


class SceneMode(Enum):
    """Режим сцены определяет сколько контекста видит LLM."""

    EXPLORATION = "EXPLORATION"  # Осмотр — полный контекст
    INTERACTION = "INTERACTION"  # Диалог — отфильтрованный
    COMBAT = "COMBAT"  # Бой/угроза — туннельное зрение


def determine_scene_mode(
    event_type: str,
    max_npc_stress: float,
) -> SceneMode:
    """
    Определяет режим на основе действия игрока и стресса NPC.

    Args:
        event_type: классификация из Router (player_attacks, player_threatens, ...)
        max_npc_stress: максимальный стресс среди видимых NPC
    """
    # Бой или критический стресс — туннельное зрение
    if event_type in ("player_attacks", "combat") or max_npc_stress > 50.0:
        return SceneMode.COMBAT

    # Осмотр — полный контекст
    if event_type in ("player_looks", "player_examines"):
        return SceneMode.EXPLORATION

    # Всё остальное — стандартный режим
    return SceneMode.INTERACTION
