"""
path: backend/tests/sandbox/micro/test_perception_decay_reduces_threat.py
Назначение: Верификация Rule 38 (Perception Decay уменьшает угрозу, ADR-138)
Зависимости: app.services.combat.physiology_decay_handler
Основные сущности: PhysiologyDecayHandler, PerceptionPayload

Запуск: cd backend; python -m pytest tests/sandbox/micro/test_perception_decay_reduces_threat.py -v --tb=short; cd ..
"""

from app.models.delta_payloads import PerceptionPayload
from app.models.state_delta import DeltaDomain
from app.services.combat.physiology_decay_handler import PhysiologyDecayHandler


def test_perception_decay_reduces_threat():
    """ДОКАЗЫВАЕТ: Активные причины (угроза/неопределённость) затухают во времени (Rule 38, ADR-138).

    Без этого PerceptualKernel застревает в состоянии вечного страха ("вечный двигатель страха").
    """
    handler = PhysiologyDecayHandler()

    # NPC с высокой угрозой в PerceptualKernel (реальный формат рантайма)
    npc_dict = {
        "npc_id": "test_npc",
        "body_state": {"pain": 0.0, "fatigue": 0.0, "blood_loss": 0.0, "shock_impulse": 0.0},
        "perceptual_kernel": {"threat_gradient": 0.8, "uncertainty": 0.5, "anomaly_score": 0.2},
    }

    results = handler.handle([npc_dict], campaign_id="test_campaign", current_tick=1)

    # Должна быть сгенерирована дельта распада
    assert len(results) > 0, "Rule 38 Нарушено: PhysiologyDecayHandler не генерирует дельты для распада угрозы"

    # Находим перцептивную дельту
    perception_delta = next((d for d in results if d.domain == DeltaDomain.PERCEPTION), None)
    assert perception_delta is not None, "Rule 38 Нарушено: Нет PerceptionPayload в дельтах распада"

    # Проверяем, что угроза уменьшается (дельта отрицательная)
    payload = perception_delta.payload
    assert isinstance(payload, PerceptionPayload)
    assert payload.threat_gradient_delta < 0.0, (
        f"Rule 38 Нарушено: Угроза не затухает, delta={payload.threat_gradient_delta} (должна быть < 0)"
    )
    assert payload.uncertainty_delta < 0.0, (
        f"Rule 38 Нарушено: Неопределённость не затухает, delta={payload.uncertainty_delta} (должна быть < 0)"
    )
