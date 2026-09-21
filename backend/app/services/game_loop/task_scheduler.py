"""
path: /backend/app/services/game_loop/task_scheduler.py
Назначение: Читает pending_tasks из scene_state, исполняет их через Executor'ы и публикует WorldEvent'ы.
Зависимости: app.domain.execution, app.services.execution.dialogue_executor, app.services.execution.dialogue_materializer
Основные сущности: TaskScheduler
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Optional


# ADR-O-399: атомарный контейнер результата worker-задачи. Не SSOT, не шина,
# не manager — пассивные данные для deterministic commit на границе тика.
@dataclass(frozen=True)
class _TaskArtifactRecord:
    submit_tick: int
    task_id: str
    events: tuple
    dialogue_entry: Optional[dict]
    economy_talks: tuple
    speech_reset: Optional[dict]
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
from app.domain.intent_profiles import produces_claim, requires_dialogue_context
from app.services.events.event_bus import get_event_bus
from app.services.execution.dialogue_executor import DialogueExecutor
from app.services.execution.dialogue_materializer import DialogueMaterializer

logger = logging.getLogger(__name__)

# 021 Calibration candidates (behavior-identical extraction)
_DIALOGUE_TTL: float = 180.0
_UI_TTL_SEC: float = 7.0
# IRON RIVER D-1 (F1b): TTL UI-кэша в ГЕЙМ-секундах (60 сек/тик × ~2 тика).
# Прежний wall-clock TTL (7с) несовместим с game-time осью timestamp (F1a).
# CALIBRATION_CANDIDATE: окно видимости реплики в UI при 60 сек/тик.
_RECENT_TTL_GAME_SEC: float = 120.0
_MAX_TASKS_PER_TICK: int = 1

class TaskScheduler:
    """
    Инфраструктурный компонент. Живёт в game_loop.
    Читает scene_state["pending_tasks"], вызывает исполнителей, генерирует события.
    """

    def __init__(self, router: Any = None, context_provider: Any = None, economy_tracker: Any = None, belief_store: Any = None, memory_manager: Any = None, confession_parser: Any = None, npc_states_provider: Any = None) -> None:
        from app.services.execution.npc_conversation import NpcConversation
        self._executors: Dict[TaskKind, TaskExecutor] = {
            TaskKind.DIALOGUE: DialogueExecutor(router, context_provider, belief_store=belief_store, memory_manager=memory_manager, confession_parser=confession_parser)
        }
        # ADR-O-342: Сохраняем для проверки STM при резолве цели
        self._memory_manager = memory_manager
        # B (пункт 10, решение Мастера 2026-09-11): провайдер NPC-статов для
        # liveness-гейта диалоговых задач (Callable[[campaign_id], list[dict]]).
        # None = гейт выключен (fail-open) — sandbox/тесты без wiring как раньше.
        self._npc_states_provider = npc_states_provider
        # Блокер 5: Sims-слой для ambient-диалогов без LLM
        self._ambient_executor: NpcConversation = NpcConversation()
        self._materializers: Dict[str, Materializer] = {
            "dialogue_line": DialogueMaterializer()
        }
        # BUG-N8 FIX: Инъекция EconomyTracker для трекинга разговоров
        self._economy_tracker = economy_tracker
        # BUG-DL-12: Кэш последних реплик для Speech Bubbles (TTL 180 сек игрового времени)
        self._recent_dialogues: list = []
        self._dialogue_ttl = _DIALOGUE_TTL
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
        # ADR-O-399: Task Worker Outbox. Lifetime = от submit до первой
        # разрешённой drain boundary (может пересекать несколько тиков —
        # completion-время воркера не является канонической категорией).
        # Писатель push — воркер (под локом), потребитель — main-thread drain.
        self._task_outbox: list = []
        self._task_outbox_lock = threading.Lock()
        # ADR-O-343: Счётчик всех задач, попавших в обработку (для IPT INV-DIALOGUE-INIT)
        self.total_processed_tasks = 0
        self._spatial_query_service = None
        from app.services.execution.dialogue_queue import DialogueQueue
        self._dialogue_queue = DialogueQueue()
        # S262: множество enqueue-дедупа (speaker, intent) — см. DLG_ENQ_DEDUP
        self._enqueued_keys: set = set()
        # S203.4 (ADR-O-365, D-2): outbox терминалов task-исполнителя.
        # Воркеры пула НИКОГДА не пишут реестр (single-writer); sync-применение —
        # drain_commitment_outbox (вход execute_pending + безусловно из idle_tick).
        self._commitment_outbox: list = []
        self._commitment_outbox_lock = threading.Lock()
        logger.info("[TASK_SCHED] DialogueQueue initialized")

    def _owner_is_dead(self, campaign_id: str, owner_id: str) -> bool:
        """B (пункт 10): True только при доказанном life_status=DEAD владельца
        задачи — канонический ADR-O-365 terminal-mapping «actor DEAD → EXPIRED»
        (достройка заявленного мэппинга, НЕ новая система смерти). Fail-open по
        S198-паритету: провайдер не задан / владелец не найден / ошибка → False
        (задача исполняется; возрастной M-29 разбирает брошенные). Чтение —
        мир не мутируется."""
        if not self._npc_states_provider or not owner_id:
            return False
        try:
            _states = self._npc_states_provider(campaign_id) or []
        except Exception as _prov_err:
            logger.warning(f"[TASK_SCHED] liveness-gate provider failed: {_prov_err}")
            return False
        for _n in _states:
            if not isinstance(_n, dict):
                continue
            if _n.get("npc_id") == owner_id or _n.get("id") == owner_id:
                _bs = _n.get("body_state") or {}
                return _bs.get("life_status") == "DEAD"
        return False

    def _owner_intent_flees(self, campaign_id: str, owner_id: str) -> bool:
        """[GC-I01-E2] GC-INTERRUPT-01: True только при доказанном текущем
        intent='flee' владельца — воля владельца ушла из разговора
        (E1b-провод: NPCState.intent -> npc_dict -> снапшот провайдера).
        Зеркало _owner_is_dead; fail-open S198-паритет (нет провайдера/
        не найден/ошибка -> False -> исполнение). Чтение — мир не мутируется."""
        if not self._npc_states_provider or not owner_id:
            return False
        try:
            _states = self._npc_states_provider(campaign_id) or []
        except Exception as _prov_err:
            logger.warning(f"[TASK_SCHED] stale-intent-gate provider failed: {_prov_err}")
            return False
        for _n in _states:
            if not isinstance(_n, dict):
                continue
            if _n.get("npc_id") == owner_id or _n.get("id") == owner_id:
                return _n.get("intent") == "flee"
        return False

    def set_epistemic_wiring(self, discovery_bridge=None, npc_states_provider=None,
                             relationship_provider=None, subject_resolver=None) -> None:
        """P6/E1 (S255): проброс игрок-контура P3→P4→P5→P6 в DialogueExecutor
        (late-binding; прецедент set_spatial_query_service)."""
        _dlg = self._executors.get(TaskKind.DIALOGUE)
        if _dlg is None:
            logger.warning("[TASK_SCHED] set_epistemic_wiring: DialogueExecutor отсутствует")
            return
        _dlg.set_epistemic_wiring(
            discovery_bridge=discovery_bridge,
            npc_states_provider=npc_states_provider,
            relationship_provider=relationship_provider,
            subject_resolver=subject_resolver,
        )

    def set_spatial_query_service(self, sqs: Any) -> None:
        """Инъекция SpatialQueryService для Social Target Resolver."""
        self._spatial_query_service = sqs

    # ── S203.4 (ADR-O-365, D-2): outbox терминалов ──────────────────────

    def _record_task_outcome(
        self, npc_id: str, outcome: str, fail_reason: str = "", interrupt_reason: str = ""
    ) -> None:
        """Воркер/синхронный путь → thread-safe outbox. Реестр НЕ пишется здесь.
        [GC-I01-E2] interrupt_reason — четвёртая позиция кортежа (D-6:
        причина прерывания ≠ причина провала; закон №16 — единый реестр)."""
        with self._commitment_outbox_lock:
            self._commitment_outbox.append(  # [GC-I01-E2] 4-позиция: interrupt_reason
                (npc_id, outcome, fail_reason or None, interrupt_reason or None)
            )

    def drain_commitment_outbox(self, scene_state: dict) -> None:
        """Единственная точка применения терминалов task → реестр.

        Вызывается: (а) на входе execute_pending (покрывает calibration/тесты),
        (б) безусловно из idle_tick между execute_pending и unlock_tick
        (F23: тихие тики не создают backlog). terminal_tick = тик дренажа —
        честный момент наблюдения. Executor-mismatch (гонка/ambient) →
        mirror_task_terminal сам откажется без мутации.
        """
        if not self._commitment_outbox:
            return
        from app.services.action.commitment_registry import CommitmentRegistry

        _tick = scene_state.get("tick", 0)
        with self._commitment_outbox_lock:
            _batch = self._commitment_outbox
            self._commitment_outbox = []
        for _entry in _batch:  # [GC-I01-E2] 4-кортежи; legacy 3-кортежи живы
            _npc_id = _entry[0]
            _outcome = _entry[1]
            _fail = _entry[2] if len(_entry) > 2 else None
            _interrupt = _entry[3] if len(_entry) > 3 else None
            CommitmentRegistry.mirror_task_terminal(
                scene_state,
                _npc_id,
                _tick,
                _outcome,
                fail_reason=_fail,
                interrupt_reason=_interrupt,
            )

    def drain_task_worker_outbox(self, scene_state: dict) -> None:
        """ADR-O-399: deterministic commit артефактов воркера (main thread).

        Batch = артефакты, готовые к данной drain boundary (completion-время
        в канон не входит). Порядок записей — сортировка по стабильному ключу
        (submit_tick, task_id). Порядок эффектов per-record зеркалит прежнюю
        последовательность воркера: events → economy → dialogue → speech_reset.
        Две точки вызова: вход execute_pending + idle_tick до unlock_tick
        (симметрия S203.4/F23); третья точка запрещена. Обе — безусловные:
        pending_tasks == 0 не блокирует дренаж готовых артефактов.
        """
        if not self._task_outbox:
            return
        with self._task_outbox_lock:
            batch = self._task_outbox
            self._task_outbox = []
        batch.sort(key=lambda _r: (_r.submit_tick, _r.task_id))
        _bus = get_event_bus()
        for _rec in batch:
            for _ev in _rec.events:
                # ADR-O-399 Iter1: штамп событийного времени — submit_tick
                # (main thread). Единственный легальный источник event-time
                # для L1-датировки; arrival воркера в канон не входит.
                _payload = getattr(_ev, "payload", None)
                if isinstance(_payload, dict):
                    _payload.setdefault("event_tick", _rec.submit_tick)
                _bus.publish(_ev)
            for _npc, _tick in _rec.economy_talks:
                if self._economy_tracker:
                    self._economy_tracker.record_talk(_npc, _tick)
            if _rec.dialogue_entry is not None:
                with self._dialogue_lock:
                    self._recent_dialogues.append(_rec.dialogue_entry)
                # ADR-O-313: зеркалирование в scene_state — только здесь, main thread
                scene_state.setdefault("recent_dialogues", []).append(_rec.dialogue_entry)
            if _rec.speech_reset is not None and hasattr(self, '_speech_scheduler'):
                self._speech_scheduler.reset_context(_rec.speech_reset)

    def _push_task_artifact(self, submit_tick: int, task_id: str, events: list,
                            dialogue_entry, talks: list, speech_reset) -> None:
        """ADR-O-399: единственный push воркера в outbox (данные, не эффекты)."""
        with self._task_outbox_lock:
            self._task_outbox.append(_TaskArtifactRecord(
                submit_tick=submit_tick,
                task_id=task_id,
                events=tuple(events),
                dialogue_entry=dialogue_entry,
                economy_talks=tuple(talks),
                speech_reset=speech_reset,
            ))

    def get_recent_dialogues(self, current_time: float) -> list:
        """Возвращает активные реплики для WorldSnapshotDTO.

        IRON RIVER D-1/P0-1 (F1b): единая каузальная ось. Запись timestamp =
        game_time (F1a); фильтр сравнивает game-time с game-time. Смешение осей
        (wall-clock запись vs game-time аргумент у всех трёх caller'ов:
        game_loop:1101/1414/1664, tick_orchestrator:1722) делало TTL-фильтр
        всегда-просроченным — реплики выметались из UI-кэша. UI-staleness
        переехал на real_ts (F1a) — отдельно, §15.2. TTL в game-секундах:
        60 сек/тик × 2 тика (CALIBRATION_CANDIDATE 021-наследие).
        """
        with self._dialogue_lock:
            self._recent_dialogues = [
                d
                for d in self._recent_dialogues
                if (current_time - d.get("timestamp", 0.0))
                < _RECENT_TTL_GAME_SEC
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
        # B (пункт 10, решение Мастера; точка №3 — найдена прогоном №149):
        # process_tasks — параллельный dispatcher (минуя DialogueQueue и оба
        # гейта execute_pending): мёртвый владелец → EXPIRED по каноническому
        # ADR-O-365 мэппингу ДО пула — «посмертные реплики через этот путь
        # при зелёном dequeue-гейте» были последним разрывом пункта 10.
        _camp = scene_state.get("campaign_id", "")
        _alive = []
        for _td in tasks_to_process:
            _own = _td.get("owner_id", "")
            if self._owner_is_dead(_camp, _own):
                self._record_task_outcome(_own, "EXPIRED")
                logger.info(
                    f"[TASK_SCHED] liveness-gate (process_tasks): owner={_own} "
                    f"DEAD → task EXPIRED (mid-generation interrupt)"
                )
                continue
            # [GC-I01-E2] GC-INTERRUPT-01: flee-гейт (после death-check — смерть
            # сильнее). Воля владельца ушла из разговора: реплика не
            # материализуется, задача INTERRUPTED(TASK_STALE_INTENT).
            from app.domain.action_commitment import INTERRUPT_TASK_STALE_INTENT  # noqa: ENIGMA002

            if self._owner_intent_flees(_camp, _own):
                self._record_task_outcome(_own, "INTERRUPTED", interrupt_reason=INTERRUPT_TASK_STALE_INTENT)
                logger.info(
                    f"[TASK_SCHED] stale-intent-gate (process_tasks): owner={_own} "
                    f"intent=flee → task INTERRUPTED (TASK_STALE_INTENT)"
                )
                continue
            _alive.append(_td)
        tasks_to_process = _alive
        scene_state["pending_tasks"] = remaining_tasks

        # Запускаем фоновую обработку
        self._executor_pool.submit(
            self._process_tasks_async, scene_state, tasks_to_process,
            submit_tick=scene_state.get("tick", 0)
        )

        return True

    def execute_pending(self, scene_state: dict, campaign_id: str) -> None:
        """Берёт задачи из очереди с учётом rate limit и запускает в фоне."""
        # S203.4 (D-2): дренаж ДО разбора — терминалы прошлого цикла применяются
        # ADR-O-399 (точка (а)): артефакты воркера коммитятся ДО dequeue новых задач
        self.drain_task_worker_outbox(scene_state)
        # даже при пустой очереди этого вызова.
        self.drain_commitment_outbox(scene_state)
        pending = scene_state.get("pending_tasks", [])
        if not pending:
            return

        # BUG-DLG-006 FIX: Используем game_time_seconds из scene_state вместо wall-clock.
        _game_time = scene_state.get("game_time_seconds", 0.0)

        # ADR-O-343: SpeechScheduler Arbitration инициализируется здесь
        if not hasattr(self, '_speech_scheduler'):
            from app.services.game_loop.speech_scheduler import SpeechScheduler
            self._speech_scheduler = SpeechScheduler(self._memory_manager)

        # [GC-I01-E2] GC-INTERRUPT-01: причина прерывания (закон №16, локальный
        # импорт — прецедент файла; шрам-закон №1: поверхность перед использованием).
        from app.domain.action_commitment import INTERRUPT_TASK_STALE_INTENT
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
                    # FIX [4]: fast-path исполняется СИНХРОННО на вызывающем потоке
                    # (не через _executor_pool). warn/spread_rumor/steal не используют
                    # LLM (stub-режим или детерминированный текст) → мгновенно. Пул с
                    # max_workers=1 (ADR-O-343) более не блокирует доставку: warn-задача
                    # публикует NPC_SPOKE и обновляет EpistemicStore ДО возврата из
                    # execute_pending → поллинг видит conf в том же тике.
                    # LLM-задачи (talk и др.) остаются на пуле — ADR-O-343 не нарушен.
                    # B (пункт 10): liveness-гейт fast-path — тот же ADR-O-365
                    # terminal-mapping, main-thread sync-ветка (как DEDUP).
                    if self._owner_is_dead(campaign_id, speaker_id):
                        self._record_task_outcome(speaker_id, "EXPIRED")
                        logger.info(
                            f"[TASK_SCHED] liveness-gate (fast-path): owner={speaker_id} "
                            f"DEAD → task EXPIRED (mid-generation interrupt)"
                        )
                        continue
                    # [GC-I01-E2] GC-INTERRUPT-01: flee-гейт fast-path (после
                    # death-check): warn/spread_rumor убегающего тоже не
                    # материализуются — воля владельца сильнее типа задачи.
                    if self._owner_intent_flees(campaign_id, speaker_id):
                        self._record_task_outcome(speaker_id, "INTERRUPTED", interrupt_reason=INTERRUPT_TASK_STALE_INTENT)
                        logger.info(
                            f"[TASK_SCHED] stale-intent-gate (fast-path): owner={speaker_id} "
                            f"intent=flee → task INTERRUPTED (TASK_STALE_INTENT)"
                        )
                        continue
                    # FIX (S271, предгейт P1): fast-path omitил submit_tick →
                    # дефолт 0 → _TaskArtifactRecord.submit_tick=0 → event_tick=0
                    # в drain. Симметрично process_tasks:333 и dequeue-пути :556 —
                    # восстановление существующего контракта, не новая семантика.
                    self._process_tasks_async(scene_state, [task_dict], campaign_id, "canonical", _game_time, scene_state.get("tick", 0))
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

                # S262 (очередной затор): enqueue-дедуп спикер+интент —
                # постоянные интенты (TRADE/CALL_FOR_HELP/OFFER_JOB каждый
                # тик от одного NPC) забивали очередь до капа 20, TALK
                # конкурировал со спамом в общем heap, ambient-потери
                # каждый тик (замер: 2-3 OVERFLOW/тик). Дедуп при enqueue
                # (а не dequeue): в очереди — не более одной задачи на
                # (speaker, intent); дубли skip с наблюдаемостью.
                # SpeechScheduler-pacing остаётся тормозом темпа; этот
                # гейт — тормозом заполнения. Множество живёт на
                # scheduler'е, очищается при dequeue/mark_completed.
                _enq_key = (speaker_id, _intent_type)
                if _enq_key in self._enqueued_keys:
                    # S262-багфикс (молчаливое исчезновение): дедуп-skip
                    # ОБЯЗАН завершать задачу честно — иначе интент висит
                    # в NPC-стейте без исполнителя → from_legacy-валидатор
                    # «intent without target» → TICK_CRASH (поймано тик-1
                    # superbox_social_deterministic). Протокол DEDUP-ветки:
                    # canonical → CANCELLED в реестре обязательств.
                    if _task_type == "canonical":
                        self._record_task_outcome(speaker_id, "CANCELLED")
                    logger.info(
                        "[DLG_ENQ_DEDUP] skip дубликата: speaker=%s intent=%s",
                        speaker_id, _intent_type,
                    )
                    continue
                # S262: overflow-наблюдаемость (L4; закрывает молчаливую
                # потерю Н-56): при enqueue на полной очереди — WARNING.
                _queue_full = (
                    self._dialogue_queue.pending_count() >= 20
                    if hasattr(self._dialogue_queue, "pending_count")
                    else False
                )
                if _queue_full:
                    logger.warning(
                        "[DLG_QUEUE_OVERFLOW] enqueue при полной очереди "
                        f"(pending>=20, speaker={speaker_id}, "
                        f"intent={task_dict.get('payload', {}).get('intent_type', '?')})"
                    )
                self._enqueued_keys.add(_enq_key)
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
        # _MAX_TASKS_PER_TICK moved to module level (021)
        # S262 (DLG-стабилизация, приказ Мастера): адаптивный дренаж —
        # при переполнении очереди (>10) лимит 3/тик, иначе базовый 1.
        # Честный pacing остаётся за SpeechScheduler (2 тика/спикер);
        # дренаж лишь перестаёт душить очередь: enqueue (интент/NPC/тик)
        # стабильно превышал дренаж 1/тик → очередь на капе 20 →
        # молчаливая потеря задач (DLG_QUEUE OVERFLOW, Н-56) → реплики-
        # лотерея (25/3/0/0 в замерах S262).
        _pending_now = (
            self._dialogue_queue.pending_count()
            if hasattr(self._dialogue_queue, "pending_count")
            else 0
        )
        _drain_limit = _MAX_TASKS_PER_TICK + 2 if _pending_now > 10 else _MAX_TASKS_PER_TICK
        _processed_count = 0

        while _processed_count < _drain_limit:
            _eligible = self._dialogue_queue.dequeue_next(game_time_seconds=_game_time)
            if not _eligible:
                break

            task_dict = _eligible.payload.get("task_dict", {})
            # S196 FIX: task_type хранится на уровне объекта QueuedDialogue, не внутри payload.
            # Ранее всегда падало в "canonical", отправляя ambient-задачи в LLM (нарушение ADR-O-342).
            _task_type = getattr(_eligible, "task_type", "canonical")

            # ADR-O-343: Narrative Arbitration после извлечения из очереди
            # IRON RIVER D-1/P0-2 (F2): admission на каузальной оси —
            # game_time (в scope, BUG-DLG-006), не wall-clock.
            _admitted, _reason = self._speech_scheduler.admit(
                task_dict, campaign_id, game_time_seconds=_game_time
            )

            if not _admitted:
                if _reason == "PACING":
                    # Возвращаем в очередь для следующего тика.
                    # S262 (F2-регрессия): break был корректен для wall-clock-
                    # pacing (2 сек реального ожидания); на game-time оси
                    # (2 тика) PACING ОДНОГО спикера не должен блокировать
                    # чужие задачи — иначе первая непрошедшая разрывает
                    # весь дренаж (processed=1 при 20 ожидающих, S262-замер).
                    # continue: следующий кандидат очереди.
                    self._dialogue_queue.enqueue(
                        task_type=_task_type,
                        payload=_eligible.payload,
                        priority=-_eligible.priority, # heapq инвертирует обратно
                        game_time_seconds=_game_time
                    )
                    continue
                elif _reason == "DEDUP":
                    # Уничтожаем спам-дубликат
                    if _task_type == "canonical":
                        # S203.4: DEDUP-смерть → CANCELLED (main-thread sync-путь;
                        # применится дренажем ЭТОГО же idle-окна ниже).
                        self._record_task_outcome(
                            task_dict.get("owner_id", ""), "CANCELLED"
                        )
                    continue

            # B (пункт 10, решение Мастера): liveness-гейт при dequeue — смерть
            # прерывает mid-generation: реплика мёртвого не материализуется,
            # задача получает EXPIRED по каноническому ADR-O-365 мэппингу
            # (жизненный цикл убитой задачи = прецедент DEDUP-ветки). Fail-open:
            # нет провайдера/не найден/ошибка → исполнение как раньше.
            if self._owner_is_dead(campaign_id, task_dict.get("owner_id", "")):
                self._record_task_outcome(task_dict.get("owner_id", ""), "EXPIRED")
                logger.info(
                    f"[TASK_SCHED] liveness-gate: owner={task_dict.get('owner_id', '')} "
                    f"DEAD → task EXPIRED (mid-generation interrupt)"
                )
                continue
            # [GC-I01-E2] GC-INTERRUPT-01: flee-гейт при dequeue (после
            # death-check). In-flight-политика = death-прецедент ADR-O-387:
            # гейт стоит до executor.execute — начатая генерация не отзывается.
            if self._owner_intent_flees(campaign_id, task_dict.get("owner_id", "")):
                self._record_task_outcome(task_dict.get("owner_id", ""), "INTERRUPTED", interrupt_reason=INTERRUPT_TASK_STALE_INTENT)
                logger.info(
                    f"[TASK_SCHED] stale-intent-gate (dequeue): owner={task_dict.get('owner_id', '')} "
                    f"intent=flee → task INTERRUPTED (TASK_STALE_INTENT)"
                )
                continue
            # Запускаем в асинхронном пуле, чтобы не блокировать idle_tick.
            # Передаём _game_time явно, чтобы избежать гонки с мутирующим scene_state.
            self._executor_pool.submit(
                self._process_tasks_async, scene_state, [task_dict], campaign_id, _task_type, _game_time,
                scene_state.get("tick", 0)
            )
            _processed_count += 1

    def _process_tasks_async(self, scene_state: dict, tasks: list, campaign_id: str = "", _task_type: str = "canonical", _game_time: float = 0.0, submit_tick: int = 0):
        """Фоновая обработка задач LLM (ADR-O-399: только compute, observable-эффекты — в drain)."""
        import os as _os
        import time
        # ADR-O-399 / §15.2-паттерн DRIFT_*: test-only латентность воркера.
        # Моделирует время ГОТОВНОСТИ артефакта, не меняет его содержание —
        # гейт controlled-latency детерминизма. Production default = 0.
        _latency_ms = int(_os.environ.get("DRIFT_WORKER_LATENCY_MS", "0"))
        if _latency_ms > 0:
            time.sleep(_latency_ms / 1000.0)

        # S203.4: константы fail_reason для терминальных хуков (закон №16).
        # [GC-I01-E2] + INTERRUPT_TASK_STALE_INTENT (flee-гейт ниже).
        from app.domain.action_commitment import (
            FAIL_TASK_CRASH,
            FAIL_TASK_ERROR,
            INTERRUPT_TASK_STALE_INTENT,
        )
        # ADR-O-399: bus воркеру больше не нужен — publish только в drain
        # (main thread). Если это последнее использование get_event_bus в
        # функции — импорт ниже не встречается (проверяет structural probe).
        if not campaign_id:
            campaign_id = scene_state.get("campaign_id", "")

        for task_dict in tasks:
            # ADR-O-399: per-task коллекторы артефакта (сброс на каждой задаче)
            _events_collected: list = []
            _talks_collected: list = []
            _dlg_entry = None
            _speech_reset = None
            # B8 (пункт 10, №149/№151-ретракция): worker-гейт — последняя
            # точка прерывания mid-generation. Dispatch-гейты не покрывают
            # in-flight: задача сабмичена ДО смерти (владелец жил — гейты
            # честно прошли), воркер исполняет ПОСЛЕ. Проверка перед
            # executor.execute переспрашивает живость на каждом хопе
            # (enqueue→dequeue→submit→execute) — любые будущие dispatch-точки
            # закрыты by construction. EXPIRED — канонический ADR-O-365
            # terminal-mapping; outbox-дренаж воркера — прецедент D-2.
            if self._owner_is_dead(campaign_id, task_dict.get("owner_id", "")):
                self._record_task_outcome(task_dict.get("owner_id", ""), "EXPIRED")
                logger.info(
                    f"[TASK_SCHED] liveness-gate (worker): owner={task_dict.get('owner_id', '')} "
                    f"DEAD → task EXPIRED (mid-generation interrupt)"
                )
                continue
            # [GC-I01-E2] GC-INTERRUPT-01: flee-гейт worker — последний рубеж
            # до executor.execute (прецедент B8: задача, сабмиченная до
            # изменения воли, не исполняется; начатая генерация не отзывается).
            if self._owner_intent_flees(campaign_id, task_dict.get("owner_id", "")):
                self._record_task_outcome(task_dict.get("owner_id", ""), "INTERRUPTED", interrupt_reason=INTERRUPT_TASK_STALE_INTENT)
                logger.info(
                    f"[TASK_SCHED] stale-intent-gate (worker): owner={task_dict.get('owner_id', '')} "
                    f"intent=flee → task INTERRUPTED (TASK_STALE_INTENT)"
                )
                continue
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
                if _task_type == "canonical":
                    self._record_task_outcome(task_dict.get("owner_id", ""), "CANCELLED")
                continue

            task.state = TaskState.PROCESSING
            task.campaign_id = campaign_id
            # S203.4: COMMITTED→EXECUTING (только canonical — ambient вне владения, D-8).
            if _task_type == "canonical":
                self._record_task_outcome(task.owner_id, "EXECUTING")

            # ADR-O-313: SocialTargetResolver — если цель не задана, выбираем ближнего NPC
            if isinstance(task.payload, DialogueRequest) and not task.payload.target_id:
                from dataclasses import replace as dc_replace

                from app.domain.communication import (
                    SELF_TALK_SENTINEL,  # Р-А: доменный сентинел вместо магической строки
                )

                _resolved_target = SELF_TALK_SENTINEL
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
                        if _task_type == "canonical":
                            self._record_task_outcome(task.owner_id, "COMPLETED")
                        logger.info(f"[TASK_SCHED] dialogue executed: speaker={task.owner_id} target={task.payload.target_id if hasattr(task.payload, 'target_id') else 'unknown'}")

                        materializer = self._materializers.get(artifact.result_type)
                        if materializer:
                            try:
                                events = materializer.materialize(artifact)
                                # ADR-O-399: publish из воркера запрещён — события
                                # уходят в артефакт, применяются в drain (main thread)
                                for ev in events:
                                    _events_collected.append(ev)
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
                                # ADR-O-399: observable economy — в drain
                                _talks_collected.append((ev.source, scene_state.get("tick", 0)))
                            import time
                            _dlg_entry = {
                                "speaker_id": ev.source,
                                "target_id": ev.payload.get("target_id", ""),
                                "text": ev.payload.get("text", ""),
                                # IRON RIVER D-1/P0-1 (F1a): timestamp — каузальная
                                # ось game_time (значение уже в точке записи, :564),
                                # детерминирован и входит в канон-хеш; real_ts —
                                # UI-staleness (§15.2-исключение), из хеша исключён.
                                "timestamp": _game_time,
                                "real_ts": time.time(),
                                # ADR-O-343 FIX: Используем зафиксированное время тика, чтобы избежать гонки с scene_state.
                                "game_time": _game_time,
                            }
                            # ADR-O-399: append в RAM-кэш перенесён в drain (main thread);
                            # _dlg_entry уходит в артефакт как есть
                            # ADR-O-313 FIX: Зеркалим в scene_state, иначе CDS видит 0 реплик (INV-DIALOGUE-PIPELINE)
                            # ADR-O-399: зеркалирование в scene_state — только в drain
                    else:
                        logger.error(
                            f"[SCHEDULER] Task {task.task_id} failed: {artifact.error_message}"
                        )
                        task.state = TaskState.FINISHED  # Пока без сложного ретрая
                        if _task_type == "canonical":
                            self._record_task_outcome(task.owner_id, "FAILED", FAIL_TASK_ERROR)
                        self.failed_tasks += 1
                        # ADR-O-343: Сбрасываем DEDUP в SpeechScheduler, чтобы NPC мог повторить попытку
                        if hasattr(self, '_speech_scheduler'):
                            # ADR-O-399: мутация admission-состояния — в drain
                            _speech_reset = task_dict
            except Exception as task_exc:
                logger.error(f"[SCHEDULER] Crashed during task execution {task.task_id}: {task_exc}", exc_info=True)
                if _task_type == "canonical":
                    # Закрывает PROCESSING-лимбо (F9): crash-исполнение = FAILED.
                    self._record_task_outcome(task.owner_id, "FAILED", FAIL_TASK_CRASH)
                self.failed_tasks += 1
                if hasattr(self, '_speech_scheduler'):
                    # ADR-O-399: reset admission-состояния — в drain (главный поток)
                    _speech_reset = task_dict
                break
            finally:
                # ADR-O-399: артефакт задачи уходит в outbox при любом исходе
                # (success / failed / crash) — эффекты применит drain.
                self._push_task_artifact(
                    submit_tick, task.task_id, _events_collected,
                    _dlg_entry, _talks_collected, _speech_reset,
                )

    def _reconstruct_task(self, task_dict: dict) -> "Optional[QueuedTask]":
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
            # S203.4 (terminal-mapping v2): drop-до-исполнения → CANCELLED
            # (ambient-дропы безопасно ноу-опят по executor-mismatch).
            self._record_task_outcome(task_dict.get("owner_id", ""), "CANCELLED")
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
            self._record_task_outcome(task_dict.get("owner_id", ""), "CANCELLED")
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
                # S203.4 (terminal-mapping v2): drop-до-исполнения → CANCELLED.
                self._record_task_outcome(task_dict.get("owner_id", ""), "CANCELLED")
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
