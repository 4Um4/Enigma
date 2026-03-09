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
"""

from app.services.llm.provider import LlmProvider, GenerationParams, ProviderInfo, ProviderType
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

__all__ = [
    # Core interfaces
    "LlmProvider",
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
]

