"""CCH-1 приёмочные тесты Character Chronicle (ADR-O-420).

Канон «запрет → тест»: запреты 1 (LLM_DRAFT≠канон), 2 (WhiteSpot guard),
3 (причина без происхождения), 4 (два времени) закреплены здесь.
T-CCH-01 — round-trip Люси через настоящий _convert_origin_events.
Запуск: cd backend ; python -m pytest tests/micro/test_chronicle_cch1.py -v
"""
from __future__ import annotations

import json

import pytest

from app.core.config import BASE_DIR
from app.domain.chronicle import (
    CauseKind,
    CauseRef,
    ChronicleDocument,
    ChronicleEntry,
    ClarificationOption,
    ClarificationQuestion,
    EntityRef,
    EntityRefKind,
    EntryKind,
    EntryProvenance,
    KnowledgeLink,
    WhiteSpot,
    make_entry_id,
)
from app.errors import ArchitecturalViolationError
from app.services.chronicle.chronicle_store import (
    ChronicleStore,
    document_from_dict,
    document_to_dict,
)
from app.services.chronicle.origin_projection import (
    chronicle_to_origin_events,
    origin_events_to_chronicle,
)
from app.services.chronicle.white_spot_registry import WhiteSpotRegistry
from app.services.npc.npc_loader import _convert_origin_events


def _entry(**kw):
    base = dict(
        entry_id="e",
        kind=EntryKind.EVENT,
        subject_id=EntityRef(ref_kind=EntityRefKind.RESOLVED, npc_id="a"),
        provenance=EntryProvenance.AUTHOR_AUTHORED,
    )
    base.update(kw)
    return ChronicleEntry(**base)


def _canon_doc():
    e1 = _entry(entry_id=make_entry_id("c1", 0, 0), kind=EntryKind.EVENT, historical_age=11)
    knower = {"ref_kind": "RESOLVED", "npc_id": "a"}
    e2 = _entry(
        entry_id=make_entry_id("c1", 0, 1),
        kind=EntryKind.KNOWLEDGE_LINK,
        payload={
            "event_ref": e1.entry_id,
            "knower": knower,
            "learned_age": 17,
            "channel": "TOLD",
            "certainty": 1.0,
        },
    )
    return ChronicleDocument(
        chronicle_id="c1", npc_ref="a", entries=(e1, e2), canonical=True, canonical_version=1
    )


def _doc_with_ws():
    subj = EntityRef(ref_kind=EntityRefKind.WHITE_SPOT, white_spot_id="ws_g", name_hint="стражник")
    e1 = _entry(
        entry_id="ev1",
        subject_id=subj,
        object_id=EntityRef(ref_kind=EntityRefKind.RESOLVED, npc_id="maid_lusya"),
        historical_age=14,
    )
    e2 = _entry(
        entry_id="ev2",
        kind=EntryKind.KNOWLEDGE_LINK,
        payload={
            "event_ref": "ev1",
            "knower": {"ref_kind": "WHITE_SPOT", "white_spot_id": "ws_g", "name_hint": "стражник"},
            "learned_age": 14,
            "channel": "WITNESSED",
            "certainty": 1.0,
        },
    )
    return ChronicleDocument(
        chronicle_id="c1",
        npc_ref="maid_lusya",
        entries=(e1, e2),
        white_spots=(WhiteSpot(white_spot_id="ws_g", label="стражник"),),
    )


# ── Запрет 4: два времени ────────────────────────────────────────────────────


def test_taboo4_two_times_invariant_fail_loud():
    event = _entry(entry_id="ev", historical_age=11)
    link = KnowledgeLink(
        event_ref="ev",
        knower_id=EntityRef(ref_kind=EntityRefKind.RESOLVED, npc_id="a"),
        learned_age=17,
    )
    KnowledgeLink.validate_against(event, link)
    bad = KnowledgeLink(event_ref="ev", knower_id=link.knower_id, learned_age=5)
    with pytest.raises(ValueError, match="Два времени"):
        KnowledgeLink.validate_against(event, bad)


# ── Запрет 3: причина без происхождения ──────────────────────────────────────


def test_taboo3_cause_requires_origin():
    CauseRef(cause_kind=CauseKind.UNKNOWN)
    with pytest.raises(ValueError):
        CauseRef(cause_kind=CauseKind.EVENT, origin_ref=None)
    with pytest.raises(ValueError):
        CauseRef(cause_kind=CauseKind.UNKNOWN, origin_ref="e1")


def test_entry_id_deterministic():
    assert make_entry_id("c", 0, 1) == make_entry_id("c", 0, 1)
    assert make_entry_id("c", 0, 1) != make_entry_id("c", 0, 2)


def test_domain_invariants_fail_loud():
    with pytest.raises(ValueError):
        EntityRef(ref_kind=EntityRefKind.RESOLVED)
    with pytest.raises(ValueError):
        EntityRef(ref_kind=EntityRefKind.WHITE_SPOT)
    with pytest.raises(ValueError):
        _entry(provenance=EntryProvenance.AUTHOR_CONFIRMED, confidence=0.9)
    with pytest.raises(ValueError):
        _entry(provenance=EntryProvenance.LLM_DRAFT)


# ── Store: WARA + гейты канона ───────────────────────────────────────────────


def test_wara_round_trip():
    d = document_to_dict(_canon_doc())
    assert document_to_dict(document_from_dict(d)) == d


