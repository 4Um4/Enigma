from typing import Any, Dict, List, Optional

# backend/app/services/events/__init__.py
#
# Устав §5.1: EventBus + подписчики — единая точка входа событий.
from app.services.events.event_bus import EventBus, get_event_bus, reset_event_bus
from app.services.events.event_types import EventType
# P0 Audit Fix: PerceptionSubscriber удалён. Восприятие перенесено в LocalCausalSolver (Фаза 9).
from app.services.events.social_subscriber import SocialSubscriber

__all__ = [
    "EventBus",
    "EventType",
    "get_event_bus",
    "reset_event_bus",
    "SocialSubscriber",
]
