"""
Файл: backend/tests/test_action_semantic_resolver.py
Назначение: Unit-тест эвристики ActionSemanticResolver.
Запуск: cd backend; python -m pytest tests/test_action_semantic_resolver.py -v; cd ..
"""

import pytest
from app.services.player_cognition.action_semantic_resolver import ActionSemanticResolver
from app.models.player_action import ActionType

class TestActionSemanticResolver:
    @pytest.fixture
    def resolver(self) -> ActionSemanticResolver:
        return ActionSemanticResolver()

    def test_parses_blackmail_lusya_basement(self, resolver: ActionSemanticResolver):
        action = resolver.resolve("Я шантажирую тебя, я знаю про подвал!", tick=1, target_id="maid_lusya")
        assert action.action_type == ActionType.BLACKMAIL
        assert action.secret_id == "lusya_basement"
        assert action.target_id == "maid_lusya"

    def test_parses_help_tornin(self, resolver: ActionSemanticResolver):
        action = resolver.resolve("Я хочу помочь тебе с долгом", tick=2, target_id="tavern_keeper_tornin")
        assert action.action_type == ActionType.HELP
        assert action.secret_id == "tornin_debt"
        
    def test_parses_dialogue_no_secret(self, resolver: ActionSemanticResolver):
        action = resolver.resolve("Привет, Люся", tick=3, target_id="maid_lusya")
        assert action.action_type == ActionType.DIALOGUE
        assert action.secret_id is None