def test_store_file_round_trip(tmp_path):
    store = ChronicleStore(canonical_dir=tmp_path / "chronicles", drafts_root=tmp_path)
    assert store.load_canonical("a") is None
    doc = _canon_doc()
    store.save_canonical(doc)
    back = store.load_canonical("a")
    assert back is not None
    assert document_to_dict(back) == document_to_dict(doc)


def test_taboo1_llm_draft_never_canonical(tmp_path):
    store = ChronicleStore(canonical_dir=tmp_path / "chronicles", drafts_root=tmp_path)
    doc = ChronicleDocument(
        chronicle_id="x",
        npc_ref="a",
        canonical=True,
        entries=(_entry(entry_id="k", provenance=EntryProvenance.LLM_DRAFT, confidence=0.5),),
    )
    with pytest.raises(ValueError, match="INV-LLM-NOT-SSOT"):
        store.save_canonical(doc)


def test_save_canonical_requires_flag(tmp_path):
    store = ChronicleStore(canonical_dir=tmp_path / "chronicles", drafts_root=tmp_path)
    doc = ChronicleDocument(chronicle_id="c2", npc_ref="a", canonical=False)
    with pytest.raises(ValueError, match="canonical"):
        store.save_canonical(doc)


def test_open_question_blocks_canon(tmp_path):
    q = ClarificationQuestion(
        question_id="q1", target_span="стражник", options=(ClarificationOption.LEAVE_WHITE_SPOT,)
    )
    doc = ChronicleDocument(
        chronicle_id="c4",
        npc_ref="a",
        canonical=True,
        entries=(_entry(entry_id="e", provenance=EntryProvenance.AUTHOR_CONFIRMED, open_questions=(q,)),),
    )
    store = ChronicleStore(canonical_dir=tmp_path / "chronicles", drafts_root=tmp_path)
    with pytest.raises(ValueError, match="без резолюции"):
        store.save_canonical(doc)


def test_dangling_white_spot_rejected(tmp_path):
    doc = ChronicleDocument(
        chronicle_id="c3",
        npc_ref="a",
        canonical=True,
        entries=(_entry(entry_id="e", object_id=EntityRef(ref_kind=EntityRefKind.WHITE_SPOT, white_spot_id="ws_missing")),),
    )
    store = ChronicleStore(canonical_dir=tmp_path / "chronicles", drafts_root=tmp_path)
    with pytest.raises(ValueError, match="dangling"):
        store.save_canonical(doc)


def test_schema_version_fail_loud():
    with pytest.raises(ValueError, match="schema_version"):
        document_from_dict({"schema_version": 2})


# ── Запрет 2: WhiteSpot guard ────────────────────────────────────────────────


def test_taboo2_resolution_guard_d_attack():
    with pytest.raises(ArchitecturalViolationError):
        WhiteSpotRegistry.resolve(_doc_with_ws(), "ws_g", "guard_x")


def test_resolution_relinks_refs_and_payload():
    d2 = WhiteSpotRegistry._resolve_impl(_doc_with_ws(), "ws_g", "guard_x")
    ws = WhiteSpotRegistry.find(d2, "ws_g")
    assert ws.resolution_state.value == "RESOLVED_AS_NPC"
    assert ws.resolution_ref == "guard_x"
    assert d2.entries[0].subject_id.npc_id == "guard_x"
    assert d2.entries[1].payload["knower"]["npc_id"] == "guard_x"
    assert d2.entries[1].payload["event_ref"] == "ev1"
    with pytest.raises(ValueError):
        WhiteSpotRegistry._resolve_impl(d2, "ws_g", "x")


def test_resolution_unknown_person_path():
    d3 = WhiteSpotRegistry._resolve_impl(_doc_with_ws(), "ws_g", None)
    assert WhiteSpotRegistry.find(d3, "ws_g").resolution_state.value == "RESOLVED_AS_UNKNOWN"
    assert d3.entries[0].subject_id.ref_kind.value == "UNKNOWN_PERSON"


# ── T-CCH-01: round-trip (живые данные Люси + синтетика) ────────────────────

_LUSYA = BASE_DIR / "config" / "npc" / "individuals" / "lusya.json"


@pytest.mark.skipif(not _LUSYA.is_file(), reason="эталонная Люся отсутствует")
def test_tcch01_lusya_origin_roundtrip():
    raw = json.loads(_LUSYA.read_text(encoding="utf-8-sig"))
    origins = raw["origin_events"]
    assert len(origins) == 5
    mem_a = _convert_origin_events(origins, "maid_lusya")
    doc = origin_events_to_chronicle("maid_lusya", origins)
    assert doc.schema_version == 1 and len(doc.entries) == 5
    mem_b = _convert_origin_events(chronicle_to_origin_events(doc), "maid_lusya")
    assert len(mem_a) == len(mem_b) == 5
    for a, b in zip(mem_a, mem_b):
        assert a == b


def test_tcch01_synthetic_roundtrip_deterministic():
    origins = [
        {"summary": "s1", "importance": 0.9, "tags": ["a"], "is_secret": True,
         "known_by": ["x"], "hidden_from": ["y"], "decay_rate": 0.001},
        {"summary": "s2", "importance": 0.5, "day": -700},
    ]
    doc = origin_events_to_chronicle("t", origins)
    assert doc == origin_events_to_chronicle("t", origins)
    mem_a = _convert_origin_events(origins, "t")
    mem_b = _convert_origin_events(chronicle_to_origin_events(doc), "t")
    for a, b in zip(mem_a, mem_b):
        assert a == b