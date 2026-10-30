"""COV-12 (п.0): семантика повторного decompose фрагмента.

Проверяет 4 инварианта merge в decompose_fragment:
1. Сокращение items (4→3) удаляет осиротевшую LLM_DRAFT-запись.
2. Авторская запись (AUTHOR_CONFIRMED) в слоте (F,idx) переживает повторный
   разбор; свежий черновик получает salted id; дубликатов entry_id нет.
3. LLM_DRAFT-записи ДРУГИХ фрагментов не затрагиваются.
4. >=100 items -> NOT_DECOMPOSED, draft не мутирует.

Чистый micro: decomposer и store подменяются, LLM/uvicorn не нужны.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.api import routes_chronicle
from app.api.routes_chronicle import decompose_fragment
from app.domain.chronicle import (
    ChronicleDocument,
    ChronicleEntry,
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


def _fake_result(n_items: int) -> SimpleNamespace:
    items = [
        SimpleNamespace(
            kind=EntryKind.EVENT,
            draft_payload={"summary": f"item {i}"},
            confidence=0.9,
            question=None,
            needs_confirmation=False,  # routes_chronicle.py:379 читает этот атрибут
        )
        for i in range(n_items)
    ]
    return SimpleNamespace(
        ok=True, items=items, age_anchors=[], error=None, raw_response=""
    )


def _install_decomposer(monkeypatch: pytest.MonkeyPatch, n_items: int) -> None:
    class _FakeDecomposer:
        async def decompose(self, npc_id: str, fragment_ord: int, fragment: str):
            return _fake_result(n_items)

    monkeypatch.setattr(
        routes_chronicle, "_get_decomposer", lambda: _FakeDecomposer()
    )


async def _decompose(fragment_ord: int) -> dict:
    return await decompose_fragment(
        _CAMPAIGN,
        _NPC,
        SimpleNamespace(
            campaign_id=_CAMPAIGN,
            npc_id=_NPC,
            fragment_ord=fragment_ord,
            fragment="текст",
        ),
    )


def _load_doc(store: ChronicleStore) -> ChronicleDocument:
    doc = store.load_draft(_CAMPAIGN, _NPC)
    assert doc is not None
    return doc


def _fragment_draft_ids(doc: ChronicleDocument, fragment_ord: int) -> set[str]:
    lo = fragment_ord * 100
    return {
        e.entry_id
        for e in doc.entries
        if e.provenance is EntryProvenance.LLM_DRAFT and lo <= e.ordinal < lo + 100
    }


def test_shrink_removes_stale_draft(tmp_path, monkeypatch):
    store = _make_store(tmp_path)
    _install_decomposer(monkeypatch, 4)
    asyncio.run(_decompose(3))
    assert len(_fragment_draft_ids(_load_doc(store), 3)) == 4

    _install_decomposer(monkeypatch, 3)  # повторный прогон: 4 -> 3
    asyncio.run(_decompose(3))
    ids = _fragment_draft_ids(_load_doc(store), 3)
    assert len(ids) == 3, "осиротевшая 4-я запись обязана исчезнуть"


def test_author_confirmed_slot_survives(tmp_path, monkeypatch):
    store = _make_store(tmp_path)
    confirmed_id = make_entry_id(_NPC, 3, 1)
    confirmed = ChronicleEntry(
        entry_id=confirmed_id,
        kind=EntryKind.EVENT,
        subject_id=EntityRef(ref_kind=EntityRefKind.RESOLVED, npc_id=_NPC),
        historical_age=30,
        payload={"summary": "авторская версия"},
        provenance=EntryProvenance.AUTHOR_CONFIRMED,
        confidence=None,  # AUTHOR_* не хранит confidence — контракт domain/chronicle.py:353
        ordinal=301,
    )
    store.save_draft(
        ChronicleDocument(
            chronicle_id=_NPC, npc_ref=_NPC, entries=(confirmed,), canonical=False
        ),
        _CAMPAIGN,
    )

    _install_decomposer(monkeypatch, 2)
    asyncio.run(_decompose(3))
    doc = _load_doc(store)

    by_id = {e.entry_id: e for e in doc.entries}
    assert by_id[confirmed_id].provenance is EntryProvenance.AUTHOR_CONFIRMED, (
        "авторская запись не должна быть подменена черновиком"
    )
    draft_ids = _fragment_draft_ids(doc, 3)
    assert len(doc.entries) == 3
    assert confirmed_id not in draft_ids
    assert len(set(e.entry_id for e in doc.entries)) == len(doc.entries), (
        "дубликатов entry_id быть не может"
    )


def test_other_fragment_drafts_untouched(tmp_path, monkeypatch):
    store = _make_store(tmp_path)
    _install_decomposer(monkeypatch, 2)
    asyncio.run(_decompose(5))
    before = _fragment_draft_ids(_load_doc(store), 5)
    assert len(before) == 2

    _install_decomposer(monkeypatch, 3)
    asyncio.run(_decompose(3))  # другой фрагмент
    after = _fragment_draft_ids(_load_doc(store), 5)
    assert after == before, "чужой фрагмент не трогается"


def test_overflow_rejected(tmp_path, monkeypatch):
    store = _make_store(tmp_path)
    _install_decomposer(monkeypatch, 100)
    resp = asyncio.run(_decompose(3))
    assert resp["status"] == "NOT_DECOMPOSED"
    assert "лимит 99" in resp["error"]
    assert store.load_draft(_CAMPAIGN, _NPC) is None