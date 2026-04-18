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

from app.services.llm.provider import LlmProvider, GenerationParams, ProviderInfo, ProviderType, StreamingLlmProvider
from app.services.llm.router import ModelRouter, Capability, get_router, initialize_router
from app.services.llm.factory import get_provider, ProviderFactory
from app.services.llm.provider_manager import (
    ProviderManager, 
    get_provider_manager, 
    initialize_providers,
    ModelPool,
    get_model_pool,
    initialize_model_pool,
    ModelMetrics,
    ModelConfig,
    ProviderStatus,
)

# Конкретные провайдеры — доступны для явного импорта при необходимости
from app.services.llm.llama_cpp_provider import LlamaCppProvider, create_llama_cpp_provider
from app.services.llm.openai_provider import OpenAIProvider
from app.services.llm.anthropic_provider import AnthropicProvider
from app.services.llm.ollama_provider import OllamaProvider
from app.services.llm.vllm_provider import VllmProvider, create_vllm_provider
from app.services.llm.mock_provider import MockProvider, MockConfig, create_mock_provider

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
    "OpenAIProvider",
    "AnthropicProvider",
    "OllamaProvider",
    "VllmProvider",
    "create_vllm_provider",
    "MockProvider",
    "MockConfig",
    "create_mock_provider",
]

