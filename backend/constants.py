# -*- coding: utf-8 -*-
"""
backend/constants.py
Константы frontend (pygame, тайминги опроса, UI).
Не зависит от app/ — живет на стороне клиента.

path: /backend/constants.py
Назначение: Константы frontend (pygame, тайминги, UI). Не зависит от app/.
Зависимости: нет
Основные сущности: IDLE_TICK_*
"""

# Тайминги опроса backend в зависимости от расстояния до ближайшего NPC
IDLE_TICK_NEAR_MS: int = 2_000
IDLE_TICK_MID_MS: int = 8_000
IDLE_TICK_FAR_MS: int = 30_000
IDLE_TICK_NEAR_RADIUS: float = 5.0
IDLE_TICK_MID_RADIUS: float = 15.0