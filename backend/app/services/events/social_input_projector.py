# backend/app/services/events/social_input_projector.py
#
# Сенсорный слой: преобразует ФАКТЫ взаимодействия в social_input (EMA).
# Не знает про gregariousness, setpoint или satiation. Только конвертирует факт в входной сигнал.
"""
path: backend/app/services/events/social_input_projector.py
Назначение: Phase8Handler — сенсор социального входа.
Зависимости: domain.events.EventDTO, models.phase8.Phase8Context/Phase8Result, services.events.event_bus.EventBus
Основные сущности: SocialInputProjector (Phase8Handler)
"""
from __future__ import annotations

import logging
from typing import List, Optional

from app.domain.events import EventDTO
from app.models.phase8 import Phase8Context, Phase8Result
from app.models.state_delta import StateDeltas, DeltaDomain
from app.models.delta_payloads import SocialPayload
from app.services.events.event_bus import EventBus
from app.services.events.event_types import EventType

logger = logging.getLogger(__name__)

# --- Коэффициенты входа (Intensity) ---
_INPUT_SPEAK = 0.10       # активный выход
_INPUT_LISTEN = 0.15      # пассивный вход (внимание к собеседнику)
_INPUT_PRESENCE = 0.05    # фоновое присутствие
_INPUT_INTERACT = 0.20    # целевое взаимодействие


class SocialInputProjector:
    """Phase8Handler: сенсор социального входа.

    Подписывается на факты взаимодействия и генерирует social_input_ema_delta.
    Не мутирует satiation — этим занимается HomeostasisProjector (Field Layer).
    """

    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus
        self._pending_events: List[EventDTO] = []
        self._subscribe()

    def _subscribe(self) -> None:
        for et in [
            EventType.NPC_SPOKE,
            EventType.PLAYER_SPOKE,
            EventType.NPC_PROXIMITY_CLOSE,
            EventType.NPC_INTERACTS_NPC,
        ]:
            self._event_bus.subscribe(et, self._on_event)

    def _on_event(self, event: EventDTO) -> Optional[dict]:
        self._pending_events.append(event)
        return None

    @property
    def name(self) -> str:
        return "social_input"

    def drain_events(self) -> List[EventDTO]:
        snapshot = list(self._pending_events)
        self._pending_events.clear()
        return snapshot

    def handle(self, events: List[EventDTO], ctx: Phase8Context) -> Phase8Result:
        deltas: List[StateDeltas] = []

        for event in events:
            payload = event.payload or {}
            _src = payload.get("source_id") or payload.get("speaker_id") or payload.get("npc_id")
            _tgt = payload.get("target_id")

            if event.type == EventType.NPC_SPOKE:
                if _src:
                    deltas.append(self._mk_delta(_src, _INPUT_SPEAK))
                for listener in payload.get("listener_ids", []):
                    deltas.append(self._mk_delta(listener, _INPUT_LISTEN))

            elif event.type == EventType.PLAYER_SPOKE:
                for listener in payload.get("listener_ids", []):
                    deltas.append(self._mk_delta(listener, _INPUT_LISTEN))

            elif event.type == EventType.NPC_PROXIMITY_CLOSE:
                if _src: deltas.append(self._mk_delta(_src, _INPUT_PRESENCE))
                if _tgt: deltas.append(self._mk_delta(_tgt, _INPUT_PRESENCE))

            elif event.type == EventType.NPC_INTERACTS_NPC:
                if _src: deltas.append(self._mk_delta(_src, _INPUT_INTERACT))
                if _tgt: deltas.append(self._mk_delta(_tgt, _INPUT_INTERACT))

        if deltas:
            print(f"[SOCIAL_INPUT] Generated {len(deltas)} input deltas from {len(events)} events.")

        return Phase8Result(deltas=deltas, events_processed=len(events))

    def _mk_delta(self, npc_id: str, gain: float) -> StateDeltas:
        return StateDeltas(
            npc_id=npc_id,
            domain=DeltaDomain.SOCIAL,
            payload=SocialPayload(
                social_input_ema_delta=gain,
            ),
            source="social_input_projector",
        )