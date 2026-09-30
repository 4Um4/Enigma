"""
path: backend/tests/sandbox/micro/test_multi_act.py
Назначение: Multi-Act Understanding — акт-валидация (белый список типов, мусор по-элементно, params строковые)
Зависимости: app.services.input.intent_compressor._VALID_ACT_TYPES недоступен (локальная) — проверяем через resolve
Основные сущности: resolve_player_intent, IntentSemanticField

Запуск: cd backend; python -m pytest tests/sandbox/micro/test_multi_act.py -v --tb=short; cd ..
"""
from app.domain.intent_profile import ActionType, IntentSemanticField
from app.services.game_loop.phase_1_input import resolve_player_intent


def _resolve_with_acts(acts):
    sf = IntentSemanticField(
        action=ActionType.DIALOGUE, raw_text="фраза", target="Люся",
        semantic_acts=acts,
    )
    return resolve_player_intent(
        raw_action="фраза", action_type="player_interacts",
        target="maid_lusya", player_dict=None, scene_context=None,
        semantic_field=sf,
    )


def test_acts_transport_to_dto():
    acts = [{"type": "GREETING", "params": {}}, {"type": "SELF_INTRODUCTION", "params": {"name": "Мю"}}]
    p = _resolve_with_acts(acts).original_intent.parameters
    assert len(p.semantic_acts) == 2
    assert p.semantic_acts[0]["type"] == "GREETING"
    assert p.semantic_acts[1]["params"] == {"name": "Мю"}


def test_acts_are_copies_not_references():
    acts = [{"type": "GREETING", "params": {}}]
    p = _resolve_with_acts(acts).original_intent.parameters
    p.semantic_acts[0]["type"] = "MUTATED"
    assert acts[0]["type"] == "GREETING"  # исходник не тронут


def test_empty_acts_transport_empty():
    p = _resolve_with_acts([]).original_intent.parameters
    assert p.semantic_acts == []
