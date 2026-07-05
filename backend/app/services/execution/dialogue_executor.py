"""
path: /backend/app/services/execution/dialogue_executor.py
Назначение: Исполнитель задач типа DIALOGUE. Вызывает LLM (или заглушку) и возвращает артефакт.
Зависимости: app.domain.execution, app.domain.communication
Основные сущности: DialogueExecutor
"""

from __future__ import annotations
from typing import Iterable, Callable, Optional
import concurrent.futures
from app.domain.execution import TaskExecutor, Artifact, QueuedTask
from app.domain.communication import DialogueRequest
import logging

logger = logging.getLogger(__name__)

class DialogueExecutor:
    """
    Исполнитель диалоговых задач.
    В продакшене вызывает LlmProvider. Соблюдает Эпистемический Барьер (ADR-TZ08-6).
    """
    def __init__(
        self,
        llm_provider=None,
        context_provider: Optional[Callable[[str, str], dict]] = None
    ):
        self._llm = llm_provider
        self._get_context = context_provider or (lambda npc_id, camp_id: {"name": npc_id, "description": ""})

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
            text = self._generate_with_timeout(task, req)

        if not text:
            text = f"[Stub LLM] {task.owner_id} молчит."

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

    def _generate_with_timeout(self, task: QueuedTask, req: DialogueRequest) -> str:
        """Генерация с таймаутом 2 сек. Не блокирует симуляцию (Правило 2 ТЗ)."""
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
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(
                    self._llm.complete,
                    user_prompt,
                    None,
                    system_prompt
                )
                return future.result(timeout=2.0).strip()
        except concurrent.futures.TimeoutError:
            logger.error(f"[DIALOGUE_EXEC] LLM timeout (2s) for {task.owner_id}. Fallback to stub.")
            return ""
        except Exception as e:
            logger.error(f"[DIALOGUE_EXEC] LLM call failed: {e}. Fallback to stub.")
            return ""