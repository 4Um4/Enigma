# backend/tests/test_behavior_mask_r62.py
# $env:PYTHONPATH="backend" pytest backend/tests/test_behavior_mask_r62.py -v
"""
Назначение: Unit-тесты R6.2 — BehaviorMask enum и BehaviorMaskState,
            включая интеграцию с NPCState и snapshot().
Зависимости: pytest, behavior_mask.py, npc_state.py
"""

import pytest

from backend.app.services.npc.behavior_mask import BehaviorMask, BehaviorMaskState
from backend.app.services.npc.npc_state import NPCState


# =========================================================
# TEST 1 — дефолтное состояние маски
# =========================================================

def test_r62_default_mask():
    """
    Проверяет:
    NPCState создаётся с NONE-маской по умолчанию.

    Критично для:
    гарантии что новые NPC не имеют активных масок.
    """
    npc = NPCState(npc_id="test_npc")

    assert npc.behavior_mask.mask is BehaviorMask.NONE
    assert npc.behavior_mask.intensity == 0.0
    assert npc.behavior_mask.applied_at_day is None
    assert npc.behavior_mask.is_active() is False


# =========================================================
# TEST 2 — is_active корректно определяет наличие маски
# =========================================================

def test_r62_is_active():
    """
    Проверяет:
    is_active() возвращает True только при не-NONE маске.

    Критично для:
    OpportunityEngine — он проверяет is_active() перед расчётом.
    """
    none_mask = BehaviorMaskState(mask=BehaviorMask.NONE)
    fake_mask = BehaviorMaskState(mask=BehaviorMask.FAKE_SUBMISSION, intensity=0.5)

    assert none_mask.is_active() is False
    assert fake_mask.is_active() is True


# =========================================================
# TEST 3 — is_concealment_mask: маски скрытия vs открытые
# =========================================================

def test_r62_concealment_masks():
    """
    Проверяет:
    FAKE_SUBMISSION и BETRAYAL — маски скрытия.
    COLLAPSE и NONE — нет.

    Критично для:
    EmotionalNuanceEngine — он показывает ложный эмоциональный
    слой только при masках скрытия.
    """
    assert BehaviorMaskState(mask=BehaviorMask.FAKE_SUBMISSION).is_concealment_mask() is True
    assert BehaviorMaskState(mask=BehaviorMask.BETRAYAL).is_concealment_mask() is True
    assert BehaviorMaskState(mask=BehaviorMask.COLLAPSE).is_concealment_mask() is False
    assert BehaviorMaskState(mask=BehaviorMask.NONE).is_concealment_mask() is False


# =========================================================
# TEST 4 — snapshot содержит поля behavior_mask
# =========================================================

def test_r62_snapshot_contains_mask_fields():
    """
    Проверяет:
    snapshot() сериализует все три поля маски.

    Критично для:
    логирования динамики слома и сохранений.
    """
    npc = NPCState(
        npc_id="test_npc",
        behavior_mask=BehaviorMaskState(
            mask=BehaviorMask.BETRAYAL,
            intensity=0.7,
            applied_at_day=3,
        )
    )

    snap = npc.snapshot()

    assert snap["behavior_mask"] == "betrayal"
    assert snap["behavior_mask_intensity"] == 0.7
    assert snap["behavior_mask_applied_at_day"] == 3


# =========================================================
# TEST 5 — все значения enum доступны
# =========================================================

def test_r62_all_enum_values():
    """
    Проверяет:
    Все четыре значения BehaviorMask существуют и уникальны.

    Критично для:
    BreakProgressEngine — он перебирает маски при переходах.
    """
    values = list(BehaviorMask)
    names  = [m.name for m in values]

    assert "NONE"             in names
    assert "FAKE_SUBMISSION"  in names
    assert "BETRAYAL"         in names
    assert "COLLAPSE"         in names
    assert len(set(values)) == 4   # уникальность