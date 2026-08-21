"""
path: backend/app/domain/world_projection.py
Назначение: Контракты для WorldProjectionBuffer (shadow causality).
Производный слой, генерирующий вторичные нарративные эффекты (слухи, репутация) 
из уже закоммиченного состояния мира. НЕ мутирует первичную реальность.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

class ProjectionType(str, Enum):
    """Тип вторичного эффекта проекции."""
    RUMOR = "rumor"          # Слух о произошедшем событии
    REPUTATION = "reputation" # Изменение социальной репутации NPC
    AMBIENT = "ambient"       # Фоновое изменение атмосферы локации

@dataclass(frozen=True)
class WorldProjectionEvent:
    """Наблюдаемый вторичный эффект, порождённый буфером проекций."""
    event_id: str
    tick: int
    projection_type: ProjectionType
    source_id: str           # Кто или что породило эффект (npc_id или "world")
    location_id: str         # Где эффект актуален
    description: str         # Человекочитаемое описание (для DM-агента)
    salience: float = 0.5    # Важность (0..1) для фильтрации
    target_id: Optional[str] = None  # Опциональный целевой NPC (для репутации)