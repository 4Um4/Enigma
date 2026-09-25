"""
path: backend/tests/sandbox/micro/test_reconciler_v0.py
Назначение: Reconciler v0 — неполный fast (ATTACK без зоны / фантом-proposition) → LLM enrichment только пустых полей; полный fast не вызывает LLM; LLM None → fast цел
Зависимости: app.services.input.intent_compressor
Основные сущности: IntentCompressor

Запуск: cd backend; python -m pytest tests/sandbox/micro/test_reconciler_v0.py -v --tb=short; cd ..
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock

from app.domain.epistemology import Predicate, Proposition
from app.domain.intent_profile import ActionType, IntentSemanticField, TargetZone
from app.services.input.intent_compressor import IntentCompressor


def _compressor(llm_response):
    client = MagicMock()
    client.compress_intent = AsyncMock(return_value=llm_response)
    return IntentCompressor(llm_client=client)


def _fast_attack(**kw):
    base = dict(action=ActionType.ATTACK, raw_text="ударить Люсю", target="люсю")
    base.update(kw)
    return IntentSemanticField(**base)


_SCENE = {"npc_positions": {"maid_lusya": {"name": "Люся"}}}


def test_incomplete_attack_enriched_and_phantom_dropped():
    llm = {"target_zone": "HEAD", "tool_reference": "нож", "proposition": None}
    comp = _compressor(llm)
    fast = _fast_attack(
        proposition=Proposition(subject_id="player", predicate=Predicate.ATTACKED, object_id="ушко", polarity=True)
    )
    result = asyncio.run(comp.compress("ударить Люсю", _SCENE, None))
    assert result.target_zone == TargetZone.HEAD
    assert result.zone_raw == "HEAD"
    assert result.tool_reference == "нож"
    assert result.target == "люсю"           # fast не перезаписан
    assert result.proposition is None        # R4-фантом снят (LLM не подтверждает)


def test_complete_fast_is_not_incomplete():
    # compress() пересобирает fast из текста (fast-ATTACK всегда без зоны →
    # incomplete по вердикту), поэтому полноту проверяем на предикате напрямую.
    comp = _compressor(None)
    fast = _fast_attack(target_zone=TargetZone.TORSO)
    assert not comp._fast_incomplete(fast, _SCENE)


def test_llm_none_keeps_fast():
    comp = _compressor(None)
    result = asyncio.run(comp.compress("ударить Люсю", _SCENE, None))
    assert result.action == ActionType.ATTACK
    assert result.target == "люсю"
