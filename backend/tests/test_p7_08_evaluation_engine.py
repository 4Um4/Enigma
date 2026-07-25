"""
Файл: backend/tests/test_p7_08_evaluation_engine.py
Назначение: Проверка логики оценки (угаданные, пропущенные, ошибочные секреты).

Запуск: cd backend; python -m pytest tests/test_p7_08_evaluation_engine.py -v -s; cd ..
"""

from pathlib import Path

import pytest
from app.models.observation import EvidencePolarity, ObservationSourceType
from app.models.player_belief import BeliefValue
from app.services.player_cognition.observation_log import ObservationLog
from app.services.player_cognition.player_belief_model import PlayerBeliefModel
from app.services.social.evaluation_engine import EvaluationEngine
from app.services.truth_state_loader import TruthStateLoader

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CANON_PATH = BASE_DIR / "config" / "canon" / "truth_state_tavern.json"

class TestP708EvaluationEngine:
    """P7-08: Тесты движка оценки."""
    
    @pytest.fixture(scope="class")
    def truth_state(self):
        state = TruthStateLoader.load(CANON_PATH)
        TruthStateLoader.validate(state)
        return state

    @pytest.fixture
    def log(self):
        return ObservationLog()

    @pytest.fixture
    def model(self):
        return PlayerBeliefModel()

    @pytest.fixture
    def engine(self):
        return EvaluationEngine()

    def test_all_secrets_missed(self, truth_state, model, log, engine):
        """Игрок ничего не нашел."""
        result = engine.evaluate(truth_state, model, log)
        assert result.secrets_identified == 0
        assert result.secrets_missed == 16
        assert result.score == 0

    def test_secret_identified_correctly(self, truth_state, model, log, engine):
        """Игрок правильно угадал секрет (TRUE)."""
        obs = log.add(tick=1, observation_type="eavesdrop", content="Видел подвал", source_id="maid_lusya", source_type=ObservationSourceType.NPC)
        ev = log.add_evidence(obs.observation_id, "lusya_basement", 0.9, EvidencePolarity.SUPPORTS)
        model.update_from_evidence(obs, ev)
        
        result = engine.evaluate(truth_state, model, log)
        assert result.secrets_identified == 1
        assert result.secrets_missed == 15
        assert result.secrets_misidentified == 0
        
        # Проверяем методы (все использованные)
        assert result.methods_used.get("eavesdrop") == 1
        assert "eavesdrop" in result.per_secret_results[0].discovery_methods

    def test_secret_misidentified_as_false(self, truth_state, model, log, engine):
        """Игрок ошибочно уверен, что секрета нет (FALSE)."""
        model.register_direct_evidence("lusya_basement", EvidencePolarity.CONTRADICTS, 1.0, evidence_id="test_001")
        
        result = engine.evaluate(truth_state, model, log)
        assert result.secrets_identified == 0
        assert result.secrets_misidentified == 1
        assert result.secrets_missed == 15
        assert result.score == 0 # Штраф за ошибку

    def test_causal_links_not_evaluated_yet(self, truth_state, model, log, engine):
        """Каузальные связи требуют PlayerCausalModel, пока не оцениваются."""
        model.register_direct_evidence("lusya_basement", EvidencePolarity.SUPPORTS, 1.0, evidence_id="t1")
        model.register_direct_evidence("tornin_basement", EvidencePolarity.SUPPORTS, 1.0, evidence_id="t2")
        
        result = engine.evaluate(truth_state, model, log)
        assert result.secrets_identified == 2
        # Даже если игрок знает оба секрета, каузальная связь не считается установленной
        assert result.causal_links_identified == 0