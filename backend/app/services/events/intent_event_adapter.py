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

        return EventDTO.create(
            event_type="actor_attacks" if getattr(intent, 'intent_type', '') == "attack" else "npc_spoke",
            source=intent.speaker,
            payload={
                "npc_id": intent.speaker,
                "audience": intent.audience,
                "topic": intent.topic,
                "intent_type": intent.intent_type,
                "emotional_state": intent.emotional_state,
                "exposure_semantic": intent.exposure_level.semantic,
                # GAP8 FIX: Сохраняем семантику директив, иначе DirectiveInterpretationSubscriber глух
                "semantic_action": getattr(intent, 'semantic_action', None),
                "target_id": getattr(intent, 'target_id', None),
            },
            visibility=_visibility_map.get(
                intent.exposure_level.semantic, "public"
            ),
            radius=intent.exposure_level.physical_radius,
            persistence_level="working",
        )