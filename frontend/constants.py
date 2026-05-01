# -*- coding: utf-8 -*-
"""
path: /frontend/constants.py

Константы frontend (pygame, тайминги опроса, UI).
Не зависит от app/ — живет на стороне клиента.

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

# Игровое время: секунды за метр ходьбы внутри помещения
TIME_DELTA_WALK_INDOOR: int = 10


def parse_hhmm(time_str: str) -> int:
    """Парсит 'HH:MM' в секунды от начала дня. При ошибке — 07:00."""
    try:
        parts = time_str.strip().split(":")
        h = max(0, min(int(parts[0]), 23))
        m = max(0, min(int(parts[1]), 59))
        return h * 3600 + m * 60
    except Exception:
        return 7 * 3600  # 07:00


def format_game_time(total_seconds: int) -> str:
    """Минимальный формат для HUD: 'HH:MM'. Заменяет Calendar.format_full."""
    if total_seconds < 0:
        total_seconds = 0
    hour = (total_seconds // 3600) % 24
    minute = (total_seconds // 60) % 60
    return f"{hour:02d}:{minute:02d}"