"""
Файл: backend/tests/test_p7_07_dilemma_engine.py
Назначение: Проверка активации и разрешения дилемм.

Запуск: cd backend; python -m pytest tests/test_p7_07_dilemma_engine.py -v -s; cd ..
"""

import pytest
from app.services.social.dilemma_engine import DilemmaEngine
from app.models.dilemma import MoralDilemma, DilemmaSide, FateConsequence, DilemmaChoice
from app.models.fate import FateOutcome

class TestP707DilemmaEngine:
    @pytest.fixture
    def engine(self) -> DilemmaEngine:
        e = DilemmaEngine()
        side_a = DilemmaSide(
            label="Сдать страже", description="Арест", npcs_affected=["guard_borko"],
            npcs_betrayed=["maid_lusya"], moral_weight=0.8,
            consequences=[FateConsequence(npc_id="maid_lusya", outcome=FateOutcome.IMPRISONED, description="Арестована", tick_delay=0)]
        )
        side_b = DilemmaSide(
            label="Молчать", description="Прикрыть", npcs_affected=["maid_lusya"],
            npcs_betrayed=[], moral_weight=0.3,
            consequences=[]
        )
        dilemma = MoralDilemma(
            dilemma_id="lusya_basement_dilemma",
            trigger_condition="lusya_basement",
            sides={DilemmaChoice.SIDE_A: side_a, DilemmaChoice.SIDE_B: side_b},
            philosophical_question="Что важнее: закон или милосердие?"
        )
        e.register_dilemma(dilemma)
        return e

    def test_dilemma_triggered_by_secret(self, engine):
        triggered = engine.check_triggers(["lusya_basement"])
        assert len(triggered) == 1
        assert triggered[0].dilemma_id == "lusya_basement_dilemma"

    def test_cannot_resolve_untriggered_dilemma(self, engine):
        """Инвариант: Нельзя разрешить неактивированную дилемму (каузальность)."""
        with pytest.raises(ValueError, match="not triggered"):
            engine.resolve("lusya_basement_dilemma", DilemmaChoice.SIDE_A, tick=1)

    def test_cannot_resolve_with_invalid_choice(self, engine):
        """Инвариант: Нельзя выбрать несуществующую сторону."""
        engine.check_triggers(["lusya_basement"])
        with pytest.raises(ValueError, match="Invalid choice"):
            engine.resolve("lusya_basement_dilemma", DilemmaChoice.SIDE_C, tick=1)

    def test_resolution_is_irreversible(self, engine):
        """Инвариант: Разрешение необратимо."""
        engine.check_triggers(["lusya_basement"])
        engine.resolve("lusya_basement_dilemma", DilemmaChoice.SIDE_A, tick=1)
        
        with pytest.raises(ValueError, match="already resolved"):
            engine.resolve("lusya_basement_dilemma", DilemmaChoice.SIDE_A, tick=2)

    def test_resolve_returns_consequences(self, engine):
        """Разрешение возвращает DilemmaResolution с последствиями."""
        engine.check_triggers(["lusya_basement"])
        resolution = engine.resolve("lusya_basement_dilemma", DilemmaChoice.SIDE_A, tick=5)
        
        assert resolution.choice == DilemmaChoice.SIDE_A
        assert resolution.tick == 5
        assert len(resolution.consequences) == 1
        assert resolution.consequences[0].outcome == FateOutcome.IMPRISONED