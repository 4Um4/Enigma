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

            case ProviderType.OPENAI:
                from app.services.llm.openai_compatible_provider import OpenAICompatibleProvider
                # endpoint: https://api.openai.com/v1 или https://api.bigmodel.cn/api/paas/v4
                # api_key: берётся из config.py (settings.openai_api_key)
                return OpenAICompatibleProvider(
                    model_name=model_path or "gpt-4o-mini",
                    api_key=api_key or "",
                    endpoint=endpoint or "https://api.openai.com/v1",
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