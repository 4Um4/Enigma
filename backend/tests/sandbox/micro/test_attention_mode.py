# -*- coding: utf-8 -*-
"""
path: backend/tests/sandbox/micro/test_attention_mode.py
Назначение: P3c-1-гейт — фазовое пространство (S,E) → AttentionMode
    (Мастер §9): четыре квадранта, границы «>=», громкий отказ на NaN.
    Сценарии-смыслы: прохожий, барсук (S↑E↓), «идёт ко мне» (S↓E↑),
    резкое приближение (S↑E↑).
Зависимости: app.domain.attention_inference.
Основные сущности: pytest-тесты attention_mode.

Запуск: cd backend; python -m pytest tests/sandbox/micro/test_attention_mode.py -v; cd ..
"""
import pytest
from app.domain.attention_inference import AttentionMode, attention_mode

_KW = dict(surprise_threshold=0.5, evidence_threshold=0.6)


def test_quadrants() -> None:
    # Прохожий: ничего необычного.
    assert attention_mode(0.1, 0.1, **_KW) is AttentionMode.ROUTINE
    # Барсук: внезапное движение, но не ко мне.
    assert attention_mode(0.9, 0.1, **_KW) is AttentionMode.ALERT
    # Спокойное целенаправленное приближение (Мастер §9: «понимает/ждёт»).
    assert attention_mode(0.1, 0.9, **_KW) is AttentionMode.ANTICIPATING
    # Резкое приближение: и неожиданно, и ко мне.
    assert attention_mode(0.9, 0.9, **_KW) is AttentionMode.STARTLED


def test_boundaries_are_inclusive() -> None:
    # «>=» на обеих осях — детерминизм на границе (KernelRNG-культура).
    assert attention_mode(0.5, 0.1, **_KW) is AttentionMode.ALERT
    assert attention_mode(0.1, 0.6, **_KW) is AttentionMode.ANTICIPATING
    assert attention_mode(0.5, 0.6, **_KW) is AttentionMode.STARTLED
    assert attention_mode(0.49, 0.59, **_KW) is AttentionMode.ROUTINE


def test_non_finite_rejected() -> None:
    with pytest.raises(ValueError):
        attention_mode(float("nan"), 0.3, **_KW)
    with pytest.raises(ValueError):
        attention_mode(0.3, float("inf"), **_KW)