# -*- coding: utf-8 -*-
"""
path: backend/tests/sandbox/micro/test_attention_evidence.py
Назначение: P3b-гейт — накопитель свидетельства (M4): различение «идёт ко
    мне» / «проходит мимо» (урок барсука: d*-гейтинг), угасание при
    остановке/бегстве, независимый канал поворота субъекта, границы [0,1],
    round-trip свидетельства.
Зависимости: app.domain.attention_inference, app.domain.attention.
Основные сущности: pytest-тесты evidence_delta + накопительная симуляция.

Запуск: cd backend; python -m pytest tests/sandbox/micro/test_attention_evidence.py -v; cd ..
"""
import math

import pytest

from app.domain.attention import AttentionObservation, attention_from_dict, attention_to_dict, create_attention_state, with_observation
from app.domain.attention_inference import (
    ApproachInference,
    evidence_delta,
    infer_approach,
    subject_turned_toward,
)

# Константы-дубли конфига (domain-чистые тесты; значения синхронны
# attention_config — расхождение поймает красный тест).
LAMBDA, RAD_W, AL_W, TURN_W = 0.85, 0.5, 0.35, 0.3
STILL, REF, TURN_MIN, SCALE = 0.15, 1.0, 0.2, 2.5

_KW = dict(
    radial_w=RAD_W, align_w=AL_W, turn_w=TURN_W,
    still_penalty=STILL, radial_ref=REF, approach_scale_m=SCALE,
)


def _win(pts, start_tick=100):
    return [
        AttentionObservation(
            tick=start_tick + i, distance=math.hypot(x, y), bearing=0.0,
            subject_heading=0.0, rel_dx=x, rel_dy=y,
        )
        for i, (x, y) in enumerate(pts)
    ]


def _accumulate(pts, turned_last=False):
    """Симуляция: E по формуле Мастера на растущем окне."""
    win = _win(pts)
    e = 0.0
    hist = []
    for k in range(2, len(pts) + 1):
        inf = infer_approach(win[:k], rel_dx=pts[k - 1][0], rel_dy=pts[k - 1][1])
        turned = turned_last and k == len(pts)
        e = max(0.0, min(1.0, LAMBDA * e + evidence_delta(inf, turned, **_KW)))
        hist.append(e)
    return e, hist


def test_direct_approach_accumulates_to_confidence() -> None:
    # Сценарий А: 8→3 по лучу, d*≈0 → E быстро к 1.
    e, hist = _accumulate([(8 - i, 0.0) for i in range(6)])
    assert hist[-1] > 0.8


def test_pass_by_does_not_accumulate() -> None:
    # Сценарий Б: сближение ЕСТЬ, но d*=3 > SCALE → d_factor=0 → E≈0.
    # КЛЮЧЕВОЙ анти-барсучий тест (Мастер: ранний проход-мимо ≠ приближение).
    e, hist = _accumulate([(3.0, 8.0 - 2.0 * i) for i in range(4)])
    assert all(h < 0.05 for h in hist)


def test_pass_by_with_turn_toward_accumulates() -> None:
    # Проход-мимо, но субъект ПОВЕРНУЛСЯ к наблюдателю на последнем тике:
    # интенция-канал независим от траектории → E растёт.
    e_no, _ = _accumulate([(3.0, 8.0 - 2.0 * i) for i in range(4)])
    e_turn, _ = _accumulate(
        [(3.0, 8.0 - 2.0 * i) for i in range(4)], turned_last=True
    )
    assert e_turn > e_no + 0.2


def test_standing_still_decays() -> None:
    # Подошёл и встал: «movement stops» → гипотеза угасает, не защёлкивается.
    e, _ = _accumulate([(8 - i, 0.0) for i in range(6)])
    assert e > 0.8
    still = ApproachInference(
        speed=0.0, radial_speed=0.0, alignment_to_me=None,
        time_to_closest=None, predicted_min_distance=None,
    )
    e2 = max(0.0, min(1.0, LAMBDA * e + evidence_delta(still, False, **_KW)))
    assert e2 < e  # затухание


def test_fleeing_decays_to_zero() -> None:
    # От меня по лучу: alignment −1, t*≤0 (d*=None) → e<0 → E → 0.
    e, _ = _accumulate([(3 + i, 0.0) for i in range(6)])
    assert e < 0.05


