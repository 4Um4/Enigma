"""
Rule 58 (ADR-130): _context_relevance() ОБЯЗАН проверять payload["target_id"]
как fallback при EventContext.target_id is None. Без этого ВСЕ NPC в зоне
получают бонус APPROACH/TALK/OBSERVE при команде игроку (G2: Uninvited NPC Approach).

Запуск:cd backend; python -m pytest tests/sandbox/movement/ -v --tb=short; cd ..

TODO:

"""

from types import SimpleNamespace

from app.domain.identity_events import EffectiveDrives

_MOCK_DRIVES = EffectiveDrives.from_dict({"control": 0.5, "significance": 0.5, "fear": 0.5, "desire": 0.5})

from app.services.events.event_types import EventType
from app.services.npc.decision_hub import DecisionHub, EventContext, Intent

# _context_relevance использует base=0.5 (нейтральная релевантность).
# Тест проверяет, что БОНУС (сверх 0.5) получают только целевые NPC.
_BASE_RELEVANCE = 0.5


def test_target_id_payload_fallback_prevents_uninvited_approach():
    """
    Сценарий G2: Игрок обращается к guard_1. EventContext.target_id = None,
    но payload содержит target_id="guard_1".
    guard_1 должен получить бонус (is_targeted=True).
    guard_2 НЕ должен получить бонус (is_targeted=False).
    """
    hub = DecisionHub()

    # Событие: игрок взаимодействует. EventContext.target_id = None (dm_scene_builder разрыв),
    # но payload содержит target_id (dm_phase.py пишет).
    # ВАЖНО: event_type должен быть EventType enum, не строка — иначе сравнение не сработает!
    event = EventContext(
        actor_id="player",
        event_type=EventType.PLAYER_INTERACTS,
        intensity=0.5,
        distance=1.0,
        witness_count=1,
        location="tavern",
        day=1,
        target_id=None,  # Разрыв!
        payload={"target_id": "guard_1"},  # Fallback источник
    )

    # Используем SimpleNamespace для NPCState (минимальный мок для проверки npc_id)
    state_targeted = SimpleNamespace(npc_id="guard_1")
    state_uninvited = SimpleNamespace(npc_id="guard_2")

    # Рассчитываем релевантность для целевого NPC
    # ВАЖНО: Intent enum, не строка — _context_relevance сравнивает с Intent.TALK.value
    relevance_targeted = hub._context_relevance(
        intent=Intent.TALK.value, event=event, state=state_targeted, personality=None
    )

    # Рассчитываем релевантность для незваного NPC
    relevance_uninvited = hub._context_relevance(
        intent=Intent.TALK.value, event=event, state=state_uninvited, personality=None
    )

    # VERDICT: Целевой NPC получает бонус (больше базового 0.5), незваный — нет
    assert relevance_targeted > _BASE_RELEVANCE, (
        f"Целевой NPC (guard_1) НЕ получил бонус! Relevance={relevance_targeted}, expected > {_BASE_RELEVANCE}"
    )
    assert relevance_uninvited == _BASE_RELEVANCE, (
        f"Незваный NPC (guard_2) получил бонус! DOUBLE TRUTH! Relevance={relevance_uninvited}, expected {_BASE_RELEVANCE}"
    )


def test_no_fallback_when_target_id_in_event_context():
    """
    Если EventContext.target_id задан напрямую, fallback на payload
    не должен переопределять или ломать логику.
    """
    hub = DecisionHub()

    event = EventContext(
        actor_id="player",
        event_type=EventType.PLAYER_INTERACTS,
        intensity=0.5,
        distance=1.0,
        witness_count=1,
        location="tavern",
        day=1,
        target_id="guard_1",  # Прямой путь
        payload={},  # Пустой payload
    )

    state_targeted = SimpleNamespace(npc_id="guard_1")
    state_uninvited = SimpleNamespace(npc_id="guard_2")

    relevance_targeted = hub._context_relevance(Intent.TALK.value, event, state_targeted, None)
    relevance_uninvited = hub._context_relevance(Intent.TALK.value, event, state_uninvited, None)

    assert relevance_targeted > _BASE_RELEVANCE, "Прямой target_id не работает!"
    assert relevance_uninvited == _BASE_RELEVANCE, "Незваный NPC получил бонус при прямом target_id!"
