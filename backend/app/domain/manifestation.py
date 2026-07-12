from __future__ import annotations

# backend/app/domain/manifestation.py
"""
Файл: backend/app/domain/manifestation.py
Назначение: Строго типизированный DTO для физически наблюдаемых проявлений. Соответствует manifestation_signals.yaml.
Зависимости: dataclasses, typing
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class BodyManifestation:
    standing_balance: float = 1.0  # 0=упал, 1=идеально стоит
    muscle_tension: float = 0.0  # 0=расслаблен, 1=каменный
    body_orientation: float = 0.0  # Угол в градусах
    openness: float = 0.0  # -1=закрылся, +1=раскрыт
    collapse: float = 0.0  # 0=прямо, 1=сгорбился
    weight_shift: float = 0.0  # -1=назад, +1=вперёд


@dataclass(frozen=True)
class GazeManifestation:
    gaze_direction: float = 0.0  # Угол в градусах
    head_orientation: float = 0.0  # Угол в градусах
    fixation_duration: float = 0.0  # Секунды


@dataclass(frozen=True)
class VoiceManifestation:
    tempo: float = 120.0  # Слов в минуту
    pauses: float = 0.0  # Доля тишины 0-1
    pitch: float = 130.0  # Гц
    pitch_variability: float = 0.0
    tremor: float = 0.0  # Вибрато 0-1
    articulation: float = 1.0  # 0=смазанно, 1=чётко
    loudness: float = 55.0  # Дб


@dataclass(frozen=True)
class BreathingManifestation:
    rate: float = 14.0  # Вдохов в минуту
    depth: float = 0.5  # 0-1
    irregularity: float = 0.0  # 0-1


@dataclass(frozen=True)
class MovementManifestation:
    precision: float = 1.0
    speed: float = 0.0  # м/с
    coordination: float = 1.0
    tremor: float = 0.0  # Амплитуда дрожи 0-1


@dataclass(frozen=True)
class HandsManifestation:
    grip_strength: float = 0.0
    gesture_active: bool = False
    fidget_intensity: float = 0.0
    held_object_left: Optional[str] = None
    held_object_right: Optional[str] = None


@dataclass(frozen=True)
class MicroExpressionManifestation:
    jaw_clench: float = 0.0
    smile_intensity: float = 0.0
    brow_position: float = 0.0
    lip_compression: float = 0.0
    pupil_dilation: float = 0.0
    blink_rate: float = 12.0


@dataclass(frozen=True)
class ManifestationState:
    """
    Единый мост между Reality и внешним миром (Инвариант 5).
    Полностью immutable. Не содержит наблюдателя.
    """

    body: BodyManifestation = field(default_factory=BodyManifestation)
    gaze: GazeManifestation = field(default_factory=GazeManifestation)
    voice: VoiceManifestation = field(default_factory=VoiceManifestation)
    breathing: BreathingManifestation = field(default_factory=BreathingManifestation)
    movement: MovementManifestation = field(default_factory=MovementManifestation)
    hands: HandsManifestation = field(default_factory=HandsManifestation)
    micro_expression: MicroExpressionManifestation = field(
        default_factory=MicroExpressionManifestation
    )
