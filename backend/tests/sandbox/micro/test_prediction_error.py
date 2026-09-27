# -*- coding: utf-8 -*-
"""
path: backend/tests/sandbox/micro/test_prediction_error.py
Назначение: S-ось v2 (вердикт Мастера) — 10 контрольных случаев:
    прямолинейность→низкая ошибка, остановка/поворот→высокая, проход мимо,
    ускорение, смена траектории при дистанции, ИЗОЛЯЦИЯ ПАР (№7 — главный),
    отсутствие утечки текущего наблюдения (№8), недостаточная история (№9),
    отсутствие наблюдаемости (№10).
Зависимости: app.domain.attention_inference.prediction_error.
Основные сущности: pytest-тесты.

Запуск: cd backend; python -m pytest tests/sandbox/micro/test_prediction_error.py -v; cd ..
"""
import math

import pytest

from app.domain.attention import AttentionObservation
from app.domain.attention_inference import prediction_error

_SCALE = 0.8


def _obs(tick, dx, dy, heading=0.0):
    return AttentionObservation(
        tick=tick, distance=math.hypot(dx, dy), bearing=0.0,
        subject_heading=heading, rel_dx=dx, rel_dy=dy,
    )


def test_1_straight_line_low_error() -> None:
    # Прямолинейное движение: прогноз точен → ошибка ≈ 0.
    win = [_obs(100 + i, 10.0 - i, 0.0) for i in range(5)]
    cur = win[-1]
    s = prediction_error(win, cur.rel_dx, cur.rel_dy, scale_m=_SCALE)
    assert s is not None and s < 0.1


def test_2_abrupt_stop_high_error() -> None:
    # Резкая остановка: факт-смещение ≈ 0 при прогнозе движения → высокая.
    win = [_obs(100 + i, 10.0 - 1.0 * i, 0.0) for i in range(4)]
    cur = _obs(104, 9.0, 0.0)  # встал: та же точка, что win[-1]
    s = prediction_error(win, cur.rel_dx, cur.rel_dy, scale_m=_SCALE)
    assert s is not None and s > 0.7


def test_3_sharp_turn_high_error() -> None:
    # Резкий поворот 90°: факт перпендикулярен прогнозу → высокая.
    win = [_obs(100 + i, 10.0 - i, 0.0) for i in range(4)]
    cur = _obs(104, 7.0, 1.0)  # было бы (7,0) по прогнозу; ушёл вбок
    s = prediction_error(win, cur.rel_dx, cur.rel_dy, scale_m=_SCALE)
    assert s is not None and s > 0.7


def test_4_pass_by_moderate() -> None:
    # Проход мимо: прямолинеен → ошибка НИЗКАЯ (прохождение мимо само по
    # себе не «неудивительно» — это различает S и E: E≈0, S≈0).
    win = [_obs(100 + i, 3.0, 8.0 - 2.0 * i) for i in range(4)]
    cur = win[-1]
    s = prediction_error(win, cur.rel_dx, cur.rel_dy, scale_m=_SCALE)
    assert s is not None and s < 0.15


def test_5_acceleration_toward() -> None:
    # Ускорение к наблюдателю: каждый шаг больше прогноза → ошибка растёт.
    win = [_obs(100 + i, 10.0 - (0.5 * i * i) ** 0.5 * 2, 0.0) for i in range(4)]
    cur = _obs(104, 10.0 - 2.0 * 1.5, 0.0)
    s = prediction_error(win, cur.rel_dx, cur.rel_dy, scale_m=_SCALE)
    assert s is not None and s > 0.3


def test_6_course_change_same_distance() -> None:
    # Смена траектории при сохранении дистанции (движение по дуге):
    # прогноз по хорде промахивается → ошибка заметная.
    win = [_obs(100 + i, 5.0 - i * 0.0, 5.0 - i * 1.0) for i in range(3)]
    cur = _obs(103, 5.0 - 0.8, 2.0)  # сдвиг вбок при том же радиусе
    s = prediction_error(win, cur.rel_dx, cur.rel_dy, scale_m=_SCALE)
    assert s is not None and s > 0.3


def test_7_pair_isolation() -> None:
    # ГЛАВНЫЙ (Мастер §2): событие субъекта A не меняет показатели пары B.
    # Функция чистая per-pair: окно A и окно B независимы; «событие» A =
    # резкий поворот в его окне. S(A) высокая, S(B) остаётся низкой.
    win_a = [_obs(100 + i, 10.0 - i, 0.0) for i in range(4)]
    turn_a = _obs(104, 7.0, 1.0)
    win_b = [_obs(100 + i, 6.0 - 0.5 * i, 0.0) for i in range(4)]
    cur_b = win_b[-1]
    s_a = prediction_error(win_a, turn_a.rel_dx, turn_a.rel_dy, scale_m=_SCALE)
    s_b = prediction_error(win_b, cur_b.rel_dx, cur_b.rel_dy, scale_m=_SCALE)
    assert s_a is not None and s_a > 0.7
    assert s_b is not None and s_b < 0.1
    # Явная изоляция: функция не имеет доступа к чужим окнам by design
    # (сигнатура принимает одно окно).


def test_8_no_leak_of_current_into_prediction() -> None:
    # №8 (запрет утечки): прогноз строится по window[:-1]. Доказательство:
    # подменяем ПОСЛЕДНИЙ элемент окна на абсурдный выброс — результат
    # НЕ меняется (текущее не участвует в прогнозе).
    win = [_obs(100 + i, 10.0 - i, 0.0) for i in range(5)]
    cur = win[-1]
    s1 = prediction_error(win, cur.rel_dx, cur.rel_dy, scale_m=_SCALE)
    win_poisoned = win[:-1] + [_obs(104, 999.0, 999.0)]
    s2 = prediction_error(
        win_poisoned, cur.rel_dx, cur.rel_dy, scale_m=_SCALE
    )
    assert s1 is not None and s2 is not None
    assert s1 == pytest.approx(s2)  # выброс в «текущем» не влияет


def test_9_insufficient_history() -> None:
    # Недостаточная история: <2 точек или v̂≈0 → None (UNKNOWN ≠ 0).
    assert prediction_error([_obs(100, 5, 0)], 5, 0, scale_m=_SCALE) is None
    win_still = [_obs(100 + i, 5.0, 0.0) for i in range(4)]
    assert prediction_error(win_still, 5.0, 0.0, scale_m=_SCALE) is None


def test_10_no_observability() -> None:
    # Нет наблюдаемости: пустое окно → None. None-вход — нарушение
    # контракта вызывающего (окно AttentionState всегда tuple): по L4
    # корректное поведение — ГРОМКИЙ TypeError, а не тихий None, который
    # маскировал бы баг источника данных. Фиксируем громкость как контракт.
    assert prediction_error([], 0, 0, scale_m=_SCALE) is None
    with pytest.raises(TypeError):
        prediction_error(None, 0, 0, scale_m=_SCALE)  # type: ignore[arg-type]