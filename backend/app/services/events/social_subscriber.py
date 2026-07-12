from __future__ import annotations
# backend/app/services/events/social_subscriber.py
#
# Устав §5.1: EventBus.publish() — единственная точка входа событий.
# SocialSubscriber подписан на шину, накапливает EventDTO.
# Фаза 8: drain_events() + handle() — детерминированный drain-этап.
# Шина для фактов, Фаза 8 для обработки. Никаких мета-событий.
#
# propagate_social_rumors() — чистая функция, возвращает List[StateDeltas].
# Оркестратор применяет дельты к all_npcs_raw в _apply_phase8_result().
# TODO: trust_delta → RelationshipStore (нужен target от SocialEngine).
"""
path: backend/app/services/events/social_subscriber.py
Назначение: Phase8Handler — социальная пропагация (Устав §5.1 + §3 Фаза 8)
Зависимости: domain.events.EventDTO, models.phase8.Phase8Context/Phase8Result, services.events.event_bus.EventBus
Основные сущности: SocialSubscriber (Phase8Handler)

TODO:
- [ ] Phase 3B.4: поддержка асинхронной очереди для world_tick
- [ ] Phase 3E: расширение для FactionSystem (пропагация по фракциям)
- [ ] Логирование и метрики: сколько NPC затрагивает социальная пропагация, какие типы событий чаще всего влияют на социальные отношения
- [ ] Тесты: юнит-тесты для SocialSubscriber, интеграционные тесты с EventBus и SocialEngine
"""


import logging
from typing import Dict, Any, Callable, List, Optional

from app.domain.events import EventDTO
from app.models.phase8 import Phase8Context, Phase8Result
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
    """Phase8Handler: социальная пропагация.

    Жизненный цикл:
      1. Шина → _on_event() накапливает EventDTO (Фазы 2/7)
      2. Оркестратор → drain_events() снимок + очистка (Фаза 8)
      3. Оркестратор → handle(events, ctx) → Phase8Result (Фаза 8)

    Чистая функция: propagate_social_rumors() возвращает List[StateDeltas].
    Оркестратор складывает дельты в delta_buffer → StateApplicator (фаза 10).
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

    def _on_event(self, event: EventDTO) -> Optional[Dict[str, Any]]:
        """EventHandler: накапливает событие для обработки на Фазе 8."""
        self._pending_events.append(event)
        return None

    @property
    def name(self) -> str:
        return "social"

    def drain_events(self) -> List[EventDTO]:
        """Снимок буфера + очистка. Вызывается строго один раз за тик."""
        snapshot = list(self._pending_events)
        self._pending_events.clear()
        return snapshot

    def set_social_engine_factory(self, factory: Callable) -> None:
        """Устанавливает фабрику SocialEngine (DI)."""
        self._social_engine_factory = factory

    def handle(
        self,
        events: List[EventDTO],
        ctx: Phase8Context,
    ) -> Phase8Result:
        """ФАЗА 8: социальная пропагация накопленных событий.

        events — из drain_events(), может быть пустым.
        ctx — READ-ONLY.
        Возвращает Phase8Result(deltas) — оркестратор применяет.

        propagate_social_rumors() — чистая функция, возвращает List[StateDeltas].
        Оркестратор применяет дельты к all_npcs_raw через _apply_phase8_result().
        """
        if self._social_engine_factory is None:
            logger.debug("[SOCIAL_SUB] handle: нет social_engine_factory — пропускаем")
            return Phase8Result()

        if not events:
            logger.debug("[SOCIAL_SUB] handle: нет накопленных событий")
            return Phase8Result()

        from app.services.social.propagation import propagate_social_rumors

        social_engine = self._social_engine_factory(ctx.campaign_id)
        self._social_tick, deltas = propagate_social_rumors(
            social_engine,
            self._social_tick,
            ctx.shared_context,
            events=events,
        )

        logger.debug(
            f"[SOCIAL_SUB] {len(events)} events "
            f"processed, social_tick={self._social_tick}, "
            f"deltas={len(deltas)}"
        )

        # Извлекаем затронутых NPC из дельт для синхронизации perception ∪ social
        _affected_ids = {d.npc_id for d in deltas if d.npc_id}

        return Phase8Result(
            deltas=deltas,
            socially_affected_npc_ids=_affected_ids,
            events_processed=len(events),
        )
