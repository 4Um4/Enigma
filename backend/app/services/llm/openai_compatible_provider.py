# backend/app/services/llm/openai_compatible_provider.py
"""
Назначение: LLM провайдер для OpenAI-совместимого API (OpenAI, ZhipuAI, LocalAI).
Зависимости: urllib, json, logging
Основные сущности: OpenAICompatibleProvider
"""
import json
import logging
import urllib.request
from typing import Any, Dict, Optional

from app.services.llm.provider import GenerationParams, LlmProvider  # BUG-DLG-041 FIX: Исправлен импорт (llm_provider → provider)

logger = logging.getLogger(__name__)

class OpenAICompatibleProvider(LlmProvider):
    """Провайдер для OpenAI-совместимого API (Cloud Fallback)."""

    def __init__(
        self,
        model_name: str,
        api_key: str,
        endpoint: str = "https://api.openai.com/v1",
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> None:
        self._model_name = model_name
        self._api_key = api_key
        self._endpoint = endpoint.rstrip("/")
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._available = bool(api_key)  # Доступен только если есть ключ

    def is_available(self) -> bool:
        return self._available

    def complete(
        self, prompt: str, params: Optional[GenerationParams] = None, system_prompt: Optional[str] = None
    ) -> str:
        if not self._available:
            raise RuntimeError("OpenAICompatibleProvider: API key is missing.")

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}",
        }

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        _temp = params.temperature if params else self._temperature
        _max_tok = params.max_tokens if params else self._max_tokens
        payload = {
            "model": self._model_name,
            "messages": messages,
            "temperature": _temp,
            "max_tokens": _max_tok,
        }

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self._endpoint}/chat/completions",
            data=data,
            headers=headers,
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                resp_data = json.loads(response.read().decode("utf-8"))
                return resp_data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            logger.error(f"[OPENAI_PROVIDER] Request failed: {e}")
            raise
