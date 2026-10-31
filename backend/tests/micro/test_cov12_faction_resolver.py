"""COV-12 p.3a: faction registry в roster backstop — распознавание организаций.

8 контрастных проверок границ контракта resolver:
1. «гильдия воров» → организация, вопрос не создаётся.
2. «Гильдия Воров» (case variant) → организация, вопрос не создаётся.
3. «городская стража» → организация/коллектив, вопрос не создаётся.
4. «писарь квартальной управы» → вопрос об идентичности носителя (не фракция).
5. «Торнин» → roster_mismatch сохраняется (partial match — отдельная задача p.3b).
6. «старый друг» → roster_mismatch сохраняется (безымянная персона).
7. «гильд» (короткий substring) → НЕ матчит (защита коротких ID).
8. «гильдия воров и городская стража» (ambiguous) → НЕ матчит (две фракции).

Не тестирует: partial matching NPC (p.3b), morphology/lemmatization (p.3c),
EVENT decomposition, effect_kind=command.
"""
from __future__ import annotations

from app.services.chronicle.decomposition_normalizer import (
    _load_faction_registry,
    _matches_faction,
    ChronicleDecompositionNormalizer,
)

_ROSTER = {
    "tavern_keeper_tornin": "Торнин Серебряная Луна",
    "guard_borko": "Стражник Борко",
    "blacksmith_orm": "Кузнец Орм",
    "maid_lusya": "Люся",
    "merchant_goran": "Купец Горан",
    "thief_shadow": "Тень",
}


def _normalize_and_check(hint: str) -> bool:
    """Проверяет, создаст ли roster backstop ClarificationQuestion для hint."""
    factions = _load_faction_registry()
    return _matches_faction(hint, factions)


# ── Группа 1: Организации — вопрос не создаётся ───────────────────────


def test_faction_exact_match_guild():
    """«гильдия воров» → организация, вопрос не создаётся."""
    assert _normalize_and_check("гильдия воров") is True


def test_faction_case_variant():
    """«Гильдия Воров» (case variant) → организация, вопрос не создаётся."""
    assert _normalize_and_check("Гильдия Воров") is True


def test_faction_city_guard():
    """«городская стража» → организация/коллектив, вопрос не создаётся."""
    assert _normalize_and_check("городская стража") is True


def test_faction_id_with_underscore():
    """«гильдия_воров» (faction_id формат) → организация, вопрос не создаётся."""
    assert _normalize_and_check("гильдия_воров") is True


# ── Группа 2: Не организации — вопрос создаётся ───────────────────────


def test_role_not_faction():
    """«писарь квартальной управы» → вопрос об идентичности носителя."""
    assert _normalize_and_check("писарь квартальной управы") is False


def test_named_npc_mismatch():
    """«Торнин» → roster_mismatch сохраняется (partial match — отдельная задача)."""
    # Не фракция → _matches_faction = False → вопрос создаётся
    assert _normalize_and_check("Торнин") is False


def test_unnamed_person():
    """«старый друг» → roster_mismatch сохраняется (безымянная персона)."""
    assert _normalize_and_check("старый друг") is False


# ── Группа 3: Защита от ложных совпадений ──────────────────────────────


def test_short_substring_no_match():
    """«гильд» (короткий substring) → НЕ матчит (защита коротких ID)."""
    assert _normalize_and_check("гильд") is False


def test_ambiguous_faction_match():
    """«гильдия воров и городская стража» (две фракции) → НЕ матчит (ambiguous)."""
    assert _normalize_and_check("гильдия воров и городская стража") is False


# ── Группа 4: Интеграционный тест через normalizer ────────────────────


def test_normalizer_skips_faction_question():
    """Интеграция: normalizer с RELATIONSHIP target_hint=«гильдия воров»
    НЕ создаёт ClarificationQuestion (faction recognized)."""
    items = ChronicleDecompositionNormalizer.normalize(
        {
            "items": [
                {
                    "kind": "RELATIONSHIP",
                    "draft_payload": {
                        "summary": "Орм предупредил гильдию воров.",
                        "target_hint": "гильдия воров",
                        "nature": "доверие",
                        "valence": "positive",
                    },
                    "confidence": 0.9,
                }
            ]
        },
        chronicle_id="test_npc",
        fragment_ord=4,
        roster=_ROSTER,
    )
    assert len(items) == 1
    item = items[0]
    # Question НЕ создан — faction recognized
    assert item.question is None, (
        "Faction hint не должен создавать ClarificationQuestion"
    )
    # Confidence не понижен (нет question → нет min(0.4))
    assert item.confidence == 0.9


def test_normalizer_creates_question_for_role():
    """Интеграция: normalizer с RELATIONSHIP target_hint=«писарь квартальной управы»
    СОЗДАЁТ ClarificationQuestion (не фракция — вопрос о носителе)."""
    items = ChronicleDecompositionNormalizer.normalize(
        {
            "items": [
                {
                    "kind": "RELATIONSHIP",
                    "draft_payload": {
                        "summary": "Орм предупредил писаря.",
                        "target_hint": "писарь квартальной управы",
                        "nature": "доверие",
                        "valence": "positive",
                    },
                    "confidence": 0.9,
                }
            ]
        },
        chronicle_id="test_npc",
        fragment_ord=4,
        roster=_ROSTER,
    )
    assert len(items) == 1
    item = items[0]
    # Question создан — не фракция, не NPC → roster_mismatch
    assert item.question is not None, (
        "Не-фракция без exact NPC match должна создавать ClarificationQuestion"
    )
    assert "roster_mismatch" in item.question.question_id