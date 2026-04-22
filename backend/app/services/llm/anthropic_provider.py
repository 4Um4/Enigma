"""
Anthropic API Provider
Реализация для Claude моделей через Anthropic API.

path: /backend/app/services/llm/anthropic_provider.py
Назначение: Anthropic API провайдер — выделен из factory.py
Зависимости: app.services.llm.provider
Основные сущности: AnthropicProvider
"""

from __future__ import annotations

import json
import urllib.request
import urllib.error
from typing import Generator

from app.services.llm.provider import (
    StreamingLlmProvider,
    GenerationParams,
    ProviderInfo,
    ProviderType,
)
from app.core.config import settings

# Anthropic использует другой формат API — messages с отдельным system параметром
ANTHROPIC_API_VERSION = "2023-06-01"
ANTHROPIC_BASE_URL = "https://api.anthropic.com/v1"


class AnthropicProvider(StreamingLlmProvider):
    """
    Anthropic API провайдер (Claude).
    
    Отличия от OpenAI:
    - system_prompt передаётся как отдельный параметр, не в messages
    - endpoint: /v1/messages
    - заголовок: anthropic-version
    - стриминг: SSE с событиями message_start, content_block_delta, message_stop
    """
    
    def __init__(
        self,
        api_key: str | None = None,
        model: str = "claude-3-opus-20240229",
        endpoint: str | None = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.endpoint = endpoint or ANTHROPIC_BASE_URL
    
    def complete(
        self,
        prompt: str,
        params: GenerationParams | None = None,
        system_prompt: str | None = None,
    ) -> str:
        gen_params = params or GenerationParams()
        payload = self._build_payload(prompt, system_prompt, gen_params, stream=False)
        response = self._do_request(payload)
        
        if response is None:
            return "[Ошибка Anthropic: пустой ответ]"
        
        try:
            data = json.loads(response)
            # Anthropic возвращает content как массив блоков
            content_blocks = data.get("content", [])
            text_parts = [b["text"] for b in content_blocks if b.get("type") == "text"]
            return "".join(text_parts).strip()
        except (json.JSONDecodeError, KeyError, IndexError) as e:
            return f"[Ошибка парсинга Anthropic: {e}]"
    
    def stream_tokens(
        self,
        prompt: str,
        params: GenerationParams | None = None,
        system_prompt: str | None = None,
    ) -> Generator[str, None, None]:
        gen_params = params or GenerationParams()
        payload = self._build_payload(prompt, system_prompt, gen_params, stream=True)
        
        data = json.dumps(payload).encode("utf-8")
        url = self.endpoint.rstrip("/") + "/messages"
        headers = self._build_headers()
        
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
                    if not data_str:
                        continue
                    try:
                        chunk = json.loads(data_str)
                        event_type = chunk.get("type", "")
                        
                        if event_type == "content_block_delta":
                            delta = chunk.get("delta", {})
                            if delta.get("type") == "text_delta":
                                token = delta.get("text", "")
                                if token:
                                    yield token
                        
                        if event_type == "message_stop":
                            return
                    except json.JSONDecodeError:
                        continue
        except urllib.error.URLError as e:
            yield f"\n[Ошибка соединения Anthropic: {e}]"
    
    def _build_headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "anthropic-version": ANTHROPIC_API_VERSION,
        }
        if self.api_key:
            headers["x-api-key"] = self.api_key
        return headers
    
    def _build_payload(
        self,
        prompt: str,
        system_prompt: str | None,
        params: GenerationParams,
        stream: bool,
    ) -> dict:
        payload: dict = {
            "model": self.model,
            "max_tokens": params.max_tokens,
            "messages": [{"role": "user", "content": prompt}],
            "stream": stream,
        }
        # Anthropic принимает system отдельно, не в messages
        if system_prompt:
            payload["system"] = system_prompt
        return payload
    
    def _do_request(self, payload: dict) -> str | None:
        data = json.dumps(payload).encode("utf-8")
        url = self.endpoint.rstrip("/") + "/messages"
        headers = self._build_headers()
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        
        try:
            with urllib.request.urlopen(req, timeout=settings.llama_cpp_timeout_sec) as resp:
                return resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace") if e.fp else ""
            raise RuntimeError(f"Anthropic HTTP {e.code}: {body}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"Не удалось подключиться к Anthropic ({self.endpoint})") from e
    
    def is_available(self) -> bool:
        if not self.api_key:
            return False
        # Anthropic не имеет лёгкого health endpoint — проверяем по ключу
        return len(self.api_key) > 10
    
    def get_info(self) -> ProviderInfo:
        return ProviderInfo(
            name=f"Anthropic ({self.model})",
            provider_type=ProviderType.ANTHROPIC,
            endpoint=self.endpoint,
            model_name=self.model,
            is_available=self.is_available(),
        )
    
    def get_provider_type(self) -> ProviderType:
        return ProviderType.ANTHROPIC