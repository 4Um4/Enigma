from __future__ import annotations

# backend/app/services/events/perception_subscriber.py
#
# Устав §5.1: EventBus.publish() — единственная точка входа событий.
# PerceptionSubscriber подписан на шину, накапливает EventDTO.
# Фаза 8: drain_events() + handle() — детерминированный drain-этап.
# Шина для фактов, Фаза 8 для обработки. Никаких мета-событий.

"""
path: backend/app/services/events/perception_subscriber.py
Назначение: Phase8Handler — фильтрация NPC по восприятию (Устав §5.1 + §3 Фаза 8)
Зависимости: domain.events.EventDTO, models.phase8.Phase8Context/Phase8Result, services.events.event_bus.EventBus
Основные сущности: PerceptionSubscriber (Phase8Handler)

- [ ] Phase 3B.4: поддержка асинхронной очереди для world_tick
- [ ] Phase 3E: расширение для FactionSystem (восприятие по фракциям)
- [ ] Логирование и метрики: сколько NPC воспринимает каждое событие, какие типы событий чаще всего влияют на восприятие
- [ ] Тесты: юнит-тесты для PerceptionSubscriber, интеграционные тесты с EventBus и perception_filter
"""


import logging
from typing import Any, Dict, List, Optional

from app.domain.events import EventDTO
from app.models.phase8 import Phase8Context, Phase8Result
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
    """Phase8Handler: фильтрация NPC по восприятию.

    Жизненный цикл:
      1. Шина → _on_event() накапливает EventDTO (Фазы 2/7)
      2. Оркестратор → drain_events() снимок + очистка (Фаза 8)
      3. Оркестратор → handle(events, ctx) → Phase8Result (Фаза 8)

    Не мутирует контекст. Все выходы — через Phase8Result.
    """

    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus
        self._pending_events: List[EventDTO] = []
        self._subscribe()

    def _subscribe(self) -> None:
        """Подписывается на все типы событий, влияющих на восприятие."""
        for et in _PERCEPTION_EVENT_TYPES:
            self._event_bus.subscribe(et, self._on_event)

    def _on_event(self, event: EventDTO) -> Optional[Dict[str, Any]]:
        """EventHandler: накапливает событие для обработки на Фазе 8."""
        self._pending_events.append(event)
        return None

    @property
    def name(self) -> str:
        return "perception"

    def drain_events(self) -> List[EventDTO]:
        """Снимок буфера + очистка. Вызывается строго один раз за тик."""
        snapshot = list(self._pending_events)
        self._pending_events.clear()
        return snapshot

    def handle(
        self,
        events: List[EventDTO],
        ctx: Phase8Context,
    ) -> Phase8Result:
        """ФАЗА 8: фильтрует NPC по восприятию накопленных событий.

        events — из drain_events(), может быть пустым.
        ctx — READ-ONLY, не мутировать.
        Возвращает Phase8Result(perceiving_npc_ids) — оркестратор применяет фильтр.
        perceiving_npc_ids=None означает «нет фильтра, все NPC видят».
        """
        _all_npc_ids = [c["npc_id"] for c in ctx.all_npc_contexts]

        if events and _all_npc_ids:
            from app.services.npc.perception_filter import filter_perceiving_npcs

            # Обрабатываем ВСЕ накопленные события — каждый NPC воспринимает
            # хотя бы одно событие (Устав §5.1: шина для фактов, Фаза 8 для обработки)
            _perceiving_ids: set[str] = set()
            for _event in events:
                _perceiving_ids.update(
                    filter_perceiving_npcs(
                        npc_ids=_all_npc_ids,
                        event=_event,
                        scene_state=ctx.shared_context.scene_state or {},
                        spatial_query=getattr(
                            ctx.shared_context, "spatial_query", None
                        ),
                    )
                )

            # Адресат всегда воспринимает + свидетели по perception
            # P1 ARCH: Чтение цели ТОЛЬКО из EventContext (Referential Closure)
            _explicit_target = getattr(ctx.event, "target_id", "") if ctx.event else ""
            if _explicit_target:
                _perceiving_ids.add(_explicit_target)

            _target_note = f" (target={_explicit_target})" if _explicit_target else ""
            logger.warning(
                f"[PERCEPTION_SUB] {len(_perceiving_ids)}/{len(_all_npc_ids)} "
                f"NPC{_target_note}: {list(_perceiving_ids)} "
                f"(events={len(events)})"
            )
            return Phase8Result(perceiving_npc_ids=_perceiving_ids)

        logger.warning(
            f"[PERCEPTION_SUB] skip: events={len(events)}, npcs={len(_all_npc_ids)}"
        )
        return Phase8Result()
