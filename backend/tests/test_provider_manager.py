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


def test_get_provider_for_capability_initialized(initialized_provider_manager):
    """Test get_provider_for_capability works after init."""
    pm = initialized_provider_manager
    
    # Test with known capability preference
    provider = pm.get_provider_for_capability("rules_reasoning")
    assert provider is not None
    assert provider.status == ProviderStatus.READY
    
    # Test general fallback
    provider = pm.get_provider_for_capability("unknown_capability")
    assert provider is not None  # Should fallback to any available


def test_model_pool_registration(initialized_model_pool):
    """ModelPool registration."""
    pool = initialized_model_pool
    configs = pool.list_model_configs()
    assert "qwen_7b" in configs
    assert "saiga" in configs


@pytest.mark.parametrize("capability,expected_keys", [
    ("general", ["qwen_7b"]), 
    ("rules_reasoning", ["saiga"]),
    ("dialogue", ["npc_major"]),
])
def test_preference_mapping(capability, expected_keys, initialized_provider_manager):
    """Verify capability preferences route correctly."""
    pm = initialized_provider_manager
    provider = pm.get_provider_for_capability(capability)
    assert provider is not None
    assert provider.key in expected_keys  # At least one preferred available


def test_provider_manager_is_ready(monkeypatch, initialized_provider_manager):
    """is_ready after init."""
    pm = initialized_provider_manager
    assert pm.is_ready is True


def test_get_any_available(monkeypatch, initialized_provider_manager):
    """Fallback to any available."""
    pm = initialized_provider_manager
    provider = pm.get_any_available()
    assert provider is not None
    assert provider.is_available()
