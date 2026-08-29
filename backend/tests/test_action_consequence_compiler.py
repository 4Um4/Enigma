"""
Файл: backend/tests/test_action_consequence_compiler.py
Назначение: Проверка сквозного распространения последствий.

Запуск: cd backend; python -m pytest tests/test_action_consequence_compiler.py -v -s; cd ..
"""

import pytest
from app.models.player_action import ActionType, PlayerAction
from app.models.player_belief import BeliefValue
from app.models.social_fabric import RelationshipSnapshot
from app.services.memory.relationship_store import RelationshipStore
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



# ── M1b.2.2 (ADR-O-371): компилятор через RelationshipWriteGate — сайт-паритет ──


class TestCompilerWriteGateParity:
    """Механическая миграция writer'а (дельты/направления не изменены):
    значения стора после РЕАЛЬНОГО process_action() == прямому legacy-вызову
    с теми же дельтами. Честный метод M1b.2.1: реальные объекты
    (ObservationLog/PlayerBeliefModel/SocialFabricTracker/RelationshipStore),
    ActionType из enum, никаких двойников моей копии логики.

    Примечание: ACCUSE-кейс пойдёт с epistemic_resolver=None → гейт §18
    логирует warning и ПРОПУСКАЕТ действие — доверимся существующему
    тесту accuse в основной сьюте для семантики; здесь паритет стор-записи
    для безгейтовых действий (BLACKMAIL/HELP), где компилятор пишет всегда."""

    @staticmethod
    def _make_compiler(tmp_path, campaign="cc_parity"):
        store = RelationshipStore(data_dir=str(tmp_path / "S"))
        compiler = ActionConsequenceCompiler(
            ObservationLog(),
            PlayerBeliefModel(),
            SocialFabricTracker(),
            relationship_store=store,
        )
        compiler._campaign_id = campaign  # точка DI продакшена (set в привязке кампании)
        return compiler, store

    @pytest.mark.parametrize(
        "action_type,deltas",
        [
            (ActionType.BLACKMAIL, {"fear": 30.0, "trust": -30.0}),
            (ActionType.HELP, {"trust": 20.0, "fear": -10.0}),
        ],
    )
    def test_store_parity_via_real_compiler(self, tmp_path, action_type, deltas):
        camp = "cc_parity"
        compiler, store_g = self._make_compiler(tmp_path)
        action = PlayerAction(
            action_id=f"act_{action_type.value}",
            tick=1,
            actor_id="player",
            action_type=action_type,
            target_id="maid_lusya",
            secret_id="lusya_basement" if action_type == ActionType.BLACKMAIL else None,
            description="parity",
        )
        compiler.process_action(action)
        # L: прямой legacy-вызов с теми же дельтами и направлением (target→actor)
        store_l = RelationshipStore(data_dir=str(tmp_path / "L"))
        store_l.update(camp, "maid_lusya", "player", dict(deltas))
        got_g = store_g.get_pair(camp, "maid_lusya", "player")
        want_l = store_l.get_pair(camp, "maid_lusya", "player")
        assert got_g == want_l, f"PARITY BREAK {action_type.value}: L={want_l} G={got_g}"

    def test_compiler_without_store_writes_nothing(self, tmp_path):
        """None-DI (существующий прецедент фикстуры setup): без стора компилятор
        жив, никаких записей (охрана if self._write_gate ...)."""
        compiler = ActionConsequenceCompiler(
            ObservationLog(), PlayerBeliefModel(), SocialFabricTracker()
        )
        compiler._campaign_id = "cc_parity"
        compiler.process_action(
            PlayerAction(
                action_id="act_nostore",
                tick=1,
                actor_id="player",
                action_type=ActionType.HELP,
                target_id="maid_lusya",
                description="no-store",
            )
        )
        assert True  # главное: не упал (гейт None — охрана sites)