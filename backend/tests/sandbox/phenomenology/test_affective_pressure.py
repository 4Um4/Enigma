"""
Файл: backend/tests/sandbox/phenomenology/test_affective_pressure.py
Назначение: Верификация трубы Аффективного Давления (ADR-O)
Зависимости: app.models.affect, app.models.cfrm, app.services.affective
Основные сущности: TestPressureDerivation, TestEmotionResolution, TestAffectivePipelineIntegration

Запуск: pytest backend/tests/sandbox/phenomenology/test_affective_pressure.py

TODO:
- Добавить тесты для крайних случаев, таких как полное отсутствие угрозы или сенсорной перегрузки.
- Включить тесты для различных комбинаций параметров ядра восприятия и состояния тела, чтобы убедиться в правильной работе формул.
- В будущем, по мере развития ADR-O, расширить тесты для покрытия новых эмоций и сценариев, таких как хронический стресс или травма.
"""

import pytest
from app.models.affect import AffectivePressureDTO
from app.models.npc_state import PerceptualKernel
from app.models.delta_payloads import EmotionPayload
from app.services.affective.pressure_derivation import derive_affective_pressure
from app.services.affective.emotion_resolution import resolve_emotion_from_pressure


class TestPressureDerivation:
    """Слой 1: Восприятие → Давление"""

    def test_high_threat_amplified_by_pain(self):
        kernel = PerceptualKernel(threat_gradient=0.8, compliance_bias=0.2, aggression_inhibition=0.5)
        body = {"pain": 60.0, "fatigue": 20.0}
        pressure = derive_affective_pressure(kernel, body)
        # 0.8 * 0.7 + 0.6 * 0.3 = 0.56 + 0.18 = 0.74
        assert pressure.threat_load == pytest.approx(0.74, abs=0.01)
        # (60/100 + 20/100) / 2 = 0.4
        assert pressure.sensory_overload == pytest.approx(0.4, abs=0.01)

    def test_aggression_charge_from_suppressed_inhibition(self):
        # Подавленная ингибиция → рост агрессии
        kernel = PerceptualKernel(aggression_inhibition=0.1, anomaly_score=0.2)
        body = {}
        pressure = derive_affective_pressure(kernel, body)
        # (1.0 - 0.1) * 0.5 + 0.2 * 0.5 = 0.45 + 0.1 = 0.55
        assert pressure.aggression_charge == pytest.approx(0.55, abs=0.01)


class TestEmotionResolution:
    """Слой 2: Давление → Эмоция"""

    def test_panic_condition_met(self):
        pressure = AffectivePressureDTO(threat_load=0.8, sensory_overload=0.6)
        psyche = {"fear": 0.8, "willpower": 0.2}
        # panic_threshold = 0.7 - (0.8 * 0.2) + (0.2 * 0.1) = 0.7 - 0.16 + 0.02 = 0.56
        # 0.8 > 0.56 and 0.6 > 0.4 → panic
        result = resolve_emotion_from_pressure(pressure, psyche)
        assert isinstance(result, EmotionPayload)
        assert result.emotion_tag == "panic"
        assert result.stress_delta > 0

    def test_no_emotion_when_calm(self):
        pressure = AffectivePressureDTO(threat_load=0.1, sensory_overload=0.1)
        psyche = {"fear": 0.5, "willpower": 0.5}
        result = resolve_emotion_from_pressure(pressure, psyche)
        assert result is None

    def test_rage_from_overload_and_low_will(self):
        pressure = AffectivePressureDTO(aggression_charge=0.8, threat_load=0.1, sensory_overload=0.1)
        psyche = {"fear": 0.1, "willpower": 0.2}
        result = resolve_emotion_from_pressure(pressure, psyche)
        assert result is not None
        assert result.emotion_tag == "rage"


class TestAffectivePipelineIntegration:
    """Вертикальный срез: Восприятие → Давление → Эмоция"""

    def test_broken_will_leads_to_panic(self):
        kernel = PerceptualKernel(
            threat_gradient=0.9,
            anomaly_score=0.3,
            compliance_bias=0.8,
            aggression_inhibition=0.9
        )
        body = {"pain": 80.0, "fatigue": 70.0}
        psyche = {"fear": 0.9, "willpower": 0.1}

        pressure = derive_affective_pressure(kernel, body)
        # threat_load = 0.9 * 0.7 + 0.8 * 0.3 = 0.63 + 0.24 = 0.87
        assert pressure.threat_load > 0.8

        emotion = resolve_emotion_from_pressure(pressure, psyche)
        # panic_threshold = 0.7 - (0.9 * 0.2) + (0.1 * 0.1) = 0.7 - 0.18 + 0.01 = 0.53
        # 0.87 > 0.53 and sensory > 0.4 → panic
        assert emotion is not None
        assert emotion.emotion_tag == "panic"