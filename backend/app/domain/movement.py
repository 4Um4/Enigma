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
    location_id: str = ""   # для загрузки правильного графа
    reason: str = ""        # "need_driven:hunger", "schedule:working"

    # ── ЗАКЛАДКА ПОД PATHING (ФАЗА 4) — пока не используются ──
    movement_mode: str = "instant"   # "instant" | "path" — когда появится pathing
    priority: float = 0.5            # 0.0–1.0, для разрешения конфликтов intent-ов