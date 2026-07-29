"""
Файл: backend/app/services/memory/dialogue_consolidator.py (NEW)
Назначение: Суммаризация законченной DialogueSession в текст для EventMemory.
Зависимости: app.services.memory.dialogue_session
Основные сущности: DialogueConsolidator
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class DialogueConsolidator:
    """Создаёт текст summary из законченной DialogueSession для EventMemory."""
    
    def __init__(self, llm_client=None):
        self._llm = llm_client
    
    def consolidate(self, session) -> Optional[str]:
        """Возвращает текст summary для EventMemory.
        
        Пока работает без LLM (structural fallback).
        """
        if not session.buffer or len(session.buffer) < 2:
            return None
        
        # Fallback (без LLM) — structural summary
        return session.consolidate_to_event_memory_summary()