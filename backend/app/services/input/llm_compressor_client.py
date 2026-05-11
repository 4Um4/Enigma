"""
Файл: backend/app/services/input/llm_compressor_client.py
Назначение: Изоляция вызова LLM. Использует существующий абстрактный класс или делает прямой вызов.
Зависимости: httpx, domain.intent_profile
Основные сущности: LLMCompressorClient (Protocol), LlamaCppCompressorClient (реализация для локального сервера)

TODO: В будущем может потребоваться расширить LLMCompressorClient для поддержки нескольких моделей (например, облачные API), более сложных схем промптинга и адаптивного формата ответа (например, если модель поддерживает структурированные данные или требует постобработки). Но для MVP достаточно базового клиента для локального llama.cpp сервера с JSON Mode.

"""

import json
import httpx
from typing import Protocol, Dict, Any, Optional
from app.domain.intent_profile import IntentSemanticField

class LLMCompressorClient(Protocol):
    """Интерфейс компрессора. LLM = Voice, но здесь она Semantic Parser."""
    async def compress_intent(self, raw_text: str, scene_context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        ...

class LlamaCppCompressorClient:
    """Реализация для локального llama.cpp сервера. Поддерживает JSON Mode."""
    def __init__(self, base_url: str = "http://127.0.0.1:8080"):
        self.base_url = base_url

    async def compress_intent(self, raw_text: str, scene_context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        prompt = self._build_prompt(raw_text, scene_context)
        payload = {
            "prompt": prompt,
            "temperature": 0.1,
            "response_format": {"type": "json_object"} # Строгий JSON
        }
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                response = await client.post(f"{self.base_url}/completion", json=payload)
                response.raise_for_status()
                data = response.json()
                content = data.get("content", "")
                return json.loads(content)
        except (httpx.RequestError, json.JSONDecodeError, KeyError):
            return None

    def _build_prompt(self, raw_text: str, scene_context: Dict[str, Any]) -> str:
        return f"""You are a Semantic Parser. Translate player input into a strict JSON schema.
Allowed action_types: [MOVE, OBSERVE, INTERACT, ATTACK, THREATEN, PERSUADE, FLIRT, STEAL, GIVE, UNCERTAIN].
Target zones: [HEAD, TORSO, ARMS, LEGS, GROIN, UNDEFINED].
Extract: action_type, target_reference (string, not ID), target_zone, physical_force, emotional_charge, social_pressure, commitment_level (all 0.0-1.0), tool_reference (string), and emotional vector (aggression, fear, shame, confidence, desperation).
If unsure, set action_type to UNCERTAIN.
Input: "{raw_text}"
Context: {json.dumps(scene_context)}"""