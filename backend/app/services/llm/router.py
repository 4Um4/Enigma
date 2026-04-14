# backend\app\services\llm\router.py
"""
Model Router - Capability-based LLM Routing with Lazy Loading

This is the core component that automatically routes agent requests
to appropriate models based on capability requirements.

Architecture:
    Agents → ModelRouter → ModelPool (lazy loading) → LlmProvider

Features:
- Lazy loading: only one model in VRAM at a time
- Capability-based routing
- Automatic model switching
- Metrics collection
"""

from __future__ import annotations

import asyncio
from enum import Enum

import time
from dataclasses import dataclass, field

from typing import Optional

import logging
from app.core.config import settings

logger = logging.getLogger(__name__)
from app.services.llm.provider import LlmProvider, GenerationParams, ProviderType


class Capability(str, Enum):
    """Возможности/задачи для LLM моделей."""
    # Narration & Story
    NARRATIVE = "narrative"           # DM storytelling
    DIALOGUE = "dialogue"             # NPC conversations
    DIALOGUE_GENERATION = "dialogue_generation"
    
    # Reasoning
    RULES_REASONING = "rules_reasoning"  # D&D rules
    WORLD_SIMULATION = "world_simulation" # World events
    STRATEGY = "strategy"             # Combat tactics
    
    # Memory & Processing
    MEMORY_SUMMARIZATION = "memory_summarization"
    FACT_EXTRACTION = "fact_extraction"
    RAG_RETRIEVAL = "rag_retrieval"
    
    # General
    GENERAL = "general"               # Default/general purpose
    FAST = "fast"                      # Quick responses


@dataclass
class ModelConfig:
    """Конфигурация модели для маршрутизации."""
    key: str                           # Уникальный ключ модели
    name: str                          # Человеческое название
    provider_type: ProviderType        # Тип провайдера
    path: str                          # Путь к файлу модели
    
    # Capabilities
    capabilities: list[Capability] = field(default_factory=list)
    
    # Parameters
    context_size: int = 4096
    temperature: float = 0.7
    top_p: float = 0.9
    repeat_penalty: float = 1.1
    n_keep: int = 512
    
    # Resource
    vram_mb: int = 4000
    
    # Endpoint (for API providers)
    endpoint: Optional[str] = None
    api_key: Optional[str] = None


# Registry всех доступных моделей - инициализируется из конфигурации
MODEL_REGISTRY: dict[str, ModelConfig] = {}


def _init_registry() -> dict[str, ModelConfig]:
    """Единственная модель проекта."""
    return {
        "qwen_7b": ModelConfig(
            key="qwen_7b",
            name="qwen_7b",
            provider_type=ProviderType.LLAMA_CPP,
            path=settings.model_qwen_7b_path,
            capabilities=[
                Capability.NARRATIVE,
                Capability.DIALOGUE,
                Capability.DIALOGUE_GENERATION,
                Capability.RULES_REASONING,
                Capability.WORLD_SIMULATION,
                Capability.MEMORY_SUMMARIZATION,
                Capability.FACT_EXTRACTION,
                Capability.STRATEGY,
                Capability.GENERAL,
                Capability.FAST,
            ],
            vram_mb=5000,
            context_size=8192,
            temperature=0.9,
            repeat_penalty=1.12,
        ),
    }


# Инициализируем при импорте
MODEL_REGISTRY = _init_registry()


# Default mapping: agent → capability
DEFAULT_AGENT_CAPABILITY_MAP: dict[str, Capability] = {
    "dm": Capability.NARRATIVE,
    "world": Capability.WORLD_SIMULATION,
    "npc": Capability.DIALOGUE,
    "rules": Capability.RULES_REASONING,
    "memory": Capability.MEMORY_SUMMARIZATION,
    "general": Capability.GENERAL,
}


# Mapping: capability → model key (единственная модель)
CAPABILITY_MODEL_PREFERENCES: dict[Capability, list[str]] = {
    Capability.NARRATIVE:             ["qwen_7b"],
    Capability.DIALOGUE:              ["qwen_7b"],
    Capability.DIALOGUE_GENERATION:   ["qwen_7b"],
    Capability.WORLD_SIMULATION:      ["qwen_7b"],
    Capability.RULES_REASONING:       ["qwen_7b"],
    Capability.MEMORY_SUMMARIZATION:  ["qwen_7b"],
    Capability.FACT_EXTRACTION:       ["qwen_7b"],
    Capability.STRATEGY:              ["qwen_7b"],
    Capability.FAST:                  ["qwen_7b"],
    Capability.GENERAL:               ["qwen_7b"],
}


