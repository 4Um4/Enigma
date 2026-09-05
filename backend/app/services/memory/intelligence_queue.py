# backend/app/services/memory/intelligence_queue.py
"""
path: /project/backend/app/services/memory/intelligence_queue.py
Назначение: ADR-O-382 (AG1-D8p / закрытие DEBT-RE-D2A) — Intelligence
    Queue: production-форма ADR-O-377 для dialogue-экстракции. Разрыв
    сцепки «момент события NPC_SPOKE ↔ момент LLM-интерпретации»:
    подписчик enqueue'ит задачу неблокирующе и немедленно пишет
    placeholder-ход в STM (существующая семантика деградации —
    intent="dialogue"); экстракция исполняется позже на СУЩЕСТВУЮЩЕМ
    executor-пуле TaskScheduler (Q4а: второй LLM execution domain НЕ
    создаётся); результат DialogueUpdate проходит STALE-гейт (Q2б) и
    применяется ТОЛЬКО через MemoryManager session API (Q3б: time
    bridge, НЕ state authority; DeltaGate не расширяется). Env-флаг
    D8P_ENABLED default OFF = байт-идентичное поведение (INV-D8P-NOOP).
Зависимости: провайдеры (memory_manager / extractor / tick / npc_states /
    pool) инъектируются проводкой (game_loop, Шаг 3.2) — модуль не знает
    GameLoop/TaskScheduler напрямую.
Основные сущности: IntelligenceTask, IntelligenceQueue, d8p_enabled,
    wire_intelligence_queue, get_intelligence_queue.
"""

from __future__ import annotations

import hashlib
import logging
import os
import threading
from collections import deque
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Флаг и calibration-константа (вердикты §13 досье D8P_PRE_FLIGHT) ──


