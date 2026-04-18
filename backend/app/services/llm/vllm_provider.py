"""
vLLM Provider
vLLM server использует OpenAI-совместимый API, но имеет свои особенности:
- /v1/chat/completions для чата
- /health для health check
- Поддержка speculative decoding, tensor parallelism

path: /backend/app/services/llm/vllm_provider.py
Назначение: Провайдер для vLLM server — OpenAI-совместимый API, но отдельный класс для конфигурации и мониторинга
Зависимости: app.services.llm.provider
Основные сущности: VllmProvider, VllmConfig
"""

from __future__ import annotations

import json
import urllib.request
import urllib.error
from dataclasses import dataclass
from typing import Optional, Generator

from app.services.llm.provider import (
    StreamingLlmProvider,
    GenerationParams,
    ProviderInfo,
    ProviderType,
)
from app.core.config import settings


@dataclass
class VllmConfig:
    """Конфигурация vLLM провайдера."""
    endpoint: str = "http://localhost:8100"
    model: str = "default"
    api_key: Optional[str] = None  # vLLM не требует, но интерфейс совместим


class VllmProvider(StreamingLlmProvider):
    """
    Провайдер для vLLM inference server.
    
    vLLM использует OpenAI-совместимый формат:
    POST /v1/chat/completions
    {
        "model": "...",
        "messages": [{"role": "system", ...}, {"role": "user", ...}],
        "max_tokens": ...,
        "temperature": ...,
        "stream": true/false
    }
    """
    
    def __init__(
        self,
        endpoint: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        config: VllmConfig | None = None,
    ) -> None:
        self._config = config or VllmConfig(
            endpoint=endpoint or "http://localhost:8100",
            model=model or "default",
            api_key=api_key,
        )
    
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
            return "[Ошибка vLLM: пустой ответ]"
        
        try:
            data = json.loads(response)
            return data["choices"][0]["message"]["content"].strip()
        except (json.JSONDecodeError, KeyError, IndexError) as e:
            return f"[Ошибка парсинга vLLM: {e}]"
    
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
        url = self._config.endpoint.rstrip("/") + "/v1/chat/completions"
        headers = {"Content-Type": "application/json"}
        if self._config.api_key:
            headers["Authorization"] = f"Bearer {self._config.api_key}"
        
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
            yield f"\n[Ошибка соединения vLLM: {e}]"
    
    def _build_messages(
        self, prompt: str, system_prompt: str | None
    ) -> list[dict]:
        """Строит массив messages для OpenAI-совместимого API."""
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
        """Строит payload для vLLM."""
        payload = {
            "model": self._config.model,
            "messages": messages,
            "max_tokens": params.max_tokens,
            "temperature": params.temperature,
            "top_p": params.top_p,
            "stream": stream,
        }
        # vLLM поддерживает stop через параметр
        if params.stop:
            payload["stop"] = params.stop
        # Дополнительные параметры если заданы
        if params.presence_penalty is not None:
            payload["presence_penalty"] = params.presence_penalty
        if params.frequency_penalty is not None:
            payload["frequency_penalty"] = params.frequency_penalty
        return payload
    
    def _do_request(self, payload: dict) -> str | None:
        """Выполняет синхронный HTTP запрос к vLLM."""
        data = json.dumps(payload).encode("utf-8")
        url = self._config.endpoint.rstrip("/") + "/v1/chat/completions"
        headers = {"Content-Type": "application/json"}
        if self._config.api_key:
            headers["Authorization"] = f"Bearer {self._config.api_key}"
        
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        
        try:
            with urllib.request.urlopen(req, timeout=settings.llama_cpp_timeout_sec) as resp:
                return resp.read().decode("utf-8")
        except urllib.error.URLError as e:
            raise RuntimeError(
                f"Не удалось подключиться к vLLM ({self._config.endpoint}). "
                "Убедитесь что vLLM server запущен."
            ) from e
    
    def is_available(self) -> bool:
        """Проверяет доступность vLLM через /health или /v1/models."""
        for endpoint in ["/health", "/v1/models"]:
            try:
                url = self._config.endpoint.rstrip("/") + endpoint
                with urllib.request.urlopen(url, timeout=2) as resp:
                    if resp.status == 200:
                        return True
            except Exception:
                continue
        return False
    
    def get_info(self) -> ProviderInfo:
        return ProviderInfo(
            name=f"vLLM ({self._config.model})",
            provider_type=ProviderType.VLLM,
            endpoint=self._config.endpoint,
            model_name=self._config.model,
            is_available=self.is_available(),
            context_size=4096,  # vLLM определяет динамически, но дефолт
            vram_mb=0,  # Не можем узнать без отдельного API
        )
    
    def get_provider_type(self) -> ProviderType:
        return ProviderType.VLLM


def create_vllm_provider(
    endpoint: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
) -> VllmProvider:
    """Фабричная функция для создания vLLM провайдера."""
    return VllmProvider(endpoint=endpoint, model=model, api_key=api_key)