# -*- coding: utf-8 -*-
"""
Llama.cpp Provider Implementation
Local LLM inference using llama.cpp server or CLI

Решение проблемы thinking у Qwen3:
  Добавляем пустой <think></think> в prefill ассистента.
  Модель видит "думать уже закончил" и сразу даёт ответ на русском.
  Это официальный способ отключения thinking в Qwen3 через llama.cpp.
"""

from __future__ import annotations

import os
import re
import json
import urllib.request
import urllib.error
from dataclasses import dataclass
from pathlib import Path
from typing import Generator

from app.core.config import settings
from app.services.llm.provider import (
    LlmProvider,
    GenerationParams,
    ProviderInfo,
    ProviderType,
    StreamingLlmProvider,
)

# Regex для вырезания thinking блоков (страховка)
_THINK_RE = re.compile(r'<think>.*?</think>', re.DOTALL)
# Regex для незакрытых thinking блоков (<think> без </think>)
_THINK_OPEN_RE = re.compile(r'<think>.*$', re.DOTALL)

def _strip_thinking(text: str) -> str:
    """Убирает <think>...</think> и незакрытые <think>... из ответа."""
    text = _THINK_RE.sub('', text)
    text = _THINK_OPEN_RE.sub('', text)
    return text.strip()


# Только ASCII стоп-токены
DEFAULT_STOP_TOKENS = [
    "</s>", "</user>", "<user>", "<assistant>",
    "<|im_end|>", "<|end_of_text|>",
]


@dataclass
class LlamaCppModelConfig:
    path: str
    name: str
    context_size: int = 4096
    temperature: float = 0.7
    top_p: float = 0.9
    repeat_penalty: float = 1.1
    n_keep: int = 800
    vram_mb: int = 4000


