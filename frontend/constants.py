# -*- coding: utf-8 -*-
"""
path: /frontend/constants.py

Константы frontend (pygame, тайминги опроса, UI).
Не зависит от app/ — живет на стороне клиента.

Назначение: Константы frontend (pygame, тайминги, UI). Не зависит от app/.
Зависимости: нет
Основные сущности: IDLE_TICK_*
"""

# ─── Версия проекта ────────────────────────────────────────────────
# Единственное место во frontend, где версия задаётся явно.
# Истина: backend/pyproject.toml (строка 7). Здесь дублируется для UI.
PROJECT_VERSION: str = "v0.5.3.8.5"

# Тайминги опроса backend в зависимости от расстояния до ближайшего NPC
IDLE_TICK_NEAR_MS: int = 500
IDLE_TICK_MID_MS: int = 1_500
IDLE_TICK_FAR_MS: int = 3_000
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
SECONDS_PER_HOUR: int = 60 * SECONDS_PER_MINUTE  # 3600
SECONDS_PER_DAY: int = HOURS_PER_DAY * SECONDS_PER_HOUR  # 86400

DAYS_PER_MONTH: int = 30
MONTHS_PER_YEAR: int = 12
REGULAR_DAYS_PER_YEAR: int = DAYS_PER_MONTH * MONTHS_PER_YEAR  # 360
INTERCALARY_DAYS: int = 5  # После 12-го месяца
DAYS_PER_YEAR: int = REGULAR_DAYS_PER_YEAR + INTERCALARY_DAYS  # 365
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
    total_seconds = int(total_seconds)
    if total_seconds < 0:
        total_seconds = 0

    year = total_seconds // SECONDS_PER_YEAR + DEFAULT_START_YEAR
    remaining_seconds = total_seconds % SECONDS_PER_YEAR

    day_of_year = remaining_seconds // SECONDS_PER_DAY + DEFAULT_START_DAY
    seconds_in_day = remaining_seconds % SECONDS_PER_DAY

    hour = seconds_in_day // SECONDS_PER_HOUR
    minute = (seconds_in_day % SECONDS_PER_HOUR) // SECONDS_PER_MINUTE

    return f"Год {year}, День {day_of_year}, {hour:02d}:{minute:02d}"


# ═══════════════════════════════════════════════════════════════════
# UI PALETTE & FONTS (ТЗ-6 C1)
# ═══════════════════════════════════════════════════════════════════

# Базовые цвета UI
COLOR_TEXT_DEFAULT: tuple = (220, 220, 220)
COLOR_TEXT_DIM: tuple = (180, 180, 180)
COLOR_TEXT_MUTED: tuple = (140, 140, 140)
COLOR_TEXT_DARK: tuple = (80, 80, 80)
COLOR_TEXT_OBS_TITLE: tuple = (160, 170, 220)
COLOR_TEXT_OBS_LINE: tuple = (200, 200, 200)
COLOR_TEXT_SCALE_HIGHLIGHT: tuple = (255, 220, 100)
COLOR_TEXT_SYS_MSG: tuple = (180, 180, 180)
COLOR_DEATH_TITLE: tuple = (180, 0, 0)
COLOR_DEATH_SUB: tuple = (140, 140, 140)
COLOR_JOURNAL_TITLE: tuple = (218, 165, 32)
COLOR_NARRATOR: tuple = (218, 165, 32)
COLOR_NPC_NAME: tuple = (100, 149, 237)
COLOR_MANIFEST_DEFAULT: tuple = (160, 160, 160)

