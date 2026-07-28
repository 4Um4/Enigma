"""
Файл: backend/app/services/memory/dialogue_update_extractor.py
Назначение: LLM-based extraction of topic/claims/questions из реплик NPC/Player.
Зависимости: app.services.llm.router, dataclasses
Основные сущности: DialogueUpdate, DialogueUpdateExtractor
"""

import json
import logging
from dataclasses import dataclass
from typing import List, Optional
from functools import lru_cache

logger = logging.getLogger(__name__)


@dataclass
class DialogueUpdate:
    """Структурированное обновление сессии диалога."""
    topic: Optional[str] = None
    topic_confidence: float = 0.0
    new_claims: Optional[List[dict]] = None
    answered_questions: Optional[List[int]] = None
    raised_questions: Optional[List[dict]] = None
    last_speaker_intent: str = ""


class DialogueUpdateExtractor:
    """Извлекает structured update из реплики через LLM."""
    
    def __init__(self, router=None):
        self._router = router
    
    def extract(self, stm_before: str, new_turn: str, partner: str) -> DialogueUpdate:
        """Cached by (stm_before, new_turn, partner) to avoid re-computation."""
        if self._router is None:
            return DialogueUpdate()
        
        try:
            prompt = self._build_extraction_prompt(stm_before, new_turn, partner)
            response = self._router.request_for_agent(
                agent_name="dialogue_extractor",
                prompt=prompt,
                params={"max_tokens": 200, "temperature": 0.1, "response_format": {"type": "json_object"}}
            )
            data = json.loads(response.text)
            return self._parse_update(data)
        except Exception as e:
            logger.warning(f"Dialogue update extraction failed: {e}")
            return DialogueUpdate()
    
    def _build_extraction_prompt(self, stm_before: str, new_turn: str, partner: str) -> str:
        return f"""Проанализируй новую реплику в контексте диалога.
Верни JSON с обновлением памяти диалога (STM).

Контекст до:
{stm_before}

Новая реплика:
{new_turn}

Верни JSON:
{{
  "topic": "string|null",
  "topic_confidence": 0.0-1.0,
  "new_claims": [{{"text": "...", "confidence": 0.0-1.0}}],
  "answered_questions": [0, 1],
  "raised_questions": [{{"text": "...", "addressed_to": "..."}}],
  "last_speaker_intent": "question|claim|answer|reflexive|greeting"
}}

JSON:"""
    
    def _parse_update(self, data: dict) -> DialogueUpdate:
        return DialogueUpdate(
            topic=data.get("topic"),
            topic_confidence=float(data.get("topic_confidence", 0.0)),
            new_claims=data.get("new_claims", []),
            answered_questions=data.get("answered_questions", []),
            raised_questions=data.get("raised_questions", []),
            last_speaker_intent=data.get("last_speaker_intent", "")
        )