class LlamaCppProvider(StreamingLlmProvider):

    def __init__(
        self,
        model_config: LlamaCppModelConfig | None = None,
        server_url: str | None = None,
        executable: str | None = None,
    ) -> None:
        self.model_config = model_config or LlamaCppModelConfig(
            path=settings.llama_cpp_model_path,
            name="default",
        )
        self.server_url = server_url or settings.llama_cpp_server_url
        self.executable = executable or settings.llama_cpp_executable
        self._use_server = bool(self.server_url)

    @property
    def use_server(self) -> bool:
        return self._use_server

    # ──────────────────────────────────────────────────────────────────────────
    # Основной метод генерации
    # ──────────────────────────────────────────────────────────────────────────

    def complete(
        self,
        prompt: str,
        params: GenerationParams | None = None,
        system_prompt: str | None = None,
    ) -> str:
        gen_params = params or GenerationParams()
        full_prompt = self._build_chatml_prompt(prompt, system_prompt)

        if self._use_server:
            raw = self._complete_via_server(full_prompt, gen_params)
        else:
            raw = self._complete_via_cli(full_prompt, gen_params)

        return _strip_thinking(raw)

    # ──────────────────────────────────────────────────────────────────────────
    # Построение ChatML промпта
    # ──────────────────────────────────────────────────────────────────────────

    def _build_chatml_prompt(
        self, user_prompt: str, system_prompt: str | None
    ) -> str:
        """
        Строит ChatML промпт для /completion.

        Для Qwen3: добавляем пустой <think></think> в prefill ассистента.
        Это отключает режим thinking — модель сразу генерирует ответ.

        Официальный способ из документации llama.cpp + Qwen3:
          <|im_start|>assistant
          <think>

          </think>

        После этого модель генерирует только финальный ответ.
        """
        model_name = self.model_config.name.lower() if self.model_config else ""

        if "saiga" in model_name or "mistral" in model_name or "yandex" in model_name:
            # Saiga / Mistral / YandexGPT
            if system_prompt:
                return (
                    f"### System\n{system_prompt}\n\n"
                    f"### User\n{user_prompt}\n\n"
                    f"### Assistant\n"
                )
            return f"### User\n{user_prompt}\n\n### Assistant\n"

        else:
            # Qwen3, NPC-LLM, default — ChatML с отключением thinking
            if system_prompt:
                return (
                    f"<|im_start|>system\n{system_prompt}\n<|im_end|>\n"
                    f"<|im_start|>user\n{user_prompt}\n<|im_end|>\n"
                    f"<|im_start|>assistant\n"
                    f"<think>\n\n</think>\n\n"  # ← пустой think = thinking отключён
                )
            return (
                f"<|im_start|>user\n{user_prompt}\n<|im_end|>\n"
                f"<|im_start|>assistant\n"
                f"<think>\n\n</think>\n\n"
            )

    # ──────────────────────────────────────────────────────────────────────────
    # Server mode — /completion
    # ──────────────────────────────────────────────────────────────────────────

    def _complete_via_server(self, prompt: str, params: GenerationParams) -> str:
        url = self.server_url.rstrip("/") + "/completion"

        stop_tokens = list(DEFAULT_STOP_TOKENS)
        if params.stop:
            stop_tokens.extend([t for t in params.stop if t.isascii()])

        payload = {
            "prompt":         prompt,
            "n_predict":      params.max_tokens,
            "stream":         False,
            "stop":           stop_tokens,
            "temperature":    params.temperature,
            "top_p":          params.top_p,
            "repeat_penalty": params.repeat_penalty,
            "top_k":          params.top_k,
            "n_keep":         params.n_keep,
        }

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=settings.llama_cpp_timeout_sec) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                return body.get("content", "")
        except urllib.error.URLError as e:
            raise RuntimeError(
                f"Не удалось подключиться к llama-server ({self.server_url}). "
                "Убедитесь что llama-server запущен."
            ) from e

    # ──────────────────────────────────────────────────────────────────────────
    # CLI mode
    # ──────────────────────────────────────────────────────────────────────────

    def _complete_via_cli(self, prompt: str, params: GenerationParams) -> str:
        import subprocess
        import tempfile

        executable = self.executable or self._find_executable()
        if not executable:
            raise RuntimeError("llama.cpp executable не найден")

        cmd = [executable, "-m", self.model_config.path, "-n", str(params.max_tokens)]

        if len(prompt) > 8000:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".txt", delete=False, encoding="utf-8"
            ) as f:
                f.write(prompt)
                tmp_path = f.name
            cmd.extend(["-f", tmp_path])
            try:
                result = subprocess.run(
                    cmd, capture_output=True, text=True,
                    encoding="utf-8", errors="replace",
                    timeout=settings.llama_cpp_timeout_sec,
                )
            finally:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
        else:
            cmd.extend(["-p", prompt])
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                encoding="utf-8", errors="replace",
                timeout=settings.llama_cpp_timeout_sec,
            )

        return result.stdout.strip() or result.stderr.strip()

    # ──────────────────────────────────────────────────────────────────────────
    # Streaming
    # ──────────────────────────────────────────────────────────────────────────

    def stream_complete(
        self,
        prompt: str,
        params: GenerationParams | None = None,
        system_prompt: str | None = None,
        callback=None,
    ) -> str:
        if not self._use_server:
            result = self.complete(prompt, params, system_prompt)
            if callback:
                callback(result)
            return result

        gen_params = params or GenerationParams()
        full_prompt = self._build_chatml_prompt(prompt, system_prompt)
        url = self.server_url.rstrip("/") + "/completion"

        stop_tokens = list(DEFAULT_STOP_TOKENS)
        if gen_params.stop:
            stop_tokens.extend([t for t in gen_params.stop if t.isascii()])

        payload = {
            "prompt":         full_prompt,
            "n_predict":      gen_params.max_tokens,
            "stream":         True,
            "stop":           stop_tokens,
            "temperature":    gen_params.temperature,
            "top_p":          gen_params.top_p,
            "repeat_penalty": gen_params.repeat_penalty,
            "top_k":          gen_params.top_k,
            "n_keep":         gen_params.n_keep,
        }

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        full_content = ""

        try:
            with urllib.request.urlopen(req, timeout=settings.llama_cpp_timeout_sec) as resp:
                import io
                stream = io.BufferedReader(resp)

                while True:
                    line = stream.readline()
                    if not line:
                        break
                    line = line.decode("utf-8").strip()
                    if not line:
                        continue
                    if line.startswith("data:"):
                        data_str = line[5:].strip()
                        if not data_str:
                            continue
                        try:
                            chunk = json.loads(data_str)
                            token = chunk.get("content", "")
                            if token:
                                full_content += token
                                if callback:
                                    callback(token)
                            if chunk.get("stop"):
                                break
                        except json.JSONDecodeError:
                            continue

        except urllib.error.URLError as e:
            raise RuntimeError(
                f"Не удалось подключиться к llama-server ({self.server_url}). "
                "Убедитесь что llama-server запущен."
            ) from e

        return _strip_thinking(full_content)

    def stream_tokens(
        self,
        prompt: str,
        params: GenerationParams | None = None,
        system_prompt: str | None = None,
    ) -> Generator[str, None, None]:
        """
        Generator версия стриминга — yield каждый токен.
        Использовать в SSE роуте: for token in provider.stream_tokens(...): ...
        """
        if not self._use_server:
            yield self.complete(prompt, params, system_prompt)
            return

        gen_params = params or GenerationParams()
        full_prompt = self._build_chatml_prompt(prompt, system_prompt)
        url = self.server_url.rstrip("/") + "/completion"

        stop_tokens = list(DEFAULT_STOP_TOKENS)
        if gen_params.stop:
            stop_tokens.extend([t for t in gen_params.stop if t.isascii()])

        payload = {
            "prompt":         full_prompt,
            "n_predict":      gen_params.max_tokens,
            "stream":         True,
            "stop":           stop_tokens,
            "temperature":    gen_params.temperature,
            "top_p":          gen_params.top_p,
            "repeat_penalty": gen_params.repeat_penalty,
            "top_k":          gen_params.top_k,
            "n_keep":         gen_params.n_keep,
        }

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

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
                        if chunk.get("stop"):
                            return
                        token = chunk.get("content", "")
                        if token:
                            yield token
                    except json.JSONDecodeError:
                        continue

        except urllib.error.URLError as e:
            yield f"\n[Ошибка соединения: {e}]"

    # ──────────────────────────────────────────────────────────────────────────
    # Служебные методы
    # ──────────────────────────────────────────────────────────────────────────

    def _find_executable(self) -> str | None:
        import shutil
        candidates = ["llama", "llama.exe", "llama-cli", "llama-cli.exe", "main", "main.exe"]
        if self.executable and Path(self.executable).exists():
            return self.executable
        for c in candidates:
            found = shutil.which(c)
            if found:
                return found
        return None

    def is_available(self) -> bool:
        if self._use_server:
            return self._check_server()
        return bool(self._find_executable()) and Path(self.model_config.path).exists()

    def _check_server(self) -> bool:
        if not self.server_url:
            return False
        for endpoint in ["/health", ""]:
            try:
                url = self.server_url.rstrip("/") + endpoint
                with urllib.request.urlopen(url, timeout=2) as resp:
                    if resp.status == 200:
                        return True
            except Exception:
                continue
        return False

    def check_server_with_retry(
        self, max_retries: int = 5, interval_sec: int = 2
    ) -> tuple[bool, str]:
        import time
        for attempt in range(1, max_retries + 1):
            if self._check_server():
                return True, f"LLM server доступен: {self.server_url}"
            if attempt < max_retries:
                time.sleep(interval_sec)
        return False, f"LLM server недоступен после {max_retries} попыток: {self.server_url}"

    def is_available_with_retry(self, max_retries: int = 5, interval_sec: int = 2) -> bool:
        ok, _ = self.check_server_with_retry(max_retries, interval_sec)
        return ok

    def get_info(self) -> ProviderInfo:
        model_name = Path(self.model_config.path).stem
        return ProviderInfo(
            name=f"LlamaCpp ({model_name})",
            provider_type=ProviderType.LLAMA_CPP,
            endpoint=self.server_url,
            model_name=model_name,
            is_available=self.is_available(),
            context_size=self.model_config.context_size,
            vram_mb=self.model_config.vram_mb,
        )

    def get_provider_type(self) -> ProviderType:
        return ProviderType.LLAMA_CPP

    def set_model(self, model_config: LlamaCppModelConfig) -> None:
        self.model_config = model_config

    def set_server_url(self, url: str) -> None:
        self.server_url = url
        self._use_server = bool(url)


def create_llama_cpp_provider(
    model_path: str | None = None,
    model_name: str = "default",
    server_url: str | None = None,
) -> LlamaCppProvider:
    config = LlamaCppModelConfig(
        path=model_path or settings.llama_cpp_model_path,
        name=model_name,
    )
    return LlamaCppProvider(
        model_config=config,
        server_url=server_url or settings.llama_cpp_server_url,
    )