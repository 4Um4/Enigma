"""
path: backend/app/domain/movement.py
Назначение: Intent перемещения NPC. Пересекает границу Decision → Execution.
Зависимости: dataclasses
Основные сущности: MovementIntent
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MacroMovementGoal:
    """LOD1: Навигация по графу локации (двери, зоны, комнаты).
    
    Генерируется: LifeEngine (schedule/need-driven).
    Обрабатывается: MovementEngine (Слой 2).
    Конвертация в {x, y} — ответственность MovementEngine.
    """
    npc_id: str
    target_node_id: str     # "behind_bar", "corner_table", "main_hall"
    from_node_id: str = ""  # текущий узел — для pathfinding (Слой 2)
    location_id: str = ""   # для загрузки правильного графа
    reason: str = ""        # "need_driven:hunger", "schedule:working"
    priority: float = 0.5   # 0.0–1.0, для разрешения конфликтов intent-ов

@dataclass(frozen=True)
class LocalSteeringGoal:
    """LOD0: Микро-рулежка внутри зоны (уклонение, расхождение, подход).
    
    Генерируется: DecisionHub / Reactive Movement.
    Обрабатывается: MovementEngine (Слой 2).
    Содержит абсолютные координаты внутри тайла.
    """
    npc_id: str
    local_target_xy: tuple[float, float]  # Целевые координаты
    reason: str = ""        # "reactive_snap", "collision_avoidance"
    priority: float = 0.7   # Микро-рулежка приоритетнее макро-маршрутов по умолчанию

# Legacy alias для плавной миграции (будет удален в Phase 4)
MovementIntent = MacroMovementGoal


# Константы приоритетов — выше = важнее (D6)
# Порядок из Диаграммы 9: flee > combat > needs > schedule > random
PRIORITY_FLEE: float = 1.0
PRIORITY_COMBAT: float = 0.85
PRIORITY_NEEDS: float = 0.7
PRIORITY_SCHEDULE: float = 0.5
PRIORITY_RANDOM: float = 0.3