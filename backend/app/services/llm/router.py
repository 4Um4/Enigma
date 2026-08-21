from __future__ import annotations

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


import asyncio
import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from app.services.logging_tools import jsonl_log

logger = logging.getLogger(__name__)
# Корневой логгер для критической телеметрии, чтобы обойти фильтрацию уровней дочерних логгеров
_root_logger = logging.getLogger()

from app.core.config import settings
from app.services.llm.provider import GenerationParams, LlmProvider, ProviderType


class Capability(str, Enum):
    """Возможности/задачи для LLM моделей."""

    # Narration & Story
    NARRATIVE = "narrative"  # DM storytelling
    DIALOGUE = "dialogue"  # NPC conversations
    DIALOGUE_GENERATION = "dialogue_generation"

    # Reasoning
    RULES_REASONING = "rules_reasoning"  # D&D rules
    WORLD_SIMULATION = "world_simulation"  # World events
    STRATEGY = "strategy"  # Combat tactics

    # Memory & Processing
    MEMORY_SUMMARIZATION = "memory_summarization"
    FACT_EXTRACTION = "fact_extraction"
    RAG_RETRIEVAL = "rag_retrieval"

    # General
    GENERAL = "general"  # Default/general purpose
    FAST = "fast"  # Quick responses


@dataclass
class ModelConfig:
    """Конфигурация модели для маршрутизации."""

    key: str  # Уникальный ключ модели
    name: str  # Человеческое название
    provider_type: ProviderType  # Тип провайдера
    path: str  # Путь к файлу модели

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
    # Читаем provider_type из settings — позволяет переключить на mock без правки кода
    _qwen_cfg = settings.available_models.get("qwen_7b")
    _qwen_pt = (
        ProviderType(getattr(_qwen_cfg, "provider_type", "llama_cpp"))
        if _qwen_cfg
        else ProviderType.LLAMA_CPP
    )
    return {
        "qwen_7b": ModelConfig(
            key="qwen_7b",
            name="qwen_7b",
            provider_type=_qwen_pt,
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
    "dialogue_extractor": Capability.MEMORY_SUMMARIZATION, # BUG-DLG-011 FIX
    "general": Capability.GENERAL,
}


# Mapping: capability → model key (единственная модель)
CAPABILITY_MODEL_PREFERENCES: dict[Capability, list[str]] = {
    Capability.NARRATIVE: ["qwen_7b"],
    Capability.DIALOGUE: ["qwen_7b"],
    Capability.DIALOGUE_GENERATION: ["qwen_7b"],
    Capability.WORLD_SIMULATION: ["qwen_7b"],
    Capability.RULES_REASONING: ["qwen_7b"],
    Capability.MEMORY_SUMMARIZATION: ["qwen_7b"],
    Capability.FACT_EXTRACTION: ["qwen_7b"],
    Capability.STRATEGY: ["qwen_7b"],
    Capability.FAST: ["qwen_7b"],
    Capability.GENERAL: ["qwen_7b"],
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

    _instance: Optional["ModelRouter"] = None

    def __new__(cls) -> "ModelRouter":
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
        self._model_pool = None  # Lazy initialization для ModelPool
        self._current_model_key = None  # Текущая активная модель (для legacy-методов)
        self._capability_map = DEFAULT_AGENT_CAPABILITY_MAP.copy()
        self._lazy_loading = True

        # Защита VRAM. Только 1 запрос обрабатывается одновременно.
        # Критично для локальных 7B-13B моделей на 16GB VRAM.
        # Ленивая инициализация — Semaphore привязан к event loop,
        # а __init__ может вызываться в другом контексте (стартап vs запрос).
        self._vram_semaphore: asyncio.Semaphore | None = None

        # Threading lock для worker threads — исключает конкурентные LLM вызовы
        # (TELEGRAPH thread + player action thread → один из них skip)
        self._worker_lock = threading.Lock()
        # Флаг активного запроса — для abort при зависании
        self._request_in_progress = False
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

        # === ЛОГИРОВАНИЕ ПРОМПТА ДЛЯ ОТЛАДКИ ===
        _prompt_preview = (prompt[:500] + "...") if len(prompt) > 500 else prompt
        _sys_preview = (
            (system_prompt[:200] + "...")
            if system_prompt and len(system_prompt) > 200
            else system_prompt
        )
        jsonl_log(
            {
                "level": "INFO",
                "agent": "llm_input",
                "capability": str(capability_obj),
                "prompt_preview": _prompt_preview,
                "system_prompt": _sys_preview or "",
            }
        )

        # === ЗАЩИТА VRAM ===
        # Ленивое создание Semaphore в текущем event loop
        if self._vram_semaphore is None:
            self._vram_semaphore = asyncio.Semaphore(1)
        async with self._vram_semaphore:
            # Логируем вход в критическую секцию
            logger.info(
                f"ModelRouter: Acquired VRAM semaphore for capability={capability_obj}"
            )

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
                logger.debug(
                    f"ModelRouter: Released VRAM semaphore for {capability_obj}"
                )

    def _abort_generation(self) -> None:
        """Прервать зависшую генерацию на llama-server."""
        try:
            pool = self._get_model_pool()
            if pool._active_model:
                pool._active_model.provider.abort_generation()
                logger.debug(f"[R4A_ABORT] sent /abort to {pool.active_model_key}")
        except Exception as e:
            logger.debug(f"[R4A_ABORT] failed: {e}")

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
        _root_logger.info(f"[R4A_POOL] active_model={pool.active_model_key}")

        # Try preferred keys in order
        for model_key in preferred_keys:
            if pool.is_model_available(model_key):
                # Get model (will load if not loaded)
                start_time = time.time()
                model_provider = pool.get_model(model_key)

                if model_provider and model_provider.is_available():
                    try:
                        # Execute request
                        _root_logger.info(
                            f"[R4A_POOL] calling complete() on {model_key}..."
                        )
                        result = model_provider.provider.complete(
                            prompt, params, system_prompt
                        )
                        _root_logger.info(
                            f"[R4A_POOL] complete() returned {len(result)} chars in {(time.time() - start_time) * 1000:.0f}ms"
                        )

                        # Record metrics
                        latency_ms = (time.time() - start_time) * 1000
                        tokens = len(result.split())  # Rough estimate
                        # record_request — опциональная метрика, не критична
                        if hasattr(pool, "record_request"):
                            pool.record_request(
                                model_key, latency_ms, tokens, success=True
                            )

                        return result
                    except Exception as e:
                        import traceback

                        latency_ms = (time.time() - start_time) * 1000
                        if hasattr(pool, "record_request"):
                            pool.record_request(model_key, latency_ms, 0, success=False)
                        logger.error(f"ModelRouter: Model {model_key} failed: {e}")
                        logger.error(f"[ROUTER_TRACEBACK]\n{traceback.format_exc()}")
                        continue

        # Fallback: try any available model from pool
        pool_configs = pool.list_model_configs()
        for model_key in pool_configs.keys():
            # Не повторяем запрос к той же модели, которая только что упала.
            # Retry должен быть реализован явно как retry-политика, а не скрыт в fallback.
            if pool.active_model_key == model_key:
                continue

            model_provider = pool.get_model(model_key)
            if model_provider and model_provider.is_available():
                try:
                    return model_provider.provider.complete(
                        prompt, params, system_prompt
                    )
                except Exception as e:
                    logger.warning(f"Fallback {model_key} failed: {e}")
                    continue
            else:
                # S129 FIX: Безопасное логирование без вложенных вызовов is_available()
                _status = model_provider.status if model_provider else "None"
                logger.error(f"ModelRouter: Fallback Model {model_key} not available. Status: {_status}")

        # Все модели пула недоступны — не создаём новые провайдеры (это порождало
        # дублирующие llama-cli процессы на занятую VRAM)
        raise RuntimeError(f"Все модели пула недоступны для capability={capability}")

    def _normalize_capability(self, capability: Capability | str) -> Capability:
        """Convert string to Capability enum."""
        if isinstance(capability, str):
            try:
                return Capability(capability)
            except ValueError as e:
                logger.debug(f"Invalid Capability, returning GENERAL: {e}")
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
            logger.debug(f"Failed to create provider for {model_key}: {e}")
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
            (key, config)
            for key, config in self._registry.items()
            if capability in config.capabilities
        ]

        if suitable_models:
            return suitable_models[0][0]

        # Fallback: general purpose
        suitable_models = [
            (key, config)
            for key, config in self._registry.items()
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
        
        # Подсистема 2: LLM Cache для Replay (Этап 2.3)
        import hashlib
        from app.core.config import settings
        _prompt_hash = hashlib.sha256(prompt.encode('utf-8')).hexdigest()
        
        if settings.replay_playback:
            # Режим воспроизведения: читаем из кэша, не дёргаем LLM
            from app.services.replay.replay_store import ReplayStore
            _store = getattr(self, "_replay_store", None)
            if _store:
                _cached = _store.get_llm_call(agent_name, _prompt_hash)
                if _cached and _cached.get("response"):
                    logger.debug(f"[LLM_CACHE] HIT: agent={agent_name} hash={_prompt_hash[:8]}")
                    return _cached["response"]
                # Cache miss в playback mode — это критическая ошибка (нарушение детерминизма)
                logger.error(f"[LLM_CACHE] MISS in playback mode! agent={agent_name} hash={_prompt_hash[:8]}")
                # Возвращаем пустую строку, чтобы не крашить игру, но это нарушит replay
                
        # Worker thread (to_thread): прямой синхронный вызов без semaphore
        # Semaphore привязан к main loop — в новом loop он мёртв
        if threading.current_thread() is not threading.main_thread():
            capability_obj = self._capability_map.get(agent_name, Capability.GENERAL)
            preferred_keys = self.get_capability_preferences(capability_obj)
            # Если предыдущий запрос завис — abort перед новым и ждём освобождения
            if self._request_in_progress:
                _root_logger.warning("[R4A_WORKER] aborting stuck request...")
                self._abort_generation()
                # Ждём пока llama-server обработает abort (1с) + закрыет HTTP
                time.sleep(1.0)
                # Если всё ещё завис — повторяем abort
                if self._request_in_progress:
                    self._abort_generation()
                    time.sleep(1.0)
            self._request_in_progress = True
            try:
                _root_logger.info(
                    f"[R4A_WORKER] direct sync call, capability={capability_obj}"
                )
                _result = self._request_via_pool(
                    capability_obj,
                    preferred_keys=preferred_keys,
                    prompt=prompt,
                    params=params,
                    system_prompt=system_prompt,
                )
                _root_logger.info(
                    f"[R4A_WORKER] returned {len(_result) if _result else 0} chars"
                )
                return _result
            except Exception as e:
                _root_logger.error(f"[R4A_WORKER] exception: {e}")
                # NEW-DLG-004 FIX: Пробрасываем исключение, чтобы вызывающий код знал о падении LLM, а не получал пустую строку.
                raise
            finally:
                self._request_in_progress = False
                
        _result = ""
        if settings.replay_playback:
            # В режиме playback мы уже вернули ответ из кэша выше, если он был.
            # Если мы здесь — cache miss, возвращаем пустую строку.
            _result = ""
        else:
            coro = self.request(capability, prompt, params, system_prompt)
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError as e:
                logger.debug(f"No running loop, starting new one: {e}")
                _result = asyncio.run(coro)
            else:
                future = asyncio.run_coroutine_threadsafe(coro, loop)
                _result = future.result(timeout=60)
                
        # Запись в кэш (если режим записи)
        if settings.replay_record:
            from app.services.replay.replay_store import ReplayStore
            _store = getattr(self, "_replay_store", None)
            if _store:
                _tick_id = getattr(self, "_current_tick_id", 0)
                _store.record_llm_call(
                    session_id=getattr(self, "_current_session_id", "unknown"),
                    tick_id=_tick_id,
                    agent_name=agent_name,
                    prompt=prompt,
                    response=_result,
                    model_name=self.get_model_for_agent(agent_name),
                    latency_ms=0
                )
                
        return _result
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError as e:
            logger.debug(f"No running loop, starting new one: {e}")
            # Нет запущенного цикла — запускаем свой
            return asyncio.run(coro)
        else:
            # Есть запущенный цикл — thread-safe запуск
            future = asyncio.run_coroutine_threadsafe(coro, loop)
            return future.result(timeout=60)

    # --- Streaming Observability (ADR-147) ---
    # Router — единственный владелец observability LLM-вызовов.
    # Streaming проходит ЧЕРЕЗ Router, не в обход.

    def notify_stream_start(
        self, agent_name: str, capability: str | Capability
    ) -> dict:
        """Уведомляет Router о начале streaming LLM-вызова. Эмитит [R4A_STREAM] маркер для CDS."""
        cap = self._normalize_capability(capability)
        _root_logger.info(
            f"[R4A_STREAM] calling stream_tokens(), agent={agent_name}, capability={cap.value}"
        )
        return {
            "start_time": time.time(),
            "agent_name": agent_name,
            "capability": cap.value,
        }

    def notify_stream_end(self, ctx: dict, chars_produced: int) -> None:
        """Уведомляет Router о завершении streaming LLM-вызова. Эмитит [R4A_STREAM] маркер для CDS."""
        elapsed_ms = (time.time() - ctx["start_time"]) * 1000
        _root_logger.info(
            f"[R4A_STREAM] stream complete, {chars_produced} chars in {elapsed_ms:.0f}ms"
        )

    def set_capability_for_agent(
        self, agent_name: str, capability: Capability | str
    ) -> None:
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
        if hasattr(selection, "model_name"):
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

    logger.debug(f"Router initialized. ModelPool: {pool_results}")
    logger.debug("Lazy loading enabled: only one model in VRAM at a time")
