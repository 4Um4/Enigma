"""
path: backend/tests/sandbox/micro/test_target_resolve_canonical_id.py
Назначение: R14 — canonical id от LLM-слоя резолвится в Слое 2 (exact-id bridge до fuzzy)
Зависимости: app.services.game_loop.phase_1_input
Основные сущности: _resolve_target_reference

Запуск: cd backend; python -m pytest tests/sandbox/micro/test_target_resolve_canonical_id.py -v --tb=short; cd ..
"""
from app.domain.intent_profile import ActionType, IntentSemanticField
from app.services.game_loop.phase_1_input import _resolve_target_reference


def _field(target):
    return IntentSemanticField(action=ActionType.ATTACK, raw_text="x", target=target)


_SCENE = {"npc_positions": {"maid_lusya": {"name": "Люся"}, "thief_shadow": {"name": "Тень"}}}


def test_canonical_id_resolves():
    assert _resolve_target_reference(_field("maid_lusya"), _SCENE) == "maid_lusya"


def test_russian_name_still_resolves():
    scene = {"npc_positions": {"maid_lusya": {"display_name": "Люся"}}}
    assert _resolve_target_reference(_field("Люся"), scene) == "maid_lusya"


def test_unknown_returns_empty():
    assert _resolve_target_reference(_field("ножом"), _SCENE) == ""
