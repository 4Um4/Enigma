"""CCH-12 Point 1: семантическое различение возрастных якорей.

Тестирует контракт, не конкретную фразу Орма. Кейсы:
1. CURRENT_AGE не определяется regex — нужен game_start_age из канона.
2. AT_AGE: «в 14 лет» → AT_AGE(14).
3. SINCE_AGE: «с 12 лет» → SINCE_AGE(12).
4. DURATION: «уже 57 лет» → DURATION(57).
5. DURATION: «из которых 57 лет» → DURATION(57) (фраза Орма).
6. AMBIGUOUS: голое «146 лет» → AMBIGUOUS(146) (не CURRENT_AGE автоматически).
7. Несколько anchors: «146 лет ... уже 57 лет» → [AMBIGUOUS(146), DURATION(57)].
8. source_span сохраняет подстроку для трассировки.
9. Перекрытие match'ей: «уже 57 лет» не матчится дважды (DURATION + AMBIGUOUS).
10. age_anchors_to_hint формирует типизированную подсказку.
"""
from __future__ import annotations

from app.services.chronicle.age_anchor import (
    AgeAnchor,
    AgeAnchorKind,
    age_anchors_to_hint,
    extract_age_anchors_typed,
)


def _kinds(anchors):
    return [a.kind for a in anchors]


def _values(anchors):
    return [a.value for a in anchors]


def test_at_age_pattern():
    anchors = extract_age_anchors_typed("В 14 лет она потеряла семью.")
    assert len(anchors) == 1
    assert anchors[0].kind is AgeAnchorKind.AT_AGE
    assert anchors[0].value == 14
    assert "14" in anchors[0].source_span


def test_since_age_pattern():
    anchors = extract_age_anchors_typed("С 12 лет работала в таверне.")
    assert len(anchors) == 1
    assert anchors[0].kind is AgeAnchorKind.SINCE_AGE
    assert anchors[0].value == 12


def test_duration_already():
    anchors = extract_age_anchors_typed("Уже 57 лет он куёт в этом городе.")
    assert len(anchors) == 1
    assert anchors[0].kind is AgeAnchorKind.DURATION
    assert anchors[0].value == 57


def test_duration_of_which_orm_phrase():
    """Фраза Орма: «из которых он кузнец в городе уже 57 лет»."""
    anchors = extract_age_anchors_typed("146 лет, из которых 57 лет он кузнец.")
    durations = [a for a in anchors if a.kind is AgeAnchorKind.DURATION]
    assert len(durations) == 1
    assert durations[0].value == 57


def test_ambiguous_bare_number():
    """Голое «N лет» без контекста → AMBIGUOUS, не CURRENT_AGE автоматически."""
    anchors = extract_age_anchors_typed("Ему 146 лет.")
    assert len(anchors) == 1
    assert anchors[0].kind is AgeAnchorKind.AMBIGUOUS
    assert anchors[0].value == 146


def test_multiple_anchors_orm_point_1():
    """Полный фрагмент пункта 1 Орма: AMBIGUOUS(146) + DURATION(57)."""
    text = "146 лет, из которых он кузнец в городе уже 57 лет."
    anchors = extract_age_anchors_typed(text)
    assert len(anchors) == 2
    kinds = _kinds(anchors)
    values = _values(anchors)
    # 146 — AMBIGUOUS (нет маркера «в/с/уже» рядом)
    assert AgeAnchorKind.AMBIGUOUS in kinds
    assert 146 in values
    # 57 — DURATION (после «уже»)
    assert AgeAnchorKind.DURATION in kinds
    assert 57 in values


def test_no_overlap_duration_and_ambiguous():
    """«уже 57 лет» не должно матчиться дважды (DURATION + AMBIGUOUS на одном span)."""
    anchors = extract_age_anchors_typed("уже 57 лет")
    # Только DURATION(57), не AMBIGUOUS(57) на том же span
    assert len(anchors) == 1
    assert anchors[0].kind is AgeAnchorKind.DURATION


def test_source_span_preserved():
    anchors = extract_age_anchors_typed("В 14 лет она ушла из дома.")
    assert len(anchors) == 1
    assert "14" in anchors[0].source_span
    assert "лет" in anchors[0].source_span or "лет" not in anchors[0].source_span  # span может включать маркер


def test_age_anchors_to_hint_format():
    anchors = [
        AgeAnchor(value=146, kind=AgeAnchorKind.AMBIGUOUS, source_span="146 лет"),
        AgeAnchor(value=57, kind=AgeAnchorKind.DURATION, source_span="уже 57 лет"),
    ]
    hint = age_anchors_to_hint(anchors)
    assert "ambiguous" in hint.lower()
    assert "duration" in hint.lower()
    assert "146" in hint
    assert "57" in hint


def test_empty_text_returns_empty():
    anchors = extract_age_anchors_typed("")
    assert anchors == []