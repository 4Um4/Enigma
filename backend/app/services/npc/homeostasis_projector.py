"""
path: backend/app/services/npc/homeostasis_projector.py
Назначение: Проекция событий во внутренние накопители NPC (homeostasis).
             Первый накопитель: social_battery.
             Факты → коэффициенты → дельты. Проектор не знает про NPCState.
Зависимости: domain.events, models.phase8, models.state_delta, models.delta_payloads,
             services.events.event_bus, services.events.event_types
Основные сущности: HomeostasisProjector (Phase8Handler)
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

# --- Коэффициенты (единственное место в системе) ---
_SOCIAL_BATTERY_CONVERSATION_GAIN = 12.0    # одна реплика NPC_SPOKE
_SOCIAL_BATTERY_ISOLATION_RATE = 0.15      # потеря за тик без взаимодействия
_SOCIAL_BATTERY_MIN = 0.0


class HomeostasisProjector:
    """Phase8Handler: проекция событий во внутренние накопители NPC.

    Жизненный цикл:
      1. __init__ → подписка на EventBus (NPC_SPOKE)
      2. _on_event() → накопление EventDTO
      3. drain_events() → снимок + очистка (Фаза 8)
      4. handle(events, ctx) → SocialPayload дельты (Фаза 8)
      5. compute_isolation_decay() → SocialPayload дельты (Фаза 0.5)

    Проектор тупой: факт → коэффициент → дельта.
    Не знает про NPCState, DecisionHub, Personality.
    """

    name: str = "homeostasis"

    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus
        self._pending_events: List[EventDTO] = []
        event_bus.subscribe(EventType.NPC_SPOKE, self._on_event)

    def _on_event(self, event: EventDTO) -> None:
        """Накопление события (Фазы 2/7)."""
        self._pending_events.append(event)

    def drain_events(self) -> List[EventDTO]:
        """Снимок + очистка (Фаза 8)."""
        events = self._pending_events
        self._pending_events = []
        return events

    def handle(self, events: List[EventDTO], ctx: Phase8Context) -> Phase8Result:
        """Обработка накопленных событий → дельты social_battery.

        Каждое NPC_SPOKE = +conversation_gain для говорящего NPC.
        """
        deltas: List[StateDeltas] = []

        for event in events:
            if event.type != EventType.NPC_SPOKE:
                continue

            _npc_id = (event.payload or {}).get("npc_id", "")
            if not _npc_id:
                continue

            deltas.append(StateDeltas(
                npc_id=_npc_id,
                domain=DeltaDomain.SOCIAL,
                payload=SocialPayload(
                    social_battery_delta=_SOCIAL_BATTERY_CONVERSATION_GAIN,
                ),
                source="homeostasis_conversation",
            ))

        if deltas:
            logger.debug(
                f"[HOMEOSTASIS] conversation: {len(deltas)} deltas "
                f"gain=+{_SOCIAL_BATTERY_CONVERSATION_GAIN}"
            )

        return Phase8Result(deltas=deltas, events_processed=len(events))

    @staticmethod
    def compute_isolation_decay(
        all_npcs_raw: List[dict],
    ) -> List[StateDeltas]:
        """Time-driven decay: social_battery падает без взаимодействия.

        Вызывается из Phase 0.5. Возвращает дельты для delta_buffer.
        Clamp выполняется в StateApplicator — проектор не знает про границы.
        """
        deltas: List[StateDeltas] = []

        for npc_dict in all_npcs_raw:
            _npc_id = npc_dict.get("npc_id", "")
            _sb = npc_dict.get("social_battery")
            # Пропускаем: нет поля, игрок, уже на нуле
            if _sb is None or _npc_id == "player" or _sb <= _SOCIAL_BATTERY_MIN:
                continue

            deltas.append(StateDeltas(
                npc_id=_npc_id,
                domain=DeltaDomain.SOCIAL,
                payload=SocialPayload(
                    social_battery_delta=-_SOCIAL_BATTERY_ISOLATION_RATE,
                ),
                source="homeostasis_isolation",
            ))

        return deltas