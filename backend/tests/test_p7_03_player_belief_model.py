"""
Файл: backend/tests/test_p7_03_player_belief_model.py
Назначение: Проверка логики инференса (накопление confidence, смена BeliefValue, прямой шантаж).

Запуск: cd backend; python -m pytest tests/test_p7_03_player_belief_model.py -v -s; cd ..
"""

import pytest
from app.models.observation import EvidencePolarity, ObservationSourceType
from app.models.player_belief import BeliefValue
from app.services.player_cognition.observation_log import ObservationLog
from app.services.player_cognition.player_belief_model import PlayerBeliefModel


class TestP703PlayerBeliefModel:
    """P7-03: Тесты модели убеждений игрока (Строгий инференс)."""

    @pytest.fixture
    def log(self) -> ObservationLog:
        return ObservationLog()

    @pytest.fixture
    def model(self) -> PlayerBeliefModel:
        return PlayerBeliefModel()

    def test_initial_state_is_empty(self, model: PlayerBeliefModel):
        assert model.get_confidence_for_secret("lusya_basement") == 0.0
        assert model.get_belief_for_secret("lusya_basement") is None

    def test_support_accumulates(self, log: ObservationLog, model: PlayerBeliefModel):
        """Поддержка накапливается симметрично (без насыщения)."""
        obs1 = log.add(tick=1, observation_type="x", content="y", source_id="z", source_type=ObservationSourceType.NPC)
        ev1 = log.add_evidence(obs1.observation_id, "sec1", 0.6, EvidencePolarity.SUPPORTS)
        model.update_from_evidence(obs1, ev1)
        
        assert model.get_belief_for_secret("sec1").support_mass == 0.6
        
        obs2 = log.add(tick=2, observation_type="x", content="y2", source_id="z", source_type=ObservationSourceType.NPC)
        ev2 = log.add_evidence(obs2.observation_id, "sec1", 0.6, EvidencePolarity.SUPPORTS)
        model.update_from_evidence(obs2, ev2)
        
        assert model.get_belief_for_secret("sec1").support_mass == 1.2

    def test_contradiction_reduces_confidence(self, log: ObservationLog, model: PlayerBeliefModel):
        """Противоречие снижает уверенность."""
        obs1 = log.add(tick=1, observation_type="x", content="y", source_id="z", source_type=ObservationSourceType.NPC)
        ev1 = log.add_evidence(obs1.observation_id, "sec1", 0.8, EvidencePolarity.SUPPORTS)
        model.update_from_evidence(obs1, ev1)
        
        assert model.get_confidence_for_secret("sec1") == 0.8
        
        obs2 = log.add(tick=2, observation_type="x", content="y2", source_id="z", source_type=ObservationSourceType.NPC)
        ev2 = log.add_evidence(obs2.observation_id, "sec1", 0.5, EvidencePolarity.CONTRADICTS)
        model.update_from_evidence(obs2, ev2)
        
        assert model.get_confidence_for_secret("sec1") == pytest.approx(0.3)

    def test_belief_reversal_to_false(self, log: ObservationLog, model: PlayerBeliefModel):
        """Сильное противоречие меняет убеждение на FALSE."""
        obs1 = log.add(tick=1, observation_type="x", content="y", source_id="z", source_type=ObservationSourceType.NPC)
        ev1 = log.add_evidence(obs1.observation_id, "sec1", 0.9, EvidencePolarity.SUPPORTS)
        model.update_from_evidence(obs1, ev1)
        assert model.get_belief_for_secret("sec1").belief_value == BeliefValue.TRUE
        
        obs2 = log.add(tick=2, observation_type="x", content="y2", source_id="z", source_type=ObservationSourceType.NPC)
        ev2 = log.add_evidence(obs2.observation_id, "sec1", 0.9, EvidencePolarity.CONTRADICTS)
        model.update_from_evidence(obs2, ev2)
        # support=0.9, contradiction=0.9 -> net=0.0 -> UNKNOWN
        
        obs3 = log.add(tick=3, observation_type="x", content="y3", source_id="z", source_type=ObservationSourceType.NPC)
        ev3 = log.add_evidence(obs3.observation_id, "sec1", 0.9, EvidencePolarity.CONTRADICTS)
        model.update_from_evidence(obs3, ev3)
        # support=0.9, contradiction=1.8 -> net=-0.9 -> FALSE
        assert model.get_belief_for_secret("sec1").belief_value == BeliefValue.FALSE

    def test_evidence_idempotency(self, log: ObservationLog, model: PlayerBeliefModel):
        """Повторная обработка того же наблюдения не меняет массы."""
        obs1 = log.add(tick=1, observation_type="x", content="y", source_id="z", source_type=ObservationSourceType.NPC)
        ev1 = log.add_evidence(obs1.observation_id, "sec1", 0.5, EvidencePolarity.SUPPORTS)
        
        model.update_from_evidence(obs1, ev1)
        initial_mass = model.get_belief_for_secret("sec1").support_mass
        
        model.update_from_evidence(obs1, ev1) # Повтор
        assert model.get_belief_for_secret("sec1").support_mass == initial_mass

    def test_contradictory_evidence_preserves_history(self, log: ObservationLog, model: PlayerBeliefModel):
        """Противоречивые доказательства не стирают историю, а суммируются (support vs contradiction)."""
        obs1 = log.add(tick=1, observation_type="x", content="y", source_id="z", source_type=ObservationSourceType.NPC)
        ev1 = log.add_evidence(obs1.observation_id, "sec1", 0.9, EvidencePolarity.SUPPORTS)
        model.update_from_evidence(obs1, ev1)
        assert model.get_belief_for_secret("sec1").belief_value == BeliefValue.TRUE
        
        obs2 = log.add(tick=2, observation_type="x", content="y2", source_id="z", source_type=ObservationSourceType.NPC)
        ev2 = log.add_evidence(obs2.observation_id, "sec1", 0.9, EvidencePolarity.CONTRADICTS)
        model.update_from_evidence(obs2, ev2)
        assert model.get_belief_for_secret("sec1").belief_value == BeliefValue.UNKNOWN
        assert model.get_belief_for_secret("sec1").support_mass == 0.9
        assert model.get_belief_for_secret("sec1").contradiction_mass == 0.9
        
        obs3 = log.add(tick=3, observation_type="x", content="y3", source_id="z", source_type=ObservationSourceType.NPC)
        ev3 = log.add_evidence(obs3.observation_id, "sec1", 0.9, EvidencePolarity.SUPPORTS)
        model.update_from_evidence(obs3, ev3)
        # support=1.8, contradiction=0.9 -> net=0.9 -> TRUE
        assert model.get_belief_for_secret("sec1").belief_value == BeliefValue.TRUE
        assert model.get_belief_for_secret("sec1").support_mass == 1.8

    def test_direct_evidence_blackmail(self, model: PlayerBeliefModel):
        """Прямое доказательство (шантаж) добавляет поддержку. Требует evidence_id."""
        model.register_direct_evidence("goran_contraband", EvidencePolarity.SUPPORTS, 1.0, evidence_id="blackmail_001")
        belief = model.get_belief_for_secret("goran_contraband")
        assert belief is not None
        assert belief.support_mass == 1.0
        assert belief.belief_value == BeliefValue.TRUE
        
        # Идемпотентность по evidence_id
        model.register_direct_evidence("goran_contraband", EvidencePolarity.SUPPORTS, 1.0, evidence_id="blackmail_001")
        assert belief.support_mass == 1.0

        # Новое событие накапливается
        model.register_direct_evidence("goran_contraband", EvidencePolarity.SUPPORTS, 0.5, evidence_id="blackmail_002")
        assert model.get_belief_for_secret("goran_contraband").support_mass == 1.5