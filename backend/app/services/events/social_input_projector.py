from __future__ import annotations

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


import logging
from typing import List

from app.domain.events import EventDTO
from app.models.delta_payloads import SocialPayload
from app.models.phase8 import Phase8Context, Phase8Result
from app.models.state_delta import DeltaDomain, StateDeltas
from app.services.events.event_bus import EventBus
from app.services.events.event_types import EventType

logger = logging.getLogger(__name__)

# --- Коэффициенты входа (Intensity) ---
_INPUT_SPEAK = 0.10  # активный выход
_INPUT_LISTEN = 0.15  # пассивный вход (внимание к собеседнику)
_INPUT_PRESENCE = 0.05  # фоновое присутствие
_INPUT_INTERACT = 0.20  # целевое взаимодействие


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
        ]:
            self._event_bus.subscribe(et, self._on_event)

    def _on_event(self, event: EventDTO) -> None:
        self._pending_events.append(event)

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
            _src = (
                payload.get("source_id")
                or payload.get("speaker_id")
                or payload.get("npc_id")
            )
            _tgt = payload.get("target_id")

            if event.type == EventType.NPC_SPOKE:
                if _src:
                    deltas.append(self._mk_delta(_src, _INPUT_SPEAK))
                
                # V8-SOC-7 FIX: Если listener_ids не заполнены, вычисляем слушателей через perception_filter
                _listeners = payload.get("listener_ids", [])
                if not _listeners and _src:
                    from app.services.npc.perception_filter import filter_perceiving_npcs
                    _all_npc_ids = [c["npc_id"] for c in ctx.all_npc_contexts]
                    _sq = getattr(ctx.shared_context, "spatial_query", None)  # noqa: ENIGMA002
                    if _sq is not None:
                        _listeners = filter_perceiving_npcs(
                            npc_ids=_all_npc_ids,
                            event=event,
                            scene_state=getattr(ctx.shared_context, "scene_state", None) or ctx.tick_ctx.scene_state or {},  # noqa: ENIGMA002
                            spatial_query=_sq,
                        )
                # BUG-V68-002 FIX: Восстановлен случайно удалённый цикл обработки слушателей.
                for listener in _listeners:
                    if listener != _src:
                        deltas.append(self._mk_delta(listener, _INPUT_LISTEN))

            elif event.type == EventType.PLAYER_SPOKE:
                _listeners = payload.get("listener_ids", [])
                if not _listeners:
                    from app.services.npc.perception_filter import filter_perceiving_npcs
                    _all_npc_ids = [c["npc_id"] for c in ctx.all_npc_contexts]
                    _sq = getattr(ctx.shared_context, "spatial_query", None)  # noqa: ENIGMA002
                    if _sq is not None:
                        _listeners = filter_perceiving_npcs(
                            npc_ids=_all_npc_ids,
                            event=event,
                            scene_state=getattr(ctx.shared_context, "scene_state", None) or ctx.tick_ctx.scene_state or {},  # noqa: ENIGMA002
                            spatial_query=_sq,
                        )
                for listener in _listeners:
                    deltas.append(self._mk_delta(listener, _INPUT_LISTEN))

            elif event.type == EventType.NPC_PROXIMITY_CLOSE:
                if _src:
                    deltas.append(self._mk_delta(_src, _INPUT_PRESENCE))
                if _tgt:
                    deltas.append(self._mk_delta(_tgt, _INPUT_PRESENCE))

        if deltas:
            logger.debug(
                f"[SOCIAL_INPUT] Generated {len(deltas)} input deltas from {len(events)} events."
            )

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
