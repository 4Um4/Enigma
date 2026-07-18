"""
path: /backend/app/services/execution/dialogue_executor.py
Назначение: Исполнитель задач типа DIALOGUE. Вызывает LLM (или заглушку) и возвращает артефакт.
Зависимости: app.domain.execution, app.domain.communication
Основные сущности: DialogueExecutor
"""
from __future__ import annotations

import concurrent.futures
import logging
from typing import Callable, Iterable, Optional

from app.domain.communication import DialogueRequest
from app.domain.execution import Artifact, QueuedTask

logger = logging.getLogger(__name__)


class DialogueExecutor:
    """
    Исполнитель диалоговых задач.
    В продакшене вызывает LlmProvider. Соблюдает Эпистемический Барьер (ADR-TZ08-6).
    """

    def __init__(
        self,
        router=None,
        context_provider: Optional[Callable[[str, str], dict]] = None,
    ):
        self._router = router
        self._get_context = context_provider or (
            lambda npc_id, camp_id: {"name": npc_id, "description": ""}
        )

    def execute(self, task: QueuedTask) -> Iterable[Artifact]:
        if not isinstance(task.payload, DialogueRequest):
            logger.error(f"[DIALOGUE_EXEC] Invalid payload type: {type(task.payload)}")
            yield Artifact(
                task_id=task.task_id,
                success=False,
                result_type="error",
                data={},
                error_message="Invalid payload for DialogueExecutor",
            )
            return

        req = task.payload
        logger.debug(
            f"[DIALOGUE_EXEC] Executing task for {task.owner_id} -> {req.target_id} on topic '{req.topic}'"
        )

        # Если роутер не задан (sandbox/test), возвращаем заглушку
        if self._router is None:
            logger.warning("[DIALOGUE_EXEC] ModelRouter is None! Fallback to stub.")
            text = f"[Заглушка] {task.owner_id} обращается к {req.target_id} по теме: '{req.topic}'"
        else:
            text = self._generate_with_router(task, req)

        if not text:
            text = f"[Заглушка] {task.owner_id} молчит."

        yield Artifact(
            task_id=task.task_id,
            success=True,
            result_type="dialogue_line",
            data={
                "speaker_id": task.owner_id,
                "target_id": req.target_id,
                "text": text,
                "exposure": req.exposure.semantic,
                "topic": req.topic,
                "emotional_state": req.emotional_state,
            },
        )

    def _generate_with_router(self, task: QueuedTask, req: DialogueRequest) -> str:
        """Генерация через ModelRouter. Не блокирует симуляцию (Правило 2 ТЗ)."""
        ctx = self._get_context(task.owner_id, task.campaign_id)

        system_prompt = (
            "Ты — NPC в мире ENIGMA. Твоя задача — сказать одну короткую реплику (1-2 предложения). "
            "Не описывай действия, только прямую речь. "
            f"Тема разговора: {req.topic}. Намерение: {req.intent_type}."
        )

        user_prompt = (
            f"Твоё имя: {ctx.get('name', task.owner_id)}. "
            f"Краткое описание твоей натуры: {ctx.get('description', 'неизвестно')}. "
            f"Ты обращаешься к: {req.target_id}. "
            "Скажи свою реплику:"
        )

        try:
            from app.services.llm.router import GenerationParams
            raw = self._router.request_for_agent(
                agent_name="npc",
                prompt=user_prompt,
                system_prompt=system_prompt,
                params=GenerationParams(max_tokens=100)
            )
            return raw.strip() if isinstance(raw, str) else ""
        except Exception as e:
            logger.error(f"[DIALOGUE_EXEC] LLM call failed: {e}. Fallback to stub.")
            return ""
