# -*- coding: utf-8 -*-
"""
path: backend/app/domain/motion_core.py
Назначение: Базовые DTO для ETKE-IK v1. Непрерывная кинематика и поле возможностей.
Зависимости: dataclasses, typing
Основные сущности: AffordanceVector, BodySchema, DriveVector, KinematicProfile
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Tuple, Optional

class MotionPrimitive(Enum):
    """ETKE-IK 2.0: Семантический примитив движения."""
    APPROACH = "approach"
    FLEE = "flee"
    RETREAT = "retreat"
    PATROL = "patrol"

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

# TODO: DynamicAffordanceField и SocialTraceField будут реализованы в WorldTopologyProvider