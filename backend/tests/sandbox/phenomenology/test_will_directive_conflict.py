"""
ТЕСТ 2: ВОЛЯ: конфликт директив
Проверка: стресс от ломки паттерна, давление на идентичность.
"""

from app.domain.identity_events import EffectiveDrives

_MOCK_DRIVES = EffectiveDrives.from_dict({"control": 0.5, "significance": 0.5, "fear": 0.5, "desire": 0.5})

from app.domain.intent import IntentDTO
from app.services.will import resolve_intent_pressure


def test_will_directive_conflict():
    intent_move = IntentDTO(action="player_moves", target="npc_test")
    pressure_move = resolve_intent_pressure(intent_move)

    # Теперь player_social должен генерировать давление (ADR-031)
    intent_defy = IntentDTO(action="player_social", target="npc_test")
    pressure_defy = resolve_intent_pressure(intent_defy)

    # Ключевой сигнал: Социальное давление должно быть больше нуля
    assert pressure_defy.identity_deviation > 0.0, "Социальная директива должна давить на идентичность"
    assert pressure_defy.social_exposure > 0.0, "Социальная директива должна создавать социальную экспозицию"
