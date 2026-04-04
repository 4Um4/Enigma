"""
LLM Provider Factory

Creates and manages LLM providers based on configuration.
"""

from __future__ import annotations

from typing import Optional

from app.core.config import settings
from app.core.settings_dm import dm_settings
from app.core.settings_npc import npc_settings
from app.core.settings_world import world_settings
from app.core.settings_rules import rules_settings
from app.services.llm.provider import LlmProvider, ProviderType
from app.services.llm.llama_cpp_provider import LlamaCppProvider, create_llama_cpp_provider


class ProviderFactory:
    """
    Фабрика для создания LLM провайдеров.
    
    Supports:
    - llama.cpp (local)
    - OpenAI API
    - Anthropic API
    - Ollama (local)
    """
    
    @staticmethod
    def create(
        provider_type: ProviderType,
        model_path: str | None = None,
        endpoint: str | None = None,
        api_key: str | None = None,
    ) -> LlmProvider:
        """
        Создать провайдер указанного типа.
        
        Args:
            provider_type: Тип провайдера
            model_path: Путь к модели (для локальных)
            endpoint: URL endpoint (для API)
            api_key: API ключ (для API)
            
        Returns:
            Настроенный провайдер
        """
        match provider_type:
            case ProviderType.LLAMA_CPP:
                return create_llama_cpp_provider(
                    model_path=model_path,
                    model_name="default",
                    server_url=endpoint or settings.get_llm_server_url(),
                )
            
            case ProviderType.OPENAI:
                return OpenAIProvider(
                    endpoint=endpoint or "https://api.openai.com/v1",
                    api_key=api_key or settings.openai_api_key,
                    model=model_path or "gpt-4",
                )
            
            case ProviderType.ANTHROPIC:
                return AnthropicProvider(
                    api_key=api_key or settings.anthropic_api_key,
                    model=model_path or "claude-3-opus",
                )
            
            case ProviderType.OLLAMA:
                return OllamaProvider(
                    endpoint=endpoint or "http://localhost:11434",
                    model=model_path or "llama2",
                )
            
            case _:
                raise ValueError(f"Unknown provider type: {provider_type}")
    
    @staticmethod
    def create_default() -> LlmProvider:
        """Создать провайдер по умолчанию (llama.cpp)."""
        return create_llama_cpp_provider()
    
    @staticmethod
    def create_for_agent(agent_name: str) -> LlamaCppProvider:
        """
        Создать провайдер для конкретного агента с правильным URL сервера.
        
        Args:
            agent_name: Имя агента (dm, npc, world, rules, memory)
            
        Returns:
            Настроенный LlamaCppProvider с правильным URL
        """
        agent_map = {
            "dm": dm_settings,
            "npc": npc_settings,
            "world": world_settings,
            "rules": rules_settings,
        }
        agent_settings = agent_map.get(agent_name, settings)
        server_url = agent_settings.get_llm_server_url(agent_name)
        model_key = agent_settings.agent_model_map.get(
            agent_name,
            settings.agent_model_map.get("_fallback", "gemma_12b"),
        )
        model_path = None
        if hasattr(agent_settings, 'available_models') and model_key in agent_settings.available_models:
            model_path = agent_settings.available_models[model_key].path
        return create_llama_cpp_provider(
            model_path=model_path,
            server_url=server_url,
        )
    
    @staticmethod
    def check_health_all() -> dict[str, bool]:
        """
        Проверить доступность всех LLM серверов для агентов.
        
        Returns:
            Словарь {agent_name: is_available}
        """
        return settings.check_llm_servers_health()


# === Additional Provider Implementations ===

class OpenAIProvider(LlmProvider):
    """OpenAI API провайдер."""
    
    def __init__(
        self,
        endpoint: str = "https://api.openai.com/v1",
        api_key: str | None = None,
        model: str = "gpt-4",
    ) -> None:
        self.endpoint = endpoint
        self.api_key = api_key
        self.model = model
    
    def complete(
        self,
        prompt: str,
        params=None,
        system_prompt: str | None = None,
    ) -> str:
        # TODO: Implement OpenAI API call
        raise NotImplementedError("OpenAI provider not yet implemented")
    
    def is_available(self) -> bool:
        return bool(self.api_key)
    
    def get_info(self):
        from app.services.llm.provider import ProviderInfo
        return ProviderInfo(
            name=f"OpenAI ({self.model})",
            provider_type=ProviderType.OPENAI,
            endpoint=self.endpoint,
            model_name=self.model,
            is_available=self.is_available(),
        )
    
    def get_provider_type(self) -> ProviderType:
        return ProviderType.OPENAI


class AnthropicProvider(LlmProvider):
    """Anthropic API провайдер."""
    
    def __init__(
        self,
        api_key: str | None = None,
        model: str = "claude-3-opus-20240229",
    ) -> None:
        self.api_key = api_key
        self.model = model
    
    def complete(
        self,
        prompt: str,
        params=None,
        system_prompt: str | None = None,
    ) -> str:
        # TODO: Implement Anthropic API call
        raise NotImplementedError("Anthropic provider not yet implemented")
    
    def is_available(self) -> bool:
        return bool(self.api_key)
    
    def get_info(self):
        from app.services.llm.provider import ProviderInfo
        return ProviderInfo(
            name=f"Anthropic ({self.model})",
            provider_type=ProviderType.ANTHROPIC,
            model_name=self.model,
            is_available=self.is_available(),
        )
    
    def get_provider_type(self) -> ProviderType:
        return ProviderType.ANTHROPIC


class OllamaProvider(LlmProvider):
    """Ollama local provider."""
    
    def __init__(
        self,
        endpoint: str = "http://localhost:11434",
        model: str = "llama2",
    ) -> None:
        self.endpoint = endpoint
        self.model = model
    
    def complete(
        self,
        prompt: str,
        params=None,
        system_prompt: str | None = None,
    ) -> str:
        # TODO: Implement Ollama API call
        raise NotImplementedError("Ollama provider not yet implemented")
    
    def is_available(self) -> bool:
        import urllib.request
        try:
            with urllib.request.urlopen(self.endpoint + "/api/tags", timeout=2):
                return True
        except Exception:
            return False
    
    def get_info(self):
        from app.services.llm.provider import ProviderInfo
        return ProviderInfo(
            name=f"Ollama ({self.model})",
            provider_type=ProviderType.OLLAMA,
            endpoint=self.endpoint,
            model_name=self.model,
            is_available=self.is_available(),
        )
    
    def get_provider_type(self) -> ProviderType:
        return ProviderType.OLLAMA


# === Convenience function ===
def get_provider(provider_type: ProviderType = ProviderType.LLAMA_CPP) -> LlmProvider:
    """Получить провайдер по умолчанию."""
    return ProviderFactory.create(provider_type)

