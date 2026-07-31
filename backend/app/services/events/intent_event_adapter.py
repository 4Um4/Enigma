# backend/app/services/events/intent_event_adapter.py
# Назначение: Единственная точка превращения решения NPC в событие (Устав §3.3).
# Зависимости: domain.communication.CommunicationIntent, domain.events.EventDTO
# Основные сущности: IntentEventAdapter

from app.domain.communication import CommunicationIntent
from app.domain.events import EventDTO


class IntentEventAdapter:
    """Конвертирует CommunicationIntent → EventDTO для публикации в EventBus.

    Единственная легальная точка такого преобразования.
    Нарушение: создание EventDTO из CommunicationIntent в другом месте = баг (Устав §3.3).
    """

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

        # V8-SOC-2 FIX: Маппим интенты в каноничные EventType, чтобы социальная пропагация работала
        _intent_val = getattr(intent, "intent_type", "")
        _event_type = "npc_spoke"
        if _intent_val == "attack":
            _event_type = "actor_attacks"
        elif _intent_val == "help":
            _event_type = "help"
        elif _intent_val in ("theft", "steal", "rob"):
            _event_type = "theft"
        elif _intent_val == "intimidate":
            _event_type = "intimidation"

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
