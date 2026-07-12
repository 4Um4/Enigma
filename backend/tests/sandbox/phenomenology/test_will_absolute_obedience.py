"""
ТЕСТ 1: ВОЛЯ: абсолютное подчинение
Проверка: дискретность давления, отсутствие кэширования.
"""

from app.domain.intent import IntentDTO
from app.models.will import IntentPressureProfile
from app.services.will import resolve_intent_pressure


def test_will_absolute_obedience():
    intent_approach = IntentDTO(action="player_moves", target="npc_test")
    pressure_1 = resolve_intent_pressure(intent_approach)
    assert isinstance(pressure_1, IntentPressureProfile)

    intent_halt = IntentDTO(action="player_threatens", target="npc_test")
    pressure_2 = resolve_intent_pressure(intent_halt)

    pressure_3 = resolve_intent_pressure(intent_approach)

    # Ключевой сигнал: Давление не накапливается батчами. Отмена приказа имеет другую структуру.
    assert (
        pressure_2.identity_deviation != pressure_1.identity_deviation
        or pressure_2.moral_violation > pressure_1.moral_violation
    )
    # Повторное подчинение не кэширует старое давление
    assert pressure_3.identity_deviation == pressure_1.identity_deviation
