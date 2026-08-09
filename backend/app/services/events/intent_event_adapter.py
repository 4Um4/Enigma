# backend/app/services/events/intent_event_adapter.py
# Назначение: Единственная точка превращения решения NPC в событие (Устав §3.3).
# Зависимости: domain.communication.CommunicationIntent, domain.events.EventDTO
# Основные сущности: IntentEventAdapter

from app.domain.communication import CommunicationIntent
from app.domain.events import EventDTO
from app.services.events.event_types import EventType


class IntentEventAdapter:
    """Конвертирует CommunicationIntent → EventDTO для публикации в EventBus.

    Единственная легальная точка такого преобразования.
    Нарушение: создание EventDTO из CommunicationIntent в другом месте = баг (Устав §3.3).
    """

    # S4 FIX: Детерминированный мост Intent → EventType.
    # Non-event интенты (IDLE, OBSERVE, FLEE, APPROACH, BLOCK_PATH, AMBUSH, SEEK_ALLY)
    # не должны попадать в IntentEventAdapter, так как они обрабатываются как MovementIntent.
    _INTENT_EVENT_MAP = {
        "talk": EventType.NPC_SPOKE,
        "warn": EventType.WARN,
        "intimidate": EventType.INTIMIDATION,
        "attack": EventType.ACTOR_ATTACKS,
        "help": EventType.HELP,
        "report": EventType.REPORT,
        "trade": EventType.TRADE,
        "explain": EventType.NPC_SPOKE,
        "offer_job": EventType.OFFER_JOB,
        "request_service": EventType.REQUEST_SERVICE,
        "spread_rumor": EventType.SPREAD_RUMOR,
        "call_for_help": EventType.CALL_FOR_HELP,
        "change_role": EventType.CHANGE_ROLE,
    }

    @staticmethod
    def to_event(intent: CommunicationIntent) -> EventDTO:
        """Конвертирует CommunicationIntent в EventDTO.

        ExposureLevel.semantic определяет visibility:
          secret/private → "private"
          whisper → "whisper"
          normal → "public"
          shout → "public" (с увеличенным radius)
        """
        _visibility_map = {
            "secret": "private",
            "private": "private",
            "whisper": "whisper",
            "normal": "public",
            "shout": "public",
        }

        _intent_val = getattr(intent, "intent_type", "")
        # S4 FIX: Явный маппинг. Если интент неизвестен, падаем в npc_spoke,
        # но логируем warning для последующего аудита.
        _event_type = IntentEventAdapter._INTENT_EVENT_MAP.get(_intent_val, EventType.NPC_SPOKE).value
        if _intent_val and _intent_val not in IntentEventAdapter._INTENT_EVENT_MAP:
            import logging
            logging.getLogger(__name__).warning(
                f"[INTENT_EVENT_ADAPTER] Unmapped intent_type '{_intent_val}' defaulted to npc_spoke."
            )

        return EventDTO.create(
            event_type=_event_type,
            source=intent.speaker,
            payload={
                "npc_id": intent.speaker,
                "audience": intent.audience,
                "topic": intent.topic,
                "intent_type": intent.intent_type,
                "emotional_state": intent.emotional_state,
                "exposure_semantic": intent.exposure_level.semantic,
                # GAP8 FIX: Сохраняем семантику директив, иначе DirectiveInterpretationSubscriber глух
                "semantic_action": getattr(intent, "semantic_action", None),
                "target_id": getattr(intent, "target_id", None),
            },
            visibility=_visibility_map.get(intent.exposure_level.semantic, "public"),
            radius=intent.exposure_level.physical_radius,
            persistence_level="working",
        )
