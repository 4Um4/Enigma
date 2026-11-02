"""
Тесты BiographyAdapter (USL-1.2, ADR-O-437).

Проверяют:
    - mapping EntryKind → USLPredicate для всех 10 EntryKind;
    - проекция EntityRef → USLEntityRef (4 вида);
    - извлечение времени из historical_age/year + payload.day/duration_years;
    - реальный канон blacksmith_orm.json проецируется без ошибок;
    - детерминизм: повторный прогон = идентичный список USLUnit;
    - source_span обязателен (USL-5);
    - PLAYER_ASSERTION ≠ AUTHOR_CANON в проекции (USL-2);
    - адаптер не падает на пустом payload.
"""
import json
from pathlib import Path

import pytest

from app.domain.chronicle import (
    ChronicleDocument,
    ChronicleEntry,
    EntityRef,
    EntityRefKind,
    EntryKind,
    EntryProvenance,
)
from app.domain.usl import (
    USLAnchorKind,
    USLEntityRef,
    USLSourceKind,
    USLTimeKind,
    USLUnit,
)
from app.services.chronicle.biography_adapter import (
    biography_to_usl,
    entry_kind_to_usl_predicate,
    entry_to_usl_unit,
)


# ── 1. Mapping table ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("entry_kind,expected", [
    (EntryKind.EVENT, "asserts"),
    (EntryKind.RELATIONSHIP, "asserts"),
    (EntryKind.LOCATION, "lives_at"),
    (EntryKind.EFFECT, "has_effect"),
    (EntryKind.BELIEF_SEED, "believes"),
    (EntryKind.KNOWLEDGE_LINK, "knows"),
    (EntryKind.TRAIT_SEED, "has_trait"),
    (EntryKind.PORTRET, "has_trait"),
    (EntryKind.OBSERVATION, "asserts"),
    (EntryKind.DESIRE_SEED, "desires"),
])
def test_entry_kind_to_usl_predicate_mapping(entry_kind, expected):
    """Все 10 EntryKind маппируются в USLPredicate (conservative mapping)."""
    pred = entry_kind_to_usl_predicate(entry_kind)
    assert pred is not None
    assert pred.value == expected


# ── 2. EntityRef проекция ─────────────────────────────────────────────────────

def test_entityref_resolved_to_usl():
    """RESOLVED → USLEntityRef(kind='resolved', ref_id=npc_id)."""
    from app.services.chronicle.biography_adapter import _entityref_to_usl
    ref = EntityRef(ref_kind=EntityRefKind.RESOLVED, npc_id="blacksmith_orm")
    usl = _entityref_to_usl(ref)
    assert usl.kind == "resolved"
    assert usl.ref_id == "blacksmith_orm"


def test_entityref_white_spot_to_usl():
    from app.services.chronicle.biography_adapter import _entityref_to_usl
    ref = EntityRef(ref_kind=EntityRefKind.WHITE_SPOT, white_spot_id="ws_001")
    usl = _entityref_to_usl(ref)
    assert usl.kind == "white_spot"
    assert usl.ref_id == "ws_001"


def test_entityref_unknown_person_to_usl():
    from app.services.chronicle.biography_adapter import _entityref_to_usl
    ref = EntityRef(ref_kind=EntityRefKind.UNKNOWN_PERSON, name_hint="стражник")
    usl = _entityref_to_usl(ref)
    assert usl.kind == "unknown_person"
    assert usl.name_hint == "стражник"


def test_entityref_none_returns_none():
    from app.services.chronicle.biography_adapter import _entityref_to_usl
    assert _entityref_to_usl(None) is None


# ── 3. Provenance → USLSourceKind (USL-2: источник ≠ истина) ───────────────

def test_provenance_author_confirmed_to_author_canon():
    from app.services.chronicle.biography_adapter import _provenance_to_usl_source
    assert _provenance_to_usl_source(EntryProvenance.AUTHOR_CONFIRMED) is USLSourceKind.AUTHOR_CANON
    assert _provenance_to_usl_source(EntryProvenance.AUTHOR_AUTHORED) is USLSourceKind.AUTHOR_CANON


def test_provenance_llm_draft_to_hypothesis():
    """LLM_DRAFT → AUTHOR_HYPOTHESIS (не AUTHOR_CANON — инвариант USL-2)."""
    from app.services.chronicle.biography_adapter import _provenance_to_usl_source
    assert _provenance_to_usl_source(EntryProvenance.LLM_DRAFT) is USLSourceKind.AUTHOR_HYPOTHESIS


# ── 4. Время из структурированных полей ────────────────────────────────────────

