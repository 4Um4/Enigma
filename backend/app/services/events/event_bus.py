from __future__ import annotations

# backend/app/services/events/event_bus.py
#
# Phase 3B.1 — EventBus: синхронный pub/sub
#
# Правила (из roadmap v8.1):
#   1. Единственная копия EventBus — только в events/. Нигде больше.
#   2. event_bus.publish() вызывается ТОЛЬКО из action/processor.py.
#      Никогда напрямую из агентов или sandbox_handler.
#   3. world_tick() работает без LLM. Только Python. Таймаут 5 сек.
#   4. Phase 3B.1: только синхронный режим.
#      Phase 3B.4: добавляется async очередь для world_tick.
#
# Подписчики (Phase 3B.3+):
#   - NPC AI (perception filter)
#   - LifeEngine
#   - FactionSystem (Phase 3E)
import logging
from typing import Callable, Dict, List, Optional

from app.domain.events import EventDTO
from app.services.events.event_types import EventType

logger = logging.getLogger(__name__)


# Тип обработчика событий (Устав §2.1: только EventDTO)
EventHandler = Callable[[EventDTO], Optional[EventDTO]]


class EventBus:
    """
    Синхронный pub/sub для игровых событий.

    Использование:
        bus = get_event_bus()           # singleton
        bus.subscribe(EventType.PLAYER_ATTACKED, my_handler)
        results = bus.publish(event)    # все обработчики вызываются немедленно

    Phase 3B.4 расширение:
        bus.enqueue_for_tick(event)     # для world_tick (без LLM)
        events = bus.flush_tick_queue() # scheduler читает раз в N минут
    """

    def __init__(self) -> None:
        self._handlers: Dict[str, List[EventHandler]] = {}
        self._tick_queue: List[EventDTO] = []
        self._event_log: List[EventDTO] = []  # последние 100 событий для debug
        # P2 CFRM: Мост для деобъективации событий в возмущения поля
        self._cfrm_bridge: Optional[Callable[[EventDTO], None]] = None

    # ── CFRM Buffer Control ───────────────────────────────────────────────

    def attach_cfrm_bridge(self, bridge: Callable[[EventDTO], None]) -> None:
        """Привязывает функцию-мост для деобъективации на время тика.

        Все события, проходящие через publish(), будут пропущены через мост,
        превращаясь из объективных EventDTO в возмущения поля (FieldDisturbance).
        """
        self._cfrm_bridge = bridge

    def detach_cfrm_bridge(self) -> None:
        """Отвязывает мост в конце тика."""
        self._cfrm_bridge = None

    # ── Подписка ──────────────────────────────────────────────────────────

    def subscribe(self, event_type: EventType, handler: EventHandler) -> None:
        """
        Регистрирует обработчик для типа события.
        Обработчик вызывается синхронно при publish().

        handler(event: EventDTO) -> Optional[Dict[str, Any]]
          Возвращает dict с результатом (добавляется в results publish)
          или None (игнорируется).
        """
        self._handlers.setdefault(event_type.value, []).append(handler)
        logger.debug(
            f"[EVENT_BUS] Подписан обработчик на {event_type.name}: "
            f"{handler.__qualname__}"
        )

    def unsubscribe(self, event_type: EventType, handler: EventHandler) -> None:
        """Удаляет обработчик."""
        handlers = self._handlers.get(event_type.value, [])
        if handler in handlers:
            handlers.remove(handler)

    # ── Публикация ────────────────────────────────────────────────────────

    def publish(self, event: EventDTO) -> List[EventDTO]:
        """Публикует событие — вызывает всех подписчиков синхронно.

        Закон 2.1.1: publish() принимает только EventDTO. Всё остальное — TypeError.
        Закон 2.1.2: Возвращает List[EventDTO] — результаты обработчиков.
        """
        if not isinstance(event, EventDTO):
            raise TypeError(
                f"EventBus.publish() принимает только EventDTO, "
                f"получен {type(event).__name__}"
            )

        # P2 CFRM: Деобъективация — превращение события в возмущение поля
        if self._cfrm_bridge is not None:
            self._cfrm_bridge(event)

        results: List[EventDTO] = []
        # S122 FIX: Нормализация ключа. subscribe использует .value (строку),
        # поэтому publish также обязан искать по строке, иначе обработчики не найдутся.
        _evt_type = event.type.value if hasattr(event.type, "value") else str(event.type)
        handlers = self._handlers.get(_evt_type, [])

        for handler in handlers:
            try:
                result = handler(event)
                if isinstance(result, EventDTO):
                    results.append(result)
            except Exception as e:
                logger.error(
                    f"[EVENT_BUS] Обработчик упал: {handler.__qualname__} → {e}",
                    exc_info=True
                )

        # логируем для debug (последние 100)
        self._event_log.append(event)
        if len(self._event_log) > 100:
            self._event_log.pop(0)

        if handlers:
            logger.info(
                f"[EVENT_BUS] {event.type} "
                f"от {event.source!r} → "
                f"{len(handlers)} обработчиков, {len(results)} результатов"
            )

        return results

    def publish_many(self, events: List[EventDTO]) -> List[EventDTO]:
        """Публикует несколько событий подряд. Возвращает все результаты (EventDTO)."""
        all_results = []
        for event in events:
            all_results.extend(self.publish(event))
        return all_results

    # ── Phase 3B.4: очередь для world_tick ───────────────────────────────

    def enqueue_for_tick(self, event: EventDTO) -> None:
        """
        Добавляет событие в очередь для обработки в world_tick().
        НЕ вызывает обработчиков немедленно.
        НЕ вызывает LLM — только Python-движки обработают при следующем тике.
        Phase 3B.4: scheduler читает эту очередь каждые N минут.
        """
        self._tick_queue.append(event)

    def flush_tick_queue(self) -> List[EventDTO]:
        """Возвращает накопленные события и очищает очередь."""
        events, self._tick_queue = self._tick_queue, []
        return events

    # ── Утилиты ───────────────────────────────────────────────────────────

    def get_recent_events(
        self, limit: int = 20, campaign_id: str = ""
    ) -> List[EventDTO]:
        """Последние N событий для debug и context_builder.
        Если campaign_id указан — фильтрует только события этой кампании.
        """
        if campaign_id:
            filtered = [
                e
                for e in self._event_log
                if e.payload.get("campaign_id") == campaign_id
            ]
            return filtered[-limit:]
        return self._event_log[-limit:]

    def get_subscriber_count(self, event_type: EventType) -> int:
        return len(self._handlers.get(event_type.value, []))

    def clear(self) -> None:
        """Сбрасывает все подписки и очереди. Для тестов."""
        self._handlers.clear()
        self._tick_queue.clear()
        self._event_log.clear()


# ── Singleton ─────────────────────────────────────────────────────────────────
# Единственный экземпляр EventBus на всё приложение.
# Импортировать через get_event_bus(), не напрямую через _bus.

_bus: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    """
    Возвращает singleton EventBus.
    Создаёт при первом вызове.
    """
    global _bus
    if _bus is None:
        _bus = EventBus()
        logger.info("[EVENT_BUS] EventBus инициализирован")
    return _bus


def reset_event_bus() -> None:
    """Сбрасывает singleton. Только для тестов."""
    global _bus
    _bus = None
