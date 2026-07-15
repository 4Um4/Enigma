"""
path: /backend/app/services/game_loop/task_scheduler.py
Назначение: Читает pending_tasks из scene_state, исполняет их через Executor'ы и публикует WorldEvent'ы.
Зависимости: app.domain.execution, app.services.execution.dialogue_executor, app.services.execution.dialogue_materializer
Основные сущности: TaskScheduler
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Dict

from app.domain.communication import DialogueRequest
from app.domain.execution import (
    Materializer,
    QueuedTask,
    TaskExecutor,
    TaskKind,
    TaskPriority,
    TaskState,
)
from app.services.events.event_bus import get_event_bus
from app.services.execution.dialogue_executor import DialogueExecutor
from app.services.execution.dialogue_materializer import DialogueMaterializer

logger = logging.getLogger(__name__)


class TaskScheduler:
    """
    Инфраструктурный компонент. Живёт в game_loop.
    Читает scene_state["pending_tasks"], вызывает исполнителей, генерирует события.
    """

    def __init__(self, llm_provider=None, context_provider=None, economy_tracker=None):
        self._executors: Dict[TaskKind, TaskExecutor] = {
            TaskKind.DIALOGUE: DialogueExecutor(llm_provider, context_provider)
        }
        self._materializers: Dict[str, Materializer] = {
            "dialogue_line": DialogueMaterializer()
        }
        # BUG-N8 FIX: Инъекция EconomyTracker для трекинга разговоров
        self._economy_tracker = economy_tracker
        # ADR-O-313: Кэш последних реплик для Speech Bubbles (TTL ~ 10 сек)
        self._recent_dialogues: list = []
        self._dialogue_ttl = 10.0
        # P1 FIX: Асинхронный пул для неблокирующего выполнения LLM
        self._executor_pool = ThreadPoolExecutor(max_workers=2)
        self._spatial_query_service = None
        from app.services.execution.dialogue_queue import DialogueQueue
        self._dialogue_queue = DialogueQueue()
        logger.info("[TASK_SCHED] DialogueQueue initialized")

    def set_spatial_query_service(self, sqs):
        """Инъекция SpatialQueryService для Social Target Resolver."""
        self._spatial_query_service = sqs

    def get_recent_dialogues(self, current_time: float) -> list:
        """Возвращает активные реплики для WorldSnapshotDTO."""
        # Чистим протухшие. Используем wall-clock time, так как кэш UI-only.
        import time
        _now = time.time()
        self._recent_dialogues = [
            d
            for d in self._recent_dialogues
            if _now - d.get("timestamp", 0.0) < self._dialogue_ttl
        ]
        return self._recent_dialogues

    def process_tasks(self, scene_state: dict, max_tasks_per_tick: int = 2) -> bool:
        pending = scene_state.get("pending_tasks", [])
        if not pending:
            return True

        logger.debug(
            f"[SCHEDULER] Found {len(pending)} pending tasks. Submitting to background pool."
        )

        # Копируем задачи и очищаем список в scene_state, чтобы не запустить повторно
        tasks_to_process = pending[:max_tasks_per_tick]
        remaining_tasks = pending[max_tasks_per_tick:]
        scene_state["pending_tasks"] = remaining_tasks

        # Запускаем фоновую обработку
        self._executor_pool.submit(
            self._process_tasks_async, scene_state, tasks_to_process
        )

        return True

    def execute_pending(self, scene_state: dict, campaign_id: str) -> None:
        """Берёт задачи из очереди с учётом rate limit и запускает в фоне."""
        pending = scene_state.get("pending_tasks", [])
        if not pending:
            return

        for task_dict in pending:
            if task_dict.get("kind") == "dialogue":
                speaker_id = task_dict.get("owner_id", "")
                _payload = task_dict.get("payload", {})
                tone = _payload.get("tone", "NEUTRAL")
                if tone == "ANGRY":
                    priority = 15
                elif _payload.get("secret_relevant"):
                    priority = 10
                else:
                    priority = 5

                self._dialogue_queue.enqueue(
                    task_type="canonical" if tone != "NEUTRAL" else "ambient",
                    payload={
                        "speaker_id": speaker_id,
                        "task_dict": task_dict,
                    },
                    priority=priority,
                )

        _eligible = self._dialogue_queue.dequeue_next()
        if not _eligible:
            return

        task_dict = _eligible.payload.get("task_dict", {})
        _task_id = task_dict.get("task_id", "")
        
        # Убираем из pending, чтобы не запустить повторно
        scene_state["pending_tasks"] = [
            t for t in pending if t.get("task_id") != _task_id
        ]

        # Запускаем в асинхронном пуле, чтобы не блокировать idle_tick
        self._executor_pool.submit(
            self._process_tasks_async, scene_state, [task_dict], campaign_id
        )

    def _process_tasks_async(self, scene_state: dict, tasks: list, campaign_id: str = ""):
        """Фоновая обработка задач LLM."""
        import time
        bus = get_event_bus()
        if not campaign_id:
            campaign_id = scene_state.get("campaign_id", "")

        for task_dict in tasks:
            try:
                task = self._reconstruct_task(task_dict)
            except Exception as e:
                logger.error(
                    f"[SCHEDULER] Failed to reconstruct task {task_dict.get('task_id')}: {e}"
                )
                continue

            executor = self._executors.get(task.kind)
            if not executor:
                logger.warning(f"[SCHEDULER] No executor for kind {task.kind}")
                continue

            task.state = TaskState.PROCESSING
            task.campaign_id = campaign_id

            # ADR-O-313: SocialTargetResolver — если цель не задана, выбираем ближнего NPC
            if isinstance(task.payload, DialogueRequest) and not task.payload.target_id:
                import random
                from dataclasses import replace as dc_replace

                _resolved_target = "soliloquy"
                # C11 FIX: DialogueRequest уже импортирован на уровне модуля

                # P2 FIX: Использование SpatialQueryService для фильтрации по радиусу
                from app.services.spatial.spatial_query_service import (
                    SpatialQueryService,
                )

                _sqs = SpatialQueryService(
                    npc_positions=scene_state.get("npc_positions", {}),
                    scene_state=scene_state,
                )

                _candidates = []
                _all_npcs = [
                    nid
                    for nid in scene_state.get("npc_positions", {}).keys()
                    if nid != "player" and nid != task.owner_id
                ]
                for nid in _all_npcs:
                    _dist = _sqs.distance(task.owner_id, nid)
                    if _dist <= 5.0:
                        _candidates.append(nid)

                if _candidates:
                    _resolved_target = random.choice(_candidates)

                task.payload = dc_replace(task.payload, target_id=_resolved_target)
                logger.debug(
                    f"[SCHEDULER] Resolved missing target_id to '{_resolved_target}' for {task.owner_id}"
                )

            artifacts = executor.execute(task)

            for artifact in artifacts:
                if artifact.success:
                    task.state = TaskState.FINISHED
                    
                    # Кэшируем для Speech Bubbles (UI)
                    self._recent_dialogues.append({
                        "speaker_id": artifact.data.get("speaker_id"),
                        "text": artifact.data.get("text"),
                        "timestamp": time.time()
                    })
                    logger.info(f"[TASK_SCHED] dialogue executed: speaker={task.owner_id} target={task.payload.target_id if hasattr(task.payload, 'target_id') else 'unknown'}")

                    materializer = self._materializers.get(artifact.result_type)
                    if materializer:
                        events = materializer.materialize(artifact)
                        for ev in events:
                            bus.publish(ev)

                    # ADR-O-313: Кэшируем реплику для Speech Bubbles
                    if artifact.result_type == "dialogue_line" and events:
                        # BUG-N8 FIX: Регистрируем разговор в EconomyTracker
                        if self._economy_tracker:
                            self._economy_tracker.record_talk(ev.source, scene_state.get("tick", 0))
                        _dlg_entry = {
                            "speaker": ev.source,
                            "text": ev.payload.get("text", ""),
                            "timestamp": scene_state.get("game_time_seconds", 0.0),
                        }
                        self._recent_dialogues.append(_dlg_entry)
                        # ADR-O-313 FIX: Зеркалим в scene_state, иначе CDS видит 0 реплик (INV-DIALOGUE-PIPELINE)
                        scene_state.setdefault("recent_dialogues", []).append(
                            _dlg_entry
                        )
                else:
                    logger.error(
                        f"[SCHEDULER] Task {task.task_id} failed: {artifact.error_message}"
                    )
                    task.state = TaskState.FINISHED  # Пока без сложного ретрая

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
                    intent_type=payload_dict.get("intent_type", "talk"),
                )
            except Exception as e:
                logger.error(
                    f"[SCHEDULER] Failed to reconstruct DialogueRequest: {e}. Payload: {payload_dict}"
                )
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
            created_tick=task_dict.get("created_tick", 0),
        )
