"""T-CCH-SV-01 — CCH-7 Semantic Validation Gate (ADR-O-422, CCH-7).

Гейт: canonize блокирует ТОЛЬКО CONTRADICTION canon-level (RESOLVED EntityRef
на несуществующего канонного NPC). Все остальные Finding.kind — диагностические
(не блокирующие). Техническая ошибка сервиса → 500, не 200.
"""
from __future__ import annotations

import json
import pathlib
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.api.routes_chronicle import _check_canonical_consistency, canonize_chronicle
from app.domain.chronicle import (
    ChronicleDocument,
    ChronicleEntry,
    EntityRef,
    EntityRefKind,
    EntryKind,
    EntryProvenance,
)
from app.services.chronicle.consistency_service import (
    CanonicalRegistry,
    ConsistencyReport,
    ConsistencyService,
    Finding,
)


# ---- helpers ----

def _entry(npc: str, **kw) -> ChronicleEntry:
    base = dict(
        entry_id=kw.pop("eid"),
        ordinal=kw.pop("ordinal", 0),
        kind=EntryKind.EVENT,
        subject_id=EntityRef(ref_kind=EntityRefKind.RESOLVED, npc_id=npc),
        provenance=EntryProvenance.AUTHOR_AUTHORED,
    )
    base.update(kw)
    return ChronicleEntry(**base)


def _doc(npc: str, entries) -> ChronicleDocument:
    return ChronicleDocument(
        chronicle_id=f"c_{npc}", npc_ref=npc, entries=tuple(entries),
        game_start_age=20, canonical=True, canonical_version=1,
    )


# Реестр содержит только известные NPC
REG_OK = CanonicalRegistry(
    alias_to_npc={"люся": "maid_lusya"},
    archetype_of={"maid_lusya": "maid", "guard_borko": "guard"},
)


# ---- СЛУЧАЙ 1: согласованный объект проходит ----

def test_case1_consistent_document_passes():
    """Документ без CONTRADICTION → гейт пропускает (нет ValueError)."""
    doc = _doc("maid_lusya", [
        _entry("maid_lusya", eid="e1", historical_age=10,
               object_id=EntityRef(ref_kind=EntityRefKind.RESOLVED, npc_id="guard_borko")),
    ])
    with patch("app.api.routes_chronicle._build_registry_for_canonize", return_value=REG_OK):
        _check_canonical_consistency(doc)  # не должно бросить


# ---- СЛУЧАЙ 2: CONTRADICTION canon-level блокирует ----

def test_case2_contradiction_blocks_with_fix_hint():
    """RESOLVED EntityRef на несуществующего NPC → ValueError с fix_hint."""
    doc = _doc("maid_lusya", [
        _entry("maid_lusya", eid="e1", historical_age=10,
               object_id=EntityRef(ref_kind=EntityRefKind.RESOLVED, npc_id="ghost_none")),
    ])
    with patch("app.api.routes_chronicle._build_registry_for_canonize", return_value=REG_OK):
        with pytest.raises(ValueError, match="Semantic validation"):
            _check_canonical_consistency(doc)
    # Проверяем диагностику: detail содержит npc_id и entry_id
    with patch("app.api.routes_chronicle._build_registry_for_canonize", return_value=REG_OK):
        try:
            _check_canonical_consistency(doc)
        except ValueError as e:
            assert "ghost_none" in str(e)
            assert "e1" in str(e)


# ---- СЛУЧАЙ 3: диагностическое нарушение НЕ блокирует ----

def test_case3_diagnostic_finding_does_not_block():
    """GAP/MERGE_CANDIDATE/QUESTION/QUESTION/CANON_SYNC/INFO — не блокируют."""
    # Документ с GAP (событие без даты между якорями) — не CONTRADICTION
    doc = _doc("maid_lusya", [
        _entry("maid_lusya", eid="e1", historical_age=10, ordinal=0),
        _entry("maid_lusya", eid="e2", ordinal=1),  # без даты → GAP
        _entry("maid_lusya", eid="e3", historical_age=14, ordinal=2),
    ])
    with patch("app.api.routes_chronicle._build_registry_for_canonize", return_value=REG_OK):
        _check_canonical_consistency(doc)  # GAP — диагностика, не блок


