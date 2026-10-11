# -*- coding: utf-8 -*-
"""path: backend/tests/sandbox/micro/test_ue_dm_rule.py
Назначение: UX-UE-01 Этап 1, ③ (DP-5, GO Тай) + R3 — правило DM: при
    readiness ≠ RESOLVED канонизированное описание хода НЕ утверждает
    исполнение (маркер «не исполнено»); при RESOLVED маркер отсутствует;
    QUESTION/GREETING-контроли не задеты. Точка — статик
    _presentation_safe_actions (Пакет C, dm_agent:702).
Зависимости: app.agents.dm_agent
Запуск: cd backend; python -m pytest tests/sandbox/micro/test_ue_dm_rule.py -q; cd ..
"""
import inspect

import pytest

from app.agents import dm_agent as _dm_mod

_MARKER = "не исполнено"


def _presentation():
    """Владелец-класс резолвится по признаку (имя класса не захардкожено)."""
    for _name, _obj in vars(_dm_mod).items():
        if inspect.isclass(_obj) and "_presentation_safe_actions" in vars(_obj):
            return _obj._presentation_safe_actions
    raise AssertionError("класс-владелец _presentation_safe_actions не найден")


def _ctx(readiness: str, acts: list) -> dict:
    return {"player_intent_projection": {
        "action": "dialogue", "target": "",
        "readiness": readiness,
        "semantic_action": "DIALOGUE",
        "semantic_acts": acts,
    }}


@pytest.mark.xfail(strict=True, reason="UX-UE-01 ③: DM-правило не реализовано (Этап 2)")
def test_dm_description_marks_nonresolved_partial():
    out = _presentation()(_ctx("PARTIAL", []), [])
    assert _MARKER in out.lower()


@pytest.mark.xfail(strict=True, reason="UX-UE-01 ③: DM-правило не реализовано (Этап 2)")
def test_dm_description_marks_nonresolved_reference_ambiguous():
    out = _presentation()(_ctx("REFERENCE_AMBIGUOUS", []), [])
    assert _MARKER in out.lower()


def test_dm_description_resolved_no_marker():
    out = _presentation()(_ctx("RESOLVED", [{"type": "QUESTION", "params": {"topic": "эль"}}]), [])
    assert _MARKER not in out.lower()


def test_dm_question_act_not_suppressed():
    # R3-негативный контроль: обычные вопросы не задеваются
    out = _presentation()(_ctx("RESOLVED", [{"type": "QUESTION", "params": {"topic": "эль"}}]), [])
    assert "вопрос" in out.lower()


def test_dm_greeting_act_not_suppressed():
    # R3-негативный контроль: приветствия не задеваются
    out = _presentation()(_ctx("RESOLVED", [{"type": "GREETING", "params": {}}]), [])
    assert _MARKER not in out.lower()


def test_dm_no_projection_degradation_lock():
    # Замок существующего поведения (dm_agent:714): без проекции — нейтральный факт
    out = _presentation()({}, [])
    assert "недоступны" in out.lower()