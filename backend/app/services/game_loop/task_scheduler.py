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
from app.domain.intent_profiles import requires_dialogue_context, produces_claim
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

    def __init__(self, router=None, context_provider=None, economy_tracker=None, belief_store=None, memory_manager=None, confession_parser=None):
        from app.services.execution.npc_conversation import NpcConversation
        from app.services.game_loop.speech_scheduler import SpeechScheduler
        self._executors: Dict[TaskKind, TaskExecutor] = {
            TaskKind.DIALOGUE: DialogueExecutor(router, context_provider, belief_store=belief_store, memory_manager=memory_manager, confession_parser=confession_parser)
        }
        # ADR-O-342: Сохраняем для проверки STM при резолве цели
        self._memory_manager = memory_manager
        # Блокер 5: Sims-слой для ambient-диалогов без LLM
        self._ambient_executor: NpcConversation = NpcConversation()
        self._materializers: Dict[str, Materializer] = {
            "dialogue_line": DialogueMaterializer()
        }
        # BUG-N8 FIX: Инъекция EconomyTracker для трекинга разговоров
        self._economy_tracker = economy_tracker
        # BUG-DL-12: Кэш последних реплик для Speech Bubbles (TTL 180 сек игрового времени)
        self._recent_dialogues: list = []
        self._dialogue_ttl = 180.0  # 3 минуты game_time (чтобы пережить несколько тиков)
        # ADR-O-343 FIX: Блокировка для защиты _recent_dialogues от гонки с ThreadPoolExecutor
        import threading
        self._dialogue_lock = threading.Lock()
        # P1 FIX: Асинхронный пул для неблокирающего выполнения LLM
        # ADR-O-343 FIX: Сериализация LLM-вызовов (max_workers=1).
        # router.py не поддерживает concurrency > 1 (aborting stuck request bug).
        # SpeechScheduler гарантирует отсутствие спама, поэтому 1 поток безопасен и стабилен.
        self._executor_pool = ThreadPoolExecutor(max_workers=1)
        # ADR-O-342: Счётчик тихих отказов (для Causal Probes / IPT)
        self.failed_tasks = 0
        # ADR-O-343: Счётчик всех задач, попавших в обработку (для IPT INV-DIALOGUE-INIT)
        self.total_processed_tasks = 0
        self._spatial_query_service = None
        from app.services.execution.dialogue_queue import DialogueQueue
        self._dialogue_queue = DialogueQueue()
        logger.info("[TASK_SCHED] DialogueQueue initialized")

    def set_spatial_query_service(self, sqs):
        """Инъекция SpatialQueryService для Social Target Resolver."""
        self._spatial_query_service = sqs

    def get_recent_dialogues(self, current_time: float) -> list:
        """Возвращает активные реплики для WorldSnapshotDTO."""
        # ADR-O-343: UI-кэш реплик живёт по wall-clock (infrastructure layer),
        # так как game_time растёт слишком быстро (60+ сек/тик) и реплики исчезают мгновенно.
        import time
        _now = time.time()
        _ui_ttl_sec = 7.0  # 7 секунд реального времени для отображения облачка
        with self._dialogue_lock:
            self._recent_dialogues = [
                d
                for d in self._recent_dialogues
                if _now - d.get("timestamp", 0.0) < _ui_ttl_sec
            ]
            return list(self._recent_dialogues)

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

        # BUG-DLG-006 FIX: Используем game_time_seconds из scene_state вместо wall-clock.
        _game_time = scene_state.get("game_time_seconds", 0.0)

        # ADR-O-343: SpeechScheduler Arbitration инициализируется здесь
        if not hasattr(self, '_speech_scheduler'):
            from app.services.game_loop.speech_scheduler import SpeechScheduler
            self._speech_scheduler = SpeechScheduler(self._memory_manager)

        from app.domain.intent_profiles import requires_llm_materialization
        
        for task_dict in pending:
            if task_dict.get("kind") == "dialogue":
                speaker_id = task_dict.get("owner_id", "")
                _payload = task_dict.get("payload", {})
                _tone = _payload.get("emotional_state", "neutral").upper()
                _intent_type = _payload.get("intent_type", "")
                _has_prop = bool(_payload.get("proposition"))

                # S216 FIX (027.1): Fast-path для задач, не требующих LLM (warn, spread_rumor, steal).
                # Они исполняются синхронно, минуя DialogueQueue, чтобы не создавать backlog.
                if not requires_llm_materialization(_intent_type):
                    self._executor_pool.submit(
                        self._process_tasks_async, scene_state, [task_dict], campaign_id, "canonical", _game_time
                    )
                    continue

                # S216 FIX (027.1): Классификация canonical/ambient через intent_profiles.
                # Если интент produces_claim=True ИЛИ payload содержит proposition -> canonical.
                # Иначе -> ambient. Это предотвращает переполнение canonical-очереди
                # экономическими и социальными интентами без proposition.
                if _has_prop or produces_claim(_intent_type):
                    _task_type = "canonical"
                    _priority = 1  # Высокий приоритет (heapq min-heap)
                else:
                    _task_type = "ambient"
                    _priority = 5  # Низкий приоритет

                self._dialogue_queue.enqueue(
                    task_type=_task_type,
                    payload={
                        "speaker_id": speaker_id,
                        "task_dict": task_dict,
                    },
                    priority=_priority,
                    game_time_seconds=_game_time
                )

        # BUG-CORE-010 / BUG-DLG-005 FIX: Диалоговые задачи перенесены в DialogueQueue.
        # Удаляем их из pending_tasks, чтобы предотвратить бесконечный ре-enqueue и спам кучи.
        # Non-dialogue задачи (если появятся в будущем) остаются в pending.
        scene_state["pending_tasks"] = [
            t for t in pending if t.get("kind") != "dialogue"
        ]

        # ADR-O-343: Жёсткий лимит 1 задача на тик для размеренного пейсинга (Human Pacing).
        # В сочетании с SpeechScheduler (2 сек) это даёт плавную последовательность реплик.
        _max_tasks_per_tick = 1
        _processed_count = 0
        
        while _processed_count < _max_tasks_per_tick:
            _eligible = self._dialogue_queue.dequeue_next(game_time_seconds=_game_time)
            if not _eligible:
                break

            task_dict = _eligible.payload.get("task_dict", {})
            # S196 FIX: task_type хранится на уровне объекта QueuedDialogue, не внутри payload.
            # Ранее всегда падало в "canonical", отправляя ambient-задачи в LLM (нарушение ADR-O-342).
            _task_type = getattr(_eligible, "task_type", "canonical")
            
            # ADR-O-343: Narrative Arbitration после извлечения из очереди
            _admitted, _reason = self._speech_scheduler.admit(task_dict, campaign_id)
            
            if not _admitted:
                if _reason == "PACING":
                    # Возвращаем в очередь для следующего тика и прерываем цикл (ждём wall-clock)
                    self._dialogue_queue.enqueue(
                        task_type=_task_type,
                        payload=_eligible.payload,
                        priority=-_eligible.priority, # heapq инвертирует обратно
                        game_time_seconds=_game_time
                    )
                    break
                elif _reason == "DEDUP":
                    # Уничтожаем спам-дубликат
                    continue

            # Запускаем в асинхронном пуле, чтобы не блокировать idle_tick.
            # Передаём _game_time явно, чтобы избежать гонки с мутирующим scene_state.
            self._executor_pool.submit(
                self._process_tasks_async, scene_state, [task_dict], campaign_id, _task_type, _game_time
            )
            _processed_count += 1

    def _process_tasks_async(self, scene_state: dict, tasks: list, campaign_id: str = "", _task_type: str = "canonical", _game_time: float = 0.0):
        """Фоновая обработка задач LLM."""
        import time
        bus = get_event_bus()
        if not campaign_id:
            campaign_id = scene_state.get("campaign_id", "")

        for task_dict in tasks:
            self.total_processed_tasks += 1
            task = self._reconstruct_task(task_dict)
            if task is None:
                # ENIGMA-ARCH-038: Реконструкция провалена. Задача уже отброшена с ERROR-логом.
                continue

            # Блокер 5: Маршрутизация ambient -> NpcConversation, canonical -> DialogueExecutor
            if _task_type == "ambient":
                executor = self._ambient_executor
            else:
                executor = self._executors.get(task.kind)

            if not executor:
                logger.warning(f"[SCHEDULER] No executor for kind {task.kind}")
                continue

            task.state = TaskState.PROCESSING
            task.campaign_id = campaign_id

            # ADR-O-313: SocialTargetResolver — если цель не задана, выбираем ближнего NPC
            if isinstance(task.payload, DialogueRequest) and not task.payload.target_id:
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
                    # BUG-CORE-011 FIX: Используем KernelRNG вместо глобального random (ADR-O-301).
                    from app.services.npc.kernel_rng import KernelRNG
                    _tick = scene_state.get("tick", 0)
                    _rng = KernelRNG(tick=_tick, npc_id=task.owner_id, salt="task_target_resolve")
                    _resolved_target = _rng.choice(_candidates)

                task.payload = dc_replace(task.payload, target_id=_resolved_target)
                logger.debug(
                    f"[SCHEDULER] Resolved missing target_id to '{_resolved_target}' for {task.owner_id}"
                )

                # ADR-O-342: Hard Contract. Если STM пуст для резолвнутой цели, меняем intent на approach
                if self._memory_manager and task.payload.intent_type not in ("greeting", "approach") and requires_dialogue_context(task.payload.intent_type):
                    _stm_check = self._memory_manager.get_stm_prompt_block_pair(
                        campaign_id, task.owner_id, _resolved_target
                    )
                    if not _stm_check:
                        logger.debug(f"[SCHEDULER] Intercept {task.owner_id} -> {_resolved_target}: No STM, changing intent '{task.payload.intent_type}' to 'approach'")
                        task.payload = dc_replace(task.payload, intent_type="approach")

            artifacts = executor.execute(task)

            try:
                for artifact in artifacts:
                    if artifact.success:
                        task.state = TaskState.FINISHED
                        logger.info(f"[TASK_SCHED] dialogue executed: speaker={task.owner_id} target={task.payload.target_id if hasattr(task.payload, 'target_id') else 'unknown'}")

                        materializer = self._materializers.get(artifact.result_type)
                        if materializer:
                            try:
                                events = materializer.materialize(artifact)
                                for ev in events:
                                    bus.publish(ev)
                            except Exception as mat_exc:
                                logger.error(f"[SCHEDULER] Materializer failed for task {task.task_id}: {mat_exc}", exc_info=True)
                                events = []
                        else:
                            logger.warning(f"[SCHEDULER] No materializer for result_type={artifact.result_type}")
                            events = []

                        # ADR-O-313: Кэшируем реплику для Speech Bubbles
                        if artifact.result_type == "dialogue_line" and events:
                            # BUG-N8 FIX: Регистрируем разговор в EconomyTracker
                            if self._economy_tracker:
                                self._economy_tracker.record_talk(ev.source, scene_state.get("tick", 0))
                            import time
                            _dlg_entry = {
                                "speaker_id": ev.source,
                                "target_id": ev.payload.get("target_id", ""),
                                "text": ev.payload.get("text", ""),
                                "timestamp": time.time(),  # для UI staleness
                                # ADR-O-343 FIX: Используем зафиксированное время тика, чтобы избежать гонки с scene_state.
                                "game_time": _game_time,
                            }
                            with self._dialogue_lock:
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
                        self.failed_tasks += 1
                        # ADR-O-343: Сбрасываем DEDUP в SpeechScheduler, чтобы NPC мог повторить попытку
                        if hasattr(self, '_speech_scheduler'):
                            self._speech_scheduler.reset_context(task_dict)
            except Exception as task_exc:
                logger.error(f"[SCHEDULER] Crashed during task execution {task.task_id}: {task_exc}", exc_info=True)
                self.failed_tasks += 1
                if hasattr(self, '_speech_scheduler'):
                    self._speech_scheduler.reset_context(task_dict)
                break

    def _reconstruct_task(self, task_dict: dict) -> Optional[QueuedTask]:
        """Собирает QueuedTask из словаря (после JSON сериализации).
        
        ENIGMA-ARCH-038: Строгая реконструкция без silent fallback'ов.
        Canonical reconstruction failure → FAILED / drop (никогда не raw dict).
        """
        from app.domain.communication import DialogueRequest, ExposureLevel

        payload_dict = task_dict.get("payload", {})
        task_id = task_dict.get("task_id", "UNKNOWN")

        # 1. Строгое восстановление Kind
        kind_str = task_dict.get("kind")
        try:
            kind = TaskKind(kind_str)
        except (ValueError, TypeError):
            logger.error(f"[SCHEDULER] Reconstruction FAILED for task {task_id}: unknown kind '{kind_str}'. Task dropped.")
            return None

        # 2. Строгое восстановление Priority
        try:
            priority_val = task_dict.get("priority", 1)
            if isinstance(priority_val, int):
                priority = TaskPriority(priority_val)
            else:
                priority = TaskPriority[priority_val]
        except (ValueError, KeyError, TypeError):
            logger.error(f"[SCHEDULER] Reconstruction FAILED for task {task_id}: invalid priority '{priority_val}'. Task dropped.")
            return None

        # 3. Строгое восстановление Payload
        req = None
        if kind == TaskKind.DIALOGUE:
            _intent_type = payload_dict.get("intent_type", "")
            _has_prop = bool(payload_dict.get("proposition"))
            _is_canonical = _has_prop or _intent_type in ("warn", "talk", "intimidate", "threaten", "report", "spread_rumor", "call_for_help", "offer_job", "request_service", "trade")
            
            try:
                semantic = payload_dict.get("exposure_semantic", "normal")
                _emotional_state = payload_dict.get("emotional_state", "нейтрально")
                
                req = DialogueRequest(
                    topic=payload_dict.get("topic", ""),
                    target_id=payload_dict.get("target_id", ""),
                    exposure=ExposureLevel(semantic=semantic),
                    intent_type=_intent_type,
                    emotional_state=_emotional_state,
                    npc_npc_context=payload_dict.get("npc_npc_context", ""),
                    thread_id=payload_dict.get("thread_id", ""),
                    prepared_prompt=payload_dict.get("prepared_prompt", ""),
                    proposition=payload_dict.get("proposition"),
                )
            except Exception as e:
                logger.error(
                    f"[SCHEDULER] Reconstruction FAILED for task {task_id} (Canonical: {_is_canonical}): {e}. "
                    f"Task dropped. Payload: {payload_dict}",
                    exc_info=True
                )
                return None
        else:
            req = payload_dict

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
