"""
path: /backend/app/services/game_loop/speech_scheduler.py
Назначение: Narrative Arbitration Layer. Арбитраж CommunicationIntent перед допуском к LLM.
Зависимости: app.services.memory.memory_manager
Основные сущности: SpeechScheduler
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class SpeechScheduler:
    """
    Арбитр материализации речи (ADR-O-343).
    Решает, достойно ли намерение стать LLM-генерацией, основываясь на pacing, дедупликации и нарративной ценности.
    Живёт в infrastructure layer (game_loop), имеет право использовать wall-clock для pacing.
    """

    MINIMUM_RESPONSE_LATENCY_SEC = 2.0
    DEDUP_CONTEXT_TTL_SEC = 4.0  # Если LLM упала (заглушка), NPC сможет повторить попытку после pacing

    def __init__(self, memory_manager: Optional[Any] = None) -> None:
        self._memory_manager = memory_manager
        # Хранит wall-clock timestamp последней реплики NPC
        self._actor_last_speech_ts: Dict[str, float] = {}
        # Хранит wall-clock timestamp последней реплики в паре (для pacing диалога A->B->A)
        self._pair_last_speech_ts: Dict[str, float] = {}
        # Хранит сигнатуры контекста для дедупликации
        self._admitted_contexts: Dict[str, tuple[str, float]] = {}

    def admit(self, task_dict: dict, campaign_id: str = "") -> tuple[bool, str]:
        """
        Арбитраж диалоговой задачи.
        Возвращает (True, "ADMITTED") если допущена.
        Возвращает (False, "PACING") если отклонена из-за тайминга (нужно вернуть в очередь).
        Возвращает (False, "DEDUP") если отклонена как дубликат (нужно уничтожить).
        """
        import time
        now = time.time()

        speaker_id = task_dict.get("owner_id", "")
        payload = task_dict.get("payload", {})
        target_id = payload.get("target_id", "all")

        if not speaker_id:
            return True, "ADMITTED"  # Неизвестный спикер — пропускаем

        # 1. Minimum Response Latency (Human Pacing)
        last_speech = self._actor_last_speech_ts.get(speaker_id, 0.0)
        if now - last_speech < self.MINIMUM_RESPONSE_LATENCY_SEC:
            logger.debug(f"[SPEECH_SCHED] Denied {speaker_id}: Pacing limit (now={now:.2f}, last={last_speech:.2f})")
            return False, "PACING"

        intent_type = payload.get("intent_type", "talk")
        topic = payload.get("topic", "наблюдение")

        # 2. Causal Context Deduplication
        causal_context_version = f"{speaker_id}->{target_id}:{intent_type}:{topic}"
        pair_key = f"{speaker_id}->{target_id}"

        admitted_context, admitted_ts = self._admitted_contexts.get(pair_key, ("", 0.0))
        if admitted_context == causal_context_version:
            if now - admitted_ts < self.DEDUP_CONTEXT_TTL_SEC:
                logger.debug(f"[SPEECH_SCHED] Denied {speaker_id}: Duplicate context {causal_context_version}")
                return False, "DEDUP"

        # Допуск (SpeechAdmission granted)
        self._actor_last_speech_ts[speaker_id] = now
        self._pair_last_speech_ts[pair_key] = now
        self._admitted_contexts[pair_key] = (causal_context_version, now)

        logger.info(f"[SPEECH_SCHED] Admitted {speaker_id} -> {target_id} ({intent_type})")
        return True, "ADMITTED"

    def reset_context(self, task_dict: dict) -> None:
        """Сбрасывает DEDUP-блокировку, если LLM физически упала и реплика не состоялась."""
        speaker_id = task_dict.get("owner_id", "")
        payload = task_dict.get("payload", {})
        target_id = payload.get("target_id", "all")
        pair_key = f"{speaker_id}->{target_id}"
        
        if pair_key in self._admitted_contexts:
            del self._admitted_contexts[pair_key]
            logger.debug(f"[SPEECH_SCHED] Reset context for {pair_key} due to execution failure.")

    def cleanup_stale_contexts(self) -> None:
        """Очистка устаревших контекстов (вызывать периодически)."""
        import time
        now = time.time()
        self._admitted_contexts = {
            k: v for k, v in self._admitted_contexts.items()
            if now - v[1] < self.DEDUP_CONTEXT_TTL_SEC
        }