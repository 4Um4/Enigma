"""
Продвижение игрового времени на основе действий игрока.

Формула для диалогов: базовое время + 0.5 секунды на символ, максимум 30 секунд.
Для перемещений: 10 секунд за каждый полный метр (условно, для упрощения, без дробных шагов).
Также поддерживаются явные команды типа "подождать 2 часа" в любом вводе игрока, с парсингом количества и единиц времени.
Время хранится в shared_context.game_time_seconds (новый путь) и в scene_state.environment.time_of_day (legacy, для совместимости).
Функция advance_game_time вызывается из Orchestrator после получения действия игрока, до выполнения этого действия, чтобы обеспечить правильное течение времени для всех последующих систем (например, для планировщика мира и для рендеринга времени суток).
Вынос этой логики в отдельный модуль позволяет легко управлять и тестировать её независимо от остального игрового цикла, а также обеспечивает чистоту кода в init.py и других местах, где может потребоваться продвижение времени.
Зависимости: app.core.constants для базовых значений времени, app.core.calendar для работы с временем и его форматированием.
Основные сущности: функция advance_game_time, которая принимает текущее состояние сцены, тип действия, сырой ввод игрока и опциональный shared_context, и обновляет время игры на основе этих данных.

path: backend/app/services/game_loop/time_advance.py
Назначение: Вынос расчёта продвижения игрового времени из init.py
"""

import re
import logging

logger = logging.getLogger(__name__)


def advance_game_time(
    scene_state: dict,
    action_type: str,
    raw_input: str,
    shared_context: dict | None = None,
) -> None:
    """
    Фаза 4 — время продвигается от действий, не от тиков.
    Обновляет total_seconds в shared_context и time_of_day в scene_state.
    """
    from app.core.constants import (
        TIME_DIALOG_BASE,
        TIME_DIALOG_PER_CHAR,
        TIME_DIALOG_MAX,
        TIME_DELTA_WALK_INDOOR,
        TIME_DELTA_TELEGRAPH,
    )
    from app.core.calendar import Calendar

    # Время диалога: базовое + длина ввода игрока (скорость речи NPC ~10 симв/с)
    if action_type in ("dialogue", "player_interacts"):
        _input_len = len(raw_input) if raw_input else 0
        _delta_seconds = min(TIME_DIALOG_BASE + int(_input_len * TIME_DIALOG_PER_CHAR), TIME_DIALOG_MAX)
    elif action_type in ("move", "stealth", "player_moves"):
        _location = scene_state.get("location_id", "")
        if "tavern" in _location.lower() or "inn" in _location.lower():
            _delta_seconds = TIME_DELTA_WALK_INDOOR
        else:
            _delta_seconds = TIME_DELTA_WALK_INDOOR * 3
    elif "TELEGRAPH" in raw_input:
        _delta_seconds = TIME_DELTA_TELEGRAPH
    else:
        _delta_seconds = 0

    # Явные запросы времени в тексте игрока
    _wait_match = re.search(r"жд[уаю]\s+(\d+)\s+(час|минут|секунд)", raw_input, re.I)
    if _wait_match:
        _amount = int(_wait_match.group(1))
        _unit = _wait_match.group(2)
        if "час" in _unit:
            _delta_seconds = _amount * 3600
        elif "минут" in _unit:
            _delta_seconds = _amount * 60
        else:
            _delta_seconds = _amount

    if _delta_seconds == 0:
        return

    # Текущее время из shared_context (новый путь) или из строки (legacy)
    if shared_context and hasattr(shared_context, "game_time_seconds"):
        _current_total = shared_context.game_time_seconds
    else:
        _env_time = scene_state.get("environment", {}).get("time_of_day", "07:00")
        _seconds_in_day = Calendar.parse_hhmm(_env_time)
        _current_total = _seconds_in_day  # legacy: без дня/года

    _new_total = Calendar.advance(_current_total, _delta_seconds)

    # Обновляем shared_context
    if shared_context is not None:
        shared_context.game_time_seconds = _new_total

    # Сохраняем абсолютное время в scene_state для персистенции (Фаза 10)
    scene_state["game_time_seconds"] = _new_total

    # Обновляем time_of_day в scene_state для совместимости
    # (scene_state_manager._select_time_variant читает строку)
    _old_hhmm = Calendar.format_time(_current_total)
    _new_hhmm = Calendar.format_time(_new_total)
    scene_state.setdefault("environment", {})["time_of_day"] = _new_hhmm

    if _delta_seconds >= 60:
        logger.warning(f"[TIME_ADVANCE] {_old_hhmm} → {_new_hhmm} (+{_delta_seconds // 60} мин)")