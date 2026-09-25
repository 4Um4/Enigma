"""
path: backend/tests/sandbox/micro/test_understanding_schema_transport.py
Назначение: инвариант Schema — поля SemanticField (condition/tool/zone/proposition) доезжают до IntentParametersDTO; UNKNOWN остаётся None
Зависимости: app.services.game_loop.phase_1_input, app.domain.intent_profile, app.domain.epistemology
Основные сущности: resolve_player_intent

Запуск: cd backend; python -m pytest tests/sandbox/micro/test_understanding_schema_transport.py -v --tb=short; cd ..
"""
from app.domain.epistemology import Predicate, Proposition
from app.domain.intent_profile import ActionType, IntentSemanticField, TargetZone
from app.services.game_loop.phase_1_input import resolve_player_intent


def test_schema_fields_reach_dto():
    sf = IntentSemanticField(
        action=ActionType.ATTACK,
        raw_text="ткни ножом в глаз",
        target="Люся",
        condition="если встанешь",
        tool_reference="нож",
        target_zone=TargetZone.HEAD,
        proposition=Proposition(
            subject_id="player", predicate=Predicate.ATTACKED,
            object_id="maid_lusya", polarity=True,
        ),
    )
    resolution = resolve_player_intent(
        raw_action="ткни ножом в глаз", action_type="player_attacks",
        target="maid_lusya", player_dict=None, scene_context=None,
        semantic_field=sf,
    )
    p = resolution.original_intent.parameters
    assert p.condition == "если встанешь"
    assert p.tool_reference == "нож"
    assert p.target_zone == "HEAD"
    assert p.proposition_predicate == "attacked"  # Predicate.ATTACKED.value — строчными (принято всеми логами)
    assert p.proposition_object_id == "maid_lusya"
    assert p.proposition_polarity is True
    assert p.addressee is None  # источника нет — догадка запрещена


def test_unknown_stays_none():
    sf = IntentSemanticField(action=ActionType.UNCERTAIN, raw_text="привет")
    resolution = resolve_player_intent(
        raw_action="привет", action_type="player_interacts",
        target="", player_dict=None, scene_context=None, semantic_field=sf,
    )
    p = resolution.original_intent.parameters
    assert p.condition is None
    assert p.tool_reference is None
    assert p.target_zone is None
    assert p.proposition_predicate is None

def test_addressee_and_zone_raw_reach_dto():
    sf = IntentSemanticField(
        action=ActionType.DIALOGUE, raw_text="Орм, стой", target="orm",
        addressee="Орм", zone_raw="EAR_LEFT", target_zone=TargetZone.HEAD,
    )
    resolution = resolve_player_intent(
        raw_action="Орм, стой", action_type="player_interacts",
        target="orm", player_dict=None, scene_context=None, semantic_field=sf,
    )
    p = resolution.original_intent.parameters
    assert p.addressee == "Орм"
    assert p.zone_raw == "EAR_LEFT"
    assert p.target_zone == "HEAD"
