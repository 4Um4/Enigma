# backend/app/services/memory/working_memory.py
"""
R1.2 — Working Memory: последние 5 ходов в RAM.
Мгновенный доступ. Не пишет на диск. Сбрасывается при перезапуске.
"""

from __future__ import annotations
from collections import deque
from typing import Any, Dict, List


class WorkingMemory:
    def __init__(self, maxlen: int = 5) -> None:
        self._buffers: Dict[str, deque] = {}
        self._maxlen = maxlen

    def push(self, campaign_id: str, event: Dict[str, Any]) -> None:
        if campaign_id not in self._buffers:
            self._buffers[campaign_id] = deque(maxlen=self._maxlen)
        self._buffers[campaign_id].append(event)

    def get(self, campaign_id: str) -> List[Dict[str, Any]]:
        return list(self._buffers.get(campaign_id, []))

    def clear(self, campaign_id: str) -> None:
        self._buffers.pop(campaign_id, None)