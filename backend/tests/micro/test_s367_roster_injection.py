# -*- coding: utf-8 -*-
"""S367: roster-инъекция — regression для contract-gated backstop.
Запуск: python -m pytest backend/tests/micro/test_s367_roster_injection.py -v

Покрытие (8):
1. known NPC -> нет roster_mismatch (exact match).
2. unknown NPC (RELATIONSHIP) -> roster_mismatch вопрос, conf<=0.4, 4 опции.
3. ambiguous (exact-fail: старая Люся vs Люся) -> вопрос.
4. absent roster (roster=None) -> backstop отключён.
5. LLM-precedence: существующий identity-вопрос -> нет дубля.
6. prompt-contains-roster: build_user_prompt с roster -> блок присутствует.
7. contract-gate: LOCATION name_hint НЕ backstopится.
8. contract-gate: EFFECT target_hint=null НЕ backstopится.
"""
from __future__ import annotations

import json

from app.domain.chronicle import ClarificationOption
from app.services.chronicle.biography_decomposer import BiographyDecomposer
from app.services.chronicle.decomposition_normalizer import (
    ChronicleDecompositionNormalizer,
)

ROSTER = {"maid_lusya": "Люся", "guard_borko": "Борко", "thief_shadow": "Тень"}


def _rel(target_hint, summary="связь", confidence=0.8):
    payload = {"summary": summary, "target_hint": target_hint, "nature": "trust", "valence": "positive"}
    return json.dumps({"items": [{"kind": "RELATIONSHIP", "draft_payload": payload, "confidence": confidence}]})


def _eff(target_hint, summary="эффект", confidence=0.8):
    payload = {"summary": summary, "effect_kind": "trauma", "target_hint": target_hint}
    return json.dumps({"items": [{"kind": "EFFECT", "draft_payload": payload, "confidence": confidence}]})


def _loc(name_hint, summary="место", confidence=0.8):
    payload = {"summary": summary, "name_hint": name_hint}
    return json.dumps({"items": [{"kind": "LOCATION", "draft_payload": payload, "confidence": confidence}]})


def _normalize(raw, roster):
    return ChronicleDecompositionNormalizer.normalize(
        raw, chronicle_id="c1", fragment_ord=0, roster=roster
    )


def _qid(item):
    q = item.question
    return q.question_id if q is not None else None


def test_known_npc_no_question():
    items = _normalize(_rel("Люся"), ROSTER)
    assert len(items) == 1
    qid = _qid(items[0])
    assert qid is None or not qid.startswith("roster_mismatch"), "known NPC; got %r" % qid


def test_unknown_npc_gets_question():
    items = _normalize(_rel("старый пьянчужка"), ROSTER)
    assert len(items) == 1
    q = items[0].question
    assert q is not None and q.question_id == "roster_mismatch_0"
    assert q.target_span == "старый пьянчужка"
    assert ClarificationOption.LEAVE_WHITE_SPOT in q.options
    assert ClarificationOption.SELECT_EXISTING_NPC in q.options
    assert items[0].confidence <= 0.4
    assert items[0].needs_confirmation is True


def test_ambiguous_phrase_gets_question():
    items = _normalize(_rel("старая Люся"), ROSTER)
    q = items[0].question
    assert q is not None and q.question_id == "roster_mismatch_0"
    assert q.target_span == "старая Люся"


def test_absent_roster_disables_backstop():
    items = _normalize(_rel("старый пьянчужка"), None)
    qid = _qid(items[0])
    assert qid is None or not qid.startswith("roster_mismatch"), "roster=None disables; got %r" % qid


def test_llm_identity_question_no_duplicate():
    raw = json.dumps({
        "items": [{
            "kind": "RELATIONSHIP",
            "draft_payload": {"summary": "связь", "target_hint": "старый пьянчужка",
                              "nature": "trust", "valence": "positive"},
            "confidence": 0.4,
            "question": {
                "question_id": "q_llm",
                "target_span": "старый пьянчужка",
                "options": ["SELECT_EXISTING_NPC", "CREATE_NEW_NPC",
                            "UNKNOWN_PERSON", "LEAVE_WHITE_SPOT"],
            },
        }]
    })
    items = _normalize(raw, ROSTER)
    q = items[0].question
    assert q is not None and q.question_id == "q_llm", "LLM identity preserved; got %r" % (
        q.question_id if q else None)
    assert not any(it.question and it.question.question_id.startswith("roster_mismatch")
                   for it in items)


def test_prompt_contains_roster_block():
    d = BiographyDecomposer()
    p = d.build_user_prompt("фрагмент биографии", [16], ROSTER)
    assert "ИЗВЕСТНЫЕ NPC (roster):" in p
    assert "Люся" in p and "Борко" in p and "Тень" in p
    assert "ФРАГМЕНТ:" in p
    p2 = d.build_user_prompt("фрагмент", [], None)
    assert "ИЗВЕСТНЫЕ NPC" not in p2
    assert "ФРАГМЕНТ:" in p2


def test_location_name_hint_not_backstopped():
    items = _normalize(_loc("Серебряный волк"), ROSTER)
    qid = _qid(items[0])
    assert qid is None or not qid.startswith("roster_mismatch"), "name_hint place; got %r" % qid


def test_effect_null_target_hint_not_backstopped():
    items = _normalize(_eff(None), ROSTER)
    qid = _qid(items[0])
    assert qid is None or not qid.startswith("roster_mismatch"), "null target_hint skip; got %r" % qid
