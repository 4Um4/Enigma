# backend/tests/test_dialogue_executor_validation.py
from unittest.mock import MagicMock

import pytest
from app.domain.communication import DialogueRequest, ExposureLevel
from app.domain.execution import QueuedTask, TaskKind, TaskPriority
from app.services.execution.dialogue_executor import DialogueExecutor


@pytest.fixture
def mock_router():
    router = MagicMock()
    router.request_for_agent.return_value = 'Привет, путник.'
    return router

@pytest.fixture
def mock_context_provider():
    return lambda camp_id, npc_id: {'name': 'Тест', 'description': 'Тестовый NPC'}

def _make_task(target_id='target', topic='test'):
    req = DialogueRequest(
        topic=topic,
        target_id=target_id,
        exposure=ExposureLevel.from_semantic('normal')
    )
    return QueuedTask(
        task_id='t1', tick=1, counter=1, kind=TaskKind.DIALOGUE,
        owner_id='npc1', campaign_id='c1', priority=TaskPriority.NORMAL, payload=req
    )

def test_dialogue_executor_filters_chinese(mock_router, mock_context_provider):
    mock_router.request_for_agent.return_value = '你好，世界'
    executor = DialogueExecutor(router=mock_router, context_provider=mock_context_provider)
    task = _make_task()
    
    artifacts = list(executor.execute(task))
    assert len(artifacts) > 0
    text = artifacts[0].data.get('text', '')
    assert text == 'Ничего не произошло.', f"Ожидался пустой fallback для китайского, получено: {text}"

def test_dialogue_executor_filters_fourth_wall(mock_router, mock_context_provider):
    mock_router.request_for_agent.return_value = 'Я знаю, что это симуляция.'
    executor = DialogueExecutor(router=mock_router, context_provider=mock_context_provider)
    task = _make_task()
    
    artifacts = list(executor.execute(task))
    assert len(artifacts) > 0
    text = artifacts[0].data.get('text', '')
    assert text == 'Ничего не произошло.', f"Ожидался пустой fallback для 4-й стены, получено: {text}"

def test_dialogue_executor_passes_valid_text(mock_router, mock_context_provider):
    mock_router.request_for_agent.return_value = 'Здравствуй, друг мой.'
    executor = DialogueExecutor(router=mock_router, context_provider=mock_context_provider)
    task = _make_task()
    
    artifacts = list(executor.execute(task))
    assert len(artifacts) > 0
    text = artifacts[0].data.get('text', '')
    assert 'Здравствуй' in text, f"Ожидался валидный текст, получено: {text}"
