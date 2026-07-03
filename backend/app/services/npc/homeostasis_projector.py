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

import math

# --- Коэффициенты гомеостаза ---
_SOCIAL_SATIATION_CONVERSATION_GAIN = 12.0  # скачок насыщения за реплику
_SOCIAL_EMA_CONVERSATION_GAIN = 0.2         # скачок EMA за реплику (факт входа)
# Полураспад EMA: 50 тиков (5 минут game-time). ln(2) / 50 ≈ 0.0138
_SOCIAL_EMA_DECAY_RATE = math.log(2) / 50.0 
# Множитель дрейфа насыщения от давления (setpoint - actual). 
# Определяет, насколько быстро NPC "скучает" или "перегружается".
_SOCIAL_DRIFT_SCALE = 2.0                   


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
                    social_satiation_delta=_SOCIAL_SATIATION_CONVERSATION_GAIN,
                    social_input_ema_delta=_SOCIAL_EMA_CONVERSATION_GAIN,
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
        """Field-driven drift: social_satiation дрейфует под давлением гомеостаза.
        
        Pressure = Setpoint (gregariousness) - Actual (EMA).
        Если Pressure > 0 (скучно) → satiation падает.
        Если Pressure < 0 (перегруз) → satiation растёт.
        Также EMA затухает к 0 (память о социальном входе растворяется).
        Вызывается из Phase 0.5. Clamp выполняется в StateApplicator.
        """
        deltas: List[StateDeltas] = []

        for npc_dict in all_npcs_raw:
            _npc_id = npc_dict.get("npc_id", "")
            if not _npc_id or _npc_id == "player":
                continue

            _psyche = npc_dict.get("psyche", {})
            # Setpoint: вычисляется на лету из gregariousness. 0.2 (интроверт) ... 0.8 (экстраверт)
            _setpoint = 0.2 + (0.6 * float(_psyche.get("gregariousness", 0.5)))
            _actual = float(npc_dict.get("social_input_ema", 0.0))

            # Давление: разница между желаемым и реальным.
            _pressure = _setpoint - _actual
            
            # Дрейф насыщения: изоляция (pressure > 0) опускает, перегруз (pressure < 0) поднимает.
            _satiation_delta = -_pressure * _SOCIAL_DRIFT_SCALE
            
            # Затухание EMA (полураспад)
            _ema_decay_delta = -_actual * _SOCIAL_EMA_DECAY_RATE

            if abs(_satiation_delta) > 1e-4 or abs(_ema_decay_delta) > 1e-4:
                deltas.append(StateDeltas(
                    npc_id=_npc_id,
                    domain=DeltaDomain.SOCIAL,
                    payload=SocialPayload(
                        social_satiation_delta=_satiation_delta,
                        social_input_ema_delta=_ema_decay_delta,
                    ),
                    source="homeostasis_isolation",
                ))

        return deltas