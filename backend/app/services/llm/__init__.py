"""
LLM Services - Provider Interface and Model Routing

Architecture:
    Agents → ModelRouter (capability-based) → ModelPool → LlmProviders

Components:
- LlmProvider: Abstract interface for all LLM providers
- ModelPool: Lazy loading for VRAM optimization (8GB constraint)
- ProviderManager: Manages multiple providers (legacy)
- ModelRouter: Capability-based routing layer
- ProviderFactory: Creates provider instances
- ModelMetrics: Performance tracking

Providers (replaceable modules):
- LlamaCppProvider: llama.cpp server / CLI
- OpenAIProvider: OpenAI API (и совместимые)
- AnthropicProvider: Claude API
- OllamaProvider: Ollama local server
- VllmProvider: vLLM inference server
- MockProvider: заглушка для прототипирования
"""

from app.services.llm.factory import ProviderFactory, get_provider

# Конкретные провайдеры — доступны для явного импорта при необходимости
from app.services.llm.llama_cpp_provider import (
    LlamaCppProvider,
    create_llama_cpp_provider,
)

# C5-FIX: Удалены импорты мёртвых провайдеров
from app.services.llm.mock_provider import (
    MockConfig,
    MockProvider,
    create_mock_provider,
)
from app.services.llm.provider import (
    GenerationParams,
    LlmProvider,
    ProviderInfo,
    ProviderType,
    StreamingLlmProvider,
)
from app.services.llm.provider_manager import (
    ModelConfig,
    ModelMetrics,
    ModelPool,
    ProviderManager,
    ProviderStatus,
    get_model_pool,
    get_provider_manager,
    initialize_model_pool,
    initialize_providers,
)
from app.services.llm.router import (
    Capability,
    ModelRouter,
    get_router,
    initialize_router,
)

__all__ = [
    # Core interfaces
    "LlmProvider",
    "StreamingLlmProvider",
    "GenerationParams",
    "ProviderInfo",
    "ProviderType",
    # Router
    "ModelRouter",
    "Capability",
    "get_router",
    "initialize_router",
    # Model Pool (Lazy Loading)
    "ModelPool",
    "get_model_pool",
    "initialize_model_pool",
    "ModelMetrics",
    "ModelConfig",
    "ProviderStatus",
    # Provider management (legacy)
    "ProviderManager",
    "get_provider_manager",
    "initialize_providers",
    # Factory
    "get_provider",
    "ProviderFactory",
    # Concrete providers (replaceable)
    "LlamaCppProvider",
    "create_llama_cpp_provider",
    # C5-FIX: Мёртвые провайдеры удалены из __all__
    "MockProvider",
    "MockConfig",
    "create_mock_provider",
]
