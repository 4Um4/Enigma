"""
Provider Manager — Multi-Provider + Lazy Loading (RTX 3070 Ti, 8 GB VRAM)

ИСПРАВЛЕНИЯ vs оригинал:
1. Класс ModelPool был СТРУКТУРНО СЛОМАН:
   блок `if __name__ == "__main__"` разрывал тело класса — все атрибуты
   (_max_loaded, _active_model, _pool_lock, list_models, etc.) оказывались
   ВНЕ класса. ModelPool работал как пустышка без полей.
   → Переписан с нуля, правильная структура.

2. asyncio.sleep(2) в measure_load() убран.
   3 агента × 2 сек = +6 сек лишнего ожидания на каждый turn.

3. unload_all() вызывал asyncio.create_task() из sync-контекста → RuntimeError.
   Заменено на синхронный _unload_active_model().

# 4. context_size по умолчанию: 8192 (с flash-attn влезает в 8 GB VRAM).
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, Optional

from app.core.config import settings
from app.services.error_interpreter import get_error_interpreter
from app.services.vram_monitor import get_vram_monitor

logger = logging.getLogger(__name__)

from app.services.llm.provider import LlmProvider, ProviderInfo, ProviderType
from app.services.llm.provider import CAPABILITY_MODEL_PREFERENCES, Capability


class ProviderStatus(str, Enum):
    UNINITIALIZED = "uninitialized"
    INITIALIZING = "initializing"
    LOADING = "loading"
    READY = "ready"
    ERROR = "error"
    DISABLED = "disabled"


@dataclass
class ModelMetrics:
    name: str
    vram_usage: int
    last_used: float


@dataclass
class ModelConfig:
    key: str
    name: str
    provider_type: ProviderType
    path: str
    context_size: int = 8192
    temperature: float = 0.7
    vram_mb: int = 4000
    metrics: ModelMetrics = field(
        default_factory=lambda: ModelMetrics(name="", vram_usage=0, last_used=0.0)
    )


@dataclass
class ModelProvider:
    key: str
    name: str
    provider: LlmProvider
    provider_type: ProviderType
    path: str
    endpoint: Optional[str] = None
    context_size: int = 2048
    vram_mb: int = 4000
    temperature: float = 0.7
    status: ProviderStatus = ProviderStatus.UNINITIALIZED
    last_used: float = 0
    error_count: int = 0
    last_error: Optional[str] = None

    def is_available(self) -> bool:
        return (
            self.status == ProviderStatus.READY
            and self.provider is not None
            and self.provider.is_available()
        )

    def get_info(self) -> ProviderInfo:
        return self.provider.get_info()

    def mark_used(self) -> None:
        self.last_used = time.time()

    def mark_error(self, error: str) -> None:
        self.error_count += 1
        self.last_error = error
        if self.error_count >= 3:
            self.status = ProviderStatus.ERROR

    def reset_errors(self) -> None:
        self.error_count = 0
        self.last_error = None
        if self.status == ProviderStatus.ERROR:
            self.status = ProviderStatus.READY


class ModelPool:
    """
    Lazy-loading pool, max_loaded=1.
    RTX 3070 Ti (8 GB): одна модель в VRAM, строгая очерёдность.
    """

    def __init__(self, max_loaded: int = 1) -> None:
        if getattr(self, "_initialized", False):
            return

        self._max_loaded = max_loaded
        self._active_model: Optional[ModelProvider] = None
        self._active_key: Optional[str] = None
        self._model_configs: Dict[str, ModelConfig] = {}
        self._metrics: Dict[str, ModelMetrics] = {}

        self._availability_cache: Dict[str, bool] = {}
        self._failure_cache: Dict[str, float] = {}
        self._cache_ttl_seconds: float = 30.0
        self._last_cache_update: float = 0.0

        self._pool_lock = asyncio.Lock()
        self._switch_semaphore = asyncio.Semaphore(1)
        self._logger = logging.getLogger(__name__)
        self._warm_model_key: Optional[str] = None
        self.debug = False

        self.error_interpreter = get_error_interpreter()
        self.vram_monitor = get_vram_monitor()

        from app.services.error_interpreter import LOG_FILE

        self._log_file = LOG_FILE

        self._initialized = True

    # ── Configuration ─────────────────────────────────────────────────────────
    def register_model_config(self, config: ModelConfig) -> None:
        self._model_configs[config.key] = config
        if config.key not in self._metrics:
            self._metrics[config.key] = ModelMetrics(
                name=config.name, vram_usage=config.vram_mb, last_used=0.0
            )

    def get_model_config(self, key: str) -> Optional[ModelConfig]:
        return self._model_configs.get(key)

    def list_model_configs(self) -> Dict[str, ModelConfig]:
        return dict(self._model_configs)

    def list_models(self) -> list[ModelProvider]:
        return [self._active_model] if self._active_model else []

    def get_model(self, key: str) -> Optional[ModelProvider]:
        """Синхронный доступ — загружает модель если ещё не в VRAM."""
        if self._active_key == key and self._active_model is not None:
            self._active_model.mark_used()
            return self._active_model
        return self._load_model(key)

    # ── Async Lazy Loading ─────────────────────────────────────────────────────
    async def get_model_async(
        self,
        key: str,
        session_id: Optional[str] = None,
        agent: Optional[str] = None,
        timeout_sec: Optional[float] = None,
    ) -> Optional[ModelProvider]:
        if timeout_sec is None:
            timeout_sec = settings.model_load_timeout_sec

        session_log = f"[{session_id}]" if session_id else ""
        self._logger.info(
            f"ModelPool{session_log} get_model_async('{key}', agent='{agent}')"
        )

        vram_before = await self.vram_monitor.get_vram_mb()
        self._jsonl_log(
            {
                "timestamp": datetime.now().isoformat(),
                "level": "INFO",
                "agent": agent or "unknown",
                "model": key,
                "status": "load_start",
                "vram_before_mb": vram_before,
            }
        )

        try:
            model = await asyncio.wait_for(
                self._get_model_locked(key, session_id),
                timeout=timeout_sec,
            )
            vram_after = await self.vram_monitor.get_vram_mb()
            delta_mb = vram_after - vram_before

            if model:
                self._logger.info(
                    f"ModelPool{session_log} ✓ '{key}' (VRAM delta={delta_mb:+}MB)"
                )
                self._jsonl_log(
                    {
                        "timestamp": datetime.now().isoformat(),
                        "level": "INFO",
                        "agent": agent or "unknown",
                        "model": key,
                        "status": "load_success",
                        "vram_after_mb": vram_after,
                        "vram_delta_mb": delta_mb,
                    }
                )
                return model
            else:
                self._jsonl_log(
                    {
                        "timestamp": datetime.now().isoformat(),
                        "level": "WARNING",
                        "agent": agent or "unknown",
                        "model": key,
                        "status": "load_failed_no_model",
                    }
                )
                return None

        except asyncio.TimeoutError as exc:
            human_msg, fix = self.error_interpreter.handle(
                exc,
                {"agent": agent, "model": key, "timeout_sec": timeout_sec},
                agent or "pool",
                key,
            )
            self._logger.error(f"ModelPool{session_log} TIMEOUT '{key}': {human_msg}")
            return None

        except Exception as exc:
            human_msg, fix = self.error_interpreter.handle(
                exc,
                {"vram_before": vram_before, "agent": agent, "model": key},
                agent or "pool",
                key,
            )
            self._logger.error(f"ModelPool{session_log} ERROR '{key}': {human_msg}")
            self._jsonl_log(
                {
                    "timestamp": datetime.now().isoformat(),
                    "level": "ERROR",
                    "agent": agent or "unknown",
                    "model": key,
                    "status": "load_error",
                    "error_type": type(exc).__name__,
                    "human_msg": human_msg,
                    "fix": fix,
                }
            )
            return None

    async def _get_model_locked(
        self, key: str, session_id: Optional[str] = None
    ) -> Optional[ModelProvider]:
        async with self._switch_semaphore:
            async with self._pool_lock:
                if self._active_key == key and self._active_model is not None:
                    self._active_model.mark_used()
                    return self._active_model
                try:
                    return await asyncio.to_thread(self._load_model, key)
                except Exception as e:
                    self._logger.error(f"ModelPool load '{key}' error: {e}")
                    return None

    def _load_model(self, key: str) -> Optional[ModelProvider]:
        config = self._model_configs.get(key)
        if not config:
            self._logger.error(f"ModelPool: Config not found: '{key}'")
            return None

        if self._active_model is not None:
            self._unload_active_model()

        load_start = time.time()
        try:
            from app.services.llm.factory import ProviderFactory

            provider = ProviderFactory.create(
                provider_type=config.provider_type,
                model_path=config.path,
            )
            model_provider = ModelProvider(
                key=key,
                name=config.name,
                provider=provider,
                provider_type=config.provider_type,
                path=config.path,
                context_size=config.context_size,
                vram_mb=config.vram_mb,
                temperature=config.temperature,
                status=ProviderStatus.READY,
            )
            if key in self._metrics:
                self._metrics[key].last_used = time.time()

            self._active_model = model_provider
            self._active_key = key

            load_ms = (time.time() - load_start) * 1000
            self._logger.info(f"ModelPool: Loaded '{key}' in {load_ms:.0f}ms")
            return model_provider

        except Exception as exc:
            self._logger.error(f"ModelPool: ProviderFactory failed '{key}': {exc}")
            return None

    def _unload_active_model(self) -> None:
        if self._active_model is not None:
            key = self._active_key
            self._logger.info(f"ModelPool: Unloading '{key}'")
            self._active_model = None
            self._active_key = None

    async def unload_model(self, key: str) -> None:
        async with self._switch_semaphore:
            async with self._pool_lock:
                if self._active_key == key:
                    await asyncio.to_thread(self._unload_active_model)

    def unload_all(self) -> None:
        self._unload_active_model()

    # ── Properties ────────────────────────────────────────────────────────────
    @property
    def active_model_key(self) -> Optional[str]:
        return self._active_key

    @property
    def active_model(self) -> Optional[ModelProvider]:
        return self._active_model

    @property
    def has_active_model(self) -> bool:
        return self._active_model is not None

    # ── Availability ──────────────────────────────────────────────────────────
    def is_model_available(self, key: str) -> bool:
        now = time.time()
        if key in self._failure_cache and now < self._failure_cache[key]:
            return False
        if (
            key in self._availability_cache
            and now - self._last_cache_update < self._cache_ttl_seconds
        ):
            return self._availability_cache[key]
        available = key in self._model_configs
        self._availability_cache[key] = available
        self._last_cache_update = now
        return available

    def record_failure(self, key: str) -> None:
        if key not in self._metrics:
            return
        backoff = 300 if self._metrics[key].last_used > 0 else 30
        self._failure_cache[key] = time.time() + backoff
        self._logger.warning(f"Model '{key}' backoff {backoff}s")

    def get_metrics(self, key: str) -> Optional[ModelMetrics]:
        return self._metrics.get(key)

    def set_warm_model(self, key: str) -> None:
        self._warm_model_key = key

    async def warm_up(self) -> bool:
        if self._warm_model_key:
            return (await self.get_model_async(self._warm_model_key)) is not None
        return False

    async def get_status(self) -> dict:
        current_vram = await self.vram_monitor.get_vram_mb()
        recent_errors = self.error_interpreter.analyze_recent_errors()
        status = {
            "active_model": self._active_key,
            "max_loaded": self._max_loaded,
            "registered_models": list(self._model_configs.keys()),
            "current_vram_mb": current_vram,
            "recent_errors": recent_errors,
            "vram_dashboard": await self.vram_monitor.get_dashboard(),
        }
        if self._active_model:
            try:
                status["active_model_info"] = vars(self._active_model.get_info())
            except Exception:
                status["active_model_info"] = {}
        return status

    def _jsonl_log(self, event: dict) -> None:
        try:
            with open(self._log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(event, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.debug(f"[PROVIDER_MGR] Ошибка записи лога: {e}")


# ── Global singletons ─────────────────────────────────────────────────────────
_model_pool: Optional[ModelPool] = None
_provider_manager: Optional[ProviderManager] = None


def get_model_pool() -> ModelPool:
    global _model_pool
    if _model_pool is None:
        _model_pool = ModelPool(max_loaded=1)
    return _model_pool


# pool создаётся через initialize_model_pool() при старте — не на уровне модуля


class ProviderManager:
    _instance: Optional["ProviderManager"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "ProviderManager":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if getattr(self, "_initialized", False):
            return
        self._providers: Dict[str, ModelProvider] = {}
        self._providers_lock = threading.RLock()
        self._startup_complete = True
        self._initialized = True

    @property
    def is_ready(self) -> bool:
        return self._startup_complete

    def register_provider(
        self, key, name, provider, provider_type, path, endpoint=None, **kwargs
    ) -> ModelProvider:
        with self._providers_lock:
            mp = ModelProvider(
                key=key,
                name=name,
                provider=provider,
                provider_type=provider_type,
                path=path,
                endpoint=endpoint,
                **kwargs,
            )
            self._providers[key] = mp
            return mp

    def get_provider(self, key: str) -> Optional[ModelProvider]:
        return self._providers.get(key)

    def get_any_available(self) -> Optional[ModelProvider]:
        with self._providers_lock:
            for p in self._providers.values():
                if p.is_available():
                    return p
        return None

    def get_provider_for_capability(
        self, capability: str, preferred_keys=None
    ) -> Optional[ModelProvider]:
        cap_enum = (
            Capability(capability)
            if capability in [c.value for c in Capability]
            else Capability.GENERAL
        )
        prefs = list(
            preferred_keys or CAPABILITY_MODEL_PREFERENCES.get(cap_enum, ["qwen_7b"])
        )
        with self._providers_lock:
            for key in prefs:
                p = self._providers.get(key)
                if p and p.is_available():
                    return p
            return self.get_any_available()

    def initialize_all(self) -> Dict[str, bool]:
        results: Dict[str, bool] = {}
        for key, model_config in settings.available_models.items():
            try:
                self._create_and_register_provider(key, model_config)
                results[key] = True
            except Exception as e:
                logger.error(f"Failed to initialize provider {key}: {e}")
                results[key] = False
        self._startup_complete = True
        return results

    def _create_and_register_provider(self, key, model_config) -> ModelProvider:
        from app.services.llm.factory import ProviderFactory

        pt = ProviderType(getattr(model_config, "provider_type", "llama_cpp"))
        provider = ProviderFactory.create(
            provider_type=pt, model_path=model_config.path
        )
        return self.register_provider(
            key=key,
            name=model_config.display_name,
            provider=provider,
            provider_type=pt,
            path=model_config.path,
            context_size=model_config.context_size,
            vram_mb=model_config.vram_mb,
            temperature=model_config.temperature,
        )


def get_provider_manager() -> ProviderManager:
    global _provider_manager
    if _provider_manager is None:
        _provider_manager = ProviderManager()
    return _provider_manager


def initialize_providers() -> Dict[str, bool]:
    return get_provider_manager().initialize_all()


def initialize_model_pool(warm_model_key: Optional[str] = None) -> Dict[str, bool]:
    pool = get_model_pool()
    results: Dict[str, bool] = {}
    for key, model_config in settings.available_models.items():
        pt_str = getattr(model_config, "provider_type", "llama_cpp")
        # Не-локальные провайдеры не требуют файл модели на диске
        _LOCAL_PROVIDERS = {"llama_cpp", "koboldcpp"}
        # S129 FIX: В server-mode (когда задан settings.llama_cpp_server_url)
        # наличие локального файла модели не требуется — сервер уже запущен.
        # Раньше ModelPool пропускал регистрацию, из-за чего Router падал с
        # "Все модели пула недоступны", хотя llama-server был жив.
        _use_server_mode = bool(getattr(settings, "llama_cpp_server_url", None)) and pt_str == "llama_cpp"
        if pt_str in _LOCAL_PROVIDERS and not _use_server_mode and not Path(model_config.path).exists():
            logger.info(f"ModelPool: Skipped '{key}' — файл модели не найден и server_url не задан")
            results[key] = False
            continue
        try:
            ctx = model_config.context_size
            config = ModelConfig(
                key=key,
                name=model_config.display_name,
                provider_type=ProviderType(
                    getattr(model_config, "provider_type", "llama_cpp")
                ),
                path=model_config.path,
                context_size=ctx,
                temperature=model_config.temperature,
                vram_mb=model_config.vram_mb,
            )
            pool.register_model_config(config)
            results[key] = True
            logger.info(f"ModelPool: Registered '{key}' (ctx={ctx})")
        except Exception as e:
            logger.error(f"ModelPool: Failed '{key}': {e}")
            results[key] = False
    if warm_model_key:
        pool.set_warm_model(warm_model_key)
    return results


def get_pool_manager() -> tuple[ModelPool, ProviderManager]:
    return get_model_pool(), get_provider_manager()


class ErrorInterpreter:
    def handle(self, exc, context=None, agent_name=None, model_key=None):
        import traceback

        human_msg = "".join(traceback.format_exception_only(type(exc), exc)).strip()
        return human_msg, "Check logs / restart / validate model pool"


async def warm_up_all(pool: ModelPool):
    for key in pool.list_model_configs().keys():
        try:
            await pool.get_model_async(key)
        except Exception as e:
            logger.warning(f"Warm-up failed for '{key}': {e}")
