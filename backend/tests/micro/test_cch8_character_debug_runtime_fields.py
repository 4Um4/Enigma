"""CCH-8 / COV-11 B1: character_debug runtime observability fields.

Tests 4 new fields in character_debug response.now:
- episodic_memory_count (from npc_dict.narrative_cache)
- relationship_cache_targets (from npc_dict.relationship_cache keys)
- affective_imprints_count (from npc_dict.affective_imprints)
- psyche_beliefs_types (from npc_dict.psyche.beliefs keys)

Conditions per Master verdict:
- Read-only: NPCState/npc_dict not mutated
- null = field absent in npc_dict; 0/[] = field present but empty
- No seeder/resolver/canonizer calls from debug code
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Dict, List

import pytest

from app.api import routes_chronicle
from app.api.routes_chronicle import get_character_debug
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


# ── AUTO-START/AUTO-KILL (принцип IPT.py) ──────────────────────────────
# B1-тесты интеграционные: требуют uvicorn:8000 + llama-server:8181.
# Поднимаем только если порт свободен; убиваем только если сами поднимали.
# Чужие процессы (поднятые Мастером в отдельном окне) НЕ трогаем.
import atexit
import os
import socket
import subprocess
import sys
import time

_BACKEND = Path(__file__).resolve().parents[2]   # .../backend
_VENV_PY = _BACKEND.parent / ".venv" / "Scripts" / "python.exe"


def _port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) == 0


# (a) LLM — через готовый менеджер, как в IPT.
# Guard: kill_llama_server регистрируем ТОЛЬКО если сами подняли.
_llm_started_here = False
try:
    from scripts.llm_server_manager import kill_llama_server, start_llama_server
    if not _port_open(8181):
        if start_llama_server():
            _llm_started_here = True
            atexit.register(kill_llama_server)
except (ModuleNotFoundError, OSError) as _e:
    print(f"⚠️ B1: LLM недоступна ({_e})", file=sys.stderr)


# (b) uvicorn — поднимаем сами, если :8000 молчит.
# Чужой uvicorn НЕ трогаем (нет atexit.register если не мы подняли).
def _shutdown_uvicorn(proc: subprocess.Popen) -> None:
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


if not _port_open(8000):
    _uvicorn_proc = subprocess.Popen(
        [str(_VENV_PY), "-m", "uvicorn", "app.main:app",
         "--host", "127.0.0.1", "--port", "8000"],
        cwd=str(_BACKEND),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    atexit.register(_shutdown_uvicorn, _uvicorn_proc)
    # Ждём готовности (≤ 10 c). Если не встал — печатаем хвост лога в stderr.
    for _ in range(100):
        if _port_open(8000):
            break
        time.sleep(0.1)
    else:
        try:
            tail = _uvicorn_proc.stdout.read().decode("utf-8", errors="replace")[-2000:]
            print(f"⚠️ B1: uvicorn не поднялся за 10с. Хвост лога:\n{tail}",
                  file=sys.stderr)
        except Exception:
            pass


# (c) ghost_reaper — гигиена перед прогоном (как в IPT).
# Opt-out: env IPT_NO_REAPER=1.
try:
    if os.environ.get("IPT_NO_REAPER", "").strip().lower() not in ("1", "true", "yes"):
        from scripts.ghost_reaper import reap as _reap
        _r = _reap(dry_run=False)
        print(f"[B1] KILLER_SPIRIT: killed={len(_r.get('killed', []))}, "
              f"spared={len(_r.get('spared', []))}, "
              f"fault={len(_r.get('fault', []))}",
              file=sys.stderr)
except Exception as _e:  # noqa: BLE001 — канальный отказ, не тика
    print(f"[B1] KILLER_SPIRIT FAULT (не критично): {_e!r}", file=sys.stderr)



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
    doc = ChronicleDocument(
        chronicle_id=npc_id,
        npc_ref=npc_id,
        entries=(entry,),
        canonical=True,
        canonical_version=1,
    )
    store.save_canonical(doc)
    return store


class _FakeGameLoop:
    """Minimal GameLoop stub for character_debug tests."""

    def __init__(self, npcs: List[Dict[str, Any]]) -> None:
        self._npcs = npcs

    def _load_npcs_with_runtime(self, campaign_id: str) -> List[Dict[str, Any]]:
        return self._npcs


def _mock_game_loop(monkeypatch, npcs: List[Dict[str, Any]]) -> None:
    """Patch get_game_loop to return a fake loop with given npc_dicts."""
    fake_loop = _FakeGameLoop(npcs)
    monkeypatch.setattr(
        "app.services.game_loop_accessor.get_game_loop",
        lambda req: fake_loop,
    )


def test_runtime_fields_present_when_state_loaded(tmp_path, monkeypatch):
    """When npc_dict has all 4 fields, response includes counts/targets/types."""
    store = _make_store_with_canon(tmp_path)
    monkeypatch.setattr(routes_chronicle, "_get_store", lambda: store)

    npc_dict = {
        "npc_id": "test_npc",
        "name": "Test NPC",
        "current_role": "guard",
        "body_state": {"hp": 100, "current_hp": 100},
        "psyche": {
            "stress": 0.5,
            "state": "free",
            "affective_load": 0.2,
            "drives_base": {},
            "beliefs": {
                "danger": [0.7, 0.8, "chronicle", 0],
                "player_hostile": [0.6, 0.7, "perception", 1],
            },
        },
        "behavior_mask": {},
        "life_project_state": "ACTIVE",
        "intent": "idle",
        "intent_target": None,
        "causal_ledger": [],
        "narrative_cache": [{"event_type": "origin"}, {"event_type": "origin"}],
        "relationship_cache": {"player": {"trust": 50.0}, "npc_b": {"trust": -40.0}},
        "affective_imprints": [{"source_entity_id": "x"}, {"source_entity_id": "y"}, {"source_entity_id": "z"}],
    }

    _mock_game_loop(monkeypatch, [npc_dict])

    response = asyncio.run(get_character_debug("test_campaign", "test_npc", None))

    assert response["states"]["runtime"] == "KNOWN"
    now = response["now"]
    assert now is not None
    assert now["episodic_memory_count"] == 2
    assert now["relationship_cache_targets"] == ["npc_b", "player"]
    assert now["affective_imprints_count"] == 3
    assert now["psyche_beliefs_types"] == ["danger", "player_hostile"]


def test_runtime_fields_null_when_absent(tmp_path, monkeypatch):
    """When npc_dict lacks the 4 fields, response shows null (not 0/[])."""
    store = _make_store_with_canon(tmp_path)
    monkeypatch.setattr(routes_chronicle, "_get_store", lambda: store)

    npc_dict = {
        "npc_id": "test_npc",
        "name": "Test NPC",
        "body_state": {"hp": 100, "current_hp": 100},
        "psyche": {"stress": 0.0, "state": "free", "affective_load": 0.0, "drives_base": {}},
        "causal_ledger": [],
    }

    _mock_game_loop(monkeypatch, [npc_dict])

    response = asyncio.run(get_character_debug("test_campaign", "test_npc", None))

    assert response["states"]["runtime"] == "KNOWN"
    now = response["now"]
    assert now is not None
    assert now["episodic_memory_count"] is None
    assert now["relationship_cache_targets"] is None
    assert now["affective_imprints_count"] is None
    assert now["psyche_beliefs_types"] is None


def test_runtime_fields_zero_when_empty(tmp_path, monkeypatch):
    """When npc_dict has empty collections, response shows 0/[] (not null)."""
    store = _make_store_with_canon(tmp_path)
    monkeypatch.setattr(routes_chronicle, "_get_store", lambda: store)

    npc_dict = {
        "npc_id": "test_npc",
        "name": "Test NPC",
        "body_state": {"hp": 100, "current_hp": 100},
        "psyche": {"stress": 0.0, "state": "free", "affective_load": 0.0, "drives_base": {}, "beliefs": {}},
        "causal_ledger": [],
        "narrative_cache": [],
        "relationship_cache": {},
        "affective_imprints": [],
    }

    _mock_game_loop(monkeypatch, [npc_dict])

    response = asyncio.run(get_character_debug("test_campaign", "test_npc", None))

    now = response["now"]
    assert now["episodic_memory_count"] == 0
    assert now["relationship_cache_targets"] == []
    assert now["affective_imprints_count"] == 0
    assert now["psyche_beliefs_types"] == []


def test_no_side_effects_on_npc_dict(tmp_path, monkeypatch):
    """character_debug is read-only: npc_dict unchanged before/after call."""
    store = _make_store_with_canon(tmp_path)
    monkeypatch.setattr(routes_chronicle, "_get_store", lambda: store)

    npc_dict = {
        "npc_id": "test_npc",
        "name": "Test NPC",
        "body_state": {"hp": 100, "current_hp": 100},
        "psyche": {
            "stress": 0.5,
            "state": "free",
            "affective_load": 0.2,
            "drives_base": {},
            "beliefs": {"danger": [0.7, 0.8, "chronicle", 0]},
        },
        "causal_ledger": [],
        "narrative_cache": [{"event_type": "origin"}],
        "relationship_cache": {"player": {"trust": 50.0}},
        "affective_imprints": [{"source_entity_id": "x"}],
    }
    narrative_before = list(npc_dict["narrative_cache"])
    rc_before = dict(npc_dict["relationship_cache"])
    imprints_before = list(npc_dict["affective_imprints"])
    beliefs_before = dict(npc_dict["psyche"]["beliefs"])

    _mock_game_loop(monkeypatch, [npc_dict])

    asyncio.run(get_character_debug("test_campaign", "test_npc", None))

    assert npc_dict["narrative_cache"] == narrative_before
    assert npc_dict["relationship_cache"] == rc_before
    assert npc_dict["affective_imprints"] == imprints_before
    assert npc_dict["psyche"]["beliefs"] == beliefs_before