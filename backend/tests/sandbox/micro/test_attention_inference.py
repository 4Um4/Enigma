# -*- coding: utf-8 -*-
"""
path: backend/tests/sandbox/micro/test_attention_inference.py
Назначение: P3a-гейт — различение траекторий (Сценарии А/Б Мастера):
    «идёт ко мне» vs «проходит мимо» при ОДИНАКОВОМ текущем сближении;
    «остановился»; «уже прошёл»; вырожденные случаи. Всё pure, детерминировано.
Зависимости: app.domain.attention_inference, app.domain.attention.
Основные сущности: pytest-тесты infer_approach.

Запуск: cd backend; python -m pytest tests/sandbox/micro/test_attention_inference.py -v; cd ..
"""
import math

import pytest
from app.domain.attention import AttentionObservation
from app.domain.attention_inference import infer_approach


def _win(points, start_tick=100):
    """points: [(rel_dx, rel_dy), ...] — по тику на точку."""
    return [
        AttentionObservation(
            tick=start_tick + i,
            distance=math.hypot(x, y),
            bearing=0.0,
            subject_heading=0.0,
            rel_dx=x,
            rel_dy=y,
        )
        for i, (x, y) in enumerate(points)
    ]


def test_direct_approach() -> None:
    # Сценарий А: 8→7→6→5→4→3 вдоль луча, прямо на наблюдателя.
    pts = [(8, 0), (7, 0), (6, 0), (5, 0), (4, 0), (3, 0)]
    inf = infer_approach(_win(pts), rel_dx=3.0, rel_dy=0.0)
    assert inf.speed == pytest.approx(1.0, abs=1e-6)
    assert inf.radial_speed < 0  # сближается
    assert inf.alignment_to_me == pytest.approx(1.0, abs=1e-6)  # прямо на меня
    assert inf.time_to_closest is not None and inf.time_to_closest > 0
    assert inf.predicted_min_distance == pytest.approx(0.0, abs=1e-6)  # дойдёт


def test_pass_by() -> None:
    # Сценарий Б (Мастер): сближение ЕСТЬ (8→2), но траектория проходит
    # мимо на d*≈3. ВАЖНО (урок разбора барсука): в момент rel=(3,2)
    # скорость ЧАСТИЧНО направлена на наблюдателя — alignment = 2/√13
    # (не 0!); он спадает до 0 в точке ближайшего сближения (3,0) и далее
    # уходит в минус. Поэтому проход-мимо различается от «идёт ко мне»
    # ТОЛЬКО d* — именно это и есть его сигнатура.
    pts = [(3.0, 8.0), (3.0, 6.0), (3.0, 4.0), (3.0, 2.0)]
    inf = infer_approach(_win(pts), rel_dx=3.0, rel_dy=2.0)
    assert inf.radial_speed < 0  # сближается — как в Сценарии А!
    assert inf.alignment_to_me == pytest.approx(2.0 / math.sqrt(13), abs=1e-6)
    assert inf.time_to_closest == pytest.approx(1.0, abs=1e-6)
    assert inf.predicted_min_distance is not None
    assert inf.predicted_min_distance == pytest.approx(3.0, abs=0.05)  # мимо
    # Ключевое различение пары А/Б: d*_А ≈ 0, d*_Б ≈ 3.


def test_pass_by_at_closest_point() -> None:
    # Субъект в точке ближайшего сближения (3,0), движется поперёк:
    # alignment = 0 ровно, radial = 0 (уже не сближается), t* = 0 —
    # граница: ближайшая точка «сейчас или позади» → t*/d* = None
    # (отрицательное свидетельство для P3b, будущее сближения нет).
    pts = [(3.0, 2.0), (3.0, 1.0), (3.0, 0.0)]
    inf = infer_approach(_win(pts), rel_dx=3.0, rel_dy=0.0)
    assert inf.alignment_to_me == pytest.approx(0.0, abs=1e-6)
    assert inf.radial_speed == pytest.approx(0.0, abs=1e-6)
    assert inf.time_to_closest is None
    assert inf.predicted_min_distance is None


def test_already_passed() -> None:
    # Точка сближения позади: t* ≤ 0 → отрицательное свидетельство (None).
    pts = [(3.0, 2.0), (3.0, 0.0), (3.0, -2.0), (3.0, -4.0)]
    inf = infer_approach(_win(pts), rel_dx=3.0, rel_dy=-4.0)
    assert inf.radial_speed > 0  # удаляется
    assert inf.time_to_closest is None
    assert inf.predicted_min_distance is None


def test_standing_still() -> None:
    pts = [(5.0, 0.0)] * 6
    inf = infer_approach(_win(pts), rel_dx=5.0, rel_dy=0.0)
    assert inf.speed == pytest.approx(0.0, abs=1e-3)
    assert inf.alignment_to_me is None  # UNKNOWN, не 0 (§ENIGMA-003)


def test_stops_after_approach() -> None:
    # Подошёл и встал: короткое окно (k=3) видит остановку.
    pts = [(8, 0), (7, 0), (6, 0), (5, 0), (5, 0), (5, 0)]
    inf = infer_approach(_win(pts), rel_dx=5.0, rel_dy=0.0)
    assert inf.speed == pytest.approx(0.0, abs=1e-3)
    assert inf.time_to_closest is None


def test_single_observation_no_inference() -> None:
    inf = infer_approach(_win([(5, 0)]), rel_dx=5.0, rel_dy=0.0)
    assert inf.speed == 0.0 and inf.alignment_to_me is None


def test_fleeing_directly() -> None:
    # От меня по лучу: alignment −1, радиальная > 0.
    pts = [(3, 0), (4, 0), (5, 0), (6, 0)]
    inf = infer_approach(_win(pts), rel_dx=6.0, rel_dy=0.0)
    assert inf.alignment_to_me == pytest.approx(-1.0, abs=1e-6)
    assert inf.radial_speed > 0
    assert inf.time_to_closest is None  # t* ≤ 0: позади