def d8p_enabled() -> bool:
    """Env-флаг D8P_ENABLED (default OFF = полный no-op; дословное зеркало
    bc1_enabled / W3_G2_ENABLED — прецеденты dormant-слоёв)."""
    return os.environ.get("D8P_ENABLED", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _max_age_ticks() -> int:
    """D8P_MAX_AGE_TICKS (default 3). Calibration-константа, НЕ онтология
    (вердикт Q2б); сравнение строго `>`: окно из N тиков = N допустимых
    возрастов."""
    raw = os.environ.get("D8P_MAX_AGE_TICKS", "3")
    try:
        return max(0, int(raw))
    except ValueError:
        # L4 (INV-SILENT-FAILURE): невалидная калибровка наблюдаема, не молча.
        logger.warning("[D8P_Q] invalid D8P_MAX_AGE_TICKS=%r — fallback 3", raw)
        return 3


# ── Lifecycle (вердикт Q5: наблюдаемая история ≠ инвариант состояния) ──

ENQUEUED = "ENQUEUED"
EXECUTED = "EXECUTED"
APPLIED = "APPLIED"
STALE_DISCARDED = "STALE_DISCARDED"
FAILED = "FAILED"

_BOUND = 512  # bounded-реестры: наблюдаемость без утечки RAM


def _trim(mapping: Dict[str, Any], bound: int = _BOUND) -> None:
    """Держит реестр ограниченным (FIFO-вытеснение старых ключей)."""
    while len(mapping) > bound:
        mapping.pop(next(iter(mapping)))


@dataclass(frozen=True)
class IntelligenceTask:
    """Единица отложенной интерпретации ОДНОГО NPC_SPOKE-события.

    task_id детерминирован (md5 campaign:event:listener) — uuid4
    запрещён (INV-REPLAY-DETERMINISM; закон №4 класса ADR-O-363).
    parent_tick — тик публикации события: возраст и provenance
    применения (тик-семантика интерпретации = тик события)."""

    event_id: str
    campaign_id: str
    speaker: str
    listener: str
    text: str
    stm_before: str
    parent_tick: int

    @property
    def task_id(self) -> str:
        raw = f"{self.campaign_id}:{self.event_id}:{self.listener}"
        return hashlib.md5(raw.encode("utf-8")).hexdigest()


class IntelligenceQueue:
    """Time bridge (ADR-O-382): FIFO отложенных экстракций.

    Потоковая модель: enqueue — из любого потока публикатора (loop /
    threadpool / pool-worker) под коротким локом; исполнение — на
    СУЩЕСТВУЮЩЕМ executor-пуле (провайдер), экстракция и применение —
    вне лока (LLM-вызов долгий). Идемпотентность (Q5): один event.id →
    ≤1 IntelligenceTask → ≤1 APPLIED."""

    def __init__(
        self,
        memory_manager: Any,
        extractor: Any,
        tick_provider: Callable[[], int],
        npc_states_provider: Optional[Callable[[], Optional[List[Any]]]] = None,
        pool_provider: Optional[Callable[[], Any]] = None,
    ) -> None:
        self._memory = memory_manager
        self._extractor = extractor
        self._tick = tick_provider
        self._npc_states = npc_states_provider
        self._pool_provider = pool_provider
        self._lock = threading.Lock()
        self._deque: deque = deque()
        self._lifecycle: Dict[str, str] = {}
        self._enqueued: Dict[str, None] = {}
        self._applied: Dict[str, None] = {}
        self._inflight: set = set()
        self._counters: Dict[str, int] = {
            "enqueued": 0,
            "duplicates": 0,
            "submitted": 0,
            "no_pool": 0,
            "executed": 0,
            "applied": 0,
            "empty_update": 0,
            "stale_discarded": 0,
            "failed": 0,
        }

    # ── Производство (поток публикатора; неблокирующе) ──

    def enqueue(
        self,
        event_id: str,
        campaign_id: str,
        speaker: str,
        listener: str,
        text: str,
        stm_before: str,
        parent_tick: int,
    ) -> bool:
        """Неблокирующий enqueue + submit на существующий пул.

        False = дубль event.id (Q5-идемпотентность). Пул не резолвится —
        задача остаётся ENQUEUED (поднятая pump_pending/execute_next)."""
        task = IntelligenceTask(
            event_id=str(event_id),
            campaign_id=campaign_id,
            speaker=speaker,
            listener=listener,
            text=text,
            stm_before=stm_before,
            parent_tick=int(parent_tick),
        )
        with self._lock:
            if task.event_id in self._enqueued:
                self._counters["duplicates"] += 1
                return False
            self._enqueued[task.event_id] = None
            _trim(self._enqueued)
            self._deque.append(task)
            self._lifecycle[task.task_id] = ENQUEUED
            _trim(self._lifecycle)
            self._counters["enqueued"] += 1
            self._submit_locked(task)
            return True

    def _submit_locked(self, task: IntelligenceTask) -> bool:
        """Submit на существующий пул (внутри лока: строгий FIFO)."""
        pool = None
        if self._pool_provider is not None:
            try:
                pool = self._pool_provider()
            except Exception as pool_err:
                logger.warning(
                    "[D8P_Q] pool provider failed: %r — задача %s остаётся "
                    "ENQUEUED (поднимется pump)",
                    pool_err,
                    task.task_id[:8],
                )
        if pool is None:
            self._counters["no_pool"] += 1
            return False
        try:
            pool.submit(self._run_one, task)
            self._inflight.add(task.task_id)
            self._counters["submitted"] += 1
            return True
        except Exception as sub_err:
            self._inflight.discard(task.task_id)
            logger.warning(
                "[D8P_Q] submit failed: %r — задача %s остаётся ENQUEUED",
                sub_err,
                task.task_id[:8],
            )
            return False

    # ── Исполнение (pool-worker / тест-поток) ──

    def _run_one(self, task: IntelligenceTask) -> None:
        """Запуск одной задачи; идемпотентен к двойному submit."""
        with self._lock:
            if self._lifecycle.get(task.task_id) != ENQUEUED:
                return
            self._lifecycle[task.task_id] = EXECUTED
            self._inflight.discard(task.task_id)
            try:
                self._deque.remove(task)
            except ValueError:
                # Ожидаемо при двойном submit/pump-гонке — но наблюдаемо (L4).
                logger.debug(
                    "[D8P_Q] task %s already removed from deque (double-run)",
                    task.task_id[:8],
                )
            self._counters["executed"] += 1
        self._execute(task)

    def _execute(self, task: IntelligenceTask) -> None:
        """Экстракция → STALE-гейт → применение (всё наблюдаемо)."""
        try:
            update = self._extractor.extract(
                task.stm_before, task.text, task.speaker
            )
        except Exception as ext_err:
            # Внутренние ошибки extractor'а глотаются им самим (S198);
            # сюда попадаем только при поломке контракта — честный FAILED.
            self._finish(task, FAILED, f"extraction error: {ext_err!r}")
            return

        stale_reason = self._stale_reason(task)
        if stale_reason is not None:
            # Табу O-377: протухшее НЕ применяется и НЕ отбрасывается молча.
            self._finish(task, STALE_DISCARDED, stale_reason)
            return

        try:
            self._apply(task, update)
            with self._lock:
                self._applied[task.event_id] = None
                _trim(self._applied)
            self._finish(task, APPLIED, "")
        except Exception as apply_err:
            self._finish(task, FAILED, f"apply error: {apply_err!r}")

    def _stale_reason(self, task: IntelligenceTask) -> Optional[str]:
        """Q2б: age > N ∨ плейсхолдер-ход исчез ∨ listener вне мира."""
        current_tick = task.parent_tick
        if self._tick is not None:
            try:
                current_tick = int(self._tick())
            except Exception as tick_err:
                logger.warning("[D8P_Q] tick provider failed: %r", tick_err)
        age = current_tick - task.parent_tick
        if age > _max_age_ticks():
            return f"age={age} > N={_max_age_ticks()}"

        session = self._memory.get_dialogue_session(
            task.campaign_id, task.listener, partner_id=task.speaker
        )
        placeholder_alive = any(
            getattr(t, "speaker", None) == task.speaker
            and getattr(t, "text", None) == task.text
            and getattr(t, "tick", -1) == task.parent_tick
            for t in getattr(session, "buffer", [])
        )
        if not placeholder_alive:
            # Мир забыл сырой текст (вытеснение буфера/clear/new_game) —
            # поздний смысл применяться не имеет права.
            return "placeholder evicted (raw text forgotten)"

        if self._npc_states is not None:
            try:
                states = self._npc_states() or []
                ids = {
                    (n.get("npc_id") or n.get("id"))
                    for n in states
                    if isinstance(n, dict)
                }
                if ids and task.listener not in ids:
                    return "listener out-of-world"
            except Exception as npc_err:
                logger.warning("[D8P_Q] npc_states provider failed: %r", npc_err)
        return None

    def _apply(self, task: IntelligenceTask, update: Any) -> None:
        """Q3б: применение ТОЛЬКО через MemoryManager session API.

        Дословная реплика enrichment-блока NpcDialogueSubscriber
        (:147–165): topic/claims/questions; provenance = parent_tick
        (интерпретация принадлежит тику события, не тику применения)."""
        session = self._memory.get_dialogue_session(
            task.campaign_id, task.listener, partner_id=task.speaker
        )
        has_content = bool(
            getattr(update, "topic", None)
            or getattr(update, "new_claims", None)
            or getattr(update, "raised_questions", None)
            or getattr(update, "answered_questions", None)
        )
        if not has_content:
            # Существующая семантика деградации (S198-fallback extractor'а):
            # применили пусто — наблюдаемо, отдельным счётчиком.
            with self._lock:
                self._counters["empty_update"] += 1
            logger.info(
                "[D8P_Q] empty update (degradation) event=%s listener=%s",
                task.event_id,
                task.listener,
            )
            return
        if getattr(update, "topic", None):
            session.topic = update.topic
            session.topic_confidence = getattr(update, "topic_confidence", 0.0)
        for claim in update.new_claims or []:
            session.add_claim(
                text=claim.get("text", ""),
                speaker=task.speaker,
                confidence=claim.get("confidence", 0.5),
                tick=task.parent_tick,
            )
        for q in update.raised_questions or []:
            session.add_open_question(
                text=q.get("text", ""),
                asked_by=task.speaker,
                addressed_to=q.get("addressed_to", task.listener),
                tick=task.parent_tick,
            )
        for q_idx in update.answered_questions or []:
            session.answer_question(q_idx, task.text, task.speaker, task.parent_tick)

    def _finish(self, task: IntelligenceTask, status: str, reason: str) -> None:
        """Терминальный статус + наблюдаемость (никогда молча)."""
        with self._lock:
            self._lifecycle[task.task_id] = status
            key = {
                APPLIED: "applied",
                STALE_DISCARDED: "stale_discarded",
                FAILED: "failed",
            }.get(status)
            if key:
                self._counters[key] += 1
        if status == APPLIED:
            logger.info(
                "[D8P_Q] APPLIED task=%s event=%s listener=%s parent_tick=%s",
                task.task_id[:8],
                task.event_id,
                task.listener,
                task.parent_tick,
            )
        elif status == STALE_DISCARDED:
            logger.info(
                "[D8P_Q] STALE_DISCARDED task=%s event=%s listener=%s "
                "parent_tick=%s reason=%s",
                task.task_id[:8],
                task.event_id,
                task.listener,
                task.parent_tick,
                reason,
            )
        else:
            logger.warning(
                "[D8P_Q] FAILED task=%s event=%s listener=%s reason=%s",
                task.task_id[:8],
                task.event_id,
                task.listener,
                reason,
            )

    # ── Насос/тест-путь (пул недоступен или smoke) ──

    def pump_pending(self) -> int:
        """Resubmit ENQUEUED-не-submitted (fallback после сбоя провайдера)."""
        submitted = 0
        with self._lock:
            for t in list(self._deque):
                if (
                    self._lifecycle.get(t.task_id) == ENQUEUED
                    and t.task_id not in self._inflight
                ):
                    if self._submit_locked(t):
                        submitted += 1
        return submitted

    def execute_next(self) -> bool:
        """Синхронное исполнение левой ENQUEUED-задачи (smoke/тесты)."""
        with self._lock:
            task = None
            for t in self._deque:
                if (
                    self._lifecycle.get(t.task_id) == ENQUEUED
                    and t.task_id not in self._inflight
                ):
                    task = t
                    break
        if task is None:
            return False
        self._run_one(task)
        return True

    def stats(self) -> Dict[str, int]:
        """Снимок счётчиков (метрика ПОСЛЕ-замера: числа, НЕ впечатление)."""
        with self._lock:
            return dict(self._counters)


# ── Проводка (singleton; инъекция из game_loop — Шаг 3.2) ──

_QUEUE: Optional[IntelligenceQueue] = None


def wire_intelligence_queue(
    memory_manager: Any,
    extractor: Any,
    tick_provider: Callable[[], int],
    npc_states_provider: Optional[Callable[[], Optional[List[Any]]]] = None,
    pool_provider: Optional[Callable[[], Any]] = None,
) -> IntelligenceQueue:
    """Конструирует/возвращает singleton очереди (идемпотентно)."""
    global _QUEUE
    if _QUEUE is None:
        _QUEUE = IntelligenceQueue(
            memory_manager=memory_manager,
            extractor=extractor,
            tick_provider=tick_provider,
            npc_states_provider=npc_states_provider,
            pool_provider=pool_provider,
        )
    return _QUEUE


def get_intelligence_queue() -> Optional[IntelligenceQueue]:
    return _QUEUE


def _reset_intelligence_queue() -> None:
    """Только для тестов: сброс singleton."""
    global _QUEUE
    _QUEUE = None
