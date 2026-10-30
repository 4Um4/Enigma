"""
path: /project/backend/app/services/events/npc_addressing_delivery_subscriber.py
Назначение: C3-A1 delivery subscriber для NPC_ADDRESSES_PLAYER.
    Двухфазное помещение (вердикт Мастера):
      Фаза 1 (staging): publish → subscriber → TickCampaignContext.staged_events
      Фаза 2 (commit): после успешного Phase 10 → commit_staged() → delivery queue
    Campaign-keyed queue, thread-safe (threading.Lock), ACK-based удаление.
    TTL не вводится (вердикт Мастера). Диагностическое предупреждение при росте.
    ACK endpoint — C3-A2 (метод существует, API отложен).
    NPCState.intent = SSOT — subscriber хранит проекцию EventDTO, не intent.
Зависимости: threading, typing, app.domain.events, app.services.events.event_bus,
    app.services.events.event_types, app.services.events.tick_campaign_context
Основные сущности: NpcAddressingDeliverySubscriber
"""
from __future__ import annotations

import logging
import threading
from typing import Any, Dict, List, Optional

from app.domain.events import EventDTO
from app.services.events.event_bus import EventBus
from app.services.events.event_types import EventType
from app.services.events.tick_campaign_context import (
    TickCampaignContext,
    get_current_tick_context,
)

logger = logging.getLogger(__name__)

# Диагностический порог (не удаляет, только логирует — вердикт Мастера:
# неограниченный рост не утверждён, но TTL/вытеснение не вводится).
_QUEUE_SIZE_WARN_THRESHOLD = 50


class NpcAddressingDeliverySubscriber:
    """Delivery subscriber для NPC_ADDRESSES_PLAYER (C3-A1).

    Двухфазное помещение:
      1. _on_event(event) — staging: добавляет в TickCampaignContext.staged_events
         (если контекст активен). Не доставляемое, пока не закоммичено.
      2. commit_staged(campaign_id) — после успешного Phase 10: переносит
         staged_events в delivery queue (_buffers[campaign_id]).

    ACK:
      ack(campaign_id, event_id) — удаляет событие из delivery queue.
      Повторный ACK безопасен (idempotent).
      Проверка принадлежности кампании обязательна.

    Thread safety:
      _lock защищает _buffers. Не удерживается во время игровых фаз/HTTP.
    """

    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus
        # campaign_id → list[EventDTO] (доставленные, ждут ACK)
        self._buffers: Dict[str, List[EventDTO]] = {}
        self._lock = threading.Lock()
        self._subscribe()

    def _subscribe(self) -> None:
        """Подписывается на NPC_ADDRESSES_PLAYER."""
        self._event_bus.subscribe(
            EventType.NPC_ADDRESSES_PLAYER, self._on_event
        )

    def _on_event(self, event: EventDTO) -> Optional[EventDTO]:
        """Фаза 1: staging. Добавляет событие в staged_events контекста тика.

        Не доставляемое, пока commit_staged() не перенесёт в delivery queue.
        Вне контекста тика (тест, лаборатория) — no-op + warning.
        """
        ctx = get_current_tick_context()
        if ctx is None:
            logger.warning(
                "[C3_DELIVERY] NPC_ADDRESSES_PLAYER published outside tick "
                "context (event_id=%s, source=%s). Event will not be delivered.",
                event.id,
                event.source,
            )
            return None
        ctx.staged_events.append(event)
        return None

    def commit_staged(self, campaign_id: str) -> None:
        """Фаза 2: commit. Переносит staged_events в delivery queue.

        Вызывается orchestrator ПОСЛЕ успешного Phase 10 + scene_manager.commit.
        При exception в Phase 10 — НЕ вызывается (staged уничтожается с контекстом).
        Thread-safe: lock вокруг transfer.
        """
        ctx = get_current_tick_context()
        if ctx is None or ctx.campaign_id != campaign_id:
            return
        if not ctx.staged_events:
            return
        with self._lock:
            buf = self._buffers.setdefault(campaign_id, [])
            buf.extend(ctx.staged_events)
            _sz = len(buf)
        ctx.staged_events.clear()
        if _sz > _QUEUE_SIZE_WARN_THRESHOLD:
            logger.warning(
                "[C3_DELIVERY] campaign=%s queue size=%s "
                "(threshold=%s). Unchecked growth — verify client ACKs (C3-A2).",
                campaign_id,
                _sz,
                _QUEUE_SIZE_WARN_THRESHOLD,
            )

    def drain(self, campaign_id: str) -> List[Dict[str, Any]]:
        """Возвращает проекцию доставки для API response.

        НЕ очищает queue (повторная выдача до ACK возвращает тот же event_id).
        ACK удаляет только подтверждённое событие.
        """
        with self._lock:
            buf = self._buffers.get(campaign_id, [])
            return [self._project(e) for e in buf]

    def ack(self, campaign_id: str, event_id: str) -> bool:
        """ACK — подтверждение получения клиентом.

        Удаляет только указанное событие из queue кампании.
        Проверка принадлежности кампании: если event_id не в
        _buffers[campaign_id] — no-op (возвращает False).
        Повторный ACK безопасен (idempotent).
        Возвращает True если событие было найдено и удалено.
        """
        with self._lock:
            buf = self._buffers.get(campaign_id, [])
            for i, e in enumerate(buf):
                if str(e.id) == event_id:
                    buf.pop(i)
                    return True
            return False

    @staticmethod
    def _project(event: EventDTO) -> Dict[str, Any]:
        """Проекция EventDTO → dict для API response (read-only)."""
        return {
            "event_id": str(event.id),
            "npc_id": event.source,
            "intent": event.payload.get("intent"),
            "intent_formed_at": event.payload.get("intent_formed_at"),
            "tick": int(event.timestamp),
            "event_type": event.type,
        }