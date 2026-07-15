"""
path:
Назначение: Верификация ADR-057 Legitimacy Gate. Доказывает, что при высоком страхе NPC подчиняется, а при его отсутствии — раздражается и снимает блоки агрессии.
Зависимости: DirectiveInterpretationSubscriber
Основные сущности: obedience_intensity, irritation_intensity, is_obedience

ЗАПУСК: python -m pytest backend/tests/sandbox/test_legitimacy_gate.py backend/tests/sandbox/test_schedule_locomotion.py backend/tests/sandbox/test_lod0_collision_avoidance.py -v --tb=short
"""

import pytest
from app.domain.identity_events import EffectiveDrives

_MOCK_DRIVES = EffectiveDrives.from_dict({"control": 0.5, "significance": 0.5, "fear": 0.5, "desire": 0.5})

from app.models.state_delta import DeltaDomain
from app.services.social.directive_interpretation_subscriber import DirectiveInterpretationSubscriber


@pytest.fixture
def subscriber():
    return DirectiveInterpretationSubscriber()


def test_fearful_npc_submits(subscriber):
    """ДОКАЗЫВАЕТ: NPC с высоким страхом подчиняется (Obedience)."""
    event = type(
        "Event",
        (),
        {"payload": {"semantic_action": "MOVE", "target_id": "npc_1", "social_pressure": 0.8}, "source": "player"},
    )()
    npc_states = [
        {
            "npc_id": "npc_1",
            "social_stats": {"fear_of_player": 0.8, "trust": 0.0},
            "body_state": {"disabled": False, "shock_impulse": 0.0},
        }
    ]  # Высокий страх + валидное тело

    deltas = subscriber.handle(event, npc_states)
    identity_delta = next((d for d in deltas if d.domain == DeltaDomain.IDENTITY), None)

    assert identity_delta is not None
    payload = identity_delta.payload

    # Ожидаем вектор подчинения
    assert payload.compliance_bias_delta > 0, "БАГ: Страшный NPC не склоняется к подчинению"
    assert payload.aggression_inhibition_delta > 0, "БАГ: Страшный NPC не подавляет агрессию"
    assert payload.recent_directive_data["is_obedience"] is True, "БАГ: Флаг подчинения не установлен"
    assert payload.recent_directive_data["interrupts_routine"] is True


def test_brave_npc_gets_annoyed(subscriber):
    """ДОКАЗЫВАЕТ: NPC без страха и доверия раздражается (Irritation). Он подходит неохотно, чтобы высказать."""
    event = type(
        "Event",
        (),
        {"payload": {"semantic_action": "MOVE", "target_id": "npc_2", "social_pressure": 0.8}, "source": "player"},
    )()
    npc_states = [
        {
            "npc_id": "npc_2",
            "social_stats": {"fear_of_player": 0.05, "trust": 5},
            "body_state": {"disabled": False, "shock_impulse": 0.0},
        }
    ]  # Низкий страх + валидное тело

    deltas = subscriber.handle(event, npc_states)
    identity_delta = next((d for d in deltas if d.domain == DeltaDomain.IDENTITY), None)

    assert identity_delta is not None
    payload = identity_delta.payload

    # Ожидаем вектор раздражения: слабое подталкивание к подходу (чтобы высказать), слабый контроль гнева
    assert 0 < payload.compliance_bias_delta < 0.5, (
        "БАГ: Храбрый NPC слишком подчиняется или наоборот сопротивляется подходу"
    )
    assert 0 < payload.aggression_inhibition_delta < 0.5, (
        "БАГ: Храбрый NPC полностью подавляет агрессию или наоборот слишком её разблокирует"
    )
    assert payload.recent_directive_data["is_obedience"] is False, "БАГ: Флаг подчинения установлен для храброго NPC"
    assert payload.recent_directive_data["interrupts_routine"] is True, (
        "БАГ: Храбрый NPC не прерывает бытовуху для реакции"
    )
