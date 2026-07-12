# -*- coding: utf-8 -*-
"""
path: backend/app/domain/motion_core.py
Назначение: Базовые DTO для ETKE-IK v1. Непрерывная кинематика и поле возможностей.
Зависимости: dataclasses, typing
Основные сущности: AffordanceVector, BodySchema, DriveVector, KinematicProfile
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Tuple


class MotionPrimitive(Enum):
    """ETKE-IK 2.0: Семантический примитив движения."""

    APPROACH = "approach"
    FLEE = "flee"
    RETREAT = "retreat"
    SOCIAL_DRIFT = (
        "social_drift"  # S91: Замена PATROL. Социально оправданное микро-перемещение.
    )


@dataclass(frozen=True)
class AffordanceVector:
    """1.1 Физические возможности среды (Моторика).

    Описывает, что тело может сделать в данной точке пространства.
    Генерируется на основе геометрии мира (load-time) и редко деформируется.
    """

    # Физические возможности
    can_stand: float = 0.0
    can_vault: float = 0.0
    can_climb: float = 0.0
    can_conceal: float = 0.0
    can_pass: float = 0.0

    # Кинематическое сопротивление
    surface_grip: float = 0.8
    drag_coefficient: float = 0.0

    # Сенсорные градиенты (L0)
    light_level: float = 0.5
    thermal_mass: float = 0.5
    exposure: float = 0.5
    mana_resonance: float = 0.0


@dataclass(frozen=True)
class BodySchema:
    """1.4 Кинематический профиль тела NPC.

    Хранит физические ограничения и возможности конкретного тела.
    Расширяет body_state в NPCState.
    """

    max_velocity: float = 2.0
    acceleration: float = 5.0
    braking_force: float = 8.0
    vault_capability: float = 0.0
    climb_capability: float = 0.0
    stamina: float = 100.0
    tunnel_vision_factor: float = 0.0
    mana_channel: float = 0.0
    mana_capacity: float = 0.0


@dataclass(frozen=True)
class DriveVector:
    """1.5 Вектор давления (замена MovementIntent для микро-уровня).

    Решение NPC, переведенное в направленный вектор желания.
    Отсутствие жесткой цели (target_node) — тело само ищет путь в поле возможностей.
    """

    direction: Tuple[float, float]
    intensity: float  # 0.0 - 1.0
    primitive: MotionPrimitive = MotionPrimitive.APPROACH


@dataclass(frozen=True)
class KinematicProfile:
    """1.6 Выходной профиль движения для фронта.

    Результат работы SteeringResolver и MotionIntegrator.
    """

    velocity: Tuple[float, float] = (0.0, 0.0)
    vertical_velocity: float = 0.0
    posture: str = "standing"  # standing, crouching, prone
    stance_width: float = 1.0
    facing: float = 0.0  # угол в радианах
    exertion_level: float = 0.0  # 0.0 - 1.0 (усталость)


@dataclass(frozen=True)
class DeformationRecord:
    """S91: Запись о динамической деформации среды (стигмергия).

    Хранит причину, силу и время жизни деформации.
    Семантика magnitude: ABSOLUTE OVERRIDE.
    Значение перезаписывает базовое поле в AffordanceVector.
    """

    deformation_type: (
        str  # Имя поля в AffordanceVector (напр. "surface_grip", "can_pass")
    )
    magnitude: float  # Absolute Override (0.0 - 1.0)
    created_tick: int  # Тик создания (для decay и history)
    ttl: int  # Time-to-live в тиках (0 = вечная)
    source_id: str  # Кто/что вызвал деформацию (npc_id, "system", weather_event_id)


@dataclass(frozen=True)
class TracePayload:
    """S91: Эмиттер стигмергического следа (SocialTraceField).

    Генерируется при движении NPC или акте насилия.
    Накапливается в DynamicAffordanceField для изменения свойств среды.
    """

    region: str  # location_id
    zone_id: str  # ID комнаты/полигона
    trace_type: str  # "movement_density" или "safety_confidence"
    magnitude: float  # Сила следа (0.0 - 1.0)
    created_tick: int  # Тик создания
    ttl: int  # Time-to-live в тиках (0 = вечная)
    source_id: str  # npc_id или "combat_event"
