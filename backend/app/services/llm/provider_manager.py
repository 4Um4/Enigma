"""
Provider Manager - Multi-Provider System with Lazy Loading

Manages multiple LLM providers with ModelPool for VRAM optimization.
Only one model loaded at a time (for 8GB VRAM constraint).

Architecture:
    ProviderManager
    ├── ModelRegistry (all model configs)
    ├── ModelPool (max 1 loaded model)
    └── Router (uses pool for routing)

Lazy Loading Flow:
    request → ModelPool → unload previous → load new → use
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from app.core.config import settings
from app.services.llm.provider import LlmProvider, ProviderType, ProviderInfo


class ProviderStatus(str, Enum):
    """Статус провайдера."""
    UNINITIALIZED = "uninitialized"
    INITIALIZING = "initializing"
    LOADING = "loading"
    READY = "ready"
    ERROR = "error"
    DISABLED = "disabled"


@dataclass
class ModelMetrics:
    """Метрики для модели."""
    # Performance
    avg_latency_ms: float = 0.0
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    
    # Load time
    last_load_time_ms: float = 0.0
    total_load_time_ms: float = 0.0
    
    # Tokens
    total_tokens: int = 0
    
    @property
    def success_rate(self) -> float:
        """Процент успешных запросов."""
        if self.total_requests == 0:
            return 0.0
        return self.successful_requests / self.total_requests
    
    @property
    def tokens_per_second(self) -> float:
        """Скорость генерации токенов."""
        if self.avg_latency_ms == 0:
            return 0.0
        # Rough estimate
        return (self.total_tokens / self.total_requests) / (self.avg_latency_ms / 1000) if self.total_requests > 0 else 0.0
    
    def record_request(self, latency_ms: float, tokens: int, success: bool) -> None:
        """Записать результат запроса."""
        self.total_requests += 1
        if success:
            self.successful_requests += 1
            # Update average latency
            self.avg_latency_ms = (
                (self.avg_latency_ms * (self.total_requests - 1) + latency_ms) 
                / self.total_requests
            )
            self.total_tokens += tokens
        else:
            self.failed_requests += 1
    
    def record_load_time(self, load_time_ms: float) -> None:
        """Записать время загрузки модели."""
        self.last_load_time_ms = load_time_ms
        self.total_load_time_ms += load_time_ms


@dataclass
class ModelConfig:
    """Конфигурация модели (без инстанса провайдера)."""
    key: str
    name: str
    provider_type: ProviderType
    path: str
    
    # Parameters
    context_size: int = 4096
    temperature: float = 0.7
    vram_mb: int = 4000
    
    # Metrics
    metrics: ModelMetrics = field(default_factory=ModelMetrics)


@dataclass
class ModelProvider:
    """
    Обёртка над провайдером для конкретной модели.
    
    Хранит конфигурацию модели и состояние провайдера.
    """
    key: str                    # Уникальный ключ (qwen_7b, saiga, etc)
    name: str                    # Человеческое название
    provider: LlmProvider        # Инстанс провайдера
    provider_type: ProviderType  # Тип провайдера
    path: str                    # Путь к файлу модели
    endpoint: Optional[str] = None
    
    # Metadata
    context_size: int = 4096
    vram_mb: int = 4000
    temperature: float = 0.7
    
    # Status
    status: ProviderStatus = ProviderStatus.UNINITIALIZED
    last_used: float = 0
    error_count: int = 0
    last_error: Optional[str] = None
    
    def is_available(self) -> bool:
        """Проверяет доступность провайдера."""
        return self.status == ProviderStatus.READY and self.provider.is_available()
    
    def get_info(self) -> ProviderInfo:
        """Получить информацию о провайдере."""
        return self.provider.get_info()
    
    def mark_used(self) -> None:
        """Отметить время последнего использования."""
        self.last_used = time.time()
    
    def mark_error(self, error: str) -> None:
        """Зафиксировать ошибку."""
        self.error_count += 1
        self.last_error = error
        if self.error_count >= 3:
            self.status = ProviderStatus.ERROR
    
    def reset_errors(self) -> None:
        """Сбросить счётчик ошибок."""
        self.error_count = 0
        self.last_error = None
        if self.status == ProviderStatus.ERROR:
            self.status = ProviderStatus.READY


class ModelPool:
    """
    Пул моделей с ленивой загрузкой для VRAM оптимизации.
    
    Загружает только одну модель в VRAM (8GB limit).
    При запросе другой моделиет текущую и загру - выгружажает новую.
    
    Architecture:
        ModelPool
        ├── max_loaded_models = 1
        ├── active_model: ModelProvider | None
        ├── model_configs: dict[str, ModelConfig]
        └── lock (thread safety)
    """
    
    _instance: Optional['ModelPool'] = None
    _lock = threading.Lock()
    _max_loaded_default: int = 1
    
    def __new__(cls, max_loaded: int = 1) -> 'ModelPool':
        """Singleton pattern."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
                    cls._instance._max_loaded = max_loaded
        return cls._instance
    
    def __init__(self, max_loaded: int = 1) -> None:
        if self._initialized:
            return
        
        # Configuration
        self._max_loaded = max_loaded  # 1 for 8GB VRAM
        
        # Active model (loaded in VRAM)
        self._active_model: Optional[ModelProvider] = None
        self._active_key: Optional[str] = None
        
        # Model configurations (without loaded providers)
        self._model_configs: dict[str, ModelConfig] = {}
        
        # Availability cache
        self._availability_cache: dict[str, bool] = {}
        self._failure_cache: dict[str, float] = {}  # Track failures for backoff
        self._cache_ttl_seconds: float = 30.0
        self._last_cache_update: float = 0
        
        # Metrics per model
        self._metrics: dict[str, ModelMetrics] = {}
        
        # Thread safety - main lock for all operations
        self._pool_lock = threading.RLock()
        
        # Warm model config
        self._warm_model_key: Optional[str] = None
        
        self._initialized = True
    
    # === Configuration Management ===
    
    def register_model_config(self, config: ModelConfig) -> None:
        """
        Зарегистрировать конфигурацию модели (без загрузки).
        
        Args:
            config: ModelConfig с параметрами модели
        """
        with self._pool_lock:
            self._model_configs[config.key] = config
            # Initialize metrics if not exists
            if config.key not in self._metrics:
                self._metrics[config.key] = ModelMetrics()
    
    def get_model_config(self, key: str) -> Optional[ModelConfig]:
        """Получить конфигурацию модели."""
        return self._model_configs.get(key)
    
    def list_model_configs(self) -> dict[str, ModelConfig]:
        """Список всех зарегистрированных моделей."""
        return dict(self._model_configs)
    
    # === Lazy Loading ===
    
    def get_model(self, key: str) -> Optional[ModelProvider]:
        """
        Получить модель с ленивой загрузкой.
        
        Если модель не загружена - загружает её.
        Если другая модель загружена - выгружает её и загружает новую.
        
        Args:
            key: Ключ модели
            
        Returns:
            ModelProvider с загруженной моделью или None
        """
        with self._pool_lock:
            # Already loaded?
            if self._active_key == key and self._active_model is not None:
                self._active_model.mark_used()
                return self._active_model
            
            # Need to load new model
            return self._load_model(key)
    
    def _load_model(self, key: str) -> Optional[ModelProvider]:
        """
        Загрузить модель в VRAM (выгрузив предыдущую если нужно).
        
        Args:
            key: Ключ модели для загрузки
            
        Returns:
            Загруженный ModelProvider или None
        """
        config = self._model_configs.get(key)
        if not config:
            print(f"ModelPool: Model config not found for key: {key}")
            return None
        
        # Unload previous model first
        if self._active_model is not None:
            self._unload_active_model()
        
        # Load new model
        load_start = time.time()
        
        try:
            from app.services.llm.factory import ProviderFactory
            
            # Create provider
            provider = ProviderFactory.create(
                provider_type=config.provider_type,
                model_path=config.path,
            )
            
            # Create ModelProvider wrapper
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
            
            # Record load time
            load_time_ms = (time.time() - load_start) * 1000
            self._metrics[key].record_load_time(load_time_ms)
            
            # Set as active
            self._active_model = model_provider
            self._active_key = key
            
            print(f"ModelPool: Loaded model '{key}' in {load_time_ms:.0f}ms")
            return model_provider
            
        except Exception as e:
            print(f"ModelPool: Failed to load model '{key}': {e}")
            return None
    
    def _unload_active_model(self) -> None:
        """Выгрузить активную модель из VRAM."""
        if self._active_model is not None:
            key = self._active_key
            print(f"ModelPool: Unloading model '{key}'")
            
            # Clear reference (provider will be garbage collected)
            self._active_model = None
            self._active_key = None
    
    def unload_all(self) -> None:
        """Выгрузить все модели из пула."""
        with self._pool_lock:
            self._unload_active_model()
    
    # === Active Model Access ===
    
    @property
    def active_model_key(self) -> Optional[str]:
        """Ключ текущей активной модели."""
        return self._active_key
    
    @property
    def active_model(self) -> Optional[ModelProvider]:
        """Текущая активная модель (или None)."""
        return self._active_model
    
    @property
    def has_active_model(self) -> bool:
        """Есть ли загруженная модель."""
        return self._active_model is not None
    
    # === Availability Cache with Failure Backoff ===
    
    def is_model_available(self, key: str) -> bool:
        """
        Проверить доступность модели (с кэшированием и failure backoff).
        
        Args:
            key: Ключ модели
            
        Returns:
            True если модель может быть загружена
        """
        now = time.time()
        
        # Check failure backoff
        if key in self._failure_cache:
            backoff_until = self._failure_cache.get(key, 0)
            if now < backoff_until:
                # Model is in backoff period
                return False
        
        # Check cache
        if key in self._availability_cache:
            if now - self._last_cache_update < self._cache_ttl_seconds:
                return self._availability_cache[key]
        
        # Check if config exists
        available = key in self._model_configs
        
        # Update cache
        self._availability_cache[key] = available
        self._last_cache_update = now
        
        return available
    
    def record_failure(self, key: str) -> None:
        """
        Записать неудачную попытку и применить backoff.
        
        1 ошибка → 30s backoff
        3 ошибки → 5 min backoff
        
        Args:
            key: Ключ модели
        """
        if key not in self._metrics:
            return
        
        metrics = self._metrics[key]
        error_count = metrics.failed_requests + 1
        
        # Calculate backoff
        if error_count >= 3:
            backoff_seconds = 300  # 5 minutes
        elif error_count >= 1:
            backoff_seconds = 30  # 30 seconds
        else:
            backoff_seconds = 0
        
        # Apply backoff
        if backoff_seconds > 0:
            self._failure_cache[key] = time.time() + backoff_seconds
            print(f"ModelPool: Model '{key}' entered backoff for {backoff_seconds}s (errors: {error_count})")
    
    def clear_failure_backoff(self, key: str) -> None:
        """Очистить backoff для модели после успешного запроса."""
        if key in self._failure_cache:
            del self._failure_cache[key]
    
    def refresh_availability_cache(self) -> None:
        """Обновить кэш доступности."""
        with self._pool_lock:
            for key in self._model_configs:
                # For lazy loading, check if model can be loaded
                # (config exists and not currently loading)
                self._availability_cache[key] = (
                    key in self._model_configs and 
                    (self._active_key != key or self._active_model is not None)
                )
            self._last_cache_update = time.time()
    
    # === Metrics ===
    
    def get_metrics(self, key: str) -> Optional[ModelMetrics]:
        """Получить метрики модели."""
        return self._metrics.get(key)
    
    def get_all_metrics(self) -> dict[str, ModelMetrics]:
        """Получить все метрики."""
        return dict(self._metrics)
    
    def record_request(self, key: str, latency_ms: float, tokens: int, success: bool) -> None:
        """Записать результат запроса в метрики."""
        if key in self._metrics:
            self._metrics[key].record_request(latency_ms, tokens, success)
    
    # === Status ===
    
    def set_warm_model(self, key: str) -> None:
        """
        Установить модель для предзагрузки (warm model).
        
        Эта модель будет загружена при старте для быстрого первого отклика.
        
        Args:
            key: Ключ модели
        """
        with self._pool_lock:
            if key in self._model_configs:
                self._warm_model_key = key
                print(f"ModelPool: Warm model set to '{key}'")
            else:
                print(f"ModelPool: Cannot set warm model - key '{key}' not found")
    
    def get_warm_model(self) -> Optional[str]:
        """Получить ключ warm модели."""
        return self._warm_model_key
    
    def warm_up(self) -> bool:
        """
        Предзагрузить warm model для быстрого первого отклика.
        
        Returns:
            True если warm model успешно загружена
        """
        if self._warm_model_key:
            print(f"ModelPool: Warming up model '{self._warm_model_key}'...")
            model = self.get_model(self._warm_model_key)
            return model is not None
        return False
    
    def get_status(self) -> dict:
        """Получить статус пула."""
        return {
            "active_model": self._active_key,
            "max_loaded": self._max_loaded,
            "registered_models": list(self._model_configs.keys()),
            "metrics": {
                key: {
                    "avg_latency_ms": m.avg_latency_ms,
                    "total_requests": m.total_requests,
                    "success_rate": m.success_rate,
                    "last_load_time_ms": m.last_load_time_ms,
                }
                for key, m in self._metrics.items()
            }
        }
    
    @property
    def is_ready(self) -> bool:
        """Пул готов к работе."""
        return len(self._model_configs) > 0


