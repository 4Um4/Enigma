"""Тесты KernelRNG determinism.

path: backend/tests/test_kernel_rng.py
Назначение: Тесты KernelRNG determinism.
Зависимости: pytest, KernelRNG
Основные сущности: test functions

Запуск: cd backend; python -m pytest tests/test_kernel_rng.py -v; cd ..
"""

import pytest
from app.services.npc.kernel_rng import KernelRNG


def test_same_tick_npc_same_sequence():
    """Same (tick, npc_id) → same RNG sequence."""
    rng_a = KernelRNG(tick=42, npc_id="maid_lusya")
    rng_b = KernelRNG(tick=42, npc_id="maid_lusya")

    assert rng_a.seed == rng_b.seed
    assert rng_a.random() == rng_b.random()
    assert rng_a.uniform(-1, 1) == rng_b.uniform(-1, 1)


def test_different_npc_independent():
    """Different npc_id → different sequences."""
    rng_a = KernelRNG(tick=42, npc_id="maid_lusya")
    rng_b = KernelRNG(tick=42, npc_id="thief_shadow")

    assert rng_a.seed != rng_b.seed
    # Very unlikely to be equal
    assert rng_a.random() != rng_b.random() or rng_a.uniform(0, 1) != rng_b.uniform(0, 1)


def test_different_tick_independent():
    """Different tick → different sequences."""
    rng_a = KernelRNG(tick=41, npc_id="maid_lusya")
    rng_b = KernelRNG(tick=42, npc_id="maid_lusya")

    assert rng_a.seed != rng_b.seed


def test_invalid_inputs():
    """Invalid inputs → ValueError."""
    with pytest.raises(ValueError):
        KernelRNG(tick=-1, npc_id="x")
    with pytest.raises(ValueError):
        KernelRNG(tick=0, npc_id="")
    with pytest.raises(ValueError):
        KernelRNG(tick="not_int", npc_id="x")


def test_choice_deterministic():
    """choice returns same element for same (tick, npc_id)."""
    seq = ["a", "b", "c", "d"]
    rng_a = KernelRNG(tick=100, npc_id="guard_borko")
    rng_b = KernelRNG(tick=100, npc_id="guard_borko")

    assert rng_a.choice(seq) == rng_b.choice(seq)


def test_choices_deterministic():
    """choices with weights returns same result."""
    seq = ["head", "torso", "arm"]
    weights = [1, 3, 2]
    rng_a = KernelRNG(tick=200, npc_id="merchant_goran")
    rng_b = KernelRNG(tick=200, npc_id="merchant_goran")

    assert rng_a.choices(seq, weights=weights, k=1) == rng_b.choices(seq, weights=weights, k=1)
