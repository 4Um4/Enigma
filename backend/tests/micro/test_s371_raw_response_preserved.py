"""
S371.0: DecomposeResult.raw_response — сырой ответ LLM сохраняется при failure.

Контракт (CCH-S371, ADR-O-420): при DecompositionError сырой ответ LLM
должен сохраняться в DecomposeResult.raw_response для диагностики
(классификация truncation/unicode/quote/escape/unknown).
"""
from __future__ import annotations

import asyncio
import pytest

from app.services.chronicle.biography_decomposer import BiographyDecomposer, DecomposeResult


def test_s371_failure_with_raw_response():
    """failure() с raw_response сохраняет сырой текст."""
    raw = '{"items": [{"kind": "EVENT"}],}'
    result = DecomposeResult.failure("JSON-парсинг: Expecting ',' delimiter", raw_response=raw)
    assert result.ok is False
    assert result.raw_response == raw


def test_s371_failure_without_raw_response_backward_compat():
    """failure() без raw_response — backward compat (None)."""
    result = DecomposeResult.failure("Пустой фрагмент")
    assert result.ok is False
    assert result.raw_response is None


def test_s371_success_has_no_raw_response():
    """success() — raw_response всегда None."""
    result = DecomposeResult.success(items=[], age_anchors=[8])
    assert result.ok is True
    assert result.raw_response is None


def test_s371_decompose_preserves_raw_on_decomposition_error():
    """decompose() сохраняет сырой ответ LLM при DecompositionError."""
    class _MockRouter:
        async def request(self, **kwargs):
            return '{"items": [{"kind": "EVENT", "draft_payload": {}, "confidence": 0.5}],}'

    decomposer = BiographyDecomposer(router=_MockRouter(), roster_provider=lambda: {})
    result = asyncio.run(decomposer.decompose("test_npc", 0, "В 8 лет что-то произошло"))

    assert result.ok is False
    assert result.raw_response is not None
    assert "items" in result.raw_response


def test_s371_routes_decompose_fragment_returns_raw_response():
    """routes_chronicle.decompose_fragment возвращает raw_response при NOT_DECOMPOSED."""
    from app.api import routes_chronicle
    from app.api.routes_chronicle import DecomposeRequest, decompose_fragment

    class _MockDecomposer:
        async def decompose(self, *args, **kwargs):
            return DecomposeResult.failure(
                "JSON-парсинг: Expecting ',' delimiter",
                raw_response='{"items": [{"kind": "EVENT"}],}',
            )

    routes_chronicle._decomposer = _MockDecomposer()
    try:
        req = DecomposeRequest(campaign_id="test", npc_id="test_npc", fragment_ord=0, fragment="test")
        result = asyncio.run(decompose_fragment("test", "test_npc", req))
        assert result["status"] == "NOT_DECOMPOSED"
        assert result["raw_response"] is not None
        assert "items" in result["raw_response"]
    finally:
        routes_chronicle._decomposer = None