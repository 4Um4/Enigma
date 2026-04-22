# C:\DDD\Codex\VSC_Enigma\Enigma\backend\tests\conftest.py
"""
conftest.py — общие фикстуры для тестов ENIGMA
"""

import sys
from pathlib import Path

# === ФИКС ИМПОРТОВ ДЛЯ ТЕСТОВ ===
# Добавляем оба возможных пути, чтобы pytest гарантированно видел пакет "app"
root = Path(__file__).resolve().parents[2]          # Enigma/
backend = root / "backend"

if str(root) not in sys.path:
    sys.path.insert(0, str(root))
if str(backend) not in sys.path:
    sys.path.insert(0, str(backend))

# Теперь импорты from app... должны работать
import pytest
from unittest.mock import Mock, patch

from app.services.llm.provider_manager import (
    get_provider_manager, 
    get_model_pool, 
    ModelConfig
)
from app.services.llm.provider import LlmProvider, ProviderType, ProviderInfo
from app.services.llm.router import ModelRouter, get_router


@pytest.fixture(scope="session")
def initialized_provider_manager():
    """Initialize ProviderManager with mock providers to avoid real model loads."""
    pm = get_provider_manager()
    
    # Mock ProviderFactory.create to return dummy provider
    with patch('app.services.llm.factory.create_llama_cpp_provider') as mock_factory:
        mock_provider = Mock(spec=LlmProvider)
        mock_provider.is_available.return_value = True
        mock_provider.get_info.return_value = ProviderInfo(
            name="test_model", provider_type=ProviderType.LLAMA_CPP, model_name="test_model", context_size=4096, vram_mb=1000, is_available=True
        )
        mock_provider.complete.return_value = '{"response": "test"}'
        mock_factory.return_value = mock_provider
        
        # Initialize
        results = pm.initialize_all()
    
    assert all(results.values()), "Provider init failed"
    assert pm.is_ready
    
    yield pm
    
    # Cleanup: unload models
    pass  # ProviderManager has no unload_all; ModelPool does


@pytest.fixture(scope="session")
def initialized_model_pool():
    """Initialize ModelPool with test configs."""
    pool = get_model_pool()
    
    # Register mock configs (dummy paths)
    test_configs = [
        ModelConfig(key="qwen_7b", name="Test Qwen", provider_type=ProviderType.LLAMA_CPP, path="/test/path/Qwen2.5-7B-Instruct-abliterated-v2.Q5_K_M.gguf"),
    ]
    
    for config in test_configs:
        pool.register_model_config(config)
    
    # Mock get_model_async to return dummy provider
    with patch.object(pool, 'get_model_async') as mock_get:
        mock_provider = Mock()
        mock_provider.is_available.return_value = True
        mock_provider.provider.complete.return_value = "mock response"
        mock_get.return_value = mock_provider
        
        yield pool


@pytest.fixture
def mock_model_router(monkeypatch):
    """Mock ModelRouter.request to return deterministic response."""
    def mock_request(self, capability, prompt, params=None, system_prompt=None):
        return {
            "dm_response": f"Mock narrative for {capability}",
            "npc_reactions": [],
            "world_changes": []
        }
    
    monkeypatch.setattr(ModelRouter, 'request', mock_request)
    monkeypatch.setattr('app.services.llm.router.ModelRouter.request', mock_request)
    
    router = get_router()
    yield router


@pytest.fixture(autouse=True)
def test_environment(monkeypatch):
    ROOT_DIR = Path(__file__).resolve().parents[2]  # Enigma/backend
    DATA_DIR = ROOT_DIR / "data"
    MODELS_DIR = ROOT_DIR.parents[0] / "Models LLM"  # Enigma/Models LLM

    monkeypatch.setattr('app.core.config.settings.model_qwen_7b_path', MODELS_DIR / 'Qwen2.5-7B-Instruct-abliterated-v2.Q5_K_M.gguf')

