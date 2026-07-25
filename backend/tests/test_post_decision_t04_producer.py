# backend/tests/test_post_decision_t04_producer.py
"""
cd C:\\DDD\\Codex\\VSC_Enigma\\Enigma\backend
python -m pytest tests/test_post_decision_t04_producer.py -v
"""

from unittest.mock import MagicMock

import pytest
from app.domain.communication import CommunicationIntent, ExposureLevel
from app.services.phases.post_decision import run_phase_6_post_decision


@pytest.fixture
def mock_ctx():
    ctx = MagicMock()
    ctx.communication_intents = [
        CommunicationIntent(
            speaker="guard_borko",
            audience="merchant_goran",
            topic="торговля",
            intent_type="talk",
            emotional_state="нейтрально",
            exposure_level=ExposureLevel.from_semantic('normal')
        )
    ]
    ctx.tick_number = 1
    ctx.campaign_id = "test_camp"
    # ВАЖНО: scene_state должен быть реальным словарём, чтобы post_decision мог в него писать
    ctx.scene_state = {}
    
    # Мокаем npc_services и memory_manager
    mock_mem = MagicMock()
    mock_mem.summary = "Вчера ты пытался меня обмануть"
    
    ctx.npc_services = MagicMock()
    _cache_tuple = (mock_mem,)
    ctx.npc_services.memory_manager.load_narrative_from_sqlite.return_value = _cache_tuple
    ctx.npc_services.memory_manager.recall.return_value = [mock_mem]
    
    return ctx

def test_post_decision_fills_npc_npc_context(mock_ctx):
    orchestrator = MagicMock()
    
    run_phase_6_post_decision(mock_ctx, orchestrator)
    
    # Проверяем, что recall был вызван с правильным target_npc_id и правильным narrative_cache
    mock_ctx.npc_services.memory_manager.recall.assert_called_once()
    args, kwargs = mock_ctx.npc_services.memory_manager.recall.call_args
    assert kwargs.get('target_npc_id') == 'merchant_goran', f"recall вызван с неверным target_npc_id: {kwargs}"
    assert kwargs.get('narrative_cache') == (mock_ctx.npc_services.memory_manager.load_narrative_from_sqlite.return_value), f"narrative_cache не передан: {kwargs}"
    
    # Проверяем, что история попала в pending_tasks
    pending_tasks = mock_ctx.scene_state.get("pending_tasks", [])
    assert len(pending_tasks) > 0, "Задача не была создана"
    
    payload = pending_tasks[0].get("payload", {})
    history = payload.get("npc_npc_context", "")
    
    assert "Вчера ты пытался меня обмануть" in history, f"История не попала в npc_npc_context: {history}"