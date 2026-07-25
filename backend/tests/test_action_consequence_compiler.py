"""
Файл: backend/tests/test_action_consequence_compiler.py
Назначение: Проверка сквозного распространения последствий.

Запуск: cd backend; python -m pytest tests/test_action_consequence_compiler.py -v -s; cd ..
"""

import pytest
from app.models.player_action import ActionType, PlayerAction
from app.models.player_belief import BeliefValue
from app.models.social_fabric import RelationshipSnapshot
from app.services.player_cognition.action_consequence_compiler import ActionConsequenceCompiler
from app.services.player_cognition.observation_log import ObservationLog
from app.services.player_cognition.player_belief_model import PlayerBeliefModel
from app.services.social.social_fabric_tracker import SocialFabricTracker


class TestActionConsequenceCompiler:
    """Тесты компилятора последствий (Каузальный мост)."""

    @pytest.fixture
    def setup(self):
        log = ObservationLog()
        model = PlayerBeliefModel()
        fabric = SocialFabricTracker()
        
        fabric.set_baseline("maid_lusya", "player", RelationshipSnapshot(
            source_id="maid_lusya", target_id="player", trust=20.0, fear=10.0, affection=0.0, debt=0.0, respect=10.0
        ))
        
        compiler = ActionConsequenceCompiler(log, model, fabric)
        return compiler, log, model, fabric

    def test_blackmail_propagates_through_all_layers(self, setup):
        """Шантаж распространяется через Наблюдение -> Доказательство -> Убеждение -> Социум."""
        compiler, log, model, fabric = setup
        
        action = PlayerAction(
            action_id="act_001",
            tick=1,
            actor_id="player",
            action_type=ActionType.BLACKMAIL,
            target_id="maid_lusya",
            secret_id="lusya_basement",
            description="Я знаю про подвал"
        )
        compiler.process_action(action)
        
        # 1. Наблюдение записано
        obs_list = log.get_all()
        assert len(obs_list) == 1
        assert obs_list[0].observation_type == "blackmail"
        
        # 2. Убеждение игрока стало TRUE через честный инференс
        belief = model.get_belief_for_secret("lusya_basement")
        assert belief is not None
        assert belief.belief_value == BeliefValue.TRUE
        assert belief.support_mass == 1.0
        
        # 3. Социальная ткань изменилась
        snap = fabric.get_current("maid_lusya", "player")
        assert snap.trust == -10.0
        assert snap.fear == 40.0

    def test_help_improves_relationship_but_no_belief(self, setup):
        """Помощь улучшает отношения, но не формирует уверенности в секрете."""
        compiler, log, model, fabric = setup
        
        action = PlayerAction(
            action_id="act_002",
            tick=2,
            actor_id="player",
            action_type=ActionType.HELP,
            target_id="maid_lusya",
            secret_id="lusya_basement"
        )
        compiler.process_action(action)
        
        belief = model.get_belief_for_secret("lusya_basement")
        assert belief is None or belief.belief_value != BeliefValue.TRUE
        
        snap = fabric.get_current("maid_lusya", "player")
        assert snap.trust == 40.0
        assert snap.fear == 0.0

    def test_action_processing_is_idempotent(self, setup):
        """Инвариант: Повторная обработка того же action_id не вызывает сбоев."""
        compiler, log, model, fabric = setup
        
        action = PlayerAction(
            action_id="act_003",
            tick=3,
            actor_id="player",
            action_type=ActionType.BLACKMAIL,
            target_id="maid_lusya",
            secret_id="lusya_basement"
        )
        
        compiler.process_action(action)
        compiler.process_action(action) # Повтор
        
        # Должна быть только 1 запись в логе
        assert len(log.get_all()) == 1
        
        # Социальная ткань не должна получить двойной штраф
        snap = fabric.get_current("maid_lusya", "player")
        assert snap.trust == -10.0 # 20 - 30 (не -40)
        assert snap.fear == 40.0   # 10 + 30 (не 70)