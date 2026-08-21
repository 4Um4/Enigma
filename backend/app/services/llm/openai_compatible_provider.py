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
        # H-14 FIX: Передаём остальные параметры генерации, если они заданы
        if params:
            _top_p = getattr(params, "top_p", None)  # noqa: ENIGMA002
            if _top_p is not None: payload["top_p"] = _top_p
            _presence = getattr(params, "presence_penalty", None)  # noqa: ENIGMA002
            if _presence is not None: payload["presence_penalty"] = _presence
            _frequency = getattr(params, "frequency_penalty", None)  # noqa: ENIGMA002
            if _frequency is not None: payload["frequency_penalty"] = _frequency
            _stop = getattr(params, "stop", None)  # noqa: ENIGMA002
            if _stop: payload["stop"] = _stop
            _resp_fmt = getattr(params, "response_format", None)  # noqa: ENIGMA002
            if _resp_fmt: payload["response_format"] = _resp_fmt

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self._endpoint}/chat/completions",
            data=data,
            headers=headers,
            method="POST",
        )

        # H-15 FIX: Bypass env proxies (согласованность с LlamaCppProvider)
        _opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        
        # H-13 FIX: Retry с exponential backoff для 429/503
        import time
        for attempt in range(1, 4):
            try:
                with _opener.open(req, timeout=60) as response:
                    resp_data = json.loads(response.read().decode("utf-8"))
                    return resp_data["choices"][0]["message"]["content"].strip()
            except urllib.error.HTTPError as e:
                if e.code in (429, 503) and attempt < 3:
                    wait_time = 2 ** attempt
                    logger.warning(f"[OPENAI_PROVIDER] HTTP {e.code}, retrying in {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                logger.error(f"[OPENAI_PROVIDER] Request failed: {e}")
                raise
            except Exception as e:
                logger.error(f"[OPENAI_PROVIDER] Request failed: {e}")
                raise
