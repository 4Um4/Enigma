# path: /project/backend/tests/test_e0_t2b_dialogue_execution.py
# T2b-1: Production Dialogue Execution Test
# CommunicationIntent -> DialogueExecutor -> mock-LLM -> DialogueMaterializer -> NPC_SPOKE
import pytest
from unittest.mock import MagicMock
from app.domain.communication import DialogueRequest, ExposureLevel
from app.domain.execution import QueuedTask, TaskKind, TaskPriority
from app.services.execution.dialogue_executor import DialogueExecutor
from app.services.execution.dialogue_materializer import DialogueMaterializer
from app.services.events.event_bus import EventBus
from app.services.events.event_types import EventType

_MOCK_LLM_RESPONSE = 'Я слышал, что караван задерживается. Нужно быть осторожнее.'

def _make_mock_router():
    router = MagicMock()
    router.request_for_agent.return_value = _MOCK_LLM_RESPONSE
    return router

def _make_task(speaker, audience, topic):
    req = DialogueRequest(
        topic=topic,
        target_id=audience,
        exposure=ExposureLevel.from_semantic('normal'),
    )
    return QueuedTask(
        task_id='t2b-1', tick=1, counter=1,
        kind=TaskKind.DIALOGUE, owner_id=speaker,
        campaign_id='c1', priority=TaskPriority.NORMAL, payload=req,
    )

def test_t2b_production_dialogue_execution_path():
    mock_router = _make_mock_router()
    executor = DialogueExecutor(
        router=mock_router,
        context_provider=lambda camp_id, npc_id: {'name': npc_id, 'description': ''},
    )
    task = _make_task('maid_lusya', 'tavern_keeper_tornin', 'безопасность')
    artifacts = list(executor.execute(task))
    assert artifacts, 'Executor returned empty list'
    dialogue_artifacts = [a for a in artifacts if a.result_type == 'dialogue_line' and a.success]
    assert dialogue_artifacts, f'No success dialogue_line. All: {[(a.result_type, a.success) for a in artifacts]}'
    artifact = dialogue_artifacts[-1]
    assert 'speaker_id' in artifact.data, f'Missing speaker_id: {list(artifact.data.keys())}'
    assert 'text' in artifact.data, f'Missing text: {list(artifact.data.keys())}'
    assert artifact.data['speaker_id'] == 'maid_lusya'
    materializer = DialogueMaterializer()
    events = list(materializer.materialize(artifact))
    npc_spoke = [e for e in events if getattr(e, 'type', '') == EventType.NPC_SPOKE.value]
    assert npc_spoke, f'No NPC_SPOKE. Events: {[getattr(e, "type", "?") for e in events]}'
    event = npc_spoke[0]
    assert event.source == 'maid_lusya', f'Wrong speaker: {event.source}'
    assert event.payload.get('target_id') == 'tavern_keeper_tornin'
    assert event.payload.get('topic') == 'безопасность'
    _text = event.payload.get('text', '')
    assert isinstance(_text, str) and len(_text) > 0, f'Empty text: {_text}'
    bus = EventBus()
    received = []
    bus.subscribe(EventType.NPC_SPOKE, lambda e: received.append(e))
    bus.publish(event)
    assert len(received) == 1
    assert received[0].source == 'maid_lusya'
    assert received[0].payload.get('text') == _text
    assert mock_router.request_for_agent.called, 'LLM not called - executor used stub/deterministic'