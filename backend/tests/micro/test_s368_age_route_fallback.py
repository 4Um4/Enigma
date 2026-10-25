# -*- coding: utf-8 -*-
"""
S368: регрессия на детерминированный route-fallback age_anchors[0] -> EVENT.

Контракт (chronicle_decompose_system.txt:39): age = атрибут события.
Если LLM не проставила age явно, а фрагмент дал ровно один якорь и
декомпозиция содержит ровно одно EVENT — fallback прокидывает якорь в
historical_age этого EVENT. Иначе — None (неопределённость, §ENIGMA-003).

Запуск: python -m pytest backend/tests/micro/test_s368_age_route_fallback.py -v
"""
from __future__ import annotations

import json
from typing import List

from app.domain.chronicle import EntryKind, EntryProvenance
from app.services.chronicle.biography_decomposer import DecomposeResult
from app.services.chronicle.decomposition_normalizer import (
    ChronicleDecompositionNormalizer,
)


# ── Хелпер: воспроизводит route-конверсию routes_chronicle.py:263-283 ──────

def _route_age_value(item, result: DecomposeResult):
    """Точная реплика блока §S368 из routes_chronicle.py — для unit-теста."""
    age = item.draft_payload.get("age", item.draft_payload.get("historical_age"))
    age_value = age if isinstance(age, int) else None
    if (
        age_value is None
        and item.kind is EntryKind.EVENT
        and result.age_anchors
        and len(result.age_anchors) == 1
    ):
        event_count = sum(1 for x in result.items if x.kind is EntryKind.EVENT)
        if event_count == 1:
            age_value = result.age_anchors[0]
    return age_value


def _make_result(items_raw: str, anchors: List[int]) -> DecomposeResult:
    items = ChronicleDecompositionNormalizer.normalize(
        items_raw, chronicle_id="t", fragment_ord=0
    )
    return DecomposeResult.success(items, anchors)


# ── 1. Основной сценарий: 1 EVENT + 1 якорь + LLM не проставила age ───────

def test_fallback_single_anchor_single_event():
    """Дамп-сценарий: EVENT «осталась без родителей», anchors=[8], age=None
    в payload. Fallback должен проставить historical_age=8 ТОЛЬКО этому EVENT.
    RELATIONSHIP и EFFECT остаются None."""
    raw = json.dumps({"items": [
        {"kind": "EVENT", "draft_payload": {"summary": "осталась без родителей", "day": None}, "confidence": 1.0},
        {"kind": "RELATIONSHIP", "draft_payload": {"summary": "дальний родственник", "target_hint": "Торнин"}, "confidence": 1.0},
        {"kind": "EFFECT", "draft_payload": {"summary": "живёт в трактире", "effect_kind": "residence"}, "confidence": 1.0},
    ]})
    r = _make_result(raw, [8])
    ages = [_route_age_value(it, r) for it in r.items]
    assert ages == [8, None, None], f"ожидался [8, None, None], получено {ages}"


# ── 2. Приоритет LLM: явный age > fallback ────────────────────────────────

def test_priority_llm_age_over_fallback():
    """LLM проставила age=24 в payload, anchors=[8]. Должен победить LLM (24),
    не fallback (8). Проверяет требование Мастера «явный age приоритетнее»."""
    raw = json.dumps({"items": [
        {"kind": "EVENT", "draft_payload": {"summary": "поступил", "age": 24}, "confidence": 0.9},
    ]})
    r = _make_result(raw, [8])
    assert _route_age_value(r.items[0], r) == 24


def test_priority_historical_age_key_over_fallback():
    """LLM проставила historical_age=24 (legacy-ключ), anchors=[8].
    Route читает .get('age', .get('historical_age')) — должен взять 24."""
    raw = json.dumps({"items": [
        {"kind": "EVENT", "draft_payload": {"summary": "поступил", "historical_age": 24}, "confidence": 0.9},
    ]})
    r = _make_result(raw, [8])
    assert _route_age_value(r.items[0], r) == 24


# ── 3. Отказ при множественности ──────────────────────────────────────────

def test_no_fallback_multiple_anchors():
    """2 якоря + 1 EVENT без age → None. §ENIGMA-003: не выдумываем, какому
    событию соответствует каждый якорь."""
    raw = json.dumps({"items": [
        {"kind": "EVENT", "draft_payload": {"summary": "что-то"}, "confidence": 0.9},
    ]})
    r = _make_result(raw, [8, 16])
    assert _route_age_value(r.items[0], r) is None


