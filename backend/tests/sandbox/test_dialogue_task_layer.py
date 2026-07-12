"""
path: /backend/tests/sandbox/test_dialogue_task_layer.py
Назначение: Верификация ADR-O-313 (Universal Task Layer). Проверка целостности контура: Intent -> Task -> Executor -> Materializer -> Event.
Зависимости: pytest, app.domain.*, app.services.*

Запуск: cd backend; python -m pytest tests/sandbox/test_dialogue_task_layer.py -v; cd ..
"""

import os
import sys

import pytest

# Добавляем корень бэкенда в путь
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from app.domain.communication import DialogueRequest, ExposureLevel
from app.domain.execution import QueuedTask, TaskKind, TaskPriority
from app.services.events.event_types import EventType
from app.services.execution.dialogue_executor import DialogueExecutor
from app.services.execution.dialogue_materializer import DialogueMaterializer


def test_dialogue_execution_pipeline():
    """Тест: Полный цикл Execution Framework для диалога."""

    # 1. Создаем задачу (как это сделал бы TickOrchestrator)
    req = DialogueRequest(
        topic="Погода", target_id="npc_2", exposure=ExposureLevel.from_semantic("normal"), intent_type="talk"
    )

    task = QueuedTask(
        task_id="task-1-npc_1-dlg",
        tick=1,
        counter=0,
        kind=TaskKind.DIALOGUE,
        priority=TaskPriority.NORMAL,
        owner_id="npc_1",
        target_ids=["npc_2"],
        payload=req,
    )

    # 2. Исполняем задачу
    executor = DialogueExecutor()
    artifacts = list(executor.execute(task))

    assert len(artifacts) == 1
    artifact = artifacts[0]
    assert artifact.success is True
    assert artifact.result_type == "dialogue_line"
    assert "Погода" in artifact.data["text"]
    assert artifact.data["speaker_id"] == "npc_1"

    # 3. Материализуем артефакт в событие
    materializer = DialogueMaterializer()
    events = materializer.materialize(artifact)

    assert len(events) == 1
    event = events[0]
    assert event.type == EventType.NPC_SPOKE.value
    assert event.source == "npc_1"
    assert event.payload["target_id"] == "npc_2"
    assert event.payload["topic"] == "Погода"


def test_invalid_payload_rejection():
    """Тест: Исполнитель отклоняет неверный тип груза."""
    task = QueuedTask(
        task_id="task-2",
        tick=1,
        counter=0,
        kind=TaskKind.DIALOGUE,
        owner_id="npc_1",
        payload={"wrong": "payload"},  # Не наследник TaskPayload
    )

    executor = DialogueExecutor()
    artifacts = list(executor.execute(task))

    assert len(artifacts) == 1
    assert artifacts[0].success is False
    assert artifacts[0].error_message is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
