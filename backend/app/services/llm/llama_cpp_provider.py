"""
Llama.cpp Provider Implementation
Local LLM inference using llama.cpp server or CLI
"""

from __future__ import annotations

import os
import json
import urllib.request
import urllib.error
from dataclasses import dataclass
from pathlib import Path

from app.core.config import settings
from app.services.llm.provider import (
    LlmProvider, 
    GenerationParams, 
    ProviderInfo, 
    ProviderType,
    StreamingLlmProvider
)


# Default stop tokens for role-playing games
DEFAULT_STOP_TOKENS = [
    "</system>", "</user>", "<user>", "<assistant>",
    "<|im_end|>", "<|end_of_text|>",
    "Игрок:", "Вы:", "Персонаж:",
    "\nИгрок", "\nВы:", "\nПерсонаж:",
]


@dataclass
class LlamaCppModelConfig:
    """Конфигурация модели для llama.cpp провайдера."""
    path: str
    name: str
    context_size: int = 4096
    temperature: float = 0.7
    top_p: float = 0.9
    repeat_penalty: float = 1.1
    n_keep: int = 512
    vram_mb: int = 4000


class LlamaCppProvider(StreamingLlmProvider):
    """
    Провайдер для llama.cpp (локальные модели).
    
    Поддерживает:
    - llama-server (HTTP API) - быстрый режим
    - llama-cli (subprocess) - медленный режим
    """
    
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
        """Проверяет, используется ли server mode."""
        return self._use_server
    
    def complete(
        self,
        prompt: str,
        params: GenerationParams | None = None,
        system_prompt: str | None = None,
    ) -> str:
        """Генерирует текст через llama.cpp."""
        # Merge with default params
        gen_params = params or GenerationParams()
        
        # Build full prompt with system
        full_prompt = self._build_prompt(prompt, system_prompt)
        
        if self._use_server:
            return self._complete_via_server(full_prompt, gen_params)
        else:
            return self._complete_via_cli(full_prompt, gen_params)
    
    def _build_prompt(self, user_prompt: str, system_prompt: str | None) -> str:
        """Формирует полный промпт с системным."""
        if system_prompt:
            return f"<system>\n{system_prompt}\n</system>\n\n<user>\n{user_prompt}\n</user>\n\n<assistant>\n"
        return user_prompt
    
    def _complete_via_server(self, prompt: str, params: GenerationParams) -> str:
        """Отправляет запрос через llama-server HTTP API."""
        url = self.server_url.rstrip("/") + "/completion"
        
        # Build stop tokens
        stop_tokens = list(DEFAULT_STOP_TOKENS)
        if params.stop:
            stop_tokens.extend(params.stop)
        
        payload = {
            "prompt": prompt,
            "n_predict": params.max_tokens,
            "stream": False,
            "stop": stop_tokens,
            "temperature": params.temperature,
            "top_p": params.top_p,
            "repeat_penalty": params.repeat_penalty,
            "top_k": params.top_k,
            "n_keep": params.n_keep,
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
                content = body.get("content", "")
                return content.strip()
        except urllib.error.URLError as e:
            raise RuntimeError(
                f"Не удалось подключиться к llama-server ({self.server_url}). "
                "Убедитесь что llama-server запущен."
            ) from e
    
    def _complete_via_cli(self, prompt: str, params: GenerationParams) -> str:
        """Выполняет запрос через llama-cli subprocess."""
        import subprocess
        import tempfile
        
        executable = self.executable or self._find_executable()
        model_path = self.model_config.path
        
        if not executable:
            raise RuntimeError("llama.cpp executable не найден")
        
        # Use file for long prompts (Windows limit ~8191)
        use_file = len(prompt) > 8000
        
        cmd = [executable, "-m", model_path, "-n", str(params.max_tokens)]
        
        if use_file:
            with tempfile.NamedTemporaryFile(
                mode="w",
                suffix=".txt",
                delete=False,
                encoding="utf-8",
            ) as f:
                f.write(prompt)
                tmp_path = f.name
            cmd.extend(["-f", tmp_path])
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
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
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=settings.llama_cpp_timeout_sec,
            )
        
        output = result.stdout.strip()
        return output or result.stderr.strip()
    
    def _find_executable(self) -> str | None:
        """Исполнительный файл llama."""
        import shutil
        
        candidates = [
            "llama",
            "llama.exe",
            "llama-cli",
            "llama-cli.exe",
            "main",
            "main.exe",
        ]
        
        # Check configured path
        if self.executable and Path(self.executable).exists():
            return self.executable
        
        # Check PATH
        for candidate in candidates:
            found = shutil.which(candidate)
            if found:
                return found
        
        return None
    
    def is_available(self) -> bool:
        """Проверяет доступность провайдера."""
        if self._use_server:
            return self._check_server()
        else:
            return bool(self._find_executable()) and Path(self.model_config.path).exists()
    
    def _check_server(self) -> bool:
        """Проверяет работает ли llama-server."""
        if not self.server_url:
            return False
        try:
            url = self.server_url.rstrip("/") + "/health"
            with urllib.request.urlopen(url, timeout=2) as resp:
                return resp.status == 200
        except Exception:
            # Try root endpoint as fallback
            try:
                with urllib.request.urlopen(self.server_url, timeout=2) as resp:
                    return resp.status == 200
            except Exception:
                return False
    
    def check_server_with_retry(self, max_retries: int = 5, interval_sec: int = 2) -> tuple[bool, str]:
        """
        Проверяет доступность сервера с повторными попытками.
        
        Args:
            max_retries: Максимальное количество попыток
            interval_sec: Интервал между попытками в секундах
            
        Returns:
            Tuple (is_available, status_message)
        """
        import time
        
        for attempt in range(1, max_retries + 1):
            if self._check_server():
                return True, f"LLM server доступен: {self.server_url}"
            
            if attempt < max_retries:
                time.sleep(interval_sec)
        
        return False, f"LLM server недоступен после {max_retries} попыток: {self.server_url}"
    
    def is_available_with_retry(self, max_retries: int = 5, interval_sec: int = 2) -> bool:
        """
        Проверяет доступность провайдера с повторными попытками.
        
        Args:
            max_retries: Максимальное количество попыток
            interval_sec: Интервал между попытками в секундах
            
        Returns:
            True если сервер доступен
        """
        is_available, _ = self.check_server_with_retry(max_retries, interval_sec)
        return is_available
    
    def get_info(self) -> ProviderInfo:
        """Возвращает информацию о провайдере."""
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
        """Возвращает тип провайдера."""
        return ProviderType.LLAMA_CPP
    
    def set_model(self, model_config: LlamaCppModelConfig) -> None:
        """Установить конфигурацию модели."""
        self.model_config = model_config
    
    def set_server_url(self, url: str) -> None:
        """Установить URL llama-server."""
        self.server_url = url
        self._use_server = bool(url)


# Factory function
def create_llama_cpp_provider(
    model_path: str | None = None,
    model_name: str = "default",
    server_url: str | None = None,
) -> LlamaCppProvider:
    """Создать LlamaCppProvider с конфигурацией."""
    config = LlamaCppModelConfig(
        path=model_path or settings.llama_cpp_model_path,
        name=model_name,
    )
    return LlamaCppProvider(
        model_config=config,
        server_url=server_url or settings.llama_cpp_server_url,
    )

