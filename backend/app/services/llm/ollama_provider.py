"""
Ollama Provider
Провайдер для локального Ollama сервера.
Ollama использует свой API формат (/api/generate, /api/chat).

path: /backend/app/services/llm/ollama_provider.py
Назначение: Ollama local provider — выделен из factory.py
Зависимости: app.services.llm.provider
Основные сущности: OllamaProvider
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


class OllamaProvider(StreamingLlmProvider):
    """
    Ollama local provider.
    
    Использует /api/chat для чата и /api/tags для health check.
    """
    
    def __init__(
        self,
        endpoint: str = "http://localhost:11434",
        model: str = "llama2",
    ) -> None:
        self.endpoint = endpoint
        self.model = model
    
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
            return "[Ошибка Ollama: пустой ответ]"
        
        try:
            data = json.loads(response)
            return data.get("message", {}).get("content", "").strip()
        except (json.JSONDecodeError, KeyError) as e:
            return f"[Ошибка парсинга Ollama: {e}]"
    
    def stream_tokens(
        self,
        prompt: str,
        params: GenerationParams | None = None,
        system_prompt: str | None = None,
    ) -> Generator[str, None, None]:
        gen_params = params or GenerationParams()
        payload = self._build_payload(prompt, system_prompt, gen_params, stream=True)
        
        data = json.dumps(payload).encode("utf-8")
        url = self.endpoint.rstrip("/") + "/api/chat"
        headers = {"Content-Type": "application/json"}
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        
        try:
            with urllib.request.urlopen(req, timeout=settings.llama_cpp_timeout_sec) as resp:
                while True:
                    line = resp.readline()
                    if not line:
                        break
                    line = line.decode("utf-8").strip()
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                        if chunk.get("done"):
                            return
                        token = chunk.get("message", {}).get("content", "")
                        if token:
                            yield token
                    except json.JSONDecodeError:
                        continue
        except urllib.error.URLError as e:
            yield f"\n[Ошибка соединения Ollama: {e}]"
    
    def _build_payload(
        self,
        prompt: str,
        system_prompt: str | None,
        params: GenerationParams,
        stream: bool,
    ) -> dict:
        payload: dict = {
            "model": self.model,
            "messages": [],
            "stream": stream,
            "options": {
                "num_predict": params.max_tokens,
                "temperature": params.temperature,
                "top_p": params.top_p,
            },
        }
        if system_prompt:
            payload["messages"].append({"role": "system", "content": system_prompt})
        payload["messages"].append({"role": "user", "content": prompt})
        return payload
    
    def _do_request(self, payload: dict) -> str | None:
        data = json.dumps(payload).encode("utf-8")
        url = self.endpoint.rstrip("/") + "/api/chat"
        headers = {"Content-Type": "application/json"}
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        
        try:
            with urllib.request.urlopen(req, timeout=settings.llama_cpp_timeout_sec) as resp:
                return resp.read().decode("utf-8")
        except urllib.error.URLError as e:
            raise RuntimeError(f"Не удалось подключиться к Ollama ({self.endpoint})") from e
    
    def is_available(self) -> bool:
        try:
            with urllib.request.urlopen(self.endpoint + "/api/tags", timeout=2) as resp:
                return resp.status == 200
        except Exception:
            return False
    
    def get_info(self) -> ProviderInfo:
        return ProviderInfo(
            name=f"Ollama ({self.model})",
            provider_type=ProviderType.OLLAMA,
            endpoint=self.endpoint,
            model_name=self.model,
            is_available=self.is_available(),
        )
    
    def get_provider_type(self) -> ProviderType:
        return ProviderType.OLLAMA