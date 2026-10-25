"""
S369: WhiteSpot creation on /resolve LEAVE_WHITE_SPOT + EntityRef perelink.

Контракт (FR-3.1 + ADR-O-420): при резолюции вопроса авторским выбором
/resolve эндпоинт обязан:
1. Создать WhiteSpot в doc.white_spots (для LEAVE_WHITE_SPOT) — idempotent
2. Перелинковать EntityRef записи:
   - LEAVE_WHITE_SPOT → WHITE_SPOT с white_spot_id=question_id
   - SELECT_EXISTING_NPC → RESOLVED с npc_id=selected_value
   - UNKNOWN_PERSON → UNKNOWN_PERSON с name_hint=target_span
   - CREATE_NEW_NPC → UNKNOWN_PERSON (placeholder)
3. Убрать вопрос из open_questions
4. Сохранить audit-запись в _resolved_questions

Регрессия S369: до фикса doc.white_spots всегда []; EntityRef не перелинковывался.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app.api import routes_chronicle
from app.api.routes_chronicle import ResolveRequest, resolve_question
from app.domain.chronicle import (
    SCHEMA_VERSION,
    ChronicleDocument,
    ChronicleEntry,
    ClarificationOption,
    ClarificationQuestion,
    EntityRef,
    EntityRefKind,
    EntryKind,
    EntryProvenance,
    WhiteSpot,
    WhiteSpotResolutionState,
    make_entry_id,
)
from app.services.chronicle.chronicle_store import ChronicleStore


# ── Fixture: сброс глобального store между тестами ──────────────────────────

@pytest.fixture(autouse=True)
def _reset_store_global():
    """Изоляция тестов: сброс routes_chronicle._store до и после."""
    saved = getattr(routes_chronicle, "_store", None)
    routes_chronicle._store = None
    yield
    routes_chronicle._store = saved


# ── Хелперы ─────────────────────────────────────────────────────────────────

def _make_store(tmp_path: Path) -> ChronicleStore:
    canonical_dir = tmp_path / "canon"
    drafts_root = tmp_path / "drafts"
    canonical_dir.mkdir(parents=True, exist_ok=True)
    drafts_root.mkdir(parents=True, exist_ok=True)
    return ChronicleStore(canonical_dir, drafts_root)


def _make_doc_with_question(
    npc_id: str = "test_npc",
    question_id: str = "q1",
    target_span: str = "старый пьянчужка",
    ref_kind: EntityRefKind = EntityRefKind.UNKNOWN_PERSON,
    object_ref: EntityRef | None = None,
) -> ChronicleDocument:
    """Драфт с одним EVENT-вопросом про subject_id.name_hint=target_span.
    Сигнатуры по реальному домену (S369 археология): entry_id через make_entry_id,
    без chronicle_id/fragment_ord в конструкторе ChronicleEntry."""
    question = ClarificationQuestion(
        question_id=question_id,
        target_span=target_span,
        options=(
            ClarificationOption.SELECT_EXISTING_NPC,
            ClarificationOption.CREATE_NEW_NPC,
            ClarificationOption.UNKNOWN_PERSON,
            ClarificationOption.LEAVE_WHITE_SPOT,
        ),
    )
    entry = ChronicleEntry(
        entry_id=make_entry_id(npc_id, 0, 0),
        kind=EntryKind.EVENT,
        subject_id=EntityRef(ref_kind=ref_kind, name_hint=target_span),
        object_id=object_ref,
        historical_age=20,
        payload={},
        provenance=EntryProvenance.AUTHOR_AUTHORED,
        open_questions=(question,),
    )
    return ChronicleDocument(
        chronicle_id=npc_id,
        npc_ref=npc_id,
        author_text="фрагмент",
        entries=(entry,),
        white_spots=(),
        schema_version=SCHEMA_VERSION,
    )


async def _resolve(store: ChronicleStore, req: ResolveRequest) -> dict:
    """Вызывает эндпоинт напрямую через asyncio; monkeypatch глобального store."""
    routes_chronicle._store = store
    return await resolve_question(req.campaign_id, req.npc_id, req)


# ── Тесты ────────────────────────────────────────────────────────────────────

def test_s369_leave_white_spot_creates_white_spot_and_relinks(tmp_path):
    """LEAVE_WHITE_SPOT: WhiteSpot создан, EntityRef перелинкован на WHITE_SPOT."""
    store = _make_store(tmp_path)
    doc = _make_doc_with_question()
    store.save_draft(doc, "camp")

    req = ResolveRequest(
        campaign_id="camp",
        npc_id="test_npc",
        question_id="q1",
        selected_option="LEAVE_WHITE_SPOT",
        selected_value=None,
    )
    result = asyncio.run(_resolve(store, req))

    assert result["status"] == "OK"
    assert result["white_spots_count"] == 1
    assert result["selected_option"] == "LEAVE_WHITE_SPOT"

    saved = store.load_draft("camp", "test_npc")
    assert len(saved.white_spots) == 1
    ws = saved.white_spots[0]
    assert ws.white_spot_id == "q1"
    assert ws.label == "старый пьянчужка"
    assert ws.resolution_state is WhiteSpotResolutionState.OPEN
    assert ws.created_from_entry == make_entry_id("test_npc", 0, 0)

    # EntityRef перелинкован на WHITE_SPOT
    e = saved.entries[0]
    assert e.subject_id.ref_kind is EntityRefKind.WHITE_SPOT
    assert e.subject_id.white_spot_id == "q1"
    assert e.subject_id.name_hint == "старый пьянчужка"

    # Вопрос убран из open_questions
    assert len(e.open_questions) == 0

    # Audit-запись сохранена
    assert len(e.payload["_resolved_questions"]) == 1
    assert e.payload["_resolved_questions"][0]["selected_option"] == "LEAVE_WHITE_SPOT"


def test_s369_leave_white_spot_idempotent(tmp_path):
    """Повторный LEAVE_WHITE_SPOT с тем же question_id не дублирует WhiteSpot."""
    store = _make_store(tmp_path)
    doc = _make_doc_with_question()
    store.save_draft(doc, "camp")

    req = ResolveRequest(
        campaign_id="camp", npc_id="test_npc", question_id="q1",
        selected_option="LEAVE_WHITE_SPOT", selected_value=None,
    )
    asyncio.run(_resolve(store, req))
    # Второй вызов — вопрос уже убран, должен дать 404 (не дублировать)
    with pytest.raises(Exception):  # HTTPException 404
        asyncio.run(_resolve(store, req))

    saved = store.load_draft("camp", "test_npc")
    assert len(saved.white_spots) == 1  # не 2


def test_s369_select_existing_npc_relinks_to_resolved(tmp_path):
    """SELECT_EXISTING_NPC: EntityRef перелинкован на RESOLVED с npc_id."""
    store = _make_store(tmp_path)
    doc = _make_doc_with_question()
    store.save_draft(doc, "camp")

    req = ResolveRequest(
        campaign_id="camp", npc_id="test_npc", question_id="q1",
        selected_option="SELECT_EXISTING_NPC", selected_value="maid_lusya",
    )
    result = asyncio.run(_resolve(store, req))
    assert result["status"] == "OK"
    assert result["white_spots_count"] == 0  # WhiteSpot не создаётся

    saved = store.load_draft("camp", "test_npc")
    e = saved.entries[0]
    assert e.subject_id.ref_kind is EntityRefKind.RESOLVED
    assert e.subject_id.npc_id == "maid_lusya"


def test_s369_select_existing_npc_requires_value(tmp_path):
    """SELECT_EXISTING_NPC без selected_value → 422 (контрактное нарушение)."""
    store = _make_store(tmp_path)
    doc = _make_doc_with_question()
    store.save_draft(doc, "camp")

    req = ResolveRequest(
        campaign_id="camp", npc_id="test_npc", question_id="q1",
        selected_option="SELECT_EXISTING_NPC", selected_value=None,
    )
    with pytest.raises(Exception) as exc_info:
        asyncio.run(_resolve(store, req))
    # FastAPI HTTPException → 422
    assert "422" in str(exc_info.value) or "SELECT_EXISTING_NPC" in str(exc_info.value)


def test_s369_unknown_person_relinks(tmp_path):
    """UNKNOWN_PERSON: EntityRef перелинкован на UNKNOWN_PERSON."""
    store = _make_store(tmp_path)
    doc = _make_doc_with_question()
    store.save_draft(doc, "camp")

    req = ResolveRequest(
        campaign_id="camp", npc_id="test_npc", question_id="q1",
        selected_option="UNKNOWN_PERSON", selected_value=None,
    )
    asyncio.run(_resolve(store, req))

    saved = store.load_draft("camp", "test_npc")
    e = saved.entries[0]
    assert e.subject_id.ref_kind is EntityRefKind.UNKNOWN_PERSON
    assert e.subject_id.name_hint == "старый пьянчужка"


def test_s369_create_new_npc_relinks_to_unknown_person_placeholder(tmp_path):
    """CREATE_NEW_NPC: placeholder — перелинковка на UNKNOWN_PERSON (warning)."""
    store = _make_store(tmp_path)
    doc = _make_doc_with_question()
    store.save_draft(doc, "camp")

    req = ResolveRequest(
        campaign_id="camp", npc_id="test_npc", question_id="q1",
        selected_option="CREATE_NEW_NPC", selected_value="новый_старец",
    )
    asyncio.run(_resolve(store, req))

    saved = store.load_draft("camp", "test_npc")
    e = saved.entries[0]
    assert e.subject_id.ref_kind is EntityRefKind.UNKNOWN_PERSON
    assert e.subject_id.name_hint == "новый_старец"


def test_s369_unknown_option_returns_422(tmp_path):
    """Неизвестная опция → 422 (fail-loud)."""
    store = _make_store(tmp_path)
    doc = _make_doc_with_question()
    store.save_draft(doc, "camp")

    req = ResolveRequest(
        campaign_id="camp", npc_id="test_npc", question_id="q1",
        selected_option="INVALID_OPTION", selected_value=None,
    )
    with pytest.raises(Exception):
        asyncio.run(_resolve(store, req))


def test_s369_question_not_found_returns_404(tmp_path):
    """Вопрос не найден в open_questions → 404."""
    store = _make_store(tmp_path)
    doc = _make_doc_with_question()
    store.save_draft(doc, "camp")

    req = ResolveRequest(
        campaign_id="camp", npc_id="test_npc", question_id="nonexistent_q",
        selected_option="LEAVE_WHITE_SPOT", selected_value=None,
    )
    with pytest.raises(Exception):
        asyncio.run(_resolve(store, req))


def test_s369_object_id_relink_when_subject_does_not_match(tmp_path):
    """Если subject_id.name_hint не совпадает, но object_id совпадает —
    перелинковать object_id."""
    store = _make_store(tmp_path)
    # doc с subject_id, у которого name_hint != target_span, и object_id, у которого == target_span
    question = ClarificationQuestion(
        question_id="q1",
        target_span="жертва",
        options=(
            ClarificationOption.SELECT_EXISTING_NPC,
            ClarificationOption.LEAVE_WHITE_SPOT,
        ),
    )
    entry = ChronicleEntry(
        entry_id=make_entry_id("test_npc", 0, 0),
        kind=EntryKind.EVENT,
        subject_id=EntityRef(ref_kind=EntityRefKind.RESOLVED, npc_id="actor_id", name_hint="агрессор"),
        object_id=EntityRef(ref_kind=EntityRefKind.UNKNOWN_PERSON, name_hint="жертва"),
        historical_age=20, payload={},
        provenance=EntryProvenance.AUTHOR_AUTHORED,
        open_questions=(question,),
    )
    doc = ChronicleDocument(
        chronicle_id="test_npc", npc_ref="test_npc", author_text="фрагмент",
        entries=(entry,), white_spots=(), schema_version=SCHEMA_VERSION,
    )
    store.save_draft(doc, "camp")

    req = ResolveRequest(
        campaign_id="camp", npc_id="test_npc", question_id="q1",
        selected_option="LEAVE_WHITE_SPOT", selected_value=None,
    )
    asyncio.run(_resolve(store, req))

    saved = store.load_draft("camp", "test_npc")
    e = saved.entries[0]
    # subject_id не тронут (name_hint != target_span)
    assert e.subject_id.ref_kind is EntityRefKind.RESOLVED
    assert e.subject_id.npc_id == "actor_id"
    # object_id перелинкован
    assert e.object_id.ref_kind is EntityRefKind.WHITE_SPOT
    assert e.object_id.white_spot_id == "q1"
    assert len(saved.white_spots) == 1