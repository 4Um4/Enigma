# -*- coding: utf-8 -*-
"""A2 — Self-reference: detection, prevent, consistency Finding (CCH-12 Audit).

7 тестов по чеклисту Мастера:
1. Явная самонаправленная связь (сохранить) — consistency не порождает Finding.
2. Ошибочная self-resolution (LLM target_hint=subject) — normalizer создаёт вопрос.
3. Неоднозначная цель (ClarificationQuestion с target_span=target_hint, не summary).
4. Обычное отношение между двумя NPC — нет вопроса.
5. Self-reference, пропущенная seeder — skip_detail заполнен.
6. Отсутствие Finding для допустимой self-reference — object_id=RESOLVED(subject).
7. Отсутствие автоматической миграции существующих записей — канон не мутируется.

Запуск: cd backend; python -m pytest tests/micro/test_a2_self_reference.py -v
"""
from __future__ import annotations

import json

from app.domain.chronicle import (
    ChronicleDocument,
    ChronicleEntry,
    ClarificationOption,
    EntityRef,
    EntityRefKind,
    EntryKind,
    EntryProvenance,
)
from app.services.chronicle.chronicle_seeder import _classify_seed_entry
from app.services.chronicle.consistency_service import (
    CanonicalRegistry,
    ConsistencyService,
    K_SELF_REFERENCE_UNRESOLVED,
)
from app.services.chronicle.decomposition_normalizer import (
    ChronicleDecompositionNormalizer,
)


# ── Helpers ─────────────────────────────────────────────────────────────────

ROSTER = {"blacksmith_orm": "Орм", "maid_lusya": "Люся", "guard_borko": "Борко"}


def _rel(target_hint, summary="связь", confidence=0.8):
    payload = {
        "summary": summary,
        "target_hint": target_hint,
        "nature": "trust",
        "valence": "positive",
    }
    return json.dumps(
        {"items": [{"kind": "RELATIONSHIP", "draft_payload": payload, "confidence": confidence}]}
    )


def _normalize(raw, roster, subject_id=None):
    return ChronicleDecompositionNormalizer.normalize(
        raw,
        chronicle_id="blacksmith_orm",
        fragment_ord=0,
        roster=roster,
        subject_id=subject_id,
    )


def _entry(npc, **kw):
    base = dict(
        entry_id=kw.pop("eid"),
        kind=EntryKind.RELATIONSHIP,
        subject_id=EntityRef(ref_kind=EntityRefKind.RESOLVED, npc_id=npc),
        provenance=EntryProvenance.AUTHOR_CONFIRMED,
        ordinal=0,
    )
    base.update(kw)
    return ChronicleEntry(**base)


def _doc(npc, entries):
    return ChronicleDocument(
        chronicle_id=f"c_{npc}", npc_ref=npc, entries=tuple(entries), game_start_age=100
    )


REG = CanonicalRegistry(
    alias_to_npc={"орм": "blacksmith_orm", "люся": "maid_lusya", "борко": "guard_borko"},
    archetype_of={
        "blacksmith_orm": "blacksmith",
        "maid_lusya": "maid",
        "guard_borko": "guard",
    },
)


# ── 1. Явная самонаправленная связь — сохраняется ───────────────────────────


def test_explicit_self_reference_no_finding():
    """Явное self (object_id=RESOLVED, npc_id=subject) — consistency не порождает
    SELF_REFERENCE_UNRESOLVED Finding. Автор явно выбрал subject — допустимо."""
    e = _entry(
        "blacksmith_orm",
        eid="e1",
        object_id=EntityRef(ref_kind=EntityRefKind.RESOLVED, npc_id="blacksmith_orm"),
        payload={"summary": "Орм ненавидит себя", "target_hint": "Орм", "nature": "self", "valence": "negative"},
    )
    doc = _doc("blacksmith_orm", [e])
    report = ConsistencyService().check([doc], REG)
    self_ref = [f for f in report.findings if f.kind == K_SELF_REFERENCE_UNRESOLVED]
    assert self_ref == [], "явное self (object_id resolved) не должно порождать Finding; got %r" % self_ref


# ── 2. Ошибочная self-resolution — normalizer создаёт вопрос ─────────────────


def test_erroneous_self_resolution_caught(monkeypatch):
    """LLM положила target_hint=subject_name. Alias registry (name_forms) резолвит
    в subject → normalizer создаёт ClarificationQuestion (4 опции).

    Использует alias registry (name_forms: орм/орма/...), а не roster (display_name
    «Кузнец Орм») — roster exact-match не находит «Орм». monkeypatch alias registry
    чтобы тест не зависел от config/npc/individuals/orm.json."""
    from app.services.chronicle import decomposition_normalizer as mod
    monkeypatch.setattr(mod, "_REGISTRY_CACHE", {"орм": "blacksmith_orm"})
    items = _normalize(_rel("Орм", summary="Гильдия терпит Орма."), ROSTER, subject_id="blacksmith_orm")
    assert len(items) == 1
    q = items[0].question
    assert q is not None, "self-ref target_hint=subject должен породить вопрос"
    assert q.question_id == "self_reference_0", "got %r" % q.question_id
    assert ClarificationOption.LEAVE_WHITE_SPOT in q.options
    assert ClarificationOption.SELECT_EXISTING_NPC in q.options
    assert items[0].confidence <= 0.4, "confidence должно понижаться; got %r" % items[0].confidence


# ── 3. Неоднозначная цель — target_span=target_hint, не summary ─────────────


