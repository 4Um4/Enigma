"""
path: backend/app/domain/movement.py
Назначение: Intent перемещения NPC. Пересекает границу Decision → Execution.
Зависимости: dataclasses
Основные сущности: MovementIntent
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MovementIntent:
    """Намерение переместить NPC к целевому узлу.
    
    Генерируется: LifeEngine (schedule/need-driven) или DecisionHub.
    Обрабатывается: MovementEngine (Слой 2).
    
    Не содержит координат — только идентификатор узла графа.
    Конвертация в {x, y} — ответственность MovementEngine.
    """
    npc_id: str
    target_node_id: str     # "behind_bar", "corner_table", "main_hall"
    from_node_id: str = ""  # текущий узел — для pathfinding (Слой 2)
    location_id: str = ""   # для загрузки правильного графа
    reason: str = ""        # "need_driven:hunger", "schedule:working"

    # ADR-0010: movement_mode удалён. Макро-перемещение — всегда атомарная Semantic Relocation.
    priority: float = 0.5            # 0.0–1.0, для разрешения конфликтов intent-ов


# Константы приоритетов — выше = важнее (D6)
# Порядок из Диаграммы 9: flee > combat > needs > schedule > random
PRIORITY_FLEE: float = 1.0
PRIORITY_COMBAT: float = 0.85
PRIORITY_NEEDS: float = 0.7
PRIORITY_SCHEDULE: float = 0.5
PRIORITY_RANDOM: float = 0.3