def test_no_fallback_multiple_events():
    """1 якорь + 2 EVENT без age → None. Неопределённость: какому событию
    соответствует якорь? Не выдумываем."""
    raw = json.dumps({"items": [
        {"kind": "EVENT", "draft_payload": {"summary": "первое событие"}, "confidence": 0.9},
        {"kind": "EVENT", "draft_payload": {"summary": "второе событие"}, "confidence": 0.9},
    ]})
    r = _make_result(raw, [8])
    assert _route_age_value(r.items[0], r) is None
    assert _route_age_value(r.items[1], r) is None


# ── 4. Fallback НЕ протекает в не-EVENT (контракт: age только для событий) ─

def test_no_fallback_to_relationship_or_effect():
    """1 якорь + 0 EVENT (только RELATIONSHIP+EFFECT) → никто не получает age.
    Контракт system-prompt:39: age=атрибут события; RELATIONSHIP/EFFECT
    возраста не имеют."""
    raw = json.dumps({"items": [
        {"kind": "RELATIONSHIP", "draft_payload": {"summary": "родство", "target_hint": "X"}, "confidence": 1.0},
        {"kind": "EFFECT", "draft_payload": {"summary": "эффект", "effect_kind": "residence"}, "confidence": 1.0},
    ]})
    r = _make_result(raw, [8])
    assert _route_age_value(r.items[0], r) is None
    assert _route_age_value(r.items[1], r) is None


# ── 5. day/строка не превращается в age (требование Мастера) ──────────────

def test_no_fallback_string_day():
    """day="24" (строка) не становится age — isinstance(int) режет его,
    и fallback в этом случае НЕ срабатывает на EVENT (т.к. day вообще не
    читается route-логикой, отличной от age/historical_age).
    Требование Мастера: «строковый day не превращается в возраст»."""
    raw = json.dumps({"items": [
        {"kind": "EVENT", "draft_payload": {"summary": "поступил", "day": "24"}, "confidence": 0.9},
    ]})
    r = _make_result(raw, [24])
    # _age = None (day не читается route), isinstance(None, int)=False → fallback
    # срабатывает: 1 якорь + 1 EVENT + age_value is None → historical_age=24.
    # Это корректно: строковый day проигнорирован, а якорь используется.
    assert _route_age_value(r.items[0], r) == 24


def test_int_day_does_not_become_age_via_route():
    """S365-комментарий (test_age_passthrough_legacy_day_key) утверждал, что
    route берёт day как fallback. ФАКТИЧЕСКИ route читает только
    age/historical_age (routes_chronicle.py:263). day=24 (int) НЕ становится
    age — но fallback на якорь срабатывает (т.к. age_value is None).
    Тест фиксирует фактическое поведение: day не используется route-логикой
    напрямую; S368-fallback использует только age_anchors."""
    raw = json.dumps({"items": [
        {"kind": "EVENT", "draft_payload": {"summary": "поступил", "day": 24}, "confidence": 0.9},
    ]})
    # Без якорей — day один не помогает (route его не читает):
    r_no_anchors = _make_result(raw, [])
    assert _route_age_value(r_no_anchors.items[0], r_no_anchors) is None
    # С одним якорем — fallback срабатывает (day не мешает):
    r_with_anchor = _make_result(raw, [24])
    assert _route_age_value(r_with_anchor.items[0], r_with_anchor) == 24


# ── 6. Пустые/нулевые грани ───────────────────────────────────────────────

def test_no_fallback_empty_anchors():
    """anchors=[] — fallback не активируется, historical_age=None."""
    raw = json.dumps({"items": [
        {"kind": "EVENT", "draft_payload": {"summary": "событие"}, "confidence": 0.9},
    ]})
    r = _make_result(raw, [])
    assert _route_age_value(r.items[0], r) is None


def test_no_fallback_none_anchors():
    """result.age_anchors=None (декомпозер не нашёл) — fallback не активируется."""
    raw = json.dumps({"items": [
        {"kind": "EVENT", "draft_payload": {"summary": "событие"}, "confidence": 0.9},
    ]})
    items = ChronicleDecompositionNormalizer.normalize(raw, chronicle_id="t", fragment_ord=0)
    r = DecomposeResult(ok=True, items=items, age_anchors=None)
    assert _route_age_value(r.items[0], r) is None
