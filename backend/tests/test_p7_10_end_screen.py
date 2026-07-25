"""
Файл: backend/tests/test_p7_10_end_screen.py
Назначение: Проверка сборки данных для финального экрана.
"""

import pytest
from app.services.social.end_screen_builder import EndScreenDataBuilder
from app.services.social.fate_tracker import FateTracker
from app.services.social.last_words_system import LastWordsSystem
from app.services.social.social_fabric_tracker import SocialFabricTracker
from app.models.evaluation import EvaluationResult, SecretEvaluation
from app.models.cognitive_dissonance import Contradiction
from app.models.fate import FateOutcome
from app.models.social_fabric import RelationshipSnapshot
from app.models.last_words import LastWordTone

class TestP710EndScreen:
    @pytest.fixture
    def setup(self):
        # Мокаем EvaluationResult (контракт P7-08: score = identified*10 - misidentified*5 + causal*2)
        evaluation = EvaluationResult(
            secrets_total=16, secrets_identified=1, secrets_misidentified=0, secrets_missed=15,
            causal_links_total=20, causal_links_identified=0,
            methods_used={"blackmail": 1},
            per_secret_results=[SecretEvaluation("lusya_basement", 1.0, True, False, ("blackmail",))]
        )
        
        contradictions = [
            Contradiction(contradiction_id="c1", action_a_id="a1", action_b_id="a2", description="test", emotional_weight=0.5)
        ]
        
        fate = FateTracker()
        fate.update_state("maid_lusya", stability=0.1, threat=0.9)
        fate.trigger_fate("maid_lusya", FateOutcome.ESCAPE, tick=10, cause="test", description="test")
        
        fabric = SocialFabricTracker()
        fabric.set_baseline("maid_lusya", "player", RelationshipSnapshot(
            source_id="maid_lusya", target_id="player", trust=80.0, fear=0.0, affection=0.0, debt=0.0, respect=0.0
        ))
        
        last_words_sys = LastWordsSystem()
        
        return evaluation, contradictions, fate, last_words_sys, fabric

    def test_end_screen_assembles_all_data(self, setup):
        """EndScreenData корректно объединяет результаты без WorldStateDiff."""
        eval_res, contr, fate, lw_sys, fabric = setup
        builder = EndScreenDataBuilder()
        
        end_screen = builder.build(eval_res, contr, fate, lw_sys, fabric)
        
        # Проверяем оценку (контракт P7-08: 1*10 - 0*5 + 0*2 = 10)
        assert end_screen.evaluation.score == 10
        assert len(end_screen.contradictions) == 1
        
        # Проверяем, что последние слова подтянулись
        assert len(end_screen.npc_fates) == 1
        assert end_screen.npc_fates[0].npc_id == "maid_lusya"
        assert end_screen.npc_fates[0].fate_outcome == "escape"
        assert end_screen.npc_fates[0].last_word is not None
        assert end_screen.npc_fates[0].last_word.tone == LastWordTone.GRATEFUL