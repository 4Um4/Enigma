# backend/app/models/contracts.py
"""
Нейтральные контракты, общие для models и domain (N-03 FIX).
"""
from dataclasses import dataclass

@dataclass(frozen=True)
class BodyCapabilities:
    radius: float = 0.35
    height: float = 1.8
    can_walk: bool = True
    can_jump: bool = True
    max_jump_height: float = 1.0
    max_jump_distance: float = 2.0
    movement_speed: float = 2.0