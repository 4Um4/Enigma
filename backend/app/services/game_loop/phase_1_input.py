# path: C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\game_loop\phase_1_input.py
"""
ФАЗА 1: Input — игрок → EventBus.

Устав 5.1: EventBus.publish() — единственная точка входа событий.
Все действия игрока публикуются здесь, нигде больше.


Назначение: ФАЗА 1 — публикация событий игрока на EventBus (Устав 5.1)
Зависимости: logging, app.domain.events.EventDTO, app.services.events.event_types.EventType, app.services.events.event_bus.get_event_bus
Основные сущности: publish_player_action, publish_player_speech
"""

import logging

from app.domain.events import EventDTO
from app.services.events.event_bus import get_event_bus
from app.services.events.event_types import EventType

logger = logging.getLogger(__name__)


def publish_player_action(
    player_name: str,
    player_text: str,
    action_type: str,
    location: str,
) -> None:
    """Публикация сырого действия игрока — PLAYER_INTERACTS.

    Вызывается рано в пайплайне, до классификации.
    Телеграфы не публикуются — технические маркеры, не действия.
    """
    if player_text.startswith("[TELEGRAPH"):
        return
    try:
        get_event_bus().publish(EventDTO.create(
            event_type=EventType.PLAYER_INTERACTS,
            source=player_name,
            payload={
                "content": player_text,
                "action_type": action_type,
                "location": location,
            },
            persistence_level="working",
        ))
        logger.debug(f"[EVENT_BUS] player_action → bus: {player_text[:50]}")
    except Exception as _bus_err:
        logger.debug(f"[EVENT_BUS] player_action publish skipped: {_bus_err}")


def publish_player_speech(
    player_name: str,
    action_text: str,
    classified_type: str,
) -> None:
    """Публикация вербального действия — PLAYER_SPOKE.

    Вызывается после Rules-агента, когда тип действия известен.
    """
    if not action_text:
        return
    try:
        get_event_bus().publish(EventDTO.create(
            event_type=EventType.PLAYER_SPOKE,
            source=player_name or "Игрок",
            payload={
                "content": action_text[:120],
                "action_type": classified_type,
            },
            persistence_level="working",
        ))
    except Exception as _bus_err:
        logger.debug(f"[EVENT_BUS] player_speech publish skipped: {_bus_err}")