"""
path: /backend/app/services/execution/dialogue_materializer.py
Назначение: Превращает доменный Artifact (результат диалога) в WorldEvent (EventDTO) для EventBus.
Зависимости: app.domain.execution, app.services.events.event_types, app.models.events
Основные сущности: DialogueMaterializer
"""
from __future__ import annotations
import logging



from typing import Any, Iterable

from app.domain.execution import Artifact
from app.services.events.event_types import EventType

logger = logging.getLogger(__name__)

class DialogueMaterializer:
    """Связывает Execution Framework с миром симуляции (EventBus)."""

    def materialize(self, artifact: Artifact) -> Iterable[Any]:
        if artifact.result_type != "dialogue_line" or not artifact.success:
            return []

        data = artifact.data

        # Импортируем EventDTO здесь, чтобы избежать циклических зависимостей на уровне модулей
        from app.domain.events import EventDTO

        # Маппинг exposure на параметры EventDTO
        exposure_semantic = data.get("exposure", "normal")
        visibility = "public"
        if exposure_semantic in ["secret", "whisper"]:
            visibility = "whisper"
        elif exposure_semantic == "private":
            visibility = "private"

        # Р-В (SpeechExposure): радиус — SSOT-вывод из semantic;
        # 999-дефолт и хардкод запрещены (ADR-148). D4: сентинел солилоквия → экстерна
        # лизованное бормотание: whisper-класс независимо от входного semantic
        # (D4); агентная обработка сентинела отсечена в подписчике (Р-А).
        from app.domain.communication import SELF_TALK_SENTINEL, exposure_radius

        _speech_radius = exposure_radius(exposure_semantic)
        if data.get("target_id") == SELF_TALK_SENTINEL:
            visibility = "whisper"
            _speech_radius = exposure_radius("whisper")

        from app.services.verbalization.tone_mapper import ToneMapper

        _tone = ToneMapper.map(data.get("emotional_state"))

        events = []
        
        events.append(EventDTO.create(
            event_type=EventType.NPC_SPOKE.value,
            source=data["speaker_id"],
            payload={
                "target_id": data.get("target_id"),
                "text": data["text"],
                "topic": data.get("topic"),
                "exposure": exposure_semantic,
                "tone": _tone,
                "intent_type": data.get("intent_type", "talk"),
            },
            visibility=visibility,
            radius=10.0,
            persistence_level="session",
        ))

        # S197: Если реплика несёт утверждение (Proposition), публикуем COMMUNICATION_CLAIM
        _prop_data = data.get("proposition")
        if _prop_data:
            events.append(EventDTO.create(
                event_type=EventType.COMMUNICATION_CLAIM.value,
                source=data["speaker_id"],
                payload={
                    "target_id": data.get("target_id"),
                    "claim_id": f"claim-{data['speaker_id']}-{data.get('target_id', 'unknown')}",
                    "proposition": _prop_data,
                    "speech_act": "assert",
                    "tick": 0 # Tick будет перезаписан в ClaimEventSubscriber
                },
                visibility=visibility,
                radius=10.0,
                persistence_level="session",
            ))

        return events
