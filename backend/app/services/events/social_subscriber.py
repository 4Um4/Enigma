# backend/app/services/events/social_subscriber.py
#
# Устав §5.1: EventBus.publish() — единственная точка входа событий.
# SocialSubscriber подписан на шину, накапливает EventDTO,
# применяет пропагацию на фазе 6 (после perception).
#
# TODO: после полной миграции на EventDTO — брать intensity из payload,
#       а не из shared_context.python_engines_result.dm_result
"""
path: backend/app/services/events/social_subscriber.py
Назначение: Подписчик EventBus для социальной пропагации (Устав §5.1)
Зависимости: domain.events.EventDTO, services.events.event_bus.EventBus, services.events.event_types.EventType
Основные сущности: SocialSubscriber

TODO:
- [ ] Phase 3B.4: поддержка асинхронной очереди для world_tick
- [ ] Phase 3E: расширение для FactionSystem (пропагация по фракциям)
- [ ] Логирование и метрики: сколько NPC затрагивает социальная пропагация, какие типы событий чаще всего влияют на социальные отношения
- [ ] Тесты: юнит-тесты для SocialSubscriber, интеграционные тесты с EventBus и SocialEngine
"""
from __future__ import annotations

import logging
from typing import Any, Callable, List, Optional

from app.domain.events import EventDTO
from app.services.events.event_bus import EventBus
from app.services.events.event_types import EventType

logger = logging.getLogger(__name__)

# Типы событий, влияющих на социальную пропагацию
_SOCIAL_EVENT_TYPES: list[EventType] = [
    EventType.PLAYER_INTERACTS,
    EventType.PLAYER_SPOKE,
    EventType.PLAYER_ATTACKED,
    EventType.PLAYER_ATTACKS,
    EventType.PLAYER_ATTACK,
    EventType.PLAYER_INSULTS,
    EventType.PLAYER_THREATENS,
    EventType.THEFT,
    EventType.COMBAT,
    EventType.HELP,
    EventType.INTIMIDATION,
    EventType.BETRAYAL,
    EventType.SAVED_LIFE,
]


class SocialSubscriber:
    """Подписчик на события для социальной пропагации (Устав §5.1).

    Накапливает EventDTO при publish(), применяет пропагацию на фазе 6.
    Заменяет прямой вызов propagate_social_rumors из TickOrchestrator.
    """

    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus
        self._social_engine_factory: Callable | None = None
        self._social_tick: int = 0
        self._pending_events: List[EventDTO] = []
        self._subscribe()

    def _subscribe(self) -> None:
        """Подписывается на все типы событий, влияющих на социальную пропагацию."""
        for et in _SOCIAL_EVENT_TYPES:
            self._event_bus.subscribe(et, self._on_event)

    def _on_event(self, event: EventDTO) -> Optional[dict]:
        """EventHandler: накапливает событие для обработки на фазе 6."""
        self._pending_events.append(event)
        return None

    def set_social_engine_factory(self, factory: Callable) -> None:
        """Устанавливает фабрику SocialEngine (DI)."""
        self._social_engine_factory = factory

    def apply(
        self,
        shared_context: Any,
        all_npcs_raw: List[dict],
        tick_ctx: Any,
        campaign_id: str,
    ) -> None:
        """ШАГ D: социальная пропагация накопленных событий.

        Мутирует all_npcs_raw (trust/stress) и tick_ctx.prop_dirty.
        Пока использует dm_result.event_context для intensity
        (TODO: миграция на EventDTO payload).
        """
        if self._social_engine_factory is None:
            logger.debug("[SOCIAL_SUB] apply: нет social_engine_factory — пропускаем")
            self._pending_events.clear()
            return

        from app.services.social.propagation import propagate_social_rumors

        social_engine = self._social_engine_factory(campaign_id)
        self._social_tick = propagate_social_rumors(
            social_engine,
            self._social_tick,
            shared_context,
            all_npcs_raw,
            tick_ctx,
        )

        # Логируем накопленные события для диагностики
        if self._pending_events:
            logger.debug(
                f"[SOCIAL_SUB] {len(self._pending_events)} events "
                f"processed, social_tick={self._social_tick}"
            )

        # Очищаем после применения
        self._pending_events.clear()