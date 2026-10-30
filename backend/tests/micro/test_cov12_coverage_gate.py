"""COV-12 (п.1): право на ноль + coverage gate.

Проверяет 4 инварианта:
1. Пустой items (шапка «кузнец Орм: гном») — легален, response.status=OK,
   coverage.items_count=0, critical_topic_warning=None.
2. Критичная тема (маркеры насилие/шантаж/донос) + пустой items — warning в
   response.coverage, draft сохраняется пустым (warning не блокирует).
3. Обычный пункт с items — coverage.items_count=N, warning=None.
4. Критичная тема + items (не пустой) — coverage.critical_topic_warning=None
   (warning только при items=0; иначе модель нашла записи, молчания нет).

Чистый micro: decomposer подменяется, LLM/uvicorn не нужны.
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


def _fake_result(items_count: int) -> SimpleNamespace:
    items = [
        SimpleNamespace(
            kind=EntryKind.EVENT,
            draft_payload={"summary": f"item {i}"},
            confidence=0.9,
            question=None,
            needs_confirmation=False,
        )
        for i in range(items_count)
    ]
    return SimpleNamespace(
        ok=True, items=items, age_anchors=[], error=None, raw_response=""
    )


def _install_decomposer(monkeypatch: pytest.MonkeyPatch, items_count: int) -> None:
    class _FakeDecomposer:
        async def decompose(self, npc_id: str, fragment_ord: int, fragment: str):
            return _fake_result(items_count)

    monkeypatch.setattr(
        routes_chronicle, "_get_decomposer", lambda: _FakeDecomposer()
    )


async def _decompose(fragment_ord: int, fragment: str) -> dict:
    return await decompose_fragment(
        _CAMPAIGN,
        _NPC,
        SimpleNamespace(
            campaign_id=_CAMPAIGN,
            npc_id=_NPC,
            fragment_ord=fragment_ord,
            fragment=fragment,
        ),
    )


def test_empty_items_header_is_legal(tmp_path, monkeypatch):
    """Право на ноль: шапка «кузнец Орм: гном» -> items=[] -> status OK,
    coverage.items_count=0, critical_topic_warning=None."""
    _make_store(tmp_path)
    _install_decomposer(monkeypatch, 0)
    resp = asyncio.run(_decompose(0, "кузнец Орм: гном"))

    assert resp["status"] == "OK"
    assert resp["coverage"]["items_count"] == 0
    assert resp["coverage"]["critical_topic_warning"] is None
    assert resp["coverage"]["fragment_text_preview"] == "кузнец Орм: гном"


def test_critical_topic_with_empty_items_warns(tmp_path, monkeypatch):
    """Маркеры критичной темы + items=0 -> warning в coverage (не блокирует)."""
    _make_store(tmp_path)
    _install_decomposer(monkeypatch, 0)
    fragment = "Борко шантажировал Орма, чтобы тот продолжал насиловать Люсю."
    resp = asyncio.run(_decompose(5, fragment))

    assert resp["status"] == "OK"
    assert resp["coverage"]["items_count"] == 0
    assert resp["coverage"]["critical_topic_warning"] is not None
    assert "критичной темы" in resp["coverage"]["critical_topic_warning"]


def test_normal_fragment_has_coverage_count(tmp_path, monkeypatch):
    """Обычный пункт с 3 items -> coverage.items_count=3, warning=None."""
    _make_store(tmp_path)
    _install_decomposer(monkeypatch, 3)
    resp = asyncio.run(_decompose(2, "Учился кузнечному делу у мастера Грунта."))

    assert resp["status"] == "OK"
    assert resp["coverage"]["items_count"] == 3
    assert resp["coverage"]["critical_topic_warning"] is None


def test_critical_topic_with_items_no_warning(tmp_path, monkeypatch):
    """Критичная тема + items>0 -> warning=None (модель нашла записи, не молчала)."""
    _make_store(tmp_path)
    _install_decomposer(monkeypatch, 2)
    fragment = "Борко шантажировал Орма."
    resp = asyncio.run(_decompose(5, fragment))

    assert resp["status"] == "OK"
    assert resp["coverage"]["items_count"] == 2
    assert resp["coverage"]["critical_topic_warning"] is None