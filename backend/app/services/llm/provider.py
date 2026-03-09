"""
LLM Provider Interface
Abstract base class for all LLM providers.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ProviderType(str, Enum):
    """Типы LLM провайдеров."""
    LLAMA_CPP = "llama_cpp"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    OLLAMA = "ollama"
    LM_STUDIO = "lm_studio"
    KOBOLD_CPP = "koboldcpp"


@dataclass
class GenerationParams:
    """Параметры генерации для LLM."""
    max_tokens: int = 512
    temperature: float = 0.7
    top_p: float = 0.9
    top_k: int = 40
    repeat_penalty: float = 1.1
    n_keep: int = 512  # System prompt tokens to keep
    stop: list[str] = field(default_factory=list)
    
    # Дополнительные параметры для API провайдеров
    presence_penalty: Optional[float] = None
    frequency_penalty: Optional[float] = None
    response_format: Optional[dict] = None


@dataclass
class ProviderInfo:
    """Информация о провайдере."""
    name: str
    provider_type: ProviderType
    endpoint: Optional[str] = None
    model_name: Optional[str] = None
    is_available: bool = True
    context_size: int = 4096
    vram_mb: int = 0


class LlmProvider(ABC):
    """
    Abstract base class for LLM providers.
    
    All providers must implement:
    - complete(): Generate text from prompt
    - is_available(): Check if provider is ready
    - get_info(): Return provider information
    """
    
    @abstractmethod
    def complete(
        self, 
        prompt: str, 
        params: GenerationParams | None = None,
        system_prompt: str | None = None
    ) -> str:
        """
        Генерирует текст на основе промпта.
        
        Args:
            prompt: Пользовательский промпт
            params: Параметры генерации
            system_prompt: Системный промпт (опционально)
            
        Returns:
            Сгенерированный текст
        """
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """
        Проверяет доступность провайдера.
        
        Returns:
            True если провайдер готов к работе
        """
        pass
    
    @abstractmethod
    def get_info(self) -> ProviderInfo:
        """
        Возвращает информацию о провайдере.
        
        Returns:
            ProviderInfo с метаданными
        """
        pass
    
    @abstractmethod
    def get_provider_type(self) -> ProviderType:
        """
        Возвращает тип провайдера.
        
        Returns:
            ProviderType enum
        """
        pass
    
    def health_check(self) -> bool:
        """Быстрая проверка здоровья провайдера."""
        return self.is_available()


class StreamingLlmProvider(LlmProvider):
    """
    Расширенный провайдер с поддержкой стриминга.
    """
    
    def stream_complete(
        self,
        prompt: str,
        params: GenerationParams | None = None,
        system_prompt: str | None = None,
        callback=None  # callable that receives chunks
    ) -> str:
        """
        Генерирует текст со стримингом.
        
        Args:
            prompt: Пользовательский промпт
            params: Параметры генерации
            system_prompt: Системный промпт
            callback: Функция для обработки чанков
            
        Returns:
            Полный сгенерированный текст
        """
        # Default implementation calls complete
        result = self.complete(prompt, params, system_prompt)
        if callback:
            callback(result)
        return result


# Типизация для создания провайдеров
ProviderFactory = LlmProvider | None

