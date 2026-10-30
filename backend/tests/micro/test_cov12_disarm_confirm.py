"""COV-12 (п.2): разоружить confirm + placeholder EntityRef.

Проверяет 5 инвариантов:
1. confirm пропускает LLM_DRAFT с open_questions (не подтверждает).
2. confirm пропускает LLM_DRAFT с confidence < 0.5.
3. confirm подтверждает LLM_DRAFT с confidence >= 0.5 и без open_questions.
4. decompose_fragment создаёт placeholder EntityRef(NEW_NPC, name_hint=target_hint)
   для RELATIONSHIP/EFFECT с non-match question (treat'ит /resolve).
5. resolve_question находит placeholder по name_hint==target_span и
   перелинковывает на EntityRef(WHITE_SPOT) — конец бага №3.

Чистый micro: decomposer и store подменяются, LLM/uvicorn не нужны.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.api import routes_chronicle
from app.api.routes_chronicle import confirm_author_entries, decompose_fragment, resolve_question
from app.domain.chronicle import (
    ChronicleDocument,
    ChronicleEntry,
    ClarificationOption,
    ClarificationQuestion,
    EntityRef,
    EntityRefKind,
    EntryKind,
    EntryProvenance,
    make_entry_id,
)
from app.services.chronicle.chronicle_store import ChronicleStore

_CAMPAIGN = "camp"
_NPC = "npc_test"


@pytest.fixture(autouse=True)
def _reset_store_global():
    saved = getattr(routes_chronicle, "_store", None)
    routes_chronicle._store = None
    yield
    routes_chronicle._store = saved


def _make_store(tmp_path: Path) -> ChronicleStore:
    store = ChronicleStore(tmp_path / "canon", tmp_path / "drafts")
    (tmp_path / "canon").mkdir(parents=True, exist_ok=True)
    (tmp_path / "drafts").mkdir(parents=True, exist_ok=True)
    routes_chronicle._store = store
    return store


def _save_draft(store: ChronicleStore, entries) -> None:
    doc = ChronicleDocument(
        chronicle_id=_NPC, npc_ref=_NPC, entries=tuple(entries), canonical=False
    )
    store.save_draft(doc, _CAMPAIGN)


def _make_entry(
    provenance=EntryProvenance.LLM_DRAFT,
    confidence=0.9,
    open_questions=(),
    object_id=None,
    ordinal=0,
) -> ChronicleEntry:
    return ChronicleEntry(
        entry_id=make_entry_id(_NPC, 0, ordinal),
        kind=EntryKind.EVENT,
        subject_id=EntityRef(ref_kind=EntityRefKind.RESOLVED, npc_id=_NPC),
        object_id=object_id,
        historical_age=20,
        payload={"summary": f"entry {ordinal}"},
        provenance=provenance,
        confidence=confidence,
        open_questions=open_questions,
        ordinal=ordinal,
    )


def _load_doc(store: ChronicleStore) -> ChronicleDocument:
    doc = store.load_draft(_CAMPAIGN, _NPC)
    assert doc is not None
    return doc


# ── 2a: разоружить confirm ──────────────────────────────────────────────


def test_confirm_skips_entries_with_open_questions(tmp_path):
    """LLM_DRAFT с open_questions не подтверждается."""
    store = _make_store(tmp_path)
    q = ClarificationQuestion(
        question_id="roster_mismatch_1",
        target_span="Торнин",
        options=(
            ClarificationOption.SELECT_EXISTING_NPC,
            ClarificationOption.CREATE_NEW_NPC,
            ClarificationOption.UNKNOWN_PERSON,
            ClarificationOption.LEAVE_WHITE_SPOT,
        ),
    )
    _save_draft(store, [_make_entry(open_questions=(q,), ordinal=0)])

    resp = asyncio.run(confirm_author_entries(_CAMPAIGN, _NPC))
    doc = _load_doc(store)
    assert resp["confirmed"] == 0
    assert resp["skipped_open_questions"] == 1
    assert doc.entries[0].provenance is EntryProvenance.LLM_DRAFT


def test_confirm_skips_low_confidence(tmp_path):
    """LLM_DRAFT с confidence < 0.5 не подтверждается."""
    store = _make_store(tmp_path)
    _save_draft(store, [_make_entry(confidence=0.4, ordinal=0)])

    resp = asyncio.run(confirm_author_entries(_CAMPAIGN, _NPC))
    doc = _load_doc(store)
    assert resp["confirmed"] == 0
    assert resp["skipped_low_confidence"] == 1
    assert doc.entries[0].provenance is EntryProvenance.LLM_DRAFT


def test_confirm_accepts_high_confidence_no_questions(tmp_path):
    """LLM_DRAFT с confidence >= 0.5 и без open_questions — подтверждается."""
    store = _make_store(tmp_path)
    _save_draft(store, [_make_entry(confidence=0.6, ordinal=0)])

    resp = asyncio.run(confirm_author_entries(_CAMPAIGN, _NPC))
    doc = _load_doc(store)
    assert resp["confirmed"] == 1
    assert resp["skipped_open_questions"] == 0
    assert resp["skipped_low_confidence"] == 0
    assert doc.entries[0].provenance is EntryProvenance.AUTHOR_CONFIRMED


# ── 2b: placeholder EntityRef + resolve flow ────────────────────────────


def _install_decomposer(monkeypatch: pytest.MonkeyPatch, question=None) -> None:
    """question=None → exact match (no question); question=ClarificationQuestion → non-match."""
    class _FakeDecomposer:
        async def decompose(self, npc_id: str, fragment_ord: int, fragment: str):
            payload = {
                "summary": "хороший друг",
                "target_hint": "Торнин",
                "nature": "дружба",
                "valence": "positive",
            }
            item = SimpleNamespace(
                kind=EntryKind.RELATIONSHIP,
                draft_payload=payload,
                confidence=0.9 if question is None else 0.4,
                question=question,
                needs_confirmation=question is not None,
            )
            return SimpleNamespace(
                ok=True, items=[item], age_anchors=[], error=None, raw_response=""
            )

    monkeypatch.setattr(routes_chronicle, "_get_decomposer", lambda: _FakeDecomposer())


async def _decompose(fragment_ord: int) -> dict:
    return await decompose_fragment(
        _CAMPAIGN,
        _NPC,
        SimpleNamespace(
            campaign_id=_CAMPAIGN,
            npc_id=_NPC,
            fragment_ord=fragment_ord,
            fragment="Орм и Торнин — друзья.",
        ),
    )


def test_decompose_creates_placeholder_for_non_match(tmp_path, monkeypatch):
    """decompose_fragment создаёт NEW_NPC placeholder с name_hint=target_hint
    при non-match question (без него /resolve не найдёт entry для перелинковки)."""
    _make_store(tmp_path)
    q = ClarificationQuestion(
        question_id="roster_mismatch_1",
        target_span="Торнин",
        options=(
            ClarificationOption.SELECT_EXISTING_NPC,
            ClarificationOption.CREATE_NEW_NPC,
            ClarificationOption.UNKNOWN_PERSON,
            ClarificationOption.LEAVE_WHITE_SPOT,
        ),
    )
    _install_decomposer(monkeypatch, question=q)

    asyncio.run(_decompose(0))
    store = routes_chronicle._get_store()
    doc = _load_doc(store)

    assert len(doc.entries) == 1
    entry = doc.entries[0]
    # Проверка placeholder: NEW_NPC с name_hint="Торнин"
    assert entry.object_id is not None
    assert entry.object_id.ref_kind is EntityRefKind.NEW_NPC
    assert entry.object_id.name_hint == "Торнин"


def test_resolve_question_relinks_placeholder_to_white_spot(tmp_path, monkeypatch):
    """Полный flow: decompose (non-match) → resolve LEAVE_WHITE_SPOT →
    entry.object_id становится EntityRef(WHITE_SPOT, white_spot_id)."""
    _make_store(tmp_path)
    q = ClarificationQuestion(
        question_id="roster_mismatch_1",
        target_span="Торнин",
        options=(
            ClarificationOption.SELECT_EXISTING_NPC,
            ClarificationOption.CREATE_NEW_NPC,
            ClarificationOption.UNKNOWN_PERSON,
            ClarificationOption.LEAVE_WHITE_SPOT,
        ),
    )
    _install_decomposer(monkeypatch, question=q)
    asyncio.run(_decompose(0))

    # Resolve с LEAVE_WHITE_SPOT
    resp = asyncio.run(resolve_question(
        _CAMPAIGN,
        _NPC,
        SimpleNamespace(
            campaign_id=_CAMPAIGN,
            npc_id=_NPC,
            question_id="roster_mismatch_1",
            selected_option="LEAVE_WHITE_SPOT",
            selected_value=None,
        ),
    ))
    assert resp["status"] == "OK"

    store = routes_chronicle._get_store()
    doc = _load_doc(store)
    entry = doc.entries[0]

    # Запись теперь ссылается на white spot
    assert entry.object_id is not None
    assert entry.object_id.ref_kind is EntityRefKind.WHITE_SPOT
    assert entry.object_id.white_spot_id == "roster_mismatch_1"

    # White spot существует в doc.white_spots
    assert any(ws.white_spot_id == "roster_mismatch_1" for ws in doc.white_spots)

    # Question убран из open_questions
    assert len(entry.open_questions) == 0