def test_subject_turned_toward_detection() -> None:
    # Субъект разворачивается К наблюдателю: зазор heading↔(на наблюдателя)
    # сокращается ≥ min_rad. rel_dx=+3 → субъект ВОСТОЧНЕЕ наблюдателя →
    # вектор субъект→наблюдатель = (−3,0) → to_obs = atan2(0,−3) = π.
    # Заголовки растут К π: 2.0→2.5→3.0, зазор 1.14→0.64→0.14 (шаг 0.5
    # ≥ min_rad). Контроль: за первые два наблюдения шаг такой же, но
    # функция смотрит только на ПОСЛЕДНЮЮ пару — и должна увидеть поворот
    # (1.14→0.64 ≥ 0.2) уже на паре (0,1).
    obs = [
        AttentionObservation(tick=100 + i, distance=3.0, bearing=math.pi,
                             subject_heading=2.0 + 0.5 * i,
                             rel_dx=3.0, rel_dy=0.0)
        for i in range(3)
    ]
    assert subject_turned_toward(obs, min_rad=TURN_MIN)
    assert subject_turned_toward(obs[:2], min_rad=TURN_MIN)


def test_subject_turned_away_not_flagged() -> None:
    # Негатив: заголовки УДАЛЯЮТСЯ от π (2.0→1.5→1.0) — зазор растёт,
    # поворот к наблюдателю не детектируется (урок красного теста:
    # to_obs = π при rel_dx=+3, направление поворота значимо).
    obs = [
        AttentionObservation(tick=100 + i, distance=3.0, bearing=math.pi,
                             subject_heading=2.0 - 0.5 * i,
                             rel_dx=3.0, rel_dy=0.0)
        for i in range(3)
    ]
    assert not subject_turned_toward(obs, min_rad=TURN_MIN)


def test_evidence_roundtrip_and_bounds() -> None:
    st = create_attention_state("a", __import__("app.domain.attention", fromlist=["AttentionPhase"]).AttentionPhase.DETECTED, 5)
    obs = AttentionObservation(tick=6, distance=4.0, bearing=0.1,
                               subject_heading=0.0, rel_dx=4.0, rel_dy=0.0)
    st = with_observation(st, st.phase, 6, obs, approach_evidence=0.77)
    restored = attention_from_dict(attention_to_dict(st))
    assert restored.approach_evidence == pytest.approx(0.77)
    with pytest.raises(ValueError):
        with_observation(st, st.phase, 7, obs, approach_evidence=1.5)


def test_approach_then_turns_away_decays() -> None:
    # Мастер §4, случай 3: приближается, затем отворачивает → Evidence снижается.
    # Фаза 1: идёт ко мне (d*≈0). Фаза 2: сворачивает поперёк — d* уходит в «мимо»,
    # t*→None → e_t < 0 → E затухает, не защёлкивается.
    pts = [(8.0, 0.0), (7.0, 0.0), (6.0, 0.0), (5.0, 0.0), (3.0, 2.0), (3.0, 5.0)]
    e, hist = _accumulate(pts)
    assert hist[2] > 0.2  # накопилось на подходе
    assert hist[-1] < hist[2]  # снижение после отворота


def test_fast_vs_slow_intensity_and_threshold() -> None:
    # Мастер §4, случаи 4-5 — v0-граница ЧЕСТНО: обе траектории прямые на
    # наблюдателя → d*=0 с первого шага → порог E достигается ОДНОВРЕМЕННО
    # (k=2: e_fast=0.85, e_slow=0.60 при инклюзивном пороге 0.6). Различие
    # скорости в v0 живёт в ИНТЕНСИВНОСТИ свидетельства (e_t fast > e_t slow
    # на каждом шаге); полный канал «реакция начинается раньше» =
    # ApproachIntensity f(E,v,T,d*) — P4 по вердикту Мастера §11. Фиксируем
    # интенситетный инвариант + одновременность порога как задокументированную
    # границу v0, а не баг.

    def _sim(speed: float) -> "tuple[float, int]":
        pts = [(max(0.5, 10.0 - speed * i), 0.0) for i in range(12)]
        win = _win(pts)
        e_acc = 0.0
        # Первое свидетельство фиксируется на первой итерации (k=2) —
        # типизированный float (Pylance: сравнение Optional запрещено).
        e_first = 0.0
        hit = -1
        for k in range(2, 13):
            inf = infer_approach(
                win[:k], rel_dx=win[k - 1].rel_dx, rel_dy=win[k - 1].rel_dy
            )
            e_t = evidence_delta(inf, False, **_KW)
            if k == 2:
                e_first = e_t
            e_acc = max(0.0, min(1.0, LAMBDA * e_acc + e_t))
            if hit < 0 and e_acc >= 0.6:
                hit = k
        return e_first, hit

    e_fast, hit_fast = _sim(1.5)
    e_slow, hit_slow = _sim(0.5)
    # Интенситетный инвариант v0: быстрое движение даёт больше свидетельства
    # за то же наблюдение (сырьё P4-интенситета).
    assert e_fast > e_slow
    # Порог достижимости для обеих (время — источник информации, но не для
    # d*-прямых траекторий в v0 — задокументированная граница).
    assert hit_fast > 0 and hit_slow > 0