# Палитра рендерера (scene_renderer)
RENDER_COLORS: dict = {
    "bg_dark": (18, 18, 23),
    "floor_visible": (35, 35, 42),
    "floor_dim": (25, 25, 30),
    "wall": (100, 100, 110),
    "wall_visible": (140, 140, 150),
    "obstacle": (55, 55, 65),
    "obstacle_visible": (75, 75, 85),
    "object": (80, 100, 80),
    "object_visible": (100, 140, 100),
    "npc_body": (180, 140, 100),
    "npc_focused": (220, 180, 120),
    "player_body": (70, 170, 255),
    "player_focused": (100, 200, 255),
    "text_audio": (200, 180, 120),
    "text_body": (200, 120, 120),
    "text_environment": (140, 140, 140),
    "fog": (12, 12, 16),
    "attention_glow": (70, 170, 255, 40),
}

# Цвета маркеров агрессии/коммуникации на карте
AGGRESSION_COLORS: dict = {
    "combat": (255, 80, 80),
    "armed": (255, 160, 60),
    "active_aggression": (255, 50, 50),
    "potential_aggression": (200, 120, 60),
    "potentially_hostile": (180, 100, 80),
    "communication": (100, 200, 100),
    "peaceful_interaction": (80, 180, 80),
    "friendly_action": (60, 160, 60),
}

# Константы шрифтов
FONT_NAME_MAIN: str = "consolas"
FONT_NAME_UI: str = "segoeui"
FONT_SIZE_SMALL: int = 12
FONT_SIZE_AUDIO: int = 13
FONT_SIZE_BODY: int = 13
FONT_SIZE_TOOLTIP: int = 14

# Графический масштаб
SCALE_PIXELS_PER_METER: int = 40


# ═══════════════════════════════════════════════════════════════════
# UI PALETTE & FONTS (ТЗ-6 C1)
# ═══════════════════════════════════════════════════════════════════

# Базовые цвета UI
COLOR_TEXT_DEFAULT: tuple = (220, 220, 220)
COLOR_TEXT_DIM: tuple = (180, 180, 180)
COLOR_TEXT_MUTED: tuple = (140, 140, 140)
COLOR_TEXT_DARK: tuple = (80, 80, 80)
COLOR_TEXT_OBS_TITLE: tuple = (160, 170, 220)
COLOR_TEXT_OBS_LINE: tuple = (200, 200, 200)
COLOR_TEXT_SCALE_HIGHLIGHT: tuple = (255, 220, 100)
COLOR_TEXT_SYS_MSG: tuple = (180, 180, 180)
COLOR_DEATH_TITLE: tuple = (180, 0, 0)
COLOR_DEATH_SUB: tuple = (140, 140, 140)
COLOR_JOURNAL_TITLE: tuple = (218, 165, 32)
COLOR_NARRATOR: tuple = (218, 165, 32)
COLOR_NPC_NAME: tuple = (100, 149, 237)
COLOR_MANIFEST_DEFAULT: tuple = (160, 160, 160)

# Палитра рендерера (scene_renderer)
RENDER_COLORS: dict = {
    "bg_dark": (18, 18, 23),
    "floor_visible": (35, 35, 42),
    "floor_dim": (25, 25, 30),
    "wall": (100, 100, 110),
    "wall_visible": (140, 140, 150),
    "obstacle": (55, 55, 65),
    "obstacle_visible": (75, 75, 85),
    "object": (80, 100, 80),
    "object_visible": (100, 140, 100),
    "npc_body": (180, 140, 100),
    "npc_focused": (220, 180, 120),
    "player_body": (70, 170, 255),
    "player_focused": (100, 200, 255),
    "text_audio": (200, 180, 120),
    "text_body": (200, 120, 120),
    "text_environment": (140, 140, 140),
    "fog": (12, 12, 16),
}

# Цвета маркеров агрессии/коммуникации на карте
AGGRESSION_COLORS: dict = {
    "combat": (255, 80, 80),
    "armed": (255, 160, 60),
    "active_aggression": (255, 50, 50),
    "potential_aggression": (200, 120, 60),
    "potentially_hostile": (180, 100, 80),
    "communication": (100, 200, 100),
    "peaceful_interaction": (80, 180, 80),
    "friendly_action": (60, 160, 60),
}
