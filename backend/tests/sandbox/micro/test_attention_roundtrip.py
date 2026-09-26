# -*- coding: utf-8 -*-
"""
path: backend/tests/sandbox/micro/test_attention_roundtrip.py
Назначение: P1-гейт домена внимания — round-trip сериализации AttentionState
    (§12.2/12.3), cap окна (FIFO), неизменяемость, громкие отказы (L4),
    UNKNOWN ≠ 0 (§ENIGMA-003), монохронность (Invariant III).
Зависимости: app.domain.attention — только domain, без services (Устав §1.2).
Основные сущности: pytest-тесты.

Запуск: cd backend; python -m pytest tests/sandbox/micro/test_attention_roundtrip.py -v; cd ..
"""
import dataclasses

import pytest

from app.domain.attention import (
    ATTENTION_OBS_WINDOW,
    AttentionObservation,
    AttentionPhase,
    attention_from_dict,
    attention_to_dict,
    create_attention_state,
    with_observation,
)


def _obs(tick: int, distance: float) -> AttentionObservation:
    return AttentionObservation(
        tick=tick,
        distance=distance,
        bearing=0.3,
        subject_heading=1.2,
        rel_dx=1.0,
        rel_dy=-0.5,
    )


def test_roundtrip_preserves_all_fields() -> None:
    st = create_attention_state("maid_lusya", AttentionPhase.DETECTED, 100, _obs(100, 9.0))
    st = with_observation(st, AttentionPhase.APPROACHING, 101, _obs(101, 7.0))
    st = with_observation(st, AttentionPhase.APPROACHING, 102, _obs(102, 5.0))
    restored = attention_from_dict(attention_to_dict(st))
    assert attention_to_dict(restored) == attention_to_dict(st)
    assert restored.phase is AttentionPhase.APPROACHING
    assert restored.first_seen_tick == 100
    assert len(restored.observation_window) == 3


def test_window_cap_is_fifo() -> None:
    st = create_attention_state("a", AttentionPhase.DETECTED, 0, _obs(0, 10.0))
    # 10 добавлений сверх рождения: окно держит последние 8, старые вытеснены
    for i in range(1, ATTENTION_OBS_WINDOW + 3):
        st = with_observation(st, AttentionPhase.NEAR, i, _obs(i, 10.0 - i))
    assert len(st.observation_window) == ATTENTION_OBS_WINDOW
    # Вытеснены tick 0..2 → первое в окне = 3 (FIFO, а не LIFO)
    assert st.observation_window[0].tick == 3


def test_no_data_is_none_not_zero() -> None:
    st = create_attention_state("a", AttentionPhase.DETECTED, 5)
    assert st.last_distance is None
    assert st.last_bearing is None


def test_frozen_immutable() -> None:
    st = create_attention_state("a", AttentionPhase.DETECTED, 5, _obs(5, 3.0))
    with pytest.raises(dataclasses.FrozenInstanceError):
        st.phase = AttentionPhase.LOST  # type: ignore[misc]


def test_past_observation_rejected() -> None:
    st = create_attention_state("a", AttentionPhase.DETECTED, 10, _obs(10, 3.0))
    with pytest.raises(ValueError):
        with_observation(st, AttentionPhase.NEAR, 9, _obs(9, 2.0))


def test_from_dict_rejects_missing_key() -> None:
    d = attention_to_dict(create_attention_state("a", AttentionPhase.DETECTED, 1))
    del d["phase"]
    with pytest.raises(KeyError):
        attention_from_dict(d)


def test_non_finite_observation_rejected() -> None:
    with pytest.raises(ValueError):
        AttentionObservation(
            tick=1, distance=float("nan"), bearing=0.0, subject_heading=0.0
        )


def test_non_finite_rel_vector_rejected() -> None:
    with pytest.raises(ValueError):
        AttentionObservation(
            tick=1, distance=1.0, bearing=0.0, subject_heading=0.0, rel_dx=float("inf")
        )