#backend\tests\test_provider_manager.py
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[2]  # backend/
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
import pytest
from unittest.mock import Mock
from app.services.llm.provider_manager import (
    get_provider_manager, ProviderManager, ProviderType, ProviderStatus
)
from app.services.llm.provider import LlmProvider

def test_provider_registration():
    """Manual registration works with relative paths."""
    pm = get_provider_manager()
    
    # Mock provider
    mock_provider = Mock(spec=LlmProvider)
    mock_provider.is_available.return_value = True
    
    # Используем относительный путь к модели
    model_path = ROOT_DIR / "Models LLM" / "qwen2.5-7b-instruct-q4_k_m.gguf"
    
    # Корректный вызов register_provider
    model_provider = pm.register_provider(
        key="test_key",
        name="Test Model",
        provider=mock_provider,
        provider_type=ProviderType.LLAMA_CPP,
        path=str(model_path)
    )
    
    assert model_provider.key == "test_key"
    assert pm.get_provider("test_key") == model_provider


def test_provider_manager_singleton():
    """ProviderManager is singleton."""
    pm1 = get_provider_manager()
    pm2 = get_provider_manager()
    assert pm1 is pm2
    assert isinstance(pm1, ProviderManager)



def test_model_pool_registration(initialized_model_pool):
    """ModelPool registration."""
    pool = initialized_model_pool
    configs = pool.list_model_configs()
    assert "qwen_7b" in configs



    assert provider.is_available()
