"""
path: backend/app/domain/movement.py
Назначение: Intent перемещения NPC. Пересекает границу Decision → Execution.
Зависимости: dataclasses
Основные сущности: MovementIntent

TODO:
- В будущем можно расширить до более сложной иерархии (например, MacroMovementIntent, LocalSteeringIntent), если потребуется более четкое разделение между разными типами перемещения.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Optional


class IntentDomain(enum.Enum):
    """Онтологический домен намерения. Определяет, в каком слое причинности существует действие.
    
    Viability: наличие SURVIVAL давления исключает ROUTINE домен из пространства кандидатов.
    Это не предпочтение (priority), а физика возможностей — NPC не может «выбрать» работу при беге.
    """
    SURVIVAL = "SURVIVAL"   # Угроза, бегство, оборона
    SOCIAL = "SOCIAL"       # Взаимодействие, подход, разговор
    ROUTINE = "ROUTINE"     # Расписание, работа, сон, рутина
    EXPLORATION = "EXPLORATION"  # Исследование, случайные события


@dataclass
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
    domain: IntentDomain = IntentDomain.ROUTINE  # ДОЛГ 4.3: Онтологический домен намерения
    priority: float = 0.5   # 0.0–1.0, для разрешения конфликтов intent-ов
    target_local_xy: Optional[tuple[float, float]] = None  # ADR-065: Точные координаты цели внутри узла (для подхода к игроку)
    # ADR-XXXX: Инвариант единого владения причинностью. Один Intent → один process_intents() → одно будущее.
    processed: bool = field(default=False, init=False)
    processor: Optional[str] = field(default=None, init=False)


@dataclass
class LocalSteeringGoal:
    """LOD0: Микро-рулежка внутри зоны (уклонение, расхождение, подход).
    
    Генерируется: DecisionHub / Reactive Movement.
    Обрабатывается: MovementEngine (Слой 2).
    Содержит абсолютные координаты внутри тайла.
    """
    actor_id: str
    local_target_xy: tuple[float, float]  # Целевые координаты
    reason: str = ""        # "reactive_snap", "collision_avoidance"
    priority: float = 0.7   # Микро-рулежка приоритетнее макро-маршрутов по умолчанию
    # ADR-XXXX: Инвариант единого владения причинностью
    processed: bool = field(default=False, init=False)
    processor: Optional[str] = field(default=None, init=False)


# Legacy alias для плавной миграции (будет удален в Phase 4)
MovementIntent = MacroMovementGoal

# Приоритеты intent-ов (для разрешения конфликтов)
PRIORITY_RANDOM   = 0.3   # Случайное блуждание
PRIORITY_NEEDS    = 0.5   # Базовые потребности (голод, отдых)
PRIORITY_SCHEDULE = 0.6   # Расписание (работа, сон)
PRIORITY_REACTIVE = 0.8   # Реактивное движение (approach, flee)