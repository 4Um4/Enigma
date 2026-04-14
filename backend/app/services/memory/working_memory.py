# backend/app/services/memory/working_memory.py
"""
R1.2 / R5.1 — Working Memory: скользящее окно событий в RAM.
R5.1: поддержка EventMemory с decay lifecycle.
Не пишет на диск. Сбрасывается при перезапуске.
"""

from __future__ import annotations

from collections import deque
from typing import Any, Dict, List, Tuple, Union
from app.models.npc_state import EventMemory, MemoryStage

# Константа из Now.md — не магическое число
_DEFAULT_MAXLEN: int = 20


class WorkingMemory:
    """
    Скользящее окно последних событий сессии.
    Хранит EventMemory (R5.1) или legacy dict (обратная совместимость).
    """

    def __init__(self, maxlen: int = _DEFAULT_MAXLEN) -> None:
        self._buffers: Dict[str, deque] = {}
        self._maxlen  = maxlen

    def push(
        self,
        campaign_id: str,
        event:       Union[EventMemory, Dict[str, Any]],
    ) -> None:
        """Добавляет событие в буфер кампании."""
        if campaign_id not in self._buffers:
            self._buffers[campaign_id] = deque(maxlen=self._maxlen)
        self._buffers[campaign_id].append(event)

    def get(self, campaign_id: str) -> List[Union[EventMemory, Dict[str, Any]]]:
        """Возвращает все события буфера (от старых к новым)."""
        return list(self._buffers.get(campaign_id, []))

    def apply_decay(
        self,
        campaign_id: str,
        ticks: int = 1,
    ) -> List[Tuple[str, float]]:
        """
        R5.3 — применяет decay, возвращает identity weights от ABSTRACT-переходов.
        Момент перехода в ABSTRACT — единственный триггер для L3 traits.
        Вызывается из MemoryManager.run_decay_if_needed() — не напрямую.
        """
        events = self.get(campaign_id)
        if not events:
            return []

        decayed: List = []
        identity_weights: List[Tuple[str, float]] = []

        for event in events:
            if isinstance(event, EventMemory):
                prev_stage = event.stage
                updated = event.decayed(ticks)

                # R5.3: переход в ABSTRACT → событие уходит в L3 Identity
                if prev_stage != MemoryStage.ABSTRACT and updated.stage == MemoryStage.ABSTRACT:
                    weight = updated.to_identity_weight()
                    if weight is not None:
                        identity_weights.append(weight)

                if not updated.is_forgotten:
                    decayed.append(updated)
                # FORGOTTEN — удаляем молча
            else:
                # Legacy dict — без decay
                decayed.append(event)

        self.replace_all(campaign_id, decayed)
        return identity_weights

    def clear(self, campaign_id: str) -> None:
        """Очищает буфер кампании."""
        self._buffers.pop(campaign_id, None)

    def replace_all(
        self,
        campaign_id: str,
        events:      List[Union[EventMemory, Dict[str, Any]]],
    ) -> None:
        """
        Атомарная замена буфера.
        Используется после decay — старые данные не трогаются до готовности нового списка.
        """
        new_buf: deque = deque(maxlen=self._maxlen)
        for event in events:
            new_buf.append(event)
        self._buffers[campaign_id] = new_buf
