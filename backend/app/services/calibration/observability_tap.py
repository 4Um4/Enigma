"""
path: backend/app/services/calibration/observability_tap.py
Назначение: Единственный пассивный наблюдатель лаборатории (ADR-O-361).
    v2 (S213): записи (event_type, source, label), где label = payload
    intent_type (NPC_SPOKE и коммуникативные события) — канал
    IntentEventAdapter, предписанный ТЗ 14.2. Решает DEBT-INTENT-SOURCE:
    писателя npc["intent"] в снапшоте загрузчика не существует (археология
    S213: поиск пуст), intent живёт в DTO-контуре и наблюдается через шину.
    take_tick_records() — дренаж тикового буфера (события/тик + labels).
    Полная try/except-изоляция: отказ наблюдателя не роняет поток (CDS §11).
Зависимости: app.services.events.event_bus, event_types.
Основные сущности: ObservabilityTap, DECISION_EVENT_VALUES, SUBSCRIBED_EVENT_TYPES.
"""
from __future__ import annotations

import logging
from collections import deque
from typing import Deque, List, Tuple

from app.services.events.event_bus import get_event_bus
from app.services.events.event_types import EventType

logger = logging.getLogger(__name__)

Record = Tuple[str, str, str]  # (event_type, source, label)

SUBSCRIBED_EVENT_TYPES: Tuple[EventType, ...] = (
    EventType.NPC_SPOKE,
    EventType.NPC_MOVED,
    EventType.NPC_PROXIMITY_CLOSE,
    EventType.NPC_PROXIMITY_LEAVE,
    EventType.NPC_INTERACTS_NPC,
    EventType.SOCIAL_ACTION,
    EventType.COMMUNICATION_CLAIM,
    EventType.OFFER_JOB,
    EventType.SPREAD_RUMOR,
    EventType.WARN,
    EventType.TRADE,
    EventType.THEFT,
    EventType.COMBAT,
    EventType.FATE_EVENT,
)

# Решенческие события (выход IntentEventAdapter._INTENT_EVENT_MAP + NPC_SPOKE):
# источник метрик DecisionDiversity / LoopRate / EventResponsiveness (ТЗ 14.2).
DECISION_EVENT_VALUES: frozenset = frozenset({
    EventType.NPC_SPOKE.value,
    EventType.OFFER_JOB.value,
    EventType.REQUEST_SERVICE.value,
    EventType.SPREAD_RUMOR.value,
    EventType.CALL_FOR_HELP.value,
    EventType.CHANGE_ROLE.value,
    EventType.WARN.value,
    EventType.TRADE.value,
    EventType.REPORT.value,
})


class ObservabilityTap:
    """Пассивный наблюдатель. attach/detach идемпотентны."""

    def __init__(self, max_events: int = 100_000) -> None:
        self._records: Deque[Record] = deque(maxlen=max_events)
        self._pending: List[Record] = []
        self._count: int = 0
        self._attached: bool = False

    def _handle(self, event: object) -> None:
        # Наблюдение не создаёт причинность: любой отказ — лог, не исключение.
        try:
            self._count += 1
            event_type = str(getattr(event, "type", "?"))
            source = str(getattr(event, "source", "?"))
            payload = getattr(event, "payload", None)
            label = ""
            if isinstance(payload, dict):
                raw = payload.get("intent_type", "")
                label = str(raw) if raw else ""
            if not label:
                label = event_type
            rec = (event_type, source, label)
            self._records.append(rec)
            self._pending.append(rec)
        except Exception:
            logger.warning("[OBS_TAP] handler failure (тик не роняем)", exc_info=True)

    def attach(self) -> None:
        if self._attached:
            return
        bus = get_event_bus()
        for event_type in SUBSCRIBED_EVENT_TYPES:
            bus.subscribe(event_type, self._handle)
        self._attached = True

    def detach(self) -> None:
        if not self._attached:
            return
        bus = get_event_bus()
        for event_type in SUBSCRIBED_EVENT_TYPES:
            bus.unsubscribe(event_type, self._handle)
        self._attached = False

    def take_tick_records(self) -> List[Record]:
        """События, накопленные с прошлого дренажа (тик-гранулярность)."""
        out = self._pending
        self._pending = []
        return out

    @property
    def count(self) -> int:
        return self._count

    @property
    def records(self) -> Tuple[Record, ...]:
        return tuple(self._records)