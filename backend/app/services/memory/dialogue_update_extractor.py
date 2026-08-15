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
        """Извлекает structured update из реплики через LLM."""
        if self._router is None:
            return DialogueUpdate()
        
        try:
            prompt = self._build_extraction_prompt(stm_before, new_turn, partner)
            from app.services.llm.provider import GenerationParams
            response = self._router.request_for_agent(
                agent_name="dialogue_extractor",
                prompt=prompt,
                params=GenerationParams(max_tokens=200, temperature=0.1, response_format={"type": "json_object"})
            )
            # Очищаем от markdown-разметки, если LLM обернула ответ
            cleaned_response = response.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            
            try:
                data = json.loads(cleaned_response)
            except json.JSONDecodeError:
                # LLM иногда возвращает JSON с одинарными кавычками, trailing commas или обрезанный (truncated).
                import ast
                try:
                    # Пробуем закрыть незакрытые скобки (грубый эвристический фикс для обрезанных ответов)
                    repaired_response = cleaned_response
                    if repaired_response.count('{') > repaired_response.count('}'):
                        repaired_response += '}' * (repaired_response.count('{') - repaired_response.count('}'))
                    if repaired_response.count('[') > repaired_response.count(']'):
                        repaired_response += ']' * (repaired_response.count('[') - repaired_response.count(']'))
                    
                    data = json.loads(repaired_response.replace("'", '"'), strict=False)
                except Exception:
                    try:
                        data = ast.literal_eval(cleaned_response)
                    except Exception as parse_err:
                        # Понижаем уровень до DEBUG, так как это ожидаемая проблема LLM, а не системы.
                        logger.debug(f"Dialogue update extraction failed (JSON parse error): {parse_err}. Raw: {cleaned_response[:200]}")
                        return DialogueUpdate()
            return self._parse_update(data)
        except Exception as e:
            # S198 FIX: Тихий fallback при недоступности LLM (для SUPERBOX тестов).
            if isinstance(e, RuntimeError) and "недоступны" in str(e).lower():
                logger.debug(f"Dialogue update skipped (LLM unavailable): {e}")
            else:
                logger.warning(f"Dialogue update failed: {e}")
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