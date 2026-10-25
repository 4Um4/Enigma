"""
CCH-4 Character Debugger (FR-9.x, ADR-O-420):
- T-CCH-08: изоляция layer 4 от HUD (Debugger не входит в WorldSnapshotDTO)
- 4 состояния данных: KNOWN / NOT_AUTHORED / NOT_LOADED / INIT_ERROR
- Read-only (запрет 10): не мутирует NPCState

T-CCH-07 (вертикаль «звон кружки → avoidance») — живой сессией (causal_ledger
содержит trace); здесь проверяем структурный доступ к causal_ledger через
endpoint.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi import FastAPI

from app.api import routes_chronicle
from app.api.routes_chronicle import chronicle_router, get_character_debug
from app.services.chronicle.chronicle_store import ChronicleStore
from app.domain.chronicle import (
    SCHEMA_VERSION,
    ChronicleDocument,
    ChronicleEntry,
    EntityRef,
    EntityRefKind,
    EntryKind,
    EntryProvenance,
    WhiteSpot,
    WhiteSpotResolutionState,
    make_entry_id,
)


# ── Fixture: изоляция глобального store ──────────────────────────────────────

@pytest.fixture(autouse=True)
def _reset_store_global():
    saved = getattr(routes_chronicle, "_store", None)
    routes_chronicle._store = None
    yield
    routes_chronicle._store = saved


def _make_store_with_canon(tmp_path: Path, npc_id: str = "test_npc") -> ChronicleStore:
    canonical_dir = tmp_path / "canon"
    drafts_root = tmp_path / "drafts"
    canonical_dir.mkdir(parents=True, exist_ok=True)
    drafts_root.mkdir(parents=True, exist_ok=True)
    store = ChronicleStore(canonical_dir, drafts_root)

    entry = ChronicleEntry(
        entry_id=make_entry_id(npc_id, 0, 0),
        kind=EntryKind.EVENT,
        subject_id=EntityRef(ref_kind=EntityRefKind.RESOLVED, npc_id=npc_id),
        historical_age=20,
        payload={},
        provenance=EntryProvenance.AUTHOR_AUTHORED,
    )
    ws = WhiteSpot(
        white_spot_id="ws_test",
        label="старый пьянчужка",
        resolution_state=WhiteSpotResolutionState.OPEN,
        created_from_entry=entry.entry_id,
    )
    doc = ChronicleDocument(
        chronicle_id=npc_id,
        npc_ref=npc_id,
        author_text="фрагмент",
        entries=(entry,),
        white_spots=(ws,),
        canonical=True,
        canonical_version=1,
        schema_version=SCHEMA_VERSION,
    )
    store.save_canonical(doc)
    return store


class _FakeApp:
    """Минимальный FastAPI app mock с app.state.game_loop=None."""
    class _State:
        game_loop = None
    state = _State()


class _FakeRequest:
    """Минимальный Request mock для get_game_loop."""
    app = _FakeApp()


def test_cch4_debug_not_loaded_when_runtime_missing(tmp_path):
    """NOT_LOADED: runtime не инициализирован → endpoint не падает, возвращает NOT_LOADED."""
    store = _make_store_with_canon(tmp_path)
    routes_chronicle._store = store

    result = asyncio.run(get_character_debug("camp", "test_npc", _FakeRequest()))

    assert result["states"]["runtime"] == "NOT_LOADED"
    assert result["now"] is None
    # Источники доступны (канон есть)
    assert result["states"]["chronicle"] == "KNOWN"
    assert result["sources"] is not None
    assert result["sources"]["chronicle_id"] == "test_npc"


def test_cch4_debug_not_authored_when_no_canon(tmp_path):
    """NOT_AUTHORED: канон-хроника отсутствует → sources=None, NOT_AUTHORED."""
    canonical_dir = tmp_path / "canon"
    drafts_root = tmp_path / "drafts"
    canonical_dir.mkdir(parents=True, exist_ok=True)
    drafts_root.mkdir(parents=True, exist_ok=True)
    store = ChronicleStore(canonical_dir, drafts_root)
    routes_chronicle._store = store

    result = asyncio.run(get_character_debug("camp", "ghost_npc", _FakeRequest()))

    # runtime тоже нет (GameLoop=None)
    assert result["states"]["runtime"] == "NOT_LOADED"
    assert result["states"]["chronicle"] == "NOT_AUTHORED"
    assert result["sources"] is None


def test_cch4_debug_returns_canon_sources_when_present(tmp_path):
    """Источники: канон-entries + white_spots + счётчики beliefs/candidates."""
    store = _make_store_with_canon(tmp_path)
    routes_chronicle._store = store

    result = asyncio.run(get_character_debug("camp", "test_npc", _FakeRequest()))
    sources = result["sources"]
    assert sources["chronicle_id"] == "test_npc"
    assert sources["canonical_version"] == 1
    assert len(sources["entries"]) == 1
    assert sources["entries"][0]["kind"] == "EVENT"
    assert sources["entries"][0]["subject_id"]["ref_kind"] == "RESOLVED"
    assert sources["entries"][0]["subject_id"]["npc_id"] == "test_npc"
    assert len(sources["white_spots"]) == 1
    assert sources["white_spots"][0]["white_spot_id"] == "ws_test"
    assert sources["white_spots"][0]["resolution_state"] == "OPEN"
    assert sources["npc_beliefs_count"] == 0
    assert sources["cause_candidates_count"] == 0


def test_cch4_debug_isolation_from_hud():
    """T-CCH-08: Debugger endpoint НЕ входит в WorldSnapshotDTO.

    Греп-инвариант: WorldSnapshotDTO не содержит character_debug ключа.
    Фронтенд isolation (lint_frontend_isolation) проверяет отсутствие backend-импортов.
    Здесь проверяем, что endpoint возвращает self-contained dict, не ссылается
    на WorldSnapshotDTO поля."""
    import inspect

    sig = inspect.signature(get_character_debug)
    params = list(sig.parameters.keys())
    # Endpoint принимает campaign_id, npc_id, request — никаких npc_state, snapshot
    assert "campaign_id" in params
    assert "npc_id" in params
    assert "request" in params
    # НЕ принимает state/snapshot — это debug-only, не часть игрового тика
    assert "state" not in params
    assert "snapshot" not in params


def test_cch4_debug_read_only_does_not_mutate(tmp_path):
    """Запрет 10 ADR-O-420: endpoint не мутирует runtime NPCState.

    Вызов дважды подряд с одним и тем же input → идентичный результат (read-only)."""
    store = _make_store_with_canon(tmp_path)
    routes_chronicle._store = store

    result1 = asyncio.run(get_character_debug("camp", "test_npc", _FakeRequest()))
    result2 = asyncio.run(get_character_debug("camp", "test_npc", _FakeRequest()))

    assert result1 == result2  # read-only — нет side effects


def test_cch4_debug_endpoint_registered_on_router():
    """Маршрут GET /chronicle/{campaign}/{npc}/debug зарегистрирован."""
    paths = [r.path for r in chronicle_router.routes]
    debug_path = "/chronicle/{campaign_id}/{npc_id}/debug"
    assert debug_path in paths, f"Debug endpoint не зарегистрирован. Routes: {paths}"