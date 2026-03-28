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

from __future__ import annotations
import logging
from typing import Callable, Dict, List, Optional

from app.services.events.event_types import EventType, GameEvent

logger = logging.getLogger(__name__)


# Тип обработчика событий
EventHandler = Callable[[GameEvent], Optional[dict]]


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
        self._handlers: Dict[EventType, List[EventHandler]] = {}
        self._tick_queue: List[GameEvent] = []
        self._event_log: List[dict] = []   # последние 100 событий для debug

    # ── Подписка ──────────────────────────────────────────────────────────

    def subscribe(self, event_type: EventType, handler: EventHandler) -> None:
        """
        Регистрирует обработчик для типа события.
        Обработчик вызывается синхронно при publish().

        handler(event: GameEvent) -> Optional[dict]
          Возвращает dict с результатом (добавляется в results publish)
          или None (игнорируется).
        """
        self._handlers.setdefault(event_type, []).append(handler)
        logger.debug(
            f"[EVENT_BUS] Подписан обработчик на {event_type.name}: "
            f"{handler.__qualname__}"
        )

    def unsubscribe(self, event_type: EventType, handler: EventHandler) -> None:
        """Удаляет обработчик."""
        handlers = self._handlers.get(event_type, [])
        if handler in handlers:
            handlers.remove(handler)

    # ── Публикация ────────────────────────────────────────────────────────

    def publish(self, event: GameEvent) -> List[dict]:
        """
        Публикует событие — вызывает всех подписчиков синхронно.

        Правило affordance (из roadmap):
          publish() вызывается ТОЛЬКО после affordance check в processor.py.
          Физически невозможные события сюда не доходят.

        Возвращает список результатов от обработчиков (для агрегации).
        """
        results = []
        handlers = self._handlers.get(event.event_type, [])

        for handler in handlers:
            try:
                result = handler(event)
                if result is not None:
                    results.append(result)
            except Exception as e:
                logger.error(
                    f"[EVENT_BUS] Обработчик упал: "
                    f"{handler.__qualname__} → {e}"
                )

        # Логируем для debug (храним последние 100)
        self._event_log.append(event.to_dict())
        if len(self._event_log) > 100:
            self._event_log.pop(0)

        if handlers:
            logger.info(
                f"[EVENT_BUS] {event.event_type.name} "
                f"от {event.actor_id!r} в {event.location!r} → "
                f"{len(handlers)} обработчиков, {len(results)} результатов"
            )

        return results

    def publish_many(self, events: List[GameEvent]) -> List[dict]:
        """Публикует несколько событий подряд. Возвращает все результаты."""
        all_results = []
        for event in events:
            all_results.extend(self.publish(event))
        return all_results

    # ── Phase 3B.4: очередь для world_tick ───────────────────────────────

    def enqueue_for_tick(self, event: GameEvent) -> None:
        """
        Добавляет событие в очередь для обработки в world_tick().
        НЕ вызывает обработчиков немедленно.
        НЕ вызывает LLM — только Python-движки обработают при следующем тике.
        Phase 3B.4: scheduler читает эту очередь каждые N минут.
        """
        self._tick_queue.append(event)

    def flush_tick_queue(self) -> List[GameEvent]:
        """Возвращает накопленные события и очищает очередь."""
        events, self._tick_queue = self._tick_queue, []
        return events

    # ── Утилиты ───────────────────────────────────────────────────────────

    def get_recent_events(self, limit: int = 20) -> List[dict]:
        """Последние N событий для debug и context_builder."""
        return self._event_log[-limit:]

    def get_subscriber_count(self, event_type: EventType) -> int:
        return len(self._handlers.get(event_type, []))

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