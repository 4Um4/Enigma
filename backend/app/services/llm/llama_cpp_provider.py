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

import json
import logging
import os
import random
import re
import subprocess
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Generator, Optional
from app.services.npc.kernel_rng import KernelRNG

from app.core.config import settings
from app.services.llm.provider import (
    GenerationParams,
    ProviderInfo,
    ProviderType,
    StreamingLlmProvider,
)

logger = logging.getLogger(__name__)

# Regex для вырезания thinking блоков (страховка)
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)
# Regex для незакрытых thinking блоков (<think> без </think>)
_THINK_OPEN_RE = re.compile(r"<think>.*$", re.DOTALL)


def _strip_thinking(text: str) -> str:
    """Убирает <think>...</think> и незакрытые <think>... из ответа."""
    text = _THINK_RE.sub("", text)
    text = _THINK_OPEN_RE.sub("", text)
    return text.strip()


# Только ASCII стоп-токены
DEFAULT_STOP_TOKENS = [
    "</s>",
    "</user>",
    "<user>",
    "<assistant>",
    "<|im_end|>",
    "<|end_of_text|>",
]


@dataclass
class LlamaCppModelConfig:
    path: str
    name: str
    context_size: int = 8192
    temperature: float = 0.9
    top_p: float = 0.9
    min_p: float = 0.1
    repeat_penalty: float = 1.12
    n_keep: int = 800
    vram_mb: int = 5000


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
        # server_url берётся из конфига, не из runtime_ports (чтобы управлять режимом)
        self.server_url = server_url or settings.llama_cpp_server_url
        self.executable = executable or settings.llama_cpp_executable
        self._use_server = bool(self.server_url)
        # CLI-режим: отслеживание процесса и блокировка параллельных вызовов
        self._cli_process: subprocess.Popen | None = None
        self._cli_lock = threading.Lock()

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
            # S128 FIX: Используем OpenAI-совместимый эндпоинт /v1/chat/completions
            # передаём чистые prompt и system_prompt, чтобы избежать двойного ChatML
            raw = self._complete_via_server(prompt, system_prompt, gen_params)
        else:
            raw = self._complete_via_cli(full_prompt, gen_params)

        return _strip_thinking(raw)

    # ──────────────────────────────────────────────────────────────────────────
    # Построение ChatML промпта
    # ──────────────────────────────────────────────────────────────────────────

    def _build_chatml_prompt(self, user_prompt: str, system_prompt: str | None) -> str:
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
        # Qwen2.5 — ChatML формат
        if system_prompt:
            return (
                f"<|im_start|>system\n{system_prompt}\n<|im_end|>\n"
                f"<|im_start|>user\n{user_prompt}\n<|im_end|>\n"
                f"<|im_start|>assistant\n"
            )
        return f"<|im_start|>user\n{user_prompt}\n<|im_end|>\n<|im_start|>assistant\n"

    # ──────────────────────────────────────────────────────────────────────────
    # Server mode — /v1/chat/completions (OpenAI compatible)
    # ──────────────────────────────────────────────────────────────────────────

    def _complete_via_server(self, prompt: str, system_prompt: Optional[str], params: GenerationParams) -> str:
        url = self.server_url.rstrip("/") + "/v1/chat/completions"

        stop_tokens = list(DEFAULT_STOP_TOKENS)
        if params.stop:
            stop_tokens.extend([t for t in params.stop if t.isascii()])

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        # BUG-DLG-044 FIX: Детерминированный seed для LLM через KernelRNG (salt=prompt).
        _rng = KernelRNG(tick=0, npc_id="llama_cpp", salt=prompt)
        _seed = _rng.randint(0, 2**31 - 1)
        payload = {
            "messages": messages,
            "max_tokens": params.max_tokens,
            "stream": False,
            "stop": stop_tokens,
            "temperature": params.temperature,
            "top_p": params.top_p,
            "repeat_penalty": params.repeat_penalty,
            "min_p": params.min_p,
            "top_k": params.top_k,
            "n_keep": params.n_keep,
            "seed": _seed,
        }

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        # ADR-113: Retry с exponential backoff при краше llama-server
        max_retries = 3
        backoff_delays = [1.0, 2.0, 2.0]
        last_error = None

        for attempt in range(max_retries):
            try:
                # S97 FIX: Обход прокси (Throne), который рвёт соединения к localhost
                _opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                with _opener.open(
                    req, timeout=settings.llama_cpp_timeout_sec
                ) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
                    return body.get("choices", [{}])[0].get("message", {}).get("content", "")
            except (
                urllib.error.URLError,
                ConnectionResetError,
                OSError,
                TimeoutError,
            ) as e:
                last_error = e
                if attempt < max_retries - 1:
                    delay = backoff_delays[attempt]
                    logger.warning(
                        f"[LLM_RETRY] attempt {attempt + 1}/{max_retries} failed: {type(e).__name__}: {e}. Retrying in {delay}s..."
                    )
                    time.sleep(delay)
                else:
                    logger.error(
                        f"[LLM_RETRY] all {max_retries} attempts failed. Last error: {type(e).__name__}: {e}"
                    )

        raise RuntimeError(
            f"Не удалось подключиться к llama-server ({self.server_url}) после {max_retries} попыток. "
            f"Последняя ошибка: {type(last_error).__name__}: {last_error}"
        ) from last_error

    def abort_generation(self) -> None:
        """Прервать текущую генерацию (server — HTTP abort, CLI — kill процесса)."""
        if self._use_server and self.server_url:
            try:
                # H-03 FIX: llama-server может не поддерживать /abort endpoint.
                # Тихо игнорируем 404/405, чтобы не засорять логи warning'ами.
                _abort_req = urllib.request.Request(
                    self.server_url.rstrip("/") + "/abort",
                    data=b"",
                    method="POST",
                )
                urllib.request.urlopen(_abort_req, timeout=2)
            except urllib.error.HTTPError as e:
                # 404 / 405 ожидаем, если сервер не поддерживает abort
                logger.debug(f"[B5-FIX] abort endpoint not supported by server: {e.code}")
            except Exception as e:
                logger.debug(f"[B5-FIX] abort_generation silent failure: {e}")
        else:
            self._kill_cli_process()

    # ──────────────────────────────────────────────────────────────────────────
    # CLI mode
    # ──────────────────────────────────────────────────────────────────────────

    def _complete_via_cli(self, prompt: str, params: GenerationParams) -> str:
        # Блокировка: только один CLI-процесс одновременно
        if not self._cli_lock.acquire(timeout=2):
            raise RuntimeError("Предыдущий CLI-запрос ещё выполняется")
        try:
            executable = self.executable or self._find_executable()
            if not executable:
                raise RuntimeError("llama.cpp executable не найден")

            cmd = [
                executable,
                "-m",
                self.model_config.path,
                "-n",
                str(params.max_tokens),
                "-ngl",
                str(settings.gpu_layers),  # все слои на GPU
                "-c",
                str(settings.ctx_size),  # размер контекста
                "-t",
                str(settings.threads),  # потоки CPU для оставшихся операций
            ]

            if len(prompt) > 8000:
                import tempfile

                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".txt", delete=False, encoding="utf-8"
                ) as f:
                    f.write(prompt)
                    tmp_path = f.name
                cmd.extend(["-f", tmp_path])
                try:
                    return self._run_cli_process(cmd)
                finally:
                    try:
                        os.unlink(tmp_path)
                    except OSError as e:
                        logger.warning(f"[B5-FIX] silent failure suppressed: {e}")
            else:
                cmd.extend(["-p", prompt])
                return self._run_cli_process(cmd)
        finally:
            self._cli_process = None
            self._cli_lock.release()

    def _run_cli_process(self, cmd: list[str]) -> str:
        """Запустить CLI-процесс с отслеживанием и гарантированным убийством при таймауте."""
        self._cli_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        try:
            stdout, stderr = self._cli_process.communicate(
                timeout=settings.llama_cpp_timeout_sec
            )
            # C-13 FIX: Проверяем код возврата. Если процесс упал или stdout пуст — raise.
            if self._cli_process.returncode != 0 or not stdout.strip():
                raise RuntimeError(
                    f"llama-cli crashed or returned empty output. Return code: {self._cli_process.returncode}. Stderr: {stderr.strip()}"
                )
            return stdout.strip()
        except subprocess.TimeoutExpired:
            self._kill_cli_process()
            raise RuntimeError(
                f"llama-cli завис и был убит (таймаут {settings.llama_cpp_timeout_sec}с)"
            )

    def _kill_cli_process(self) -> None:
        """Жёсткое убийство CLI-процесса — освобождает VRAM."""
        proc = self._cli_process
        if proc is None:
            return
        try:
            proc.kill()
            proc.wait(timeout=3)
        except Exception:
            try:
                proc.terminate()
                proc.wait(timeout=2)
            except Exception as e:
                logger.warning(f"[B5-FIX] silent failure suppressed: {e}")
        self._cli_process = None

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
            "prompt": full_prompt,
            "n_predict": gen_params.max_tokens,
            "stream": True,
            "stop": stop_tokens,
            "temperature": gen_params.temperature,
            "top_p": gen_params.top_p,
            "repeat_penalty": gen_params.repeat_penalty,
            "min_p": gen_params.min_p,
            "top_k": gen_params.top_k,
            "n_keep": gen_params.n_keep,
        }

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        full_content = ""

        # ADR-113: Retry с exponential backoff + partial recovery при обрыве стрима
        max_retries = 3
        backoff_delays = [1.0, 2.0, 2.0]
        last_error = None

        for attempt in range(max_retries):
            try:
                # S97 FIX: Обход прокси (Throne)
                _opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                with _opener.open(
                    req, timeout=settings.llama_cpp_timeout_sec
                ) as resp:
                    while True:
                        line = resp.readline()
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
                            except json.JSONDecodeError as e:
                                logger.debug(f"JSONDecodeError in stream, skipping: {e}")
                                continue
                # Успешное завершение стрима
                break
            except (
                urllib.error.URLError,
                ConnectionResetError,
                OSError,
                TimeoutError,
            ) as e:
                last_error = e
                # Partial recovery: если уже получили >20 символов — используем
                if len(full_content) > 20:
                    logger.warning(
                        f"[LLM_RETRY] Stream broke after {len(full_content)} chars on attempt {attempt + 1}. Using partial content."
                    )
                    break
                if attempt < max_retries - 1:
                    delay = backoff_delays[attempt]
                    logger.warning(
                        f"[LLM_RETRY] attempt {attempt + 1}/{max_retries} failed: {type(e).__name__}: {e}. Retrying in {delay}s..."
                    )
                    time.sleep(delay)
                else:
                    logger.error(
                        f"[LLM_RETRY] all {max_retries} attempts failed. Last error: {type(e).__name__}: {e}"
                    )
                    raise RuntimeError(
                        f"Не удалось подключиться к llama-server ({self.server_url}) после {max_retries} попыток. "
                        f"Последняя ошибка: {type(last_error).__name__}: {last_error}"
                    ) from last_error

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
            "prompt": full_prompt,
            "n_predict": gen_params.max_tokens,
            "stream": True,
            "stop": stop_tokens,
            "temperature": gen_params.temperature,
            "top_p": gen_params.top_p,
            "repeat_penalty": gen_params.repeat_penalty,
            "min_p": gen_params.min_p,
            "top_k": gen_params.top_k,
            "n_keep": gen_params.n_keep,
        }

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            # S97 FIX: Обход прокси (Throne)
            _opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with _opener.open(
                req, timeout=settings.llama_cpp_timeout_sec
            ) as resp:
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
                    except json.JSONDecodeError as e:
                        logger.debug(f"JSONDecodeError in stream, skipping: {e}")
                        continue

        except urllib.error.URLError as e:
            # C-14 FIX: Не инжектим ошибку в токены LLM, пробрасываем исключение.
            raise RuntimeError(f"LLM stream connection error: {e}") from e

    # ──────────────────────────────────────────────────────────────────────────
    # Служебные методы
    # ──────────────────────────────────────────────────────────────────────────

    def _find_executable(self) -> str | None:
        import shutil

        candidates = [
            "llama",
            "llama.exe",
            "llama-cli",
            "llama-cli.exe",
            "main",
            "main.exe",
        ]
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
            logger.debug("[LLAMA_DEBUG] _check_server: server_url is missing!")
            return False
        for endpoint in ["/health", "/v1/models", ""]:
            try:
                url = self.server_url.rstrip("/") + endpoint
                logger.debug(f"[LLAMA_DEBUG] _check_server: trying {url}")
                # S97 FIX: Обход прокси (Throne)
                _opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                with _opener.open(url, timeout=2) as resp:
                    logger.debug(f"[LLAMA_DEBUG] _check_server: got status {resp.status}")
                    if resp.status == 200:
                        return True
            except Exception as e:
                logger.debug(f"[LLAMA_DEBUG] _check_server: exception {type(e).__name__}: {e}")
                continue
        logger.debug("[LLAMA_DEBUG] _check_server: all endpoints failed, returning False")
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
        return (
            False,
            f"LLM server недоступен после {max_retries} попыток: {self.server_url}",
        )

    def is_available_with_retry(
        self, max_retries: int = 5, interval_sec: int = 2
    ) -> bool:
        # CLI-режим: проверяем наличие файлов (без retry — нет сети)
        if not self._use_server:
            return self.is_available()
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
    temperature: float | None = None,
    repeat_penalty: float | None = None,
) -> LlamaCppProvider:
    config = LlamaCppModelConfig(
        path=model_path or settings.llama_cpp_model_path,
        name=model_name,
        temperature=temperature if temperature is not None else 0.9,
        repeat_penalty=repeat_penalty if repeat_penalty is not None else 1.12,
    )
    return LlamaCppProvider(
        model_config=config,
        server_url=server_url or settings.llama_cpp_server_url,
    )
