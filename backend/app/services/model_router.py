# backend/app/services/model_router.py
import asyncio
import logging
from pathlib import Path
from typing import Dict, Optional, List

from dataclasses import dataclass

from app.models.schemas import ModelSelection, ModelProvider
from app.core.config import settings
from app.services.llm.provider_manager import get_model_pool


@dataclass
class ModelInfo:
    """Информация о модели для ModelRouter."""
    key: str
    name: str
    path: str
    display_name: str
    vram_mb: int
    context_size: int
    temperature: float
    top_p: float
    repeat_penalty: float
    n_keep: int

    @property
    def is_available(self) -> bool:
        """Проверка доступности через pool"""
        pool = get_model_pool()
        model = pool.get_model(self.key)
        return model.is_available if model else False


class ModelRouter:
    """
    Асинхронный роутер моделей для LLM-агентов (DM, NPC, Rules, World, Memory)
    Поддерживает:
      - Lazy loading
      - VRAM-aware выгрузку
      - Совместимость со старыми тестами
      - Относительные пути для Windows
    """

    def __init__(self) -> None:
        self.pool = get_model_pool()  # singleton pool
        self._models: Dict[str, ModelInfo] = {}
        self._agent_map: Dict[str, str] = {}
        self.current: Optional[ModelSelection] = None
        self._current_agent: Optional[str] = None
        self.logger = logging.getLogger(__name__)
        self._init_models()

    def _init_models(self) -> None:
        """Инициализация моделей из settings"""
        for key, cfg in settings.available_models.items():
            model_path = str(Path(cfg.path).resolve())
            self._models[key] = ModelInfo(
                key=key,
                name=cfg.name,
                path=model_path,
                display_name=cfg.display_name,
                vram_mb=cfg.vram_mb,
                context_size=cfg.context_size,
                temperature=cfg.temperature,
                top_p=cfg.top_p,
                repeat_penalty=cfg.repeat_penalty,
                n_keep=cfg.n_keep,
            )
        self._agent_map = settings.agent_model_map.copy()
        self.logger.info(f"ModelRouter инициализирован с агентами: {list(self._agent_map.keys())}")

    # -------------------------
    # VRAM-aware Lazy Activation
    # -------------------------
    async def switch_to_agent(
        self,
        agent_name: str,
        session_id: Optional[str] = None,
        timeout_sec: Optional[float] = None
    ) -> Optional[ModelInfo]:
        """Активирует модель для агента с выгрузкой предыдущей"""
        agent_name = agent_name.lower()
        model_key = self._agent_map.get(agent_name)
        if not model_key or model_key not in self._models:
            self.logger.warning(f"[ModelRouter] Нет модели для агента '{agent_name}'")
            return None

        # Если модель уже активна, ничего не делаем
        if self.pool.active_model_key == model_key:
            self.logger.info(f"[ModelRouter] Модель '{model_key}' уже активна")
            return await self.get_model_for_agent(agent_name)

        # Выгружаем предыдущую модель
        if self.pool.active_model_key:
            prev_key = self.pool.active_model_key
            self.logger.info(f"[ModelRouter] Выгружаем предыдущую модель '{prev_key}'")
            await self.pool.unload_model(prev_key)

        # Загружаем новую модель
        self.logger.info(f"[ModelRouter] Загружаем модель '{model_key}' для '{agent_name}'")
        model_provider = await self.pool.get_model_async(model_key, session_id, agent_name, timeout_sec)

        if not model_provider:
            self.logger.warning(f"[ModelRouter] Не удалось загрузить модель '{model_key}'")
            return None

        model_info = self._models[model_key]
        self.current = ModelSelection(
            provider=ModelProvider.llama_cpp,
            model_name=model_info.name,
            endpoint=getattr(settings, "llama_cpp_server_url", None),
        )
        self._current_agent = agent_name
        await self._health_check(model_key, session_id or "unknown")
        self.logger.info(f"[ModelRouter] Модель '{model_key}' активирована для '{agent_name}'")
        return model_info

    async def get_model_for_agent(
        self, agent_name: str, session_id: Optional[str] = None, timeout_sec: Optional[float] = None
    ) -> Optional[ModelSelection]:
        """Асинхронная активация и возврат модели для агента"""
        agent_name = agent_name.lower()
        model_key = self._agent_map.get(agent_name)
        if not model_key or model_key not in self._models:
            self.logger.warning(f"[ModelRouter] Нет модели для агента '{agent_name}'")
            return None

        # Если модель не активна, активируем
        if self.pool.active_model_key != model_key:
            await self.switch_to_agent(agent_name, session_id, timeout_sec)

        model_info = self._models[model_key]
        selection = ModelSelection(
            provider=ModelProvider.llama_cpp,
            model_name=model_info.name,
            endpoint=getattr(settings, "llama_cpp_server_url", None),
        )
        self.current = selection
        return selection

    async def _health_check(self, model_key: str, session_id: str) -> bool:
        """Проверка доступности модели после загрузки"""
        try:
            model = self.pool.get_model(model_key)
            if model and model.is_available:
                self.logger.info(f"[HEALTH {session_id}] ✓ Модель '{model_key}' готова")
                return True
            self.logger.warning(f"[HEALTH {session_id}] ✗ Модель '{model_key}' недоступна")
            return False
        except Exception as e:
            self.logger.error(f"[HEALTH {session_id}] ✗ Ошибка: {e}")
            return False

    # -------------------------
    # Методы для тестов и утилиты
    # -------------------------
    def list_models_for_test(self) -> List[ModelInfo]:
        return list(self._models.values())

    def list_agents(self) -> Dict[str, str]:
        return self._agent_map.copy()

    def get_current_model_info(self) -> Optional[ModelInfo]:
        if not self.current:
            return None
        for m in self._models.values():
            if m.name == self.current.model_name:
                return m
        return None

    def describe(self) -> str:
        if not self.current:
            return "Модель не выбрана"
        endpoint = f" ({self.current.endpoint})" if self.current.endpoint else ""
        return f"{self.current.provider}:{self.current.model_name}{endpoint}"

    def get_model_path(self, model_key: str) -> Optional[str]:
        model = self._models.get(model_key)
        return model.path if model else None

    async def get_agent_model_path(self, agent_name: str) -> Optional[str]:
        model_info = await self.get_model_for_agent(agent_name)
        return model_info.path if model_info else None