# path: backend/tests/test_will.py
# Назначение: Тестирование IntentPressureResolver и WillpowerGate (ADR-031)
"""
ЗАПУСК: pytest backend/tests/test_will.py

TODO: расширить тесты, покрыть больше сценариев и крайних случаев.
Пока что эти тесты проверяют базовую логику трансформации намерений вдавление и реакции воли, но не охватывают все нюансы психики и типов давления.
"""

from app.domain.intent import IntentDTO
from app.models.will import IntentPressureProfile, WillState
from app.services.will import compute_willpower, resolve_intent_pressure


class TestIntentPressureResolver:
    """Тесты трансляции синтаксиса в семантику давления."""

    def test_attack_generates_high_violence(self):
        intent = IntentDTO(action="attack", target="guard")
        pressure = resolve_intent_pressure(intent)
        assert pressure.violence > 0.5
        assert pressure.identity_deviation > 0.5

    def test_talk_is_low_pressure(self):
        intent = IntentDTO(action="talk", target="npc_lucy")
        pressure = resolve_intent_pressure(intent)
        assert pressure.violence == 0.0
        assert pressure.identity_deviation < 0.1

    def test_flee_generates_social_exposure(self):
        intent = IntentDTO(action="flee", target="")
        pressure = resolve_intent_pressure(intent)
        assert pressure.social_exposure > 0.5
        assert pressure.identity_deviation > 0.3


class TestWillpowerGate:
    """Тесты Cumulative Strain Model."""

    def test_coward_panics_on_risk(self):
        """Трусливый аватар впадает в панику при риске."""
        pressure = IntentPressureProfile(self_risk=0.8)
        coward_psyche = {"fear": 0.9, "conviction": 0.1, "identity_rigidity": 0.2}
        response = compute_willpower(pressure, coward_psyche)
        assert response.state in (WillState.PANICKED, WillState.DISTRESSED, WillState.BROKEN)
        assert response.resistance > 0.5

    def test_aggressor_complies_with_violence(self):
        """Агрессивный аватар легко подчиняется насилию."""
        pressure = IntentPressureProfile(violence=0.8, identity_deviation=0.5)
        aggressor_psyche = {"aggression": 0.9, "fear": 0.1, "identity_rigidity": 0.3}
        response = compute_willpower(pressure, aggressor_psyche)
        # Агрессия вычитается из сопротивления
        assert response.state in (WillState.COMPLY, WillState.RELUCTANT)
        assert response.resistance < 0.5

    def test_stoic_resists_humiliation(self):
        """Стоик сопротивляется унижению."""
        pressure = IntentPressureProfile(humiliation=0.8, identity_deviation=0.7)
        stoic_psyche = {"shame": 0.8, "identity_rigidity": 0.9, "conviction": 0.8}
        response = compute_willpower(pressure, stoic_psyche)
        assert response.state in (WillState.DISTRESSED, WillState.PANICKED, WillState.DISSOCIATING)
        assert response.resistance > 0.6

    def test_zero_pressure_means_comply(self):
        """Отсутствие давления = полное согласие."""
        pressure = IntentPressureProfile()
        psyche = {"fear": 0.5, "identity_rigidity": 0.5}
        response = compute_willpower(pressure, psyche)
        assert response.state == WillState.COMPLY
        assert response.resistance == 0.0

    def test_counter_offer_on_resistance(self):
        """При сильном сопротивлении авар предлагает альтернативу."""
        pressure = IntentPressureProfile(violence=0.9)
        psyche = {"fear": 0.9, "aggression": 0.1}  # Трус перед насилием
        response = compute_willpower(pressure, psyche)
        if response.state not in (WillState.COMPLY, WillState.RELUCTANT):
            assert response.counter_offer is not None
            assert response.counter_offer.action == "flee"