def test_temporal_from_historical_age():
    from app.services.chronicle.biography_adapter import _extract_temporal
    entry = ChronicleEntry(
        entry_id="test1",
        kind=EntryKind.EVENT,
        subject_id=EntityRef(ref_kind=EntityRefKind.RESOLVED, npc_id="orm"),
        historical_age=76,
        provenance=EntryProvenance.AUTHOR_CONFIRMED,
    )
    temporal = _extract_temporal(entry)
    assert len(temporal) == 1
    assert temporal[0].kind is USLTimeKind.POINT
    assert temporal[0].anchor is USLAnchorKind.AGE_N
    assert temporal[0].value == 76


def test_temporal_from_duration_years_payload():
    from app.services.chronicle.biography_adapter import _extract_temporal
    entry = ChronicleEntry(
        entry_id="test2",
        kind=EntryKind.EVENT,
        subject_id=EntityRef(ref_kind=EntityRefKind.RESOLVED, npc_id="orm"),
        payload={"summary": "работал 57 лет", "duration_years": 57},
        provenance=EntryProvenance.AUTHOR_CONFIRMED,
    )
    temporal = _extract_temporal(entry)
    duration = [t for t in temporal if t.kind is USLTimeKind.DURATION]
    assert len(duration) == 1
    assert duration[0].value == 57


def test_temporal_empty_when_no_fields():
    """§ENIGMA-003: отсутствие данных = честный empty, не UNKNOWN-галлюцинация."""
    from app.services.chronicle.biography_adapter import _extract_temporal
    entry = ChronicleEntry(
        entry_id="test3",
        kind=EntryKind.TRAIT_SEED,
        subject_id=EntityRef(ref_kind=EntityRefKind.RESOLVED, npc_id="orm"),
        payload={"trait": "занятость работой"},
        provenance=EntryProvenance.AUTHOR_CONFIRMED,
    )
    assert _extract_temporal(entry) == ()


# ── 5. Реальный канон blacksmith_orm.json ─────────────────────────────────────

def _load_orm_doc() -> ChronicleDocument:
    """Загружает реальный канон orm.json как ChronicleDocument."""
    canon_path = Path("config/npc/chronicles/blacksmith_orm.json")
    if not canon_path.exists():
        # fallback для запуска из backend/
        canon_path = Path("../config/npc/chronicles/blacksmith_orm.json")
    if not canon_path.exists():
        pytest.skip("blacksmith_orm.json не найден — должен запускаться из корня проекта")
    raw = canon_path.read_text(encoding="utf-8")
    data = json.loads(raw)
    # Конвертируем JSON dict в ChronicleDocument (через конструктор, не from_legacy)
    from app.domain.chronicle import ChronicleEntry, EntityRef
    entries = []
    for e in data.get("entries", []):
        subj = e["subject_id"]
        subject_ref = EntityRef(
            ref_kind=EntityRefKind(subj["ref_kind"]),
            npc_id=subj.get("npc_id"),
            white_spot_id=subj.get("white_spot_id"),
            name_hint=subj.get("name_hint", ""),
        )
        obj_ref = None
        if e.get("object_id"):
            o = e["object_id"]
            obj_ref = EntityRef(
                ref_kind=EntityRefKind(o["ref_kind"]),
                npc_id=o.get("npc_id"),
                white_spot_id=o.get("white_spot_id"),
                name_hint=o.get("name_hint", ""),
            )
        entries.append(ChronicleEntry(
            entry_id=e["entry_id"],
            kind=EntryKind(e["kind"]),
            subject_id=subject_ref,
            object_id=obj_ref,
            payload=e.get("payload", {}),
            provenance=EntryProvenance(e.get("provenance", "AUTHOR_CONFIRMED")),
            confidence=e.get("confidence"),
            ordinal=e.get("ordinal", 0),
            historical_age=e.get("historical_age"),
            historical_year=e.get("historical_year"),
        ))
    return ChronicleDocument(
        chronicle_id=data["chronicle_id"],
        npc_ref=data["npc_ref"],
        author_text=data.get("author_text", ""),
        entries=tuple(entries),
        canonical=data.get("canonical", True),
    )


def test_orm_canon_projects_without_errors():
    """Реальный канон blacksmith_orm.json проецируется без исключений."""
    doc = _load_orm_doc()
    units = biography_to_usl(doc)
    assert len(units) == len(doc.entries)
    # Все USLUnit имеют unit_id
    assert all(u.unit_id for u in units)
    # Все имеют source_span (USL-5)
    assert all(u.text_span for u in units)
    # Все имеют хотя бы одно событие
    assert all(len(u.events) >= 1 for u in units)


