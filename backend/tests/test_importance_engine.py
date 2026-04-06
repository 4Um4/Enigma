"""
Тесты R5.3 — ImportanceEngine: расширенный score_event.
Запуск: python -m pytest tests/test_importance_engine.py -v --tb=short
Назначение: проверяет что score_event() корректно учитывает clarity, stress, emotion.
"""

import pytest
from app.services.memory.importance_engine import score_event


def test_known_event_type_uses_base_importance() -> None:
    """combat должен иметь базовую важность 0.85 при идеальном восприятии."""
    score = score_event({"type": "combat"}, npc_clarity=1.0, npc_stress=0.0)
    assert score == pytest.approx(0.85, abs=0.01)


def test_low_clarity_reduces_importance() -> None:
    """Плохое восприятие снижает итоговую важность."""
    high = score_event({"type": "theft"}, npc_clarity=1.0)
    low  = score_event({"type": "theft"}, npc_clarity=0.3)
    assert low < high


def test_high_stress_with_angry_amplifies_importance() -> None:
    """Стресс + гнев усиливают важность угрозы."""
    base   = score_event({"type": "combat"}, npc_stress=0.0,  emotion_tag="neutral")
    amped  = score_event({"type": "combat"}, npc_stress=80.0, emotion_tag="angry")
    assert amped > base


def test_unknown_type_uses_default_base() -> None:
    """Неизвестный тип → базовое значение 0.30."""
    score = score_event({"type": "totally_unknown_xyz"}, npc_clarity=1.0, npc_stress=0.0)
    assert score == pytest.approx(0.30, abs=0.01)


def test_score_always_clamped_to_valid_range() -> None:
    """Результат всегда в диапазоне [0.05, 1.0]."""
    extremes = [
        score_event({"type": "combat"},    npc_clarity=0.0, npc_stress=100.0, emotion_tag="angry"),
        score_event({"type": "movement"},  npc_clarity=1.0, npc_stress=0.0,  emotion_tag="neutral"),
    ]
    for s in extremes:
        assert 0.05 <= s <= 1.0


def test_action_type_key_also_works() -> None:
    """action_type как ключ — legacy совместимость."""
    score = score_event({"action_type": "combat"})
    assert score > 0.5