class ModelRouter:
    """
    Маршрутизатор LLM запросов на основе возможностей.
    
    Key features:
    - Automatic model selection by capability
    - Uses ModelPool for lazy loading (8GB VRAM constraint)
    - Fallback routing when preferred model unavailable
    - Agent-agnostic (agents request capability, not model)
    - Metrics collection for performance tracking
    """
    
    _instance: Optional['ModelRouter'] = None
    
    def __new__(cls) -> 'ModelRouter':
        """Singleton pattern for global router access."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self) -> None:
        if self._initialized:
            return
            
        # Инициализация реестра и зависимостей
        self._registry: dict[str, ModelConfig] = _init_registry()
        self._pool: dict[str, ModelConfig] = _init_registry()
        self._providers: dict[str, Any] = {}
        self._provider_manager = None
        self._model_pool = None      # Lazy initialization для ModelPool
        self._current_model_key = None # Текущая активная модель (для legacy-методов)
        self._capability_map = DEFAULT_AGENT_CAPABILITY_MAP.copy()
        self._lazy_loading = True
        
        # Защита VRAM. Только 1 запрос обрабатывается одновременно.
        # Критично для локальных 7B-13B моделей на 16GB VRAM.
        # Ленивая инициализация — Semaphore привязан к event loop,
        # а __init__ может вызываться в другом контексте (стартап vs запрос).
        self._vram_semaphore: asyncio.Semaphore | None = None
        
        self._initialized = True
    
    def _get_model_pool(self):
        """Lazy initialization of ModelPool."""
        if self._model_pool is None:
            from app.services.llm.provider_manager import get_model_pool
            self._model_pool = get_model_pool()
        return self._model_pool
    
    def _get_provider_manager(self):
        """Lazy initialization of ProviderManager (legacy)."""
        if self._provider_manager is None:
            from app.services.llm.provider_manager import get_provider_manager
            self._provider_manager = get_provider_manager()
        return self._provider_manager
    
    @property
    def model_pool(self):
        """Get the model pool."""
        return self._get_model_pool()
    
    @property
    def provider_manager(self):
        """Get the provider manager (legacy)."""
        return self._get_provider_manager()
    
    def set_lazy_loading(self, enabled: bool) -> None:
        """Включить/выключить ленивую загрузку."""
        self._use_lazy_loading = enabled
    
    # === Main Request Methods ===
    
    async def request(
        self,
        capability: Capability | str,
        prompt: str,
        params: GenerationParams | None = None,
        system_prompt: str | None = None,
    ) -> str:
        """
        Основной асинхронный запрос к LLM с жёсткой защитой VRAM.
        
        Семaphore(1) гарантирует, что в любой момент времени только ОДИН запрос
        обрабатывается моделью — критично для 7B–13B на 16 ГБ и меньше.
        """
        capability_obj = self._normalize_capability(capability)
        preferred_keys = self.get_capability_preferences(capability_obj)

        # === ЗАЩИТА VRAM ===
        # Ленивое создание Semaphore в текущем event loop
        if self._vram_semaphore is None:
            self._vram_semaphore = asyncio.Semaphore(1)
        async with self._vram_semaphore:
            # Логируем вход в критическую секцию
            logger.info(f"ModelRouter: Acquired VRAM semaphore for capability={capability_obj}")

            try:
                if self._lazy_loading:
                    return self._request_via_pool(
                        capability=capability_obj,
                        preferred_keys=preferred_keys,
                        prompt=prompt,
                        params=params,
                        system_prompt=system_prompt,
                    )
                else:
                    return await self._request_sync(
                        capability=capability_obj,
                        prompt=prompt,
                        params=params,
                        system_prompt=system_prompt,
                    )
            finally:
                logger.debug(f"ModelRouter: Released VRAM semaphore for {capability_obj}")
    
    def _request_via_pool(
        self,
        capability: Capability,
        preferred_keys: list[str],
        prompt: str,
        params: GenerationParams | None,
        system_prompt: str | None,
    ) -> str:
        """
        Отправить запрос через ModelPool (ленивая загрузка).
        
        Args:
            capability: Требуемая возможность
            preferred_keys: Предпочтительные ключи моделей
            prompt: Пользовательский промпт
            params: Параметры генерации
            system_prompt: Системный промпт
            
        Returns:
            Ответ от LLM
        """
        pool = self._get_model_pool()
        
        # Try preferred keys in order
        for model_key in preferred_keys:
            if pool.is_model_available(model_key):
                # Get model (will load if not loaded)
                start_time = time.time()
                model_provider = pool.get_model(model_key)
                
                if model_provider and model_provider.is_available():
                    try:
                        # Execute request
                        result = model_provider.provider.complete(prompt, params, system_prompt)
                        
                        # Record metrics
                        latency_ms = (time.time() - start_time) * 1000
                        tokens = len(result.split())  # Rough estimate
                        # record_request — опциональная метрика, не критична
                        if hasattr(pool, 'record_request'):
                            pool.record_request(model_key, latency_ms, tokens, success=True)
                        
                        return result
                    except Exception as e:
                        # Record failure
                        latency_ms = (time.time() - start_time) * 1000
                        if hasattr(pool, 'record_request'):
                            pool.record_request(model_key, latency_ms, 0, success=False)
                        print(f"ModelRouter: Model {model_key} failed: {e}")
                        continue
        
        # Fallback: try any available model from pool
        pool_configs = pool.list_model_configs()
        for model_key in pool_configs.keys():
            if pool.active_model_key != model_key:  # Don't retry same model
                model_provider = pool.get_model(model_key)
                if model_provider and model_provider.is_available():
                    try:
                        return model_provider.provider.complete(prompt, params, system_prompt)
                    except Exception:
                        continue
        
        # Last resort: legacy fallback
        print("ModelRouter: Falling back to legacy mode")
        return self._request_sync(capability, prompt, params, system_prompt)
    
    def _normalize_capability(self, capability: Capability | str) -> Capability:
        """Convert string to Capability enum."""
        if isinstance(capability, str):
            try:
                return Capability(capability)
            except ValueError:
                return Capability.GENERAL
        return capability
    
    def _request_sync(
        self,
        capability: Capability,
        prompt: str,
        params: GenerationParams | None,
        system_prompt: str | None,
    ) -> str:
        """Legacy single-provider request (fallback)."""
        model_key = self.select_model(capability)
        model_config = self._registry.get(model_key)
        
        if not model_config:
            model_key = self._get_fallback_model()
            model_config = self._registry.get(model_key)
        
        if not model_config:
            raise RuntimeError("No available models in registry")
        
        # Get or create provider
        provider = self._get_or_create_provider(model_key, model_config)
        
        if provider:
            return provider.complete(prompt, params, system_prompt)
        
        raise RuntimeError(f"No provider available for capability: {capability}")
    
    def _get_or_create_provider(self, model_key: str, model_config: ModelConfig):
        """Get or create a provider for the model."""
        from app.services.llm.factory import ProviderFactory
        
        try:
            return ProviderFactory.create(
                provider_type=model_config.provider_type,
                model_path=model_config.path,
            )
        except Exception as e:
            print(f"Failed to create provider for {model_key}: {e}")
            return None
    
    def select_model(self, capability: Capability) -> str:
        """
        Выбрать лучшую модель для требуемой возможности.
        
        Args:
            capability: Требуемая возможность
            
        Returns:
            Ключ модели из реестра
        """
        # Check preferences first
        preferred_keys = CAPABILITY_MODEL_PREFERENCES.get(capability, [])
        
        for key in preferred_keys:
            if key in self._registry:
                config = self._registry[key]
                if capability in config.capabilities:
                    return key
        
        # Fallback: find any model with this capability
        suitable_models = [
            (key, config) for key, config in self._registry.items()
            if capability in config.capabilities
        ]
        
        if suitable_models:
            return suitable_models[0][0]
        
        # Fallback: general purpose
        suitable_models = [
            (key, config) for key, config in self._registry.items()
            if Capability.GENERAL in config.capabilities
        ]
        
        if suitable_models:
            return suitable_models[0][0]
        
        # Last resort: first model in registry
        return list(self._registry.keys())[0]
    
    def _get_fallback_model(self) -> str:
        """Получить резервную модель."""
        return "qwen_7b"

    
    # === Agent-friendly methods ===
    
    def request_for_agent(
        self,
        agent_name: str,
        prompt: str,
        params: GenerationParams | None = None,
        system_prompt: str | None = None,
    ) -> str:
        """
        Отправить запрос от имени агента.
        
        Автоматически определяет capability по имени агента.
        
        Args:
            agent_name: dm, npc, rules, world, memory
            prompt: Пользовательский промпт
            params: Параметры генерации
            system_prompt: Системный промпт
            
        Returns:
            Ответ от LLM
        """
        capability = self._capability_map.get(agent_name, Capability.GENERAL)
        coro = self.request(capability, prompt, params, system_prompt)
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                future = asyncio.run_coroutine_threadsafe(coro, loop)
                return future.result(timeout=60)
            else:
                return asyncio.run(coro)
        except Exception:
            return asyncio.run(coro)
    
    def set_capability_for_agent(self, agent_name: str, capability: Capability | str) -> None:
        """Установить маппинг агент → capability."""
        if isinstance(capability, str):
            capability = Capability(capability)
        self._capability_map[agent_name] = capability
    
    def get_model_for_agent(self, agent_name: str) -> str:
        """Получить ключ модели для агента."""
        capability = self._capability_map.get(agent_name, Capability.GENERAL)
        return self.select_model(capability)

    def get_provider(self, capability: Capability | str) -> LlmProvider | None:
        """
        Возвращает провайдер для capability.
        Используется для прямого стриминга в dm_agent.stream_narrate.
    
        ВАЖНО: Этот метод ЗАГРУЖАЕТ модель синхронно если её нет в VRAM.
        Для streaming-контекста где нельзя использовать async.
        """
        capability_obj = self._normalize_capability(capability)
        preferred_keys = CAPABILITY_MODEL_PREFERENCES.get(capability_obj, [])

        pool = self._get_model_pool()
        if pool is None:
            return None

        for model_key in preferred_keys:
            if pool.is_model_available(model_key):
                model_provider = pool.get_model(model_key)
                if model_provider and model_provider.is_available():
                    return model_provider.provider

        return None   
    
    def get_model_info(self, model_key: str) -> ModelConfig | None:
        """Получить конфигурацию модели."""
        return self._registry.get(model_key)
    
    def list_capabilities(self) -> dict[str, Capability]:
        """Список всех capability для агентов."""
        return dict(self._capability_map)
    
    def list_models(self) -> dict[str, ModelConfig]:
        """Список всех моделей в реестре."""
        return dict(self._registry)
    
    def get_capability_preferences(self, capability: Capability) -> list[str]:
        """Get preferred model keys for a capability."""
        return CAPABILITY_MODEL_PREFERENCES.get(capability, [])
    
    # === Legacy compatibility ===
    
    def switch(self, selection) -> None:
        """Legacy: ручное переключение модели."""
        if hasattr(selection, 'model_name'):
            self._current_model_key = selection.model_name
    
    def describe(self) -> str:
        """Legacy: описание текущей модели."""
        if self._current_model_key:
            config = self._registry.get(self._current_model_key)
            if config:
                return f"{config.provider_type.value}:{config.name}"
        return "model: not selected"


# Global singleton
_router: Optional[ModelRouter] = None


def get_router() -> ModelRouter:
    """Получить глобальный инстанс роутера."""
    global _router
    if _router is None:
        _router = ModelRouter()
    return _router


def initialize_router() -> None:
    """Инициализировать роутер и ModelPool при старте."""
    from app.services.llm.provider_manager import initialize_model_pool
    
    # Initialize ModelPool (registers configs, lazy loading)
    pool_results = initialize_model_pool()
    
    # Get router
    router = get_router()
    
    print(f"Router initialized. ModelPool: {pool_results}")
    print("Lazy loading enabled: only one model in VRAM at a time")
