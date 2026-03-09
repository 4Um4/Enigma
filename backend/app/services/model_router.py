from dataclasses import dataclass
from typing import Dict, Optional

from app.models.schemas import ModelSelection, ModelProvider
from app.core.config import settings


@dataclass
class ModelInfo:
    """Информация о модели для роутера."""
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


class ModelRouter:
    """
    Runtime model selection для мультимодальной LLM архитектуры.
    
    Поддерживает:
    - Выбор модели по агенту (dm, npc, rules, world, memory)
    - Ручной выбор модели
    - Swap моделей через llama.cpp server
    """

    def __init__(self) -> None:
        self._models: Dict[str, ModelInfo] = {}
        self._agent_map: Dict[str, str] = {}
        self.current: Optional[ModelSelection] = None
        self._init_models()

    def _init_models(self) -> None:
        """Инициализирует доступные модели из конфигурации."""
        # Загружаем модели из конфигурации
        for key, config in settings.available_models.items():
            self._models[key] = ModelInfo(
                key=key,
                name=config.name,
                path=config.path,
                display_name=config.display_name,
                vram_mb=config.vram_mb,
                context_size=config.context_size,
                temperature=config.temperature,
                top_p=config.top_p,
                repeat_penalty=config.repeat_penalty,
                n_keep=config.n_keep,
            )
        
        # Загружаем маппинг агент → модель
        self._agent_map = settings.agent_model_map.copy()

    def get_model_for_agent(self, agent_name: str) -> Optional[ModelInfo]:
        """
        Получить модель для указанного агента.
        
        Args:
            agent_name: имя агента (dm, npc, rules, world, memory)
            
        Returns:
            ModelInfo или None если агент не найден
        """
        model_key = self._agent_map.get(agent_name.lower())
        if model_key:
            return self._models.get(model_key)
        return None

    def switch_to_agent(self, agent_name: str) -> ModelSelection:
        """
        Переключить модель на указанного агента.
        
        Args:
            agent_name: имя агента
            
        Returns:
            ModelSelection для использования в LLM
        """
        model_info = self.get_model_for_agent(agent_name)
        
        if not model_info:
            # Fallback на первую доступную модель
            model_info = next(iter(self._models.values()))
        
        self.current = ModelSelection(
            provider=ModelProvider.llama_cpp,
            model_name=model_info.name,
            endpoint=settings.llama_cpp_server_url,
        )
        
        return self.current

    def switch(self, selection: ModelSelection) -> ModelSelection:
        """Ручное переключение на указанную модель."""
        self.current = selection
        return selection

    def switch_by_key(self, model_key: str) -> ModelSelection:
        """
        Переключить модель по ключу.
        
        Args:
            model_key: ключ модели (saiga, yandex, qwen_7b, qwen_9b)
        """
        model_info = self._models.get(model_key)
        
        if not model_info:
            raise ValueError(f"Модель с ключом '{model_key}' не найдена")
        
        self.current = ModelSelection(
            provider=ModelProvider.llama_cpp,
            model_name=model_info.name,
            endpoint=settings.llama_cpp_server_url,
        )
        
        return self.current

    def get_current_model_info(self) -> Optional[ModelInfo]:
        """Получить информацию о текущей модели."""
        if not self.current:
            return None
        return self._models.get(self.current.model_name)

    def list_models(self) -> Dict[str, ModelInfo]:
        """Список всех доступных моделей."""
        return self._models.copy()

    def list_agents(self) -> Dict[str, str]:
        """Список маппинга агентов на модели."""
        return self._agent_map.copy()

    def describe(self) -> str:
        """Описание текущей модели."""
        if not self.current:
            return "Модель не выбрана"
        endpoint = f" ({self.current.endpoint})" if self.current.endpoint else ""
        return f"{self.current.provider}:{self.current.model_name}{endpoint}"

    def get_model_path(self, model_key: str) -> Optional[str]:
        """Получить путь к файлу модели по ключу."""
        model = self._models.get(model_key)
        return model.path if model else None

    def get_agent_model_path(self, agent_name: str) -> Optional[str]:
        """Получить путь к модели для указанного агента."""
        model_info = self.get_model_for_agent(agent_name)
        return model_info.path if model_info else None

