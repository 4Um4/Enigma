# backend/tests/test_dialogue_context_and_target.py
"""
cd backend
python -m pytest tests/test_dialogue_context_and_target.py -v
"""

import pytest
from unittest.mock import MagicMock, patch
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
    # Возвращаем богатый контекст с voice_profile и backstory
    def _provider(camp_id, npc_id):
        if npc_id == 'maid_lusya':
            return {
                'name': 'Люся', 
                'description': 'Служанка',
                'voice_profile': 'Тихо, запинаясь',
                'backstory': 'Работает у Торнина 3 года',
                'author_notes': 'Никогда не признаётся в связях с ворами'
            }
        if npc_id == 'guard_borko':
            return {'name': 'Борко', 'description': 'Стражник'}
        return {'name': npc_id, 'description': ''}
    return _provider

def _make_task(target_id='guard_borko', owner_id='maid_lusya'):
    req = DialogueRequest(
        topic='работа', target_id=target_id, exposure=ExposureLevel.from_semantic('normal')
    )
    return QueuedTask(
        task_id='t1', tick=1, counter=1, kind=TaskKind.DIALOGUE, 
        owner_id=owner_id, campaign_id='c1', priority=TaskPriority.NORMAL, payload=req
    )

def test_dialogue_executor_uses_voice_profile_and_resolves_target_name(mock_router, mock_context_provider):
    executor = DialogueExecutor(router=mock_router, context_provider=mock_context_provider)
    task = _make_task()
    
    list(executor.execute(task))
    
    # Проверяем, что роутер был вызван с правильным промптом
    args, kwargs = mock_router.request_for_agent.call_args
    user_prompt = kwargs.get('prompt', '')
    
    # L-03: voice_profile и backstory должны быть в промпте
    assert 'Тихо, запинаясь' in user_prompt, f"voice_profile не попал в промпт: {user_prompt}"
    assert 'Работает у Торнина 3 года' in user_prompt, f"backstory не попал в промпт: {user_prompt}"
    
    # L-05: target_id должен быть резолвлен в имя (Борко), не оставаться 'guard_borko'
    assert 'Борко' in user_prompt, f"Имя цели не резолвнулось: {user_prompt}"
    assert 'guard_borko' not in user_prompt, f"ID цели утёк в промпт: {user_prompt}"