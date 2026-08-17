"""
path: /project/backend/app/services/events/social_action_subscriber.py
Назначение: S201 — Социальный актуализатор. Слушает SOCIAL_ACTION и проецирует его в legacy-события.
Зависимости: app.domain.events, app.services.events.event_bus
Основные сущности: SocialActionSubscriber
"""

import logging
from typing import Any

from app.domain.events import EventDTO
from app.services.events.event_bus import EventBus

logger = logging.getLogger(__name__)

class SocialActionSubscriber:
    """Слушает SOCIAL_ACTION и генерирует проекции (COMMUNICATION_CLAIM, NPC_SPOKE, ACTOR_ATTACKS)."""

    def __init__(self, event_bus: EventBus):
        self._bus = event_bus

    def on_social_action(self, event: EventDTO) -> None:
        payload = event.payload
        action = payload.get("action", "DIALOGUE")
        speech_act = payload.get("speech_act", "assert")
        prop = payload.get("proposition")
        target = payload.get("target", "")
        text = payload.get("text", "") # Текст может приходить, если это реплика

        logger.debug(f"[SOCIAL_ACTION_SUB] Received action={action} from={event.source} to={target}")

        # 1. Projection → COMMUNICATION_CLAIM (если есть proposition)
        if prop:
            claim_event = EventDTO.create(
                event_type="communication_claim",
                source=event.source,
                payload={
                    "target_id": target,
                    "proposition": prop,
                    "speech_act": speech_act,
                    "claim_id": f"proj-{event.id}",
                    "tick": payload.get("tick", 0)
                },
                visibility=event.visibility,
                radius=event.radius
            )
            self._bus.publish(claim_event)

        # 2. Projection → NPC_SPOKE (если action == DIALOGUE или есть text)
        if action == "DIALOGUE" and text:
            spoke_event = EventDTO.create(
                event_type="npc_spoke",
                source=event.source,
                payload={
                    "target_id": target,
                    "text": text,
                    "tone": payload.get("tone", "NEUTRAL"),
                    "topic": payload.get("topic", ""),
                    "intent_type": payload.get("social_intent", "talk")
                },
                visibility=event.visibility,
                radius=event.radius
            )
            self._bus.publish(spoke_event)

        # 3. Projection → ACTOR_ATTACKS (если action == ATTACK)
        if action == "ATTACK":
            attack_event = EventDTO.create(
                event_type="actor_attacks",
                source=event.source,
                payload={
                    "target_id": target,
                    "force": payload.get("physical_force", 0.8)
                },
                visibility=event.visibility,
                radius=event.radius
            )
            self._bus.publish(attack_event)