# backend/tests/test_dialogue_npc_npc_context.py
"""
cd C:\DDD\Codex\VSC_Enigma\Enigma\backend
python -m pytest tests/test_dialogue_npc_npc_context.py -v
"""

import pytest
from unittest.mock import MagicMock
from app.services.execution.dialogue_executor import DialogueExecutor
from app.domain.execution import QueuedTask, TaskKind, TaskPriority
from app.domain.communication import DialogueRequest, ExposureLevel

@pytest.fixture
def mock_router():
    router = MagicMock()
    router.request_for_agent.return_value = 'Привет.'
    return router

@pytest.fixture
def mock_context_provider():
    return lambda camp_id, npc_id: {'name': 'Тест', 'description': 'Тестовый NPC'}

def _make_task(target_id='target_npc', owner_id='npc1', history="Мы встречались вчера у бара"):
    req = DialogueRequest(
        topic='test', 
        target_id=target_id, 
        exposure=ExposureLevel.from_semantic('normal'),
        npc_npc_context=history
    )
    return QueuedTask(
        task_id='t1', tick=1, counter=1, kind=TaskKind.DIALOGUE, 
        owner_id=owner_id, campaign_id='c1', priority=TaskPriority.NORMAL, payload=req
    )

def test_dialogue_executor_includes_npc_npc_context(mock_router, mock_context_provider):
    executor = DialogueExecutor(router=mock_router, context_provider=mock_context_provider)
    task = _make_task()
    
    list(executor.execute(task))
    
    # Проверяем, что история попала в промпт
    args, kwargs = mock_router.request_for_agent.call_args
    user_prompt = kwargs.get('prompt', '')
    assert 'Мы встречались вчера у бара' in user_prompt, f"История не попала в промпт: {user_prompt}"