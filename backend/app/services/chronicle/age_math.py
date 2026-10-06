"""
Единственная конверсия возраста хроники (ADR-O-420).

Файл: backend/app/services/chronicle/age_math.py
Назначение: age ⇄ total_seconds ⇄ day<0 для хроники и seed. Один модуль —
            одна семантика года. Никакого второго множителя в проекте.
Зависимости: app.core.constants (SECONDS_PER_YEAR, SECONDS_PER_DAY)
Основные сущности: SENTINEL_DAY, birth_epoch_from_age, age_at,
                   historical_event_seconds, day_offset

ВЕРДИКТ МАСТЕРА (S331):
- точный отрицательный day — нормальная историческая координата;
- -1000 — исключительно legacy-sentinel «точная дата неизвестна»;
- любое вычисление времени знания из исторического (и наоборот) запрещено —
  это оси разных доменов (запрет 4 ADR-O-420).
"""
from __future__ import annotations

from app.core.constants import SECONDS_PER_DAY, SECONDS_PER_YEAR

# Legacy-sentinel «без точной даты». Совместим с прецедентом
# npc_loader._convert_origin_events (day=-1000, decay 0.001).
SENTINEL_DAY: int = -1000


def birth_epoch_from_age(age_at_game_start: int, campaign_start_total_seconds: int) -> int:
    """Абсолютный момент рождения на оси Calendar.total_seconds."""
    if age_at_game_start < 0:
        raise ValueError(f"age_at_game_start не может быть отрицательным: {age_at_game_start}")
    return campaign_start_total_seconds - age_at_game_start * SECONDS_PER_YEAR


def age_at(total_seconds: int, birth_epoch: int) -> int:
    """Возраст (полных лет) в момент total_seconds. До рождения — ошибка данных."""
    if total_seconds < birth_epoch:
        raise ValueError("total_seconds раньше birth_epoch: событие до рождения")
    return (total_seconds - birth_epoch) // SECONDS_PER_YEAR


def historical_event_seconds(age_years: int, birth_epoch: int) -> int:
    """Абсолютный момент события «в N лет» (N ≥ 0; может быть < 0 на оси эпохи)."""
    if age_years < 0:
        raise ValueError(f"age_years не может быть отрицательным: {age_years}")
    return birth_epoch + age_years * SECONDS_PER_YEAR


def day_offset(event_total_seconds: int, reference_total_seconds: int) -> int:
    """
    Смещение события от опорной точки в днях (floor: полные сутки).
    Отрицательный результат — прошлое до старта кампании (легальная координата
    EventMemory.day < 0, прецедент origin_events).
    """
    return (event_total_seconds - reference_total_seconds) // SECONDS_PER_DAY
