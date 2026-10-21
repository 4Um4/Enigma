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
from typing import TYPE_CHECKING, Any, Optional, cast

from app.services.logging_tools import jsonl_log

logger = logging.getLogger(__name__)
# Корневой логгер для критической телеметрии, чтобы обойти фильтрацию уровней дочерних логгеров
_root_logger = logging.getLogger()

from app.core.config import settings
from app.services.llm.provider import (
    CAPABILITY_MODEL_PREFERENCES,
    Capability,
    GenerationParams,
    LlmProvider,
    ProviderType,
)

if TYPE_CHECKING:
    # Циклический импорт: provider_manager импортирует router — только для типов.
    from app.services.llm.provider_manager import ModelPool, ProviderManager


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
    _yandex_cfg = settings.available_models.get("yandexgpt_8b")
    _yandex_pt = (
        ProviderType(getattr(_yandex_cfg, "provider_type", "llama_cpp"))
        if _yandex_cfg
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
        "yandexgpt_8b": ModelConfig(
            key="yandexgpt_8b",
            name="yandexgpt_8b",
            provider_type=_yandex_pt,
            path=settings.model_yandexgpt_8b_path,
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
            vram_mb=6600,
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


# ── COV-2/D62: приоритетная очередь worker-ветки (LLM_RESILIENCE_V1) ──────
# Вердикты Мастера: canonical default; ambient назначается явно (только
# D8P-экстракция); FIFO среди canonical; ambient cap=8 + дедлайн 300с
# (контролируемый DROP с причиной); canonical-бюджет 90с (громкий отказ,
# никогда пустой успех); выполняющийся запрос не прерывается прибытием.
# Wall-time — ДВА НЕСМЕШИВАЕМЫХ свойства: (1) best-effort реальная отмена
# (/abort); (2) гарантированное владение слотом + защита от позднего
# результата (epoch). CALIBRATION-константы (не env): перевод в env — только
# вместе с записью flags.yaml (иначе C1-линтер RED).

_CANONICAL_QUEUE_TIMEOUT_SEC: float = 90.0   # бюджет ОЖИДАНИЯ слота (НЕ загрузка модели — та: model_load_timeout_sec)
_AMBIENT_QUEUE_DEADLINE_SEC: float = 300.0   # дедлайн фоновой задачи, действует ВО ВРЕМЯ ожидания
_AMBIENT_QUEUE_CAP: int = 8                  # максимум одновременно ожидающих ambient (сверх — DROP)
_WORKER_WALL_TIME_CEILING_SEC: float = 120.0 # потолок ВЫПОЛНЯЮЩЕГОСЯ вызова (3x30с retry + 1+2с sleeps + запас)
_ABORT_GRACE_SEC: float = 2.0                # ожидание эффекта /abort до форфейта (прецедент: sleep 1-2с старого пути)


def _llm_resilience_v1_enabled() -> bool:
    """Env-флаг LLM_RESILIENCE_V1 (default OFF = прежняя abort-механика).

    Call-time чтение. Устанавливать ДО первого запроса процесса: смена при
    живых вызовах смешивает пути владения слотом (старый _request_in_progress
    и новый epoch не видят друг друга)."""
    import os

    return os.environ.get("LLM_RESILIENCE_V1", "").strip().lower() in (
        "1", "true", "yes", "on",
    )


class LlmQueueOverflowError(RuntimeError):
    """D62: ambient-задача отброшена — очередь ожидающих ambient переполнена."""


class LlmQueueDeadlineError(RuntimeError):
    """D62: бюджет ожидания слота истёк (ambient-дедлайн или canonical-таймаут)."""


class _QueueWaiter:
    """Ожидающий слот: собственный Event — дедлайн действует во время ожидания
    (wait(remaining) + самоудаление dead-маркером); granted_epoch — защита от
    позднего результата (форфейт продвигает epoch владельца слота)."""

    __slots__ = ("rank", "seq", "event", "dead", "granted_epoch")

    def __init__(self, rank: int, seq: int) -> None:
        self.rank = rank  # 0 = canonical, 1 = ambient
        self.seq = seq
        self.event = threading.Event()
        self.dead = False
        self.granted_epoch = -1

    def __lt__(self, other: "_QueueWaiter") -> bool:
        return (self.rank, self.seq) < (other.rank, other.seq)


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
    _initialized: bool

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
        self._provider_manager: Optional["ProviderManager"] = None
        self._model_pool: Optional["ModelPool"] = None  # Lazy initialization для ModelPool
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

    def _get_model_pool(self) -> "ModelPool":
        """Lazy initialization of ModelPool."""
        if self._model_pool is None:
            from app.services.llm.provider_manager import get_model_pool

            self._model_pool = get_model_pool()
        return self._model_pool

    def _get_provider_manager(self) -> "ProviderManager":
        """Lazy initialization of ProviderManager (legacy)."""
        if self._provider_manager is None:
            from app.services.llm.provider_manager import get_provider_manager

            self._provider_manager = get_provider_manager()
        return self._provider_manager

    @property
    def model_pool(self) -> "ModelPool":
        """Get the model pool."""
        return self._get_model_pool()

    @property
    def provider_manager(self) -> "ProviderManager":
        """Get the provider manager (legacy)."""
        return self._get_provider_manager()

    def set_lazy_loading(self, enabled: bool) -> None:
        """Включить/выключить ленивую загрузку."""
        self._use_lazy_loading = enabled

    def set_replay_context(self, store: Any, session_id: str) -> None:
        """
        Подсистема 2: Инъекция ReplayStore для кэширования LLM-вызовов (Этап 2.3).
        Вызывается из GameLoop при старте сессии, если replay_mode != "off".
        """
        self._replay_store = store
        self._current_session_id = session_id
        self._current_tick_id = getattr(self, "_current_tick_id", 0)
        logger.info(f"[LLM_CACHE] Replay context bound. Session: {session_id}")

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
                    return self._request_sync(
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
        """Прервать зависшую генерацию на llama-server (H-10 FIX: безопасный вызов)."""
        try:
            pool = self._get_model_pool()
            _active_model = pool.active_model
            if _active_model and hasattr(_active_model.provider, "abort_generation"):
                _active_model.provider.abort_generation()
                logger.debug(f"[R4A_ABORT] sent /abort to {pool.active_model_key}")
        except Exception as e:
            logger.debug(f"[R4A_ABORT] failed: {e}")

    def _grant_next_locked(self) -> None:
        """COV-2/D62: выдать освободившийся слот лучшему живому ожидающему.

        Порядок: canonical раньше ambient; внутри класса — FIFO по прибытию
        (seq). Требует удержания _worker_lock. dead-ожидающие пропускаются:
        их дедлайн сработал во время ожидания, задача уже отброшена."""
        import heapq

        while self._waiters:
            _w = heapq.heappop(self._waiters)
            if _w.dead:
                continue
            self._slot_busy = True
            self._slot_epoch += 1
            _w.granted_epoch = self._slot_epoch
            _w.event.set()
            return

    def _wall_time_watchdog(self, my_epoch: int) -> None:
        """COV-2/D62: потолок выполняющегося вызова (Timer-поток; прецедент
        ADR-O-364 per-task-timeout).

        Слой 1 — best-effort реальная отмена: /abort llama-server (HTTP вне
        локов — цикл lock/abort замкнуться не может, lock всегда листовой).
        Слой 2 — гарантия владения: если отмена не подействовала за грейс,
        слот форфейтится лучшему ожидающему, epoch продвигается — поздний
        результат старого вызова будет сконвертирован в исключение, кэш не
        пишется, состояние нового владельца не затрагивается."""
        with self._worker_lock:
            if not self._slot_busy or self._slot_epoch != my_epoch:
                return  # вызов успел завершиться штатно (или уже осиротевший)
        _root_logger.warning(
            f"[R4A_WALLTIME] вызов epoch={my_epoch} превысил потолок — /abort"
        )
        self._abort_generation()
        time.sleep(_ABORT_GRACE_SEC)
        with self._worker_lock:
            if self._slot_busy and self._slot_epoch == my_epoch:
                _root_logger.error(
                    f"[R4A_WALLTIME] abort не подействовал — форфейт слота epoch={my_epoch}"
                )
                self._slot_epoch += 1  # осиротить выполняющийся вызов
                self._slot_busy = False
                self._grant_next_locked()

    def _worker_request_queued(
        self,
        agent_name: str,
        prompt: str,
        params: "GenerationParams | None",
        system_prompt: "str | None",
        priority: str,
        prompt_hash: str,
        worker_start: float,
    ) -> str:
        """COV-2/D62 (LLM_RESILIENCE_V1=ON): worker-вызов через приоритетную очередь.

        Слои: admission (ambient cap → контролируемый DROP) → ожидание
        (Event на каждого ждущего: дедлайн действует ВО ВРЕМЯ ожидания,
        canonical обходит ambient, FIFO внутри класса) → grant (epoch) →
        выполнение под wall-time watchdog → фиксация (поздний результат
        осиротевшего вызова = громкое исключение, не возврат) → release →
        grant-next. Сериализация модели: один слот = один вызов."""
        import heapq

        from app.core.config import settings

        rank = 0 if priority == "canonical" else 1

        waiter: "_QueueWaiter | None" = None
        _my_epoch = -1
        with self._worker_lock:
            # Ленивая инициализация состояния очереди: OFF-путь эти поля не
            # читает; __init__ не трогаем (прежний путь неприкосновенен).
            if not hasattr(self, "_slot_epoch"):
                self._slot_busy = False
                self._slot_epoch: int = 0
                self._waiters: "list[_QueueWaiter]" = []
                self._waiter_seq: int = 0
            if self._slot_busy:
                if rank == 1:
                    _live_ambient = sum(
                        1 for _w in self._waiters if not _w.dead and _w.rank == 1
                    )
                    if _live_ambient >= _AMBIENT_QUEUE_CAP:
                        _root_logger.warning(
                            f"[R4A_QUEUE] ambient DROP (overflow): agent={agent_name}"
                        )
                        raise LlmQueueOverflowError(
                            f"ambient queue overflow (cap={_AMBIENT_QUEUE_CAP}): {agent_name}"
                        )
                waiter = _QueueWaiter(rank, self._waiter_seq)
                self._waiter_seq += 1
                heapq.heappush(self._waiters, waiter)
            else:
                self._slot_busy = True
                self._slot_epoch += 1
                _my_epoch = self._slot_epoch

        if waiter is not None:
            _deadline = time.monotonic() + (
                _AMBIENT_QUEUE_DEADLINE_SEC if rank == 1
                else _CANONICAL_QUEUE_TIMEOUT_SEC
            )
            _granted = waiter.event.wait(timeout=max(0.0, _deadline - time.monotonic()))
            if not _granted:
                with self._worker_lock:
                    waiter.dead = True  # самоудаление: дедлайн сработал в ожидании
                    _granted = waiter.event.is_set()  # гонка выдачи <-> таймаута
            if not _granted:
                if rank == 1:
                    _root_logger.warning(
                        f"[R4A_QUEUE] ambient DROP (deadline): agent={agent_name}"
                    )
                    raise LlmQueueDeadlineError(
                        f"ambient queue deadline exceeded: {agent_name}"
                    )
                raise LlmQueueDeadlineError(
                    f"canonical queue timeout exceeded: {agent_name}"
                )
            _my_epoch = waiter.granted_epoch

        _watchdog = threading.Timer(
            _WORKER_WALL_TIME_CEILING_SEC,
            self._wall_time_watchdog,
            args=(_my_epoch,),
        )
        _watchdog.daemon = True
        _watchdog.start()
        try:
            capability_obj = self._capability_map.get(agent_name, Capability.GENERAL)
            preferred_keys = self.get_capability_preferences(capability_obj)
            _result = self._request_via_pool(
                capability_obj,
                preferred_keys=preferred_keys,
                prompt=prompt,
                params=params,
                system_prompt=system_prompt,
            )
            # Защита от позднего результата: осиротевший (форфейтенный) вызов
            # не возвращает результат владельцу и не пишет кэш — только отказ.
            with self._worker_lock:
                _orphaned = self._slot_epoch != _my_epoch
            if _orphaned:
                raise RuntimeError(
                    "R4A_WALLTIME: вызов покинут — слот форфейтен после потолка "
                    "wall-time; результат отброшен, слот у следующего владельца"
                )
            _root_logger.info(
                f"[R4A_WORKER] returned {len(_result) if _result else 0} chars"
            )
            # Кэш + телеметрия: контракт прежнего worker-пути (дублирование
            # сознательное — OFF-путь остаётся нетронутым)
            if settings.replay_record:
                _store = getattr(self, "_replay_store", None)  # noqa: ENIGMA002
                if _store:
                    _store.record_llm_call(
                        session_id=getattr(self, "_current_session_id", "unknown"),
                        tick_id=getattr(self, "_current_tick_id", 0),
                        agent_name=agent_name,
                        prompt=prompt,
                        response=_result,
                        model_name=self.get_model_for_agent(agent_name),
                        latency_ms=int((time.perf_counter() - worker_start) * 1000),
                        system_prompt=system_prompt,
                        params=params,
                    )
            from app.services.logging_tools import jsonl_log
            from app.services.replay.llm_cache import compute_prompt_hash

            jsonl_log({
                "level": "INFO",
                "agent": "llm_output",
                "tick_id": getattr(self, "_current_tick_id", 0),
                "npc_id": agent_name,
                "prompt_hash": prompt_hash,
                "response_hash": compute_prompt_hash(_result) if _result else None,  # noqa: ENIGMA001
                "model": self.get_model_for_agent(agent_name),
                "latency": round((time.perf_counter() - worker_start) * 1000, 1),
                "cache_hit": False,
            })
            return _result
        finally:
            _watchdog.cancel()
            with self._worker_lock:
                if self._slot_busy and self._slot_epoch == _my_epoch:
                    self._slot_busy = False
                    self._grant_next_locked()

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

                if model_provider:
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
                        # H-09 FIX: Включаем backoff и статус ERROR для упавшей модели
                        model_provider.mark_error(str(e))
                        pool.record_failure(model_key)
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
            if model_provider:
                try:
                    return model_provider.provider.complete(
                        prompt, params, system_prompt
                    )
                except Exception as e:
                    logger.warning(f"Fallback {model_key} failed: {e}")
                    # H-12 FIX: Прерываем цикл, чтобы не thrash VRAM, выгружая и загружая модели подряд.
                    break
            else:
                # S129 FIX: Безопасное логирование без вложенных вызовов is_available()
                _status = model_provider.status if model_provider else "None"
                logger.error(f"ModelRouter: Fallback Model {model_key} not available. Status: {_status}")
                # H-12 FIX: Если модель не загрузилась, нет смысла пытаться загрузить следующую.
                break

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
        return capability  # type: ignore[unreachable]  # S313: runtime-гвард (cast лжёт на мусоре)

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
            return cast(str, provider.complete(prompt, params, system_prompt))

        raise RuntimeError(f"No provider available for capability: {capability}")

    def _get_or_create_provider(self, model_key: str, model_config: ModelConfig) -> Any:
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
        priority: str = "canonical",
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
        # COV-2/D62: класс запроса для приоритетной очереди (используется
        # только при LLM_RESILIENCE_V1=ON; валидация всегда — опечатка не
        # имеет права молча превратиться в canonical).
        if priority not in ("canonical", "ambient"):
            raise ValueError(
                f"priority must be 'canonical'|'ambient', got {priority!r}"
            )
        capability = self._capability_map.get(agent_name, Capability.GENERAL)

        # Подсистема 2: LLM Cache для Replay (Этап 2.3)
        from app.core.config import settings
        from app.services.replay.llm_cache import compute_prompt_hash
        _prompt_hash = compute_prompt_hash(prompt, system_prompt, params)

        # === ЛОГИРОВАНИЕ ПРОМПТА ДЛЯ ОТЛАДКИ (M-08 FIX) ===
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
                "capability": str(capability),
                "prompt_preview": _prompt_preview,
                "system_prompt": _sys_preview or "",
                "tick_id": getattr(self, "_current_tick_id", 0),
                "npc_id": agent_name,
                "prompt_hash": _prompt_hash,
                "response_hash": None, # Логируется в llm_output
                "model": self.get_model_for_agent(agent_name),
                "latency": 0.0, # Логируется в llm_output
                "cache_hit": False, # Логируется в llm_output
                "intent_before": None,
                "intent_after": None,
            }
        )

        if settings.replay_playback:
            # Режим воспроизведения: читаем только из кэша
            _store = getattr(self, "_replay_store", None)  # noqa: ENIGMA002
            if _store:
                _current_session = getattr(self, "_current_session_id", "unknown")
                _cached = _store.get_llm_call(_current_session, agent_name, _prompt_hash)
                # COV-2/D67b (находка T2): различать «нет записи» (None → miss,
                # громкий RuntimeError) и «запись с пустым ответом» (валидный
                # кэш — пустой ответ ЛОКАЛЕН и честен). Прежний truthiness-гейт
                # `_cached.get("response")` объявлял законную пустую запись
                # отсутствующей и проваливал её в miss-ветку.
                if _cached is not None and "response" in _cached:
                    logger.debug(f"[LLM_CACHE] HIT: agent={agent_name} hash={_prompt_hash[:8]}")
                    return str(_cached["response"])
                # Cache miss в playback mode — критическая ошибка
                logger.error(f"[LLM_CACHE] MISS in playback mode! agent={agent_name} hash={_prompt_hash[:8]}")
                raise RuntimeError("Replay determinism broken: LLM cache miss in playback")
        elif settings.replay_record:
            # Режим записи: пытаемся читать из кэша (hot-path), при miss идём к LLM
            _store = getattr(self, "_replay_store", None)  # noqa: ENIGMA002
            if _store:
                _current_session = getattr(self, "_current_session_id", "unknown")
                _cached = _store.get_llm_call(_current_session, agent_name, _prompt_hash)
                # COV-2/D67b: симметричное различение miss/empty (см. ветку выше).
                if _cached is not None and "response" in _cached:
                    logger.debug(f"[LLM_CACHE] HIT: agent={agent_name} hash={_prompt_hash[:8]}")
                    return str(_cached["response"])

        # Worker thread (to_thread): прямой синхронный вызов без semaphore
        # Semaphore привязан к main loop — в новом loop он мёртв
        if threading.current_thread() is not threading.main_thread():
            # COV-2/D64-ядро: фактическая латентность worker-пути (раньше
            # кэш/телеметрия писали константный ноль).
            _worker_start = time.perf_counter()
            # COV-2/D62: приоритетная очередь за флагом. OFF = код ниже не
            # тронут ни на строку (механика abort при in_progress сохранена).
            if _llm_resilience_v1_enabled():
                return self._worker_request_queued(
                    agent_name=agent_name,
                    prompt=prompt,
                    params=params,
                    system_prompt=system_prompt,
                    priority=priority,
                    prompt_hash=_prompt_hash,
                    worker_start=_worker_start,
                )
            with self._worker_lock: # H-11 FIX: Потокобезопасная проверка и установка флага
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
                # C-11 FIX: Worker-thread path не писал в кэш. Пишем до возврата.
                # H-07 FIX: Не пишем пустые ответы в кэш, чтобы не нарушать детерминизм.
                # H-08 FIX: Передаём system_prompt и params для корректного вычисления хэша.
                if settings.replay_record and _result:
                    _store = getattr(self, "_replay_store", None)  # noqa: ENIGMA002
                    if _store:
                        _tick_id = getattr(self, "_current_tick_id", 0)
                        _store.record_llm_call(
                            session_id=getattr(self, "_current_session_id", "unknown"),
                            tick_id=_tick_id,
                            agent_name=agent_name,
                            prompt=prompt,
                            response=_result,
                            model_name=self.get_model_for_agent(agent_name),
                            latency_ms=int((time.perf_counter() - _worker_start) * 1000),
                            system_prompt=system_prompt,
                            params=params
                        )

                # M-09/M-10 FIX: Логируем ответ LLM с метриками
                from app.services.replay.llm_cache import compute_prompt_hash
                jsonl_log({
                    "level": "INFO",
                    "agent": "llm_output",
                    "tick_id": getattr(self, "_current_tick_id", 0),
                    "npc_id": agent_name,
                    "prompt_hash": _prompt_hash,
                    "response_hash": compute_prompt_hash(_result) if _result else None,  # noqa: ENIGMA001
                    "model": self.get_model_for_agent(agent_name),
                    # COV-2/D64-ядро: фактическая latency worker-пути (perf_counter)
                    "latency": round((time.perf_counter() - _worker_start) * 1000, 1),
                    "cache_hit": False
                })
                return _result
            except Exception as e:
                _root_logger.error(f"[R4A_WORKER] exception: {e}")
                # NEW-DLG-004 FIX: Пробрасываем исключение, чтобы вызывающий код знал о падении LLM, а не получал пустую строку.
                raise
            finally:
                self._request_in_progress = False

        _result = ""
        if settings.replay_playback:
            # COV-2/D67 (вердикт Мастера): cache miss в playback — нарушение
            # детерминизма записанной сессии, а НЕ «пустой ответ». Тихая пустышка
            # маскировала разрыв реплея как ложный успех потребителя. Симметрия
            # с main-loop-веткой (miss там уже RuntimeError) + стандарт
            # NEW-DLG-004: исключение вместо пустой строки.
            raise RuntimeError(
                "Replay determinism broken: LLM cache miss in playback "
                f"(agent={agent_name}, prompt_hash={_prompt_hash[:8]})"
            )
        else:
            coro = self.request(capability, prompt, params, system_prompt)
            try:
                # RE-D2: значение не нужно — вызов работает как детектор
                # контекста: успех = текущий поток ЕСТЬ поток петли (else-ветка
                # ниже поднимает громкий отказ). F841-гигиена.
                asyncio.get_running_loop()
            except RuntimeError as e:
                logger.debug(f"No running loop, starting new one: {e}")
                _result = asyncio.run(coro)
            else:
                # RE-D2 FIX: в эту ветку попадаем ТОЛЬКО с потока самой
                # event loop (get_running_loop() выше успел — значит текущий
                # поток и есть поток петли). Спланировать корутину на
                # собственную петлю и блокирующе ждать future — дедлок по
                # построению: петля не исполнит колбэк, пока её поток стоит
                # в .result(). До фикса — 60-секундная заморозка всего
                # бэкенда (RE-D2; репродукции S241 и 2026-09-05: submit ->
                # блок -> timeout -> зомби-корутина исполнилась ПОСЛЕ отказа
                # ждущего, результат выброшен). Громкий отказ вместо тихой
                # минуты. Правильные пути тяжёлых вызовов — worker-поток
                # (asyncio.to_thread) либо async request(); перенос экстракции
                # в intelligence queue — DEBT-RE-D2A.
                coro.close()
                raise RuntimeError(
                    "RE-D2: request_for_agent() вызван с потока event loop: "
                    "run_coroutine_threadsafe на собственную петлю + "
                    "блокирующее ожидание = гарантированный дедлок. "
                    "Вызывай из worker-потока (asyncio.to_thread) или "
                    "используй await router.request(...)."
                )

        # Запись в кэш (если режим записи)
        if settings.replay_record:
            _store = getattr(self, "_replay_store", None)  # noqa: ENIGMA002
            if _store:
                _tick_id = getattr(self, "_current_tick_id", 0)
                _store.record_llm_call(
                    session_id=getattr(self, "_current_session_id", "unknown"),
                    tick_id=_tick_id,
                    agent_name=agent_name,
                    prompt=prompt,
                    response=_result,
                    model_name=self.get_model_for_agent(agent_name),
                    latency_ms=0,
                    system_prompt=system_prompt,
                    params=params
                )

        return _result
        # BUGFIX-ROUTER-DEADCODE-001: Удалён мёртвый код (try/except get_running_loop + asyncio.run после return)

    # --- Streaming Observability (ADR-147) ---
    # Router — единственный владелец observability LLM-вызовов.
    # Streaming проходит ЧЕРЕЗ Router, не в обход.

    def notify_stream_start(
        self,
        agent_name: str,
        capability: str | Capability,
        prompt: str | None = None,
        system_prompt: str | None = None,
        params: GenerationParams | None = None,
    ) -> dict:
        """Уведомляет Router о начале streaming LLM-вызова. Эмитит [R4A_STREAM] маркер для CDS.

        COV-2/D65: prompt/system_prompt/params (опционально, back-compat) —
        контекст для записи стрим-ответа в replay-кэш: вызывающий буферизует
        полный декодированный ответ и передаёт его в notify_stream_end(full_text=...).
        Хеш вычисляет стор (prompt|system|params) — ключи совместимы с не-стрим путями."""
        cap = self._normalize_capability(capability)
        _root_logger.info(
            f"[R4A_STREAM] calling stream_tokens(), agent={agent_name}, capability={cap.value}"
        )
        return {
            "start_time": time.time(),
            "agent_name": agent_name,
            "capability": cap.value,
            "prompt": prompt,
            "system_prompt": system_prompt,
            "params": params,
        }

    def notify_stream_end(
        self, ctx: dict, chars_produced: int, full_text: str | None = None
    ) -> None:
        """Уведомляет Router о завершении streaming LLM-вызова. Эмитит [R4A_STREAM] маркер для CDS.

        COV-2/D65: при full_text (буфер декодированного стрима) и активном
        replay_record — запись в кэш по контракту не-стрим путей. Отказ записи
        наблюдаем (warning, L4): недозапись вскроется громким playback-miss (D67)."""
        elapsed_ms = (time.time() - ctx["start_time"]) * 1000
        _root_logger.info(
            f"[R4A_STREAM] stream complete, {chars_produced} chars in {elapsed_ms:.0f}ms"
        )
        if full_text is None or ctx.get("prompt") is None:
            return
        from app.core.config import settings as _settings

        if not _settings.replay_record:
            return
        _store = getattr(self, "_replay_store", None)  # noqa: ENIGMA002
        if _store is None:
            return
        try:
            _store.record_llm_call(
                session_id=getattr(self, "_current_session_id", "unknown"),
                tick_id=getattr(self, "_current_tick_id", 0),
                agent_name=ctx["agent_name"],
                prompt=ctx["prompt"],
                response=full_text,
                model_name=self.get_model_for_agent(ctx["agent_name"]),
                latency_ms=int(elapsed_ms),
                system_prompt=ctx.get("system_prompt"),
                params=ctx.get("params"),
            )
        except Exception as e:  # наблюдаемо; тишина = ложный успех реплея
            logger.warning(f"[LLM_CACHE] stream record failed: {e}")

    def playback_stream_lookup(
        self,
        agent_name: str,
        prompt: str,
        system_prompt: str | None = None,
        params: GenerationParams | None = None,
    ) -> str | None:
        """COV-2/D65: playback для стрим-пути.

        Returns:
            None — не playback-режим: вызывающий идёт в живой стрим;
            str  — кэш найден: эмуляция стрима из кэша, модель НЕ запрашивается.
        Raises:
            RuntimeError — playback без стора или cache miss: громко, стандарт D67
            (тихая пустышка = ложный успех воспроизведения записанной сессии)."""
        from app.core.config import settings as _settings

        if not _settings.replay_playback:
            return None
        _store = getattr(self, "_replay_store", None)  # noqa: ENIGMA002
        if _store is None:
            raise RuntimeError(
                "Replay determinism broken: playback mode without replay store "
                f"(agent={agent_name})"
            )
        from app.services.replay.llm_cache import compute_prompt_hash

        _hash = compute_prompt_hash(prompt, system_prompt, params)
        _cached = _store.get_llm_call(
            getattr(self, "_current_session_id", "unknown"), agent_name, _hash
        )
        if _cached is not None and "response" in _cached:
            return str(_cached["response"])
        raise RuntimeError(
            "Replay determinism broken: LLM stream cache miss in playback "
            f"(agent={agent_name}, hash={_hash[:8]})"
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
            return None  # type: ignore[unreachable]  # S313: runtime-гвард (cast лжёт на мусоре)

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

    def switch(self, selection: Any) -> None:
        """Legacy: ручное переключение модели."""
        if hasattr(selection, "model_name"):
            self._current_model_key = selection.model_name

    def describe(self) -> str:
        """Legacy: описание текущей модели."""
        if self._current_model_key:
            config = self._registry.get(self._current_model_key)  # type: ignore[unreachable]  # S313: runtime-гвард (cast лжёт на мусоре)
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
    # F841-гигиена (pre-existing): присваивание было мёртвым; вызов сохранён —
    # get_router() создаёт/возвращает синглтон, побочный эффект важен, значение — нет.
    get_router()

    logger.debug(f"Router initialized. ModelPool: {pool_results}")
    logger.debug("Lazy loading enabled: only one model in VRAM at a time")

__all__ = [
    "ModelRouter",
    "Capability",
    "GenerationParams",
    "CAPABILITY_MODEL_PREFERENCES",
    "get_router",
    "initialize_router",
]