# === Global ModelPool Instance ===

_model_pool: Optional[ModelPool] = None


def get_model_pool() -> ModelPool:
    """Получить глобальный инстанс ModelPool."""
    global _model_pool
    if _model_pool is None:
        _model_pool = ModelPool(max_loaded=1)  # 8GB VRAM constraint
    return _model_pool


class ProviderManager:
    """
    Менеджер всех LLM провайдеров.
    
    Responsibilities:
    - Создание и инициализация провайдеров при старте
    - Хранение реестра всех моделей
    - Выбор лучшего доступного провайдера
    - Fallback при недоступности основного
    - Health checks
    """
    
    _instance: Optional['ProviderManager'] = None
    _lock = threading.Lock()
    
    def __new__(cls) -> 'ProviderManager':
        """Singleton pattern."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self) -> None:
        if self._initialized:
            return
            
        self._providers: dict[str, ModelProvider] = {}
        self._providers_lock = threading.RLock()
        self._initialized = True
        self._startup_complete = False
    
    # === Registry Management ===
    
    def register_provider(
        self,
        key: str,
        name: str,
        provider: LlmProvider,
        provider_type: ProviderType,
        path: str,
        endpoint: Optional[str] = None,
        **kwargs,
    ) -> ModelProvider:
        """
        Зарегистрировать новый провайдер.
        
        Args:
            key: Уникальный ключ модели
            name: Человеческое название
            provider: Инстанс провайдера
            provider_type: Тип провайдера
            path: Путь к файлу модели
            endpoint: URL для API провайдеров
            **kwargs: Дополнительные параметры
            
        Returns:
            Зарегистрированный ModelProvider
        """
        with self._providers_lock:
            model_provider = ModelProvider(
                key=key,
                name=name,
                provider=provider,
                provider_type=provider_type,
                path=path,
                endpoint=endpoint,
                **kwargs,
            )
            self._providers[key] = model_provider
            return model_provider
    
    def get_provider(self, key: str) -> Optional[ModelProvider]:
        """Получить провайдер по ключу."""
        return self._providers.get(key)
    
    def get_all_providers(self) -> dict[str, ModelProvider]:
        """Получить все провайдеры."""
        return dict(self._providers)
    
    def list_available(self) -> list[str]:
        """Список доступных провайдеров."""
        return [k for k, p in self._providers.items() if p.is_available()]
    
    # === Initialization ===
    
    def initialize_all(self) -> dict[str, bool]:
        """
        Инициализировать все провайдеры при старте системы.
        
        Returns:
            Dict с результатами инициализации
        """
        results = {}
        
        # Инициализируем все модели из конфигурации
        for key, model_config in settings.available_models.items():
            try:
                self._create_and_register_provider(key, model_config)
                results[key] = True
            except Exception as e:
                print(f"Failed to initialize provider {key}: {e}")
                results[key] = False
        
        self._startup_complete = True
        return results
    
    def _create_and_register_provider(
        self,
        key: str,
        model_config,
    ) -> ModelProvider:
        """Создать и зарегистрировать провайдер для модели."""
        from app.services.llm.factory import ProviderFactory
        
        provider_type = ProviderType.LLAMA_CPP  # Default for now
        
        # Создаём провайдер
        provider = ProviderFactory.create(
            provider_type=provider_type,
            model_path=model_config.path,
        )
        
        # Регистрируем
        return self.register_provider(
            key=key,
            name=model_config.display_name,
            provider=provider,
            provider_type=provider_type,
            path=model_config.path,
            context_size=model_config.context_size,
            vram_mb=model_config.vram_mb,
            temperature=model_config.temperature,
        )
    
    # === Selection & Routing ===
    
    def get_provider_for_capability(
        self,
        capability: str,
        preferred_keys: list[str] | None = None,
    ) -> Optional[ModelProvider]:
        """
        Получить лучший провайдер для указанной capability.
        
        Args:
            capability: Требуемая возможность
            preferred_keys: Предпочтительные ключи моделей
            
        Returns:
            Лучший доступный ModelProvider или None
        """
        with self._providers_lock:
            # 1. Try preferred keys first
            if preferred_keys:
                for key in preferred_keys:
                    provider = self._providers.get(key)
                    if provider and provider.is_available():
                        provider.mark_used()
                        return provider
            
            # 2. Find any available
            for key, provider in self._providers.items():
                if provider.is_available():
                    provider.mark_used()
                    return provider
            
            return None
    
    def get_any_available(self) -> Optional[ModelProvider]:
        """Получить любой доступный провайдер (fallback)."""
        with self._providers_lock:
            for key, provider in self._providers.items():
                if provider.is_available():
                    provider.mark_used()
                    return provider
            return None
    
    # === Health & Maintenance ===
    
    def health_check(self) -> dict[str, dict]:
        """
        Проверить здоровье всех провайдеров.
        
        Returns:
            Dict с статусами всех провайдеров
        """
        results = {}
        
        for key, provider in self._providers.items():
            try:
                is_available = provider.provider.is_available()
                provider.status = ProviderStatus.READY if is_available else ProviderStatus.ERROR
                
                results[key] = {
                    "status": provider.status.value,
                    "available": is_available,
                    "error_count": provider.error_count,
                    "last_used": provider.last_used,
                }
            except Exception as e:
                provider.status = ProviderStatus.ERROR
                results[key] = {
                    "status": ProviderStatus.ERROR.value,
                    "available": False,
                    "error": str(e),
                }
        
        return results
    
    def check_and_recover(self) -> list[str]:
        """
        Проверить и восстановить упавшие провайдеры.
        
        Returns:
            List восстановленных ключей
        """
        recovered = []
        
        for key, provider in self._providers.items():
            if provider.status == ProviderStatus.ERROR:
                try:
                    if provider.provider.is_available():
                        provider.reset_errors()
                        provider.status = ProviderStatus.READY
                        recovered.append(key)
                except Exception:
                    pass
        
        return recovered
    
    # === Legacy Compatibility ===
    
    def get_default_provider(self) -> Optional[LlmProvider]:
        """Получить провайдер по умолчанию (для совместимости)."""
        # Get first available or any registered
        for key, provider in self._providers.items():
            if provider.is_available():
                return provider.provider
        
        # Fallback to first registered
        if self._providers:
            return next(iter(self._providers.values())).provider
        
        return None
    
    @property
    def is_ready(self) -> bool:
        """Проверить готовность системы."""
        return self._startup_complete and len(self.list_available()) > 0


# === Global Instance ===

_provider_manager: Optional[ProviderManager] = None


def get_provider_manager() -> ProviderManager:
    """Получить глобальный инстанс ProviderManager."""
    global _provider_manager
    if _provider_manager is None:
        _provider_manager = ProviderManager()
    return _provider_manager


def initialize_providers() -> dict[str, bool]:
    """Инициализировать все провайдеры при старте приложения."""
    manager = get_provider_manager()
    return manager.initialize_all()


def initialize_model_pool(warm_model_key: Optional[str] = None) -> dict[str, bool]:
    """
    Инициализировать ModelPool с конфигурациями моделей.
    
    Регистрирует все модели из конфигурации, но НЕ загружает их в VRAM.
    Загрузка происходит лениво при первом запросе.
    
    Args:
        warm_model_key: Ключ модели для предзагрузки (опционально)
        
    Returns:
        Dict с результатами регистрации моделей
    """
    pool = get_model_pool()
    results = {}
    
    # Register all models from settings
    for key, model_config in settings.available_models.items():
        try:
            # Create ModelConfig for pool (without provider)
            config = ModelConfig(
                key=key,
                name=model_config.display_name,
                provider_type=ProviderType.LLAMA_CPP,
                path=model_config.path,
                context_size=model_config.context_size,
                temperature=model_config.temperature,
                vram_mb=model_config.vram_mb,
            )
            pool.register_model_config(config)
            results[key] = True
            print(f"ModelPool: Registered model config '{key}'")
        except Exception as e:
            print(f"ModelPool: Failed to register model '{key}': {e}")
            results[key] = False
    
    # Set warm model if specified
    if warm_model_key:
        pool.set_warm_model(warm_model_key)
    
    print(f"ModelPool: Initialized with {len(results)} models (warm={warm_model_key})")
    return results


def get_pool_manager() -> tuple[ModelPool, ProviderManager]:
    """
    Получить и ModelPool, и ProviderManager.
    
    Returns:
        Tuple (ModelPool, ProviderManager)
    """
    return get_model_pool(), get_provider_manager()

