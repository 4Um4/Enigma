"""
path: /backend/app/services/execution/dialogue_materializer.py
Назначение: Превращает доменный Artifact (результат диалога) в WorldEvent (EventDTO) для EventBus.
Зависимости: app.domain.execution, app.services.events.event_types, app.models.events
Основные сущности: DialogueMaterializer
"""
from __future__ import annotations

from typing import List, Dict, Iterable, Any
from app.domain.execution import Artifact
from app.services.events.event_types import EventType


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

        event = EventDTO.create(
            event_type=EventType.NPC_SPOKE.value,
            source=data["speaker_id"],
            payload={
                "target_id": data.get("target_id"),
                "text": data["text"],
                "topic": data.get("topic"),
                "exposure": exposure_semantic,
            },
            visibility=visibility,
            radius=10.0,  # Упрощённый радиус для материализатора
            persistence_level="session",
        )
        return [event]
