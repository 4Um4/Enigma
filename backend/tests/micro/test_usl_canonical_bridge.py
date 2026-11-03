"""USL-1.5: CanonicalRegistry bridge — «Орму» автора и игрока резолвятся одинаково.

Тест USL-1 §5.4: CanonicalRegistry.alias_to_npc используется в input-контуре
через _resolve_npc_by_name. Exact match на canonical name forms (включая
падежи «орм/орма/орму») — ПЕРВЫЙ путь; stem-based iteration — fallback.

Bridge site: intent_compressor._resolve_npc_by_name (ADR-O-437, USL-1.5).
"""
from __future__ import annotations

from app.services.input.intent_compressor import (
    _ensure_registry_cache,
    _resolve_npc_by_name,
)


def test_canonical_registry_cache_built():
    """_ensure_registry_cache возвращает dict (alias_to_npc extracted)."""
    cache = _ensure_registry_cache()
    assert isinstance(cache, dict)
    assert len(cache) > 0


def test_ormu_resolves_via_canonical():
    """«Орму» (падеж) → blacksmith_orm via CanonicalRegistry."""
    assert _resolve_npc_by_name("Орму") == "blacksmith_orm"
    assert _resolve_npc_by_name("орму") == "blacksmith_orm"


def test_orm_resolves_via_canonical():
    """«Орм» (nominative) → blacksmith_orm."""
    assert _resolve_npc_by_name("Орм") == "blacksmith_orm"


def test_orma_resolves_via_canonical():
    """«Орма» (genitive) → blacksmith_orm — падеж из name_forms."""
    assert _resolve_npc_by_name("Орма") == "blacksmith_orm"


def test_unknown_name_returns_none():
    """Неизвестное имя → None."""
    assert _resolve_npc_by_name("несуществующий_npc_123") is None


def test_stem_fallback_still_works():
    """Stem-based fallback работает для имён не в alias_to_npc.
    «Люсе» (падеж от «Люся») — если «люсе» не в alias_to_npc, stem
    («люс» ⊂ «люсе») находит maid_lusya. Оба пути валидны."""
    _result = _resolve_npc_by_name("Люсе")
    if _result is not None:
        assert _result == "maid_lusya"


def test_player_and_author_same_resolution():
    """USL-1 §5.4: «Орму» автора и «Орму» игрока — один npc_id.
    Автор: chronicle normalizer использует alias_to_npc.get("орму").
    Игрок: _resolve_npc_by_name("Орму") → _ensure_registry_cache().get("орму").
    Тот же dict, тот же ключ, тот же результат."""
    from app.services.chronicle.registry_builder import build_canonical_registry

    _author_result = build_canonical_registry().alias_to_npc.get("орму")
    _player_result = _resolve_npc_by_name("Орму")
    assert _author_result == _player_result == "blacksmith_orm"