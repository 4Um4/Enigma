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


# --- Календарные константы (Дублирование из backend/app/core/constants.py ради Устава §1.1) ---
HOURS_PER_DAY: int = 24
SECONDS_PER_MINUTE: int = 60
SECONDS_PER_HOUR: int = 60 * SECONDS_PER_MINUTE    # 3600
SECONDS_PER_DAY: int = HOURS_PER_DAY * SECONDS_PER_HOUR  # 86400

DAYS_PER_MONTH: int = 30
MONTHS_PER_YEAR: int = 12
REGULAR_DAYS_PER_YEAR: int = DAYS_PER_MONTH * MONTHS_PER_YEAR  # 360
INTERCALARY_DAYS: int = 5                                          # После 12-го месяца
DAYS_PER_YEAR: int = REGULAR_DAYS_PER_YEAR + INTERCALARY_DAYS     # 365
SECONDS_PER_YEAR: int = DAYS_PER_YEAR * SECONDS_PER_DAY

DEFAULT_START_YEAR: int = 1
DEFAULT_START_DAY: int = 1


def format_game_time(total_seconds: int) -> str:
    """Минимальный формат для HUD: 'HH:MM'. Заменяет Calendar.format_full."""
    if total_seconds < 0:
        total_seconds = 0
    hour = (total_seconds // 3600) % 24
    minute = (total_seconds // 60) % 60
    return f"{hour:02d}:{minute:02d}"


def format_world_date(total_seconds: int) -> str:
    """Переводит абсолютные секунды симуляции в дату мира: 'Год X, День Y, HH:MM'."""
    if total_seconds < 0:
        total_seconds = 0
    
    year = total_seconds // SECONDS_PER_YEAR + DEFAULT_START_YEAR
    remaining_seconds = total_seconds % SECONDS_PER_YEAR
    
    day_of_year = remaining_seconds // SECONDS_PER_DAY + DEFAULT_START_DAY
    seconds_in_day = remaining_seconds % SECONDS_PER_DAY
    
    hour = seconds_in_day // SECONDS_PER_HOUR
    minute = (seconds_in_day % SECONDS_PER_HOUR) // SECONDS_PER_MINUTE
    
    return f"Год {year}, День {day_of_year}, {hour:02d}:{minute:02d}"