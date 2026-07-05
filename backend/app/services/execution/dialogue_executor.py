"""
path: /backend/app/services/execution/dialogue_executor.py
Назначение: Исполнитель задач типа DIALOGUE. Вызывает LLM (или заглушку) и возвращает артефакт.
Зависимости: app.domain.execution, app.domain.communication
Основные сущности: DialogueExecutor
"""

from __future__ import annotations
from typing import Iterable
from app.domain.execution import TaskExecutor, Artifact, QueuedTask
from app.domain.communication import DialogueRequest
import logging

logger = logging.getLogger(__name__)

class DialogueExecutor:
    """
    Исполнитель диалоговых задач.
    В продакшене здесь будет вызов DM_Agent / NPC_Agent.
    Для тестов и песочниц используется заглушка (Stub).
    """
    def __init__(self, llm_provider=None):
        self._llm = llm_provider

    def execute(self, task: QueuedTask) -> Iterable[Artifact]:
        if not isinstance(task.payload, DialogueRequest):
            logger.error(f"[DIALOGUE_EXEC] Invalid payload type: {type(task.payload)}")
            yield Artifact(
                task_id=task.task_id,
                success=False,
                result_type="error",
                data={},
                error_message="Invalid payload for DialogueExecutor"
            )
            return

        req = task.payload
        logger.debug(f"[DIALOGUE_EXEC] Executing task for {task.owner_id} -> {req.target_id} on topic '{req.topic}'")
        
        # Если провайдер не задан (sandbox/test), возвращаем заглушку
        if self._llm is None:
            text = f"[Stub LLM] {task.owner_id} говорит {req.target_id} о '{req.topic}'"
        else:
            # Здесь будет вызов self._llm.generate(req)
            text = f"[LLM] {task.owner_id} отвечает на тему {req.topic}"

        yield Artifact(
            task_id=task.task_id,
            success=True,
            result_type="dialogue_line",
            data={
                "speaker_id": task.owner_id,
                "target_id": req.target_id,
                "text": text,
                "exposure": req.exposure.semantic,
                "topic": req.topic
            }
        )