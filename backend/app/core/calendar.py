"""
Календарь ENIGMA — вычисляет дату/время из total_seconds.

Файл: backend/app/core/calendar.py
Назначение: Единственное место логики календаря. Позволяет менять правила
            (високосные годы, длина месяца) без переписывания сохранений.
Зависимости: app.core.constants
Основные сущности: Calendar

ПРИНЦИПЫ:
- Calendar не хранит состояние — чистые функции от total_seconds
- total_seconds = абсолютное смещение от начала эпохи (год 1, день 1, 00:00)
- Сохранения хранят total_seconds → при изменении календаря старые сейвы
  пересчитываются автоматически (если длина года не изменилась)
- Часы: 0–23 (вариант А, стандарт цифровых часов)
- Месяц: GameMonth (1–12) или None для межсезонья
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.core.constants import (
    DAYS_PER_MONTH,
    DAYS_PER_YEAR,
    DEFAULT_START_SECOND_ABS,
    INTERCALARY_DAYS,
    INTERCALARY_NAME_RU,
    SECONDS_PER_DAY,
    SECONDS_PER_HOUR,
    MONTH_NAMES_RU,
    REGULAR_DAYS_PER_YEAR,
    GameMonth,
)


@dataclass(frozen=True, slots=True)
class GameTimePoint:
    """Неизменяемый результат декомпозиции total_seconds."""
    total_seconds: int
    year: int
    day_of_year: int          # 1–365
    month: Optional[GameMonth]  # None = межсезонье
    day_of_month: int         # 1–30 для месяцев, 1–5 для межсезонья
    hour: int                 # 0–23
    minute: int               # 0–59
    is_intercalary: bool


class Calendar:
    """
    Сервис преобразования total_seconds → человекочитаемые компоненты.

    Не хранит состояние — все методы принимают total_seconds.
    Можно создать подкласс с другой длиной года для иных культур.
    """

    # ── Декомпозиция ──────────────────────────────────────────────

    @staticmethod
    def decompose(total_seconds: int) -> GameTimePoint:
        """Разбирает total_seconds на год, месяц, день, час, минуту."""
        if total_seconds < 0:
            total_seconds = 0

        # Год и день в году
        total_days = total_seconds // SECONDS_PER_DAY
        year = total_days // DAYS_PER_YEAR + 1          # годы с 1
        day_of_year = total_days % DAYS_PER_YEAR + 1    # дни с 1

        # Месяц и день месяца
        is_intercalary = day_of_year > REGULAR_DAYS_PER_YEAR
        if is_intercalary:
            month = None
            day_of_month = day_of_year - REGULAR_DAYS_PER_YEAR  # 1–5
        else:
            # day_of_year 1–30 → месяц 1, 31–60 → месяц 2, ...
            zero_based_idx = (day_of_year - 1) // DAYS_PER_MONTH  # 0–11
            month = GameMonth(zero_based_idx + 1)
            day_of_month = (day_of_year - 1) % DAYS_PER_MONTH + 1

        # Час и минута
        seconds_in_day = total_seconds % SECONDS_PER_DAY
        hour = seconds_in_day // SECONDS_PER_HOUR        # 0–23
        minute = (seconds_in_day % SECONDS_PER_HOUR) // 60  # 0–59

        return GameTimePoint(
            total_seconds=total_seconds,
            year=year,
            day_of_year=day_of_year,
            month=month,
            day_of_month=day_of_month,
            hour=hour,
            minute=minute,
            is_intercalary=is_intercalary,
        )

    # ── Форматирование ────────────────────────────────────────────

    @staticmethod
    def format_time(total_seconds: int) -> str:
        """Формирует строку времени: '14:05'."""
        pt = Calendar.decompose(total_seconds)
        return f"{pt.hour:02d}:{pt.minute:02d}"

    @staticmethod
    def format_date(total_seconds: int) -> str:
        """
        Формирует строку даты: '15 Марта' или 'Межсезонье 3'.
        Неразрывный пробел между числом и месяцем для моноширинного шрифта.
        """
        pt = Calendar.decompose(total_seconds)
        if pt.is_intercalary:
            return f"{INTERCALARY_NAME_RU} {pt.day_of_month}"
        month_name = MONTH_NAMES_RU.get(pt.month, "???")  # type: ignore[arg-type]
        return f"{pt.day_of_month}\u00A0{month_name}"

    @staticmethod
    def format_full(total_seconds: int) -> str:
        """
        Полная строка для HUD: '14:05 | 15 Марта, Год 1'
        или '14:05 | Межсезонье 3, Год 1'.
        """
        time_str = Calendar.format_time(total_seconds)
        date_str = Calendar.format_date(total_seconds)
        pt = Calendar.decompose(total_seconds)
        return f"{time_str} | {date_str}, Год {pt.year}"

    @staticmethod
    def format_time_of_day(total_seconds: int) -> str:
        """
        Совместимость: возвращает 'HH:MM' как раньше хранилось в environment.
        Используется для _select_time_variant в scene_state_manager.
        TODO: удалить после миграции scene_state_manager на total_seconds
        """
        return Calendar.format_time(total_seconds)

    # ── Утилиты ───────────────────────────────────────────────────

    @staticmethod
    def parse_hhmm(time_str: str) -> int:
        """
        Парсит строку 'HH:MM' в секунды от начала дня (0–86399).
        При ошибке возвращает дефолт (07:00 = 25200).
        """
        try:
            parts = time_str.strip().split(":")
            h, m = int(parts[0]), int(parts[1])
            h = max(0, min(h, 23))
            m = max(0, min(m, 59))
            return h * SECONDS_PER_HOUR + m * 60
        except (ValueError, IndexError, AttributeError):
            return DEFAULT_START_SECOND_ABS

    @staticmethod
    def advance(total_seconds: int, delta_seconds: int) -> int:
        """Прибавляет дельту в секундах, возвращает новый total_seconds."""
        return total_seconds + delta_seconds

    @staticmethod
    def is_night(total_seconds: int) -> bool:
        """Ночь: 22:00–05:59 — влияет на свет в локациях."""
        pt = Calendar.decompose(total_seconds)
        return pt.hour >= 22 or pt.hour < 6