def test_ambiguous_target_span_is_hint_not_summary():
    """target_span в ClarificationQuestion для self-ref = target_hint (не summary).
    /resolve matcher ищет по name_hint=target_hint; placeholder EntityRef создаётся
    с name_hint=target_hint. summary доступен автору через author_text по ordinal."""
    items = _normalize(
        _rel("Орм", summary="Гильдия терпит Орма."),
        ROSTER,
        subject_id="blacksmith_orm",
    )
    q = items[0].question
    assert q is not None
    assert q.target_span == "Орм", "target_span must be target_hint, not summary; got %r" % q.target_span
    assert q.target_span != "Гильдия терпит Орма."


# ── 4. Обычное отношение между двумя NPC — нет вопроса ──────────────────────


def test_normal_relationship_no_question():
    """target_hint=другой NPC (Люся) при subject=blacksmith_orm — нормальная
    связь, normalizer не создаёт self-reference вопрос."""
    items = _normalize(_rel("Люся"), ROSTER, subject_id="blacksmith_orm")
    assert len(items) == 1
    q = items[0].question
    if q is not None:
        assert not q.question_id.startswith("self_reference"), (
            "normal cross-NPC relation must not trigger self-ref; got %r" % q.question_id
        )


# ── 5. Self-reference, пропущенная seeder — skip_detail ──────────────────────


def test_seeder_self_relation_skip_detail():
    """RELATIONSHIP с object_id=RESOLVED(subject) → seeder skip с skip_reason=
    'self_relation' и заполненным skip_detail (entry_id, subject, target, summary)."""
    e = _entry(
        "blacksmith_orm",
        eid="e1",
        object_id=EntityRef(ref_kind=EntityRefKind.RESOLVED, npc_id="blacksmith_orm"),
        payload={"summary": "Гильдия терпит Орма.", "target_hint": "Орм", "nature": "dependence", "valence": "positive"},
    )
    doc = _doc("blacksmith_orm", [e])
    seed_result, skip_reason, day, day_anomaly, skip_detail = _classify_seed_entry(e, doc, "RELATIONSHIP")
    assert seed_result == "SKIPPED"
    assert skip_reason == "self_relation"
    assert skip_detail is not None
    assert skip_detail["entry_id"] == "e1"
    assert skip_detail["subject_id"] == "blacksmith_orm"
    assert skip_detail["target_id"] == "blacksmith_orm"
    assert skip_detail["summary"] == "Гильдия терпит Орма."
    assert skip_detail["target_hint"] == "Орм"
    assert "reason" in skip_detail and skip_detail["reason"]


# ── 6. Отсутствие Finding для допустимой self-reference ─────────────────────


def test_no_finding_for_resolved_self_reference():
    """object_id=RESOLVED(subject) → не порождает SELF_REFERENCE_UNRESOLVED.
    Finding ловит только object_id=None + target_hint resolves to subject."""
    e_resolved = _entry(
        "blacksmith_orm",
        eid="e1",
        object_id=EntityRef(ref_kind=EntityRefKind.RESOLVED, npc_id="blacksmith_orm"),
        payload={"summary": "Орм знает себя", "target_hint": "Орм", "nature": "self", "valence": "neutral"},
    )
    doc = _doc("blacksmith_orm", [e_resolved])
    report = ConsistencyService().check([doc], REG)
    self_ref = [f for f in report.findings if f.kind == K_SELF_REFERENCE_UNRESOLVED]
    assert self_ref == [], "resolved self must not trigger Finding; got %r" % self_ref

    # Контроль: object_id=None + target_hint="Орм" → Finding создаётся
    e_unresolved = _entry(
        "blacksmith_orm",
        eid="e2",
        object_id=None,
        open_questions=(),
        payload={"summary": "Гильдия терпит Орма.", "target_hint": "Орм"},
    )
    doc2 = _doc("blacksmith_orm", [e_unresolved])
    report2 = ConsistencyService().check([doc2], REG)
    self_ref2 = [f for f in report2.findings if f.kind == K_SELF_REFERENCE_UNRESOLVED]
    assert len(self_ref2) == 1, "unresolved self-ref must trigger Finding; got %r" % report2.findings


# ── 7. Отсутствие автоматической миграции существующих записей ───────────────


def test_no_automatic_canon_migration():
    """Канон с записями Орма (object_id=null, target_hint="Орм") не мутируется
    при consistency check. ConsistencyService — read-only."""
    e1 = _entry(
        "blacksmith_orm",
        eid="guild",
        object_id=None,
        open_questions=(),
        payload={"summary": "Гильдия терпит Орма.", "target_hint": "Орм", "nature": "dependence", "valence": "positive"},
        ordinal=1501,
    )
    e2 = _entry(
        "blacksmith_orm",
        eid="govt",
        object_id=None,
        open_questions=(),
        payload={"summary": "Правительство терпит Орма.", "target_hint": "Орм", "nature": "dependence", "valence": "positive"},
        ordinal=1502,
    )
    e3 = _entry(
        "blacksmith_orm",
        eid="borko",
        object_id=None,
        open_questions=(),
        payload={"summary": "Борко не имеет власти над Ормом.", "target_hint": "Орм", "nature": "dependence", "valence": "negative"},
        ordinal=1700,
    )
    doc = _doc("blacksmith_orm", [e1, e2, e3])

    report = ConsistencyService().check([doc], REG)
    self_ref = [f for f in report.findings if f.kind == K_SELF_REFERENCE_UNRESOLVED]
    assert len(self_ref) == 3, "3 unresolved self-ref → 3 Findings; got %d" % len(self_ref)

    # Документ не мутирован (consistency_service — read-only)
    assert doc.entries[0].object_id is None, "entry must remain unresolved"
    assert doc.entries[0].payload["target_hint"] == "Орм", "payload must be untouched"