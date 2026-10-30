"""COV-12 G1: прослеживаемость source → entry через author_text.

5 инвариантов:
1. Новый draft: author_text_full передан → doc.author_text == full
2. Несколько фрагментов: первый создаёт с full, второй (без full) — сохраняет
3. Повторный decompose с другим author_text_full — НЕ затирает оригинал
4. Существующий draft с author_text — decompose без full — author_text сохраняется
5. Новый draft без author_text_full → NOT_DECOMPOSED с явной ошибкой прослеживаемости
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.api import routes_chronicle
from app.api.routes_chronicle import decompose_fragment
from app.domain.chronicle import EntryKind
from app.services.chronicle.chronicle_store import ChronicleStore

_CAMPAIGN = "camp_g1"
_NPC = "npc_g1"
_FULL_TEXT = "Кузнец Орм: гном\n\n1. 146 лет.\n2. Увлечён работой."


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


def _install_decomposer(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeDecomposer:
        async def decompose(self, npc_id: str, fragment_ord: int, fragment: str):
            from types import SimpleNamespace as NS
            return NS(
                ok=True,
                items=[NS(
                    kind=EntryKind.EVENT,
                    draft_payload={"summary": "test", "day": None},
                    confidence=0.9,
                    question=None,
                    needs_confirmation=False,
                )],
                age_anchors=[],
                error=None,
                raw_response="{}",
            )

    monkeypatch.setattr(routes_chronicle, "_get_decomposer", lambda: _FakeDecomposer())


async def _decompose(fragment_ord: int, fragment: str, author_text_full=None) -> dict:
    return await decompose_fragment(
        _CAMPAIGN,
        _NPC,
        SimpleNamespace(
            campaign_id=_CAMPAIGN,
            npc_id=_NPC,
            fragment_ord=fragment_ord,
            fragment=fragment,
            author_text_full=author_text_full,
        ),
    )


def _load_doc(store: ChronicleStore):
    doc = store.load_draft(_CAMPAIGN, _NPC)
    assert doc is not None
    return doc


def test_new_draft_with_full_author_text(tmp_path, monkeypatch):
    """Инвариант 1: новый draft создаётся с author_text из запроса."""
    store = _make_store(tmp_path)
    _install_decomposer(monkeypatch)

    asyncio.run(_decompose(0, "1. 146 лет.", author_text_full=_FULL_TEXT))
    doc = _load_doc(store)
    assert doc.author_text == _FULL_TEXT


def test_multiple_fragments_preserve_author_text(tmp_path, monkeypatch):
    """Инвариант 2: второй фрагмент (без author_text_full) не затирает текст."""
    store = _make_store(tmp_path)
    _install_decomposer(monkeypatch)

    # Первый фрагмент — создаёт draft с полным текстом
    asyncio.run(_decompose(0, "1. 146 лет.", author_text_full=_FULL_TEXT))
    # Второй фрагмент — без author_text_full (фронт уже не передаёт)
    asyncio.run(_decompose(1, "2. Увлечён работой."))
    doc = _load_doc(store)
    assert doc.author_text == _FULL_TEXT, "author_text должен сохраниться от первого вызова"


def test_repeated_decompose_does_not_overwrite_author_text(tmp_path, monkeypatch):
    """Инвариант 3: повторный decompose с другим author_text_full НЕ заменяет оригинал."""
    store = _make_store(tmp_path)
    _install_decomposer(monkeypatch)

    asyncio.run(_decompose(0, "1. 146 лет.", author_text_full=_FULL_TEXT))
    other_text = "Другой текст, не должен примениться"
    asyncio.run(_decompose(0, "1. 146 лет.", author_text_full=other_text))
    doc = _load_doc(store)
    assert doc.author_text == _FULL_TEXT, (
        "существующий author_text не должен затираться новым запросом"
    )


def test_existing_author_text_preserved(tmp_path, monkeypatch):
    """Инвариант 4: draft с author_text, decompose без author_text_full — сохраняется."""
    store = _make_store(tmp_path)
    _install_decomposer(monkeypatch)

    asyncio.run(_decompose(0, "1. 146 лет.", author_text_full=_FULL_TEXT))
    asyncio.run(_decompose(1, "2. Увлечён работой.", author_text_full=None))
    doc = _load_doc(store)
    assert doc.author_text == _FULL_TEXT


def test_missing_author_text_returns_not_decomposed(tmp_path, monkeypatch):
    """Инвариант 5: новый draft без author_text_full → NOT_DECOMPOSED с явной ошибкой."""
    _make_store(tmp_path)
    _install_decomposer(monkeypatch)

    resp = asyncio.run(_decompose(0, "1. 146 лет.", author_text_full=None))
    assert resp["status"] == "NOT_DECOMPOSED"
    assert "author_text_full" in resp["error"]
    assert "PUT /draft" in resp["error"]