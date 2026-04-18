"""
OpenAI API Provider
Полная реализация для OpenAI и OpenAI-совместимых API.

path: /backend/app/services/llm/openai_provider.py
Назначение: OpenAI API провайдер — выделен из factory.py для соблюдения SRP
Зависимости: app.services.llm.provider
Основные сущности: OpenAIProvider
"""

from __future__ import annotations

import json
import urllib.request
import urllib.error
from typing import Optional, Generator

from app.services.llm.provider import (
    StreamingLlmProvider,
    GenerationParams,
    ProviderInfo,
    ProviderType,
)
from app.core.config import settings


class OpenAIProvider(StreamingLlmProvider):
    """
    OpenAI API провайдер.
    
    Поддерживает:
    - Официальный OpenAI API (gpt-4, gpt-3.5-turbo, ...)
    - Любой OpenAI-совместимый endpoint (LM Studio, LocalAI, ...)
    """
    
    def __init__(
        self,
        endpoint: str = "https://api.openai.com/v1",
        api_key: str | None = None,
        model: str = "gpt-4",
    ) -> None:
        self.endpoint = endpoint
        self.api_key = api_key
        self.model = model
    
    def complete(
        self,
        prompt: str,
        params: GenerationParams | None = None,
        system_prompt: str | None = None,
    ) -> str:
        gen_params = params or GenerationParams()
        messages = self._build_messages(prompt, system_prompt)
        payload = self._build_payload(messages, gen_params, stream=False)
        response = self._do_request(payload)
        
        if response is None:
            return "[Ошибка OpenAI: пустой ответ]"
        
        try:
            data = json.loads(response)
            return data["choices"][0]["message"]["content"].strip()
        except (json.JSONDecodeError, KeyError, IndexError) as e:
            return f"[Ошибка парсинга OpenAI: {e}]"
    
    def stream_tokens(
        self,
        prompt: str,
        params: GenerationParams | None = None,
        system_prompt: str | None = None,
    ) -> Generator[str, None, None]:
        gen_params = params or GenerationParams()
        messages = self._build_messages(prompt, system_prompt)
        payload = self._build_payload(messages, gen_params, stream=True)
        
        data = json.dumps(payload).encode("utf-8")
        url = self.endpoint.rstrip("/") + "/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        
        try:
            with urllib.request.urlopen(req, timeout=settings.llama_cpp_timeout_sec) as resp:
                while True:
                    line = resp.readline()
                    if not line:
                        break
                    line = line.decode("utf-8").strip()
                    if not line or not line.startswith("data:"):
                        continue
                    data_str = line[5:].strip()
                    if data_str == "[DONE]":
                        return
                    try:
                        chunk = json.loads(data_str)
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        token = delta.get("content", "")
                        if token:
                            yield token
                    except (json.JSONDecodeError, IndexError):
                        continue
        except urllib.error.URLError as e:
            yield f"\n[Ошибка соединения OpenAI: {e}]"
    
    def _build_messages(
        self, prompt: str, system_prompt: str | None
    ) -> list[dict]:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        return messages
    
    def _build_payload(
        self,
        messages: list[dict],
        params: GenerationParams,
        stream: bool,
    ) -> dict:
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": params.max_tokens,
            "temperature": params.temperature,
            "top_p": params.top_p,
            "stream": stream,
        }
        if params.stop:
            payload["stop"] = params.stop
        if params.presence_penalty is not None:
            payload["presence_penalty"] = params.presence_penalty
        if params.frequency_penalty is not None:
            payload["frequency_penalty"] = params.frequency_penalty
        if params.response_format is not None:
            payload["response_format"] = params.response_format
        return payload
    
    def _do_request(self, payload: dict) -> str | None:
        data = json.dumps(payload).encode("utf-8")
        url = self.endpoint.rstrip("/") + "/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        
        try:
            with urllib.request.urlopen(req, timeout=settings.llama_cpp_timeout_sec) as resp:
                return resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace") if e.fp else ""
            raise RuntimeError(f"OpenAI HTTP {e.code}: {body}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"Не удалось подключиться к OpenAI ({self.endpoint})") from e
    
    def is_available(self) -> bool:
        if not self.api_key:
            return False
        try:
            url = self.endpoint.rstrip("/") + "/models"
            headers = {"Authorization": f"Bearer {self.api_key}"}
            req = urllib.request.Request(url, headers=headers, method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status == 200
        except Exception:
            return False
    
    def get_info(self) -> ProviderInfo:
        return ProviderInfo(
            name=f"OpenAI ({self.model})",
            provider_type=ProviderType.OPENAI,
            endpoint=self.endpoint,
            model_name=self.model,
            is_available=self.is_available(),
        )
    
    def get_provider_type(self) -> ProviderType:
        return ProviderType.OPENAI