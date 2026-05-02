# backend/app/services/events/perception_subscriber.py
#
# Устав §5.1: EventBus.publish() — единственная точка входа событий.
# PerceptionSubscriber подписан на шину, накапливает EventDTO,
# применяет фильтр на фазе 5 (когда npc_contexts доступны).
#
# Заменяет хак get_recent_events() — прямой подписчик шины.

"""
path: backend/app/services/events/perception_subscriber.py
Назначение: Подписчик EventBus для фильтрации NPC по восприятию (Устав §5.1)
Зависимости: domain.events.EventDTO, services.events.event_bus.EventBus, services.events.event_types.EventType
Основные сущности: PerceptionSubscriber

TODO:
- [ ] Phase 3B.4: поддержка асинхронной очереди для world_tick
- [ ] Phase 3E: расширение для FactionSystem (восприятие по фракциям)
- [ ] Логирование и метрики: сколько NPC воспринимает каждое событие, какие типы событий чаще всего влияют на восприятие
- [ ] Тесты: юнит-тесты для PerceptionSubscriber, интеграционные тесты с EventBus и perception_filter
"""
from __future__ import annotations

import logging
from typing import Any, List, Optional

from app.domain.events import EventDTO
from app.services.events.event_bus import EventBus
from app.services.events.event_types import EventType

logger = logging.getLogger(__name__)

# Типы событий, влияющих на восприятие NPC
_PERCEPTION_EVENT_TYPES: list[EventType] = [
    EventType.PLAYER_INTERACTS,
    EventType.PLAYER_SPOKE,
    EventType.PLAYER_ATTACKED,
    EventType.PLAYER_MOVED,
    EventType.PLAYER_USED_ITEM,
    EventType.PLAYER_CAST_SPELL,
    EventType.NPC_SPOKE,
    EventType.NPC_MOVED,
    EventType.SOUND_EMITTED,
    EventType.OBJECT_DESTROYED,
    EventType.OBJECT_MOVED,
    EventType.OBJECT_CHANGED,
]


class PerceptionSubscriber:
    """Подписчик на события для фильтрации NPC по восприятию (Устав §5.1).

    Накапливает EventDTO при publish(), применяет фильтр на фазе 5.
    Заменяет прямой вызов apply_perception_filter и хак get_recent_events().
    """

    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus
        self._pending_events: List[EventDTO] = []
        self._subscribe()

    def _subscribe(self) -> None:
        """Подписывается на все типы событий, влияющих на восприятие."""
        for et in _PERCEPTION_EVENT_TYPES:
            self._event_bus.subscribe(et, self._on_event)

    def _on_event(self, event: EventDTO) -> Optional[dict]:
        """EventHandler: накапливает событие для обработки на фазе 5."""
        self._pending_events.append(event)
        return None

    def apply(
        self,
        all_npc_contexts: List[dict],
        shared_context: Any,
        campaign_id: str,
    ) -> None:
        """ФАЗА 5: фильтрует NPC по восприятию накопленных событий.

        Мутирует shared_context.npc_contexts и shared_context.perceiving_npcs.
        Берёт последнее событие (эквивалент get_recent_events(limit=1)).
        """
        _all_npc_ids = [ctx["npc_id"] for ctx in all_npc_contexts]

        if self._pending_events and _all_npc_ids:
            from app.services.npc.perception_filter import filter_perceiving_npcs

            # Последнее событие — самое актуальное (классифицированное)
            last_event = self._pending_events[-1]

            _perceiving_ids = set(filter_perceiving_npcs(
                npc_ids=_all_npc_ids,
                event=last_event,
                scene_state=shared_context.scene_state or {},
            ))

            # Адресат всегда воспринимает + свидетели по perception
            _explicit_target = shared_context.player_target_id
            if _explicit_target:
                _perceiving_ids.add(_explicit_target)

            # ФИЛЬТРУЕМ — только воспринимающие NPC получают вербализацию
            _filtered_ctxs = [
                c for c in all_npc_contexts
                if c.get("npc_id") in _perceiving_ids
            ]
            shared_context.npc_contexts = _filtered_ctxs
            shared_context.perceiving_npcs = list(_perceiving_ids)

            _target_note = f" (target={_explicit_target})" if _explicit_target else ""
            logger.warning(
                f"[PERCEPTION_SUB] {len(_perceiving_ids)}/{len(_all_npc_ids)} "
                f"NPC{_target_note}: {list(_perceiving_ids)} "
                f"(events={len(self._pending_events)})"
            )
        else:
            shared_context.npc_contexts = all_npc_contexts
            logger.warning(
                f"[PERCEPTION_SUB] skip: events={len(self._pending_events)}, "
                f"npcs={len(_all_npc_ids)}"
            )

        # Очищаем после применения
        self._pending_events.clear()