# ---- СЛУЧАЙ 4: техническая ошибка сервиса → не маскируется под успех ----

def test_case4_service_exception_not_masked():
    """Если ConsistencyService.check бросает Exception — пробрасывается как 500."""
    doc = _doc("maid_lusya", [_entry("maid_lusya", eid="e1", historical_age=10)])

    def _explode(*args, **kwargs):
        raise RuntimeError("simulated internal failure")

    with patch("app.api.routes_chronicle._build_registry_for_canonize", return_value=REG_OK):
        with patch.object(ConsistencyService, "check", side_effect=_explode):
            # Гейт должен пробросить Exception (route ловит в 500, но сам гейт пробрасывает)
            with pytest.raises(Exception, match="simulated internal failure"):
                _check_canonical_consistency(doc)


# ---- СЛУЧАЙ 5: существующие допустимые входы сохраняют поведение ----

def test_case5_existing_canons_pass_gate(tmp_path):
    """Все 6 существующих канонов должны проходить новый гейт (обратная совместимость).
    Реальная проверка: загружаем каждый canon из config/npc/chronicles/ и зовём гейт."""
    canon_dir = pathlib.Path(__file__).resolve().parents[3] / "config" / "npc" / "chronicles"
    if not canon_dir.is_dir():
        pytest.skip("canon dir not found")
    # Реальный registry (без мока) — production path
    from app.services.chronicle.registry_builder import build_canonical_registry
    reg = build_canonical_registry()
    from app.services.chronicle.chronicle_store import document_from_dict
    for canon_file in sorted(canon_dir.glob("*.json")):
        raw = json.loads(canon_file.read_text(encoding="utf-8-sig"))
        doc = document_from_dict(raw)
        with patch("app.api.routes_chronicle._build_registry_for_canonize", return_value=reg):
            # Не должно бросить — все 6 канонов без CONTRADICTION (верифицировано S384 аудит)
            _check_canonical_consistency(doc)


# ---- СЛУЧАЙ 6: ответ API и диагностика соответствуют контракту ----

@pytest.mark.asyncio
async def test_case6_api_response_422_with_diagnostics(tmp_path, monkeypatch):
    """Integration: POST canonize с CONTRADICTION → 422 + detail с npc_id/entry_id."""
    # Готовим store с draft, содержащим RESOLVED на несуществующего NPC
    from app.services.chronicle.chronicle_store import ChronicleStore
    from app.api import routes_chronicle

    canon_dir = tmp_path / "canon"
    drafts_dir = tmp_path / "drafts"
    store = ChronicleStore(canon_dir, drafts_dir)

    # Draft с CONTRADICTION
    bad_doc = _doc("maid_lusya", [
        _entry("maid_lusya", eid="e1", historical_age=10,
               object_id=EntityRef(ref_kind=EntityRefKind.RESOLVED, npc_id="ghost_none")),
    ])
    import dataclasses
    bad_doc = dataclasses.replace(bad_doc, canonical=False, canonical_version=0)
    store.save_draft(bad_doc, "silver_wolf")

    # Monkeypatch store + registry
    monkeypatch.setattr(routes_chronicle, "_store", store)
    monkeypatch.setattr(routes_chronicle, "_build_registry_for_canonize", lambda: REG_OK)

    from app.api.routes_chronicle import CanonizeRequest
    req = CanonizeRequest(campaign_id="silver_wolf")
    with pytest.raises(HTTPException) as exc_info:
        await canonize_chronicle("silver_wolf", "maid_lusya", req)

    assert exc_info.value.status_code == 422
    detail = exc_info.value.detail
    assert "Semantic validation" in detail
    assert "ghost_none" in detail
    assert "e1" in detail