"""
Файл: backend/app/models/last_words.py
Назначение: Структура финальной цитаты NPC.
Зависимости: dataclasses
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class LastWordTone(str, Enum):
    GRATEFUL = "grateful"
    BITTER = "bitter"
    BROKEN = "broken"
    SILENT = "silent"

@dataclass(frozen=True)
class LastWord:
    """Финальная цитата NPC перед выходом игрока или своей судьбой."""
    npc_id: str
    quote: str
    tone: LastWordTone