def test_orm_canon_has_expected_kinds():
    """В orm.json есть все ключевые EntryKind (EFFECT/EVENT/RELATIONSHIP/TRAIT_SEED)."""
    doc = _load_orm_doc()
    kinds_present = {e.kind for e in doc.entries}
    assert EntryKind.EFFECT in kinds_present
    assert EntryKind.EVENT in kinds_present
    assert EntryKind.RELATIONSHIP in kinds_present
    assert EntryKind.TRAIT_SEED in kinds_present


def test_orm_canon_units_are_frozen():
    """Все USLUnit из реального канона — frozen."""
    doc = _load_orm_doc()
    units = biography_to_usl(doc)
    import dataclasses
    for u in units:
        with pytest.raises(dataclasses.FrozenInstanceError):
            u.text_span = "mutated"  # type: ignore


# ── 6. Детерминизм (USL-6) ───────────────────────────────────────────────────

def test_biography_to_usl_is_deterministic():
    """USL-6: повторный прогон того же doc = идентичный список USLUnit."""
    doc = _load_orm_doc()
    units1 = biography_to_usl(doc)
    units2 = biography_to_usl(doc)
    assert len(units1) == len(units2)
    for u1, u2 in zip(units1, units2):
        assert u1.unit_id == u2.unit_id
        assert u1.text_span == u2.text_span
        assert u1.origin_id == u2.origin_id


def test_unit_id_stable_across_recomputations():
    """unit_id стабилен — одинаковый entry → одинаковый id всегда."""
    doc = _load_orm_doc()
    first_unit = biography_to_usl(doc)[0]
    same_unit_again = biography_to_usl(doc)[0]
    assert first_unit.unit_id == same_unit_again.unit_id


# ── 7. Source kind в проекции ────────────────────────────────────────────────

def test_orm_canon_units_have_author_canon_source():
    """Все entries orm.json имеют provenance=AUTHOR_CONFIRMED → USLSourceKind.AUTHOR_CANON."""
    doc = _load_orm_doc()
    units = biography_to_usl(doc)
    for u in units:
        assert u.source_ref.source_kind is USLSourceKind.AUTHOR_CANON


def test_player_assertion_never_in_biography():
    """PLAYER_ASSERTION не может появиться в проекции биографии (USL-2).
    BiographyAdapter проецирует только AUTHOR_* → AUTHOR_CANON.
    PLAYER_ASSERTION — это для InteractiveLanguageAdapter (USL-1.3).
    """
    doc = _load_orm_doc()
    units = biography_to_usl(doc)
    for u in units:
        assert u.source_ref.source_kind is not USLSourceKind.PLAYER_ASSERTION


# ── 8. Edge cases ─────────────────────────────────────────────────────────────

def test_empty_payload_does_not_crash():
    """Адаптер не падает на пустом payload (§13: Real Data First — но defensive)."""
    entry = ChronicleEntry(
        entry_id="test_empty",
        kind=EntryKind.TRAIT_SEED,
        subject_id=EntityRef(ref_kind=EntityRefKind.RESOLVED, npc_id="orm"),
        payload={},
        provenance=EntryProvenance.AUTHOR_CONFIRMED,
    )
    doc = ChronicleDocument(chronicle_id="test", npc_ref="orm", entries=(entry,))
    units = biography_to_usl(doc)
    assert len(units) == 1
    # text_span fallback на entry_id (USL-5: span обязателен)
    assert units[0].text_span == "test_empty"


def test_relationship_creates_uslrelation():
    """RELATIONSHIP entry → USLEvent + USLRelation (relation_type=nature, valence)."""
    entry = ChronicleEntry(
        entry_id="rel1",
        kind=EntryKind.RELATIONSHIP,
        subject_id=EntityRef(ref_kind=EntityRefKind.RESOLVED, npc_id="orm"),
        object_id=EntityRef(ref_kind=EntityRefKind.RESOLVED, npc_id="tornin"),
        payload={
            "summary": "напоминает старого друга",
            "target_hint": "Торнин",
            "nature": "идеализация",
            "valence": "positive",
        },
        provenance=EntryProvenance.AUTHOR_CONFIRMED,
    )
    doc = ChronicleDocument(chronicle_id="test", npc_ref="orm", entries=(entry,))
    units = biography_to_usl(doc)
    assert len(units[0].relations) == 1
    rel = units[0].relations[0]
    assert rel.relation_type == "идеализация"
    assert rel.valence == "positive"
    assert rel.subject == "orm"
    assert rel.object == "tornin"


# ── 9. origin_id трассировка к entry_id ───────────────────────────────────────

def test_origin_id_points_to_entry_id():
    """USLUnit.origin_id == ChronicleEntry.entry_id (трассировка, не дублирование)."""
    doc = _load_orm_doc()
    units = biography_to_usl(doc)
    for u, e in zip(units, doc.entries):
        assert u.origin_id == e.entry_id
        assert u.origin_kind == "chronicle_entry"