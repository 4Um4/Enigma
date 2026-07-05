"""
path: /backend/app/services/game_loop/task_scheduler.py
Назначение: Читает pending_tasks из scene_state, исполняет их через Executor'ы и публикует WorldEvent'ы.
Зависимости: app.domain.execution, app.services.execution.dialogue_executor, app.services.execution.dialogue_materializer
Основные сущности: TaskScheduler
"""

from __future__ import annotations
import logging
from typing import Dict, Type
from app.domain.execution import QueuedTask, TaskState, TaskKind, TaskPriority, TaskExecutor, Materializer, Artifact
from app.services.execution.dialogue_executor import DialogueExecutor
from app.services.execution.dialogue_materializer import DialogueMaterializer
from app.services.events.event_bus import get_event_bus

logger = logging.getLogger(__name__)

class TaskScheduler:
    """
    Инфраструктурный компонент. Живёт в game_loop.
    Читает scene_state["pending_tasks"], вызывает исполнителей, генерирует события.
    """
    def __init__(self):
        self._executors: Dict[TaskKind, TaskExecutor] = {
            TaskKind.DIALOGUE: DialogueExecutor()
        }
        self._materializers: Dict[str, Materializer] = {
            "dialogue_line": DialogueMaterializer()
        }

    def process_tasks(self, scene_state: dict, max_tasks_per_tick: int = 2) -> None:
        pending = scene_state.get("pending_tasks", [])
        if not pending:
            return
            
        logger.debug(f"[SCHEDULER] Found {len(pending)} pending tasks.")
        processed_count = 0
        remaining_tasks = []
        bus = get_event_bus()

        for task_dict in pending:
            if processed_count >= max_tasks_per_tick:
                remaining_tasks.append(task_dict)
                continue
                
            try:
                task = self._reconstruct_task(task_dict)
            except Exception as e:
                logger.error(f"[SCHEDULER] Failed to reconstruct task {task_dict.get('task_id')}: {e}")
                continue

            executor = self._executors.get(task.kind)
            if not executor:
                logger.warning(f"[SCHEDULER] No executor for kind {task.kind}")
                remaining_tasks.append(task_dict)
                continue
                
            task.state = TaskState.PROCESSING
            artifacts = executor.execute(task)
            
            for artifact in artifacts:
                if artifact.success:
                    task.state = TaskState.FINISHED
                    materializer = self._materializers.get(artifact.result_type)
                    if materializer:
                        events = materializer.materialize(artifact)
                        for ev in events:
                            bus.publish(ev)
                    processed_count += 1
                else:
                    logger.error(f"[SCHEDULER] Task {task.task_id} failed: {artifact.error_message}")
                    task.state = TaskState.FINISHED # Пока без сложного ретрая
                    
        scene_state["pending_tasks"] = remaining_tasks

    def _reconstruct_task(self, task_dict: dict) -> QueuedTask:
        """Собирает QueuedTask из словаря (после JSON сериализации)."""
        from app.domain.communication import DialogueRequest, ExposureLevel
        
        payload_dict = task_dict.get("payload", {})
        req = payload_dict  # По умолчанию оставляем как dict
        
        kind_str = task_dict.get("kind")
        if kind_str == "dialogue":
            try:
                semantic = payload_dict.get("exposure_semantic", "normal")
                exposure = ExposureLevel.from_semantic(semantic)
                
                req = DialogueRequest(
                    topic=payload_dict["topic"],
                    target_id=payload_dict["target_id"],
                    exposure=exposure,
                    intent_type=payload_dict.get("intent_type", "talk")
                )
            except Exception as e:
                logger.error(f"[SCHEDULER] Failed to reconstruct DialogueRequest: {e}. Payload: {payload_dict}")
                req = payload_dict

        # Безопасное восстановление Enum'ов
        try:
            kind = TaskKind(kind_str)
        except ValueError:
            kind = TaskKind.DIALOGUE
            
        try:
            priority_val = task_dict.get("priority", 1)
            if isinstance(priority_val, int):
                priority = TaskPriority(priority_val)
            else:
                priority = TaskPriority[priority_val]
        except ValueError:
            priority = TaskPriority.NORMAL

        return QueuedTask(
            task_id=task_dict["task_id"],
            tick=task_dict["tick"],
            counter=task_dict["counter"],
            kind=kind,
            priority=priority,
            state=TaskState.PENDING,
            creator_system=task_dict.get("creator_system", "AI"),
            owner_id=task_dict["owner_id"],
            target_ids=task_dict.get("target_ids", []),
            payload=req,
            created_tick=task_dict.get("created_tick", 0)
        )