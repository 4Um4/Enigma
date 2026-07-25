"""
path: /project/backend/app/services/execution/dialogue_queue.py
Назначение: Единая очередь LLM-вызовов с приоритетами и rate limiting для автономных NPC-NPC диалогов.
Зависимости: heapq, time, logging, uuid
Основные сущности: QueuedDialogue, DialogueQueue
"""

from __future__ import annotations

import heapq
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)

@dataclass(order=True)
class QueuedDialogue:
    """Задача на LLM-генерацию реплики. Сортируется по priority (desc)."""
    priority: int                          # 0-15, выше = важнее
    enqueued_at: float                     # timestamp
    task_type: str = field(compare=False)  # canonical, eavesdrop, culmination, dm_response, ...
    payload: dict = field(compare=False)   # данные для LLM-вызова
    task_id: str = field(compare=False)

class DialogueQueue:
    """Единая очередь LLM-вызовов с приоритетами.

    Один LLM-вызов за раз (single-threaded). Все canonical/eavesdrop/DM
    запросы идут через эту очередь.

    Приоритеты (0-15):
        15 = crisis_anger (NPC в гневе, может атаковать)
        12 = dm_response (ответ игроку — высокий, но не кризис)
        10 = secret_relevant (разговор о секрете)
        8 = eavesdrop (игрок подошёл к разговору)
        5 = culmination (10+ ходов разговора)
        3 = npc_initiates_player (NPC подошёл к игроку)
    """

    MAX_RATE_PER_MINUTE = 20  # 20 LLM-вызовов в минуту максимум
    COOLDOWN_PER_NPC_SEC = 30 # Один NPC говорит раз в 30 сек

    def __init__(self) -> None:
        self._heap: list[QueuedDialogue] = []
        self._minute_count: int = 0
        self._minute_start: float = time.time()
        self._recent_npc_speak: dict[str, float] = {}  # npc_id -> last_speak_timestamp

    def enqueue(self, task_type: str, payload: dict, priority: int) -> str:
        """Добавить задачу в очередь."""
        task_id = f"dlg-{uuid.uuid4().hex[:8]}"
        task = QueuedDialogue(
            priority=-priority,  # heapq = min-heap, инвертируем
            enqueued_at=time.time(),
            task_type=task_type,
            payload=payload,
            task_id=task_id,
        )
        heapq.heappush(self._heap, task)
        logger.info(
            f"[DLG_QUEUE] enqueued task_id={task_id} type={task_type} priority={priority}"
        )
        return task_id

    def dequeue_next(self) -> Optional[QueuedDialogue]:
        """Возвращает следующую задачу с учётом rate limit и cooldown NPC."""
        now = time.time()

        # Сброс минутного счётчика
        if now - self._minute_start > 60.0:
            self._minute_count = 0
            self._minute_start = now

        if self._minute_count >= self.MAX_RATE_PER_MINUTE:
            return None

        if not self._heap:
            return None

        # Ищем задачу, которая не нарушает cooldown NPC
        temp_skipped = []
        task = None

        while self._heap:
            candidate = heapq.heappop(self._heap)
            speaker_id = candidate.payload.get("speaker_id")

            if speaker_id:
                last_speak = self._recent_npc_speak.get(speaker_id, 0)
                if now - last_speak < self.COOLDOWN_PER_NPC_SEC:
                    # NPC на cooldown'е, пропускаем
                    temp_skipped.append(candidate)
                    continue

            task = candidate
            self._recent_npc_speak[speaker_id] = now
            self._minute_count += 1
            break

        # Возвращаем пропущенные задачи обратно в очередь
        for skipped in temp_skipped:
            heapq.heappush(self._heap, skipped)

        return task

    def mark_completed(self, task_id: str) -> None:
        """Отметить задачу как выполненную."""
        pass  # В текущей реализации не требуется, так как dequeue_next уже вытащил задачу

    def pending_count(self) -> int:
        return len(self._heap)
