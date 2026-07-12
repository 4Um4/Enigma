"""
LLM Provider Factory

Создаёт LLM провайдеров по типу. Не содержит реализаций — только маппинг.
Реализации живут в отдельных модулях:
- llama_cpp_provider.py
- openai_provider.py
- anthropic_provider.py
- ollama_provider.py
- vllm_provider.py
- mock_provider.py
"""
from __future__ import annotations

from app.core.config import settings
from app.core.settings_dm import dm_settings
from app.core.settings_npc import npc_settings
from app.core.settings_rules import rules_settings
from app.core.settings_world import world_settings
from app.services.llm.llama_cpp_provider import create_llama_cpp_provider

# C5-FIX: Удалены импорты мёртвых провайдеров
from app.services.llm.mock_provider import create_mock_provider
from app.services.llm.provider import LlmProvider, ProviderType


class ProviderFactory:
    """
    Фабрика для создания LLM провайдеров.

    Каждый провайдер — отдельный replaceable модуль.
    Добавить новый провайдер = создать файл + добавить case в create().
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
            model_path: Путь/имя модели
            endpoint: URL endpoint (для API)
            api_key: API ключ (для API)

        Returns:
            Настроенный провайдер
        """
        match provider_type:
            case ProviderType.LLAMA_CPP:
                # server_url=None → create_llama_cpp_provider берёт из settings.llama_cpp_server_url
                # Пустая строка там = CLI режим, URL = серверный режим
                return create_llama_cpp_provider(
                    model_path=model_path,
                    model_name="default",
                    server_url=endpoint,
                )

            case ProviderType.MOCK:
                # B4-FIX: MockProvider excluded from production (No fallback reality).
                from app.core.config import settings

                if settings.environment == "production":
                    raise RuntimeError(
                        "[LLM_FACTORY] CRITICAL: MockProvider in production. "
                        "Mock is simulation of simulation — no place in runtime reality. "
                        "Set settings.environment='development' to allow."
                    )
                return create_mock_provider()

            case _:
                raise ValueError(f"Unknown provider type: {provider_type}")

    @staticmethod
    def create_default() -> LlmProvider:
        """Создать провайдер по умолчанию (llama.cpp)."""
        return create_llama_cpp_provider()

    @staticmethod
    def create_for_agent(agent_name: str) -> LlmProvider:
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
        # Не перезаписываем server_url из runtime_ports — используем settings
        server_url = None
        model_key = agent_settings.agent_model_map.get(
            agent_name,
            settings.agent_model_map.get(agent_name, "qwen_7b"),
        )
        model_path = None
        if (
            hasattr(agent_settings, "available_models")
            and model_key in agent_settings.available_models
        ):
            model_path = agent_settings.available_models[model_key].path
        # Передаём temperature и repeat_penalty из настроек агента
        _temp = getattr(agent_settings, "temperature", 0.9)
        _rep = getattr(agent_settings, "repeat_penalty", 1.12)
        return create_llama_cpp_provider(
            model_path=model_path,
            server_url=server_url,
            temperature=_temp,
            repeat_penalty=_rep,
        )

    @staticmethod
    def check_health_all() -> dict[str, bool]:
        """
        Проверить доступность всех LLM серверов для агентов.

        Returns:
            Словарь {agent_name: is_available}
        """
        return settings.check_llm_servers_health()


def get_provider(provider_type: ProviderType = ProviderType.LLAMA_CPP) -> LlmProvider:
    """Получить провайдер по типу."""
    return ProviderFactory.create(provider_type)
