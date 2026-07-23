# backend/tests/test_new_7_tick_crash.py
"""
Тест на регрессию NEW-7: TICK_CRASH из-за отсутствия action_type в SimpleNamespace.
Проверяет, что decision.py использует getattr для безопасного извлечения action_type.
Запуск: cd backend
python -m pytest tests/test_new_7_tick_crash.py -v
"""
import types
import pytest
from unittest.mock import MagicMock
from app.services.dto import _TickContext
from app.services.phases.decision import assemble_preloaded_data

def test_new_7_idle_tick_simple_namespace_does_not_crash():
    """
    Сценарий: idle_tick передаёт shared_context как types.SimpleNamespace().
    Проверка: assemble_preloaded_data не должна падать с AttributeError.
    """
    # 1. Arrange
    mock_ctx = _TickContext(
        campaign_id="test",
        scene_state={},
        tick_number=1,
        drf_bus=MagicMock(),
        all_npcs_raw=[{"id": "test_npc"}],
        shared_context=types.SimpleNamespace() # Эмулируем idle_tick
    )
    
    mock_svc = MagicMock()
    mock_svc.social_engine.compute_social_modifiers.return_value = {}
    mock_svc.memory_manager.get_identity_traits.return_value = []
    mock_svc.reputation_engine.compute_reputation_modifier.return_value = {}
    mock_svc.economic_profiles.get.return_value = {}
    
    # 2. Act & Assert
    try:
        assemble_preloaded_data(mock_ctx, mock_svc)
    except AttributeError as e:
        pytest.fail(f"assemble_preloaded_data упал с AttributeError: {e}. Фикс NEW-7 не работает!")