# backend/app/domain/perception_physics.py
"""
Файл: backend/app/domain/perception_physics.py
Назначение: DTO для ObservationRelation (среда пары observer-target) и PerceivedSignal (сигнал с confidence).
Зависимости: dataclasses, typing
"""

from __future__ import annotations
import dataclasses
from dataclasses import dataclass
from typing import Dict, Any, Tuple

@dataclass(frozen=True)
class ObservationRelation:
    """
    Объект отношения (Инвариант 4).
    Содержит ТОЛЬКО параметры среды. Запрещено хранить NPC id, Faction, Mood.
    """
    distance: float                # В метрах (от SpatialQueryService)
    angle: float                   # Угол между observer и target в градусах
    light_level: float             # 0.0-1.0 (из scene_state.environment)
    noise_level: float             # 0.0-1.0 (из scene_state.environment)
    is_line_of_sight_clear: bool   # True если нет преград
    observer_type: str             # "humanoid", "animal", "camera" и т.д.

@dataclass(frozen=True)
class PerceivedSignal:
    """
    Что физически зарегистрировали органы чувств.
    Содержит confidence и пороги видимости.
    """
    signal_id: str                 # UUID
    target_id: str                 # Кого касается
    channel: str                   # body_manifestation | gaze | voice | ...
    field: str                     # tremor | muscle_tension | ...
    
    perceived_value: Any           # float, bool, str или None
    confidence: float              # 0.0-1.0 (вычисляется из resolution и signal_salience)
    
    perceived_at: float            # game_time_seconds
    perceived_via: Tuple[str, ...]           # ("visual",) | ("auditory",) | ("visual", "auditory")
    
    # Дистанция и свет (для UI: размытие/шум при low confidence)
    distance: float
    lighting: float
    
    # Искажения (что повлияло на точность)
    distortions: Dict[str, float] = dataclasses.field(default_factory=dict)