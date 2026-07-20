# path: backend/tests/sandbox/micro/test_recognition_and_eavesdrop.py
"""
Тесты для S128 FIX: Персистенция player_recognition и механика Eavesdrop.
Проверяет, что имя NPC не сбрасывается после idle_tick и что подслушанные реплики попадают в журнал.

Запуск: cd backend; python -m pytest tests/sandbox/micro/test_recognition_and_eavesdrop.py -v
"""

import pytest
from unittest.mock import MagicMock, patch
from types import SimpleNamespace


def test_eavesdrop_into_journal():
    """Тест: Если игрок в радиусе 8м, реплика NPC-NPC попадает в журнал аватара."""
    from app.services.events.npc_dialogue_subscriber import NpcDialogueSubscriber

    # Моки
    mock_avatar = MagicMock()
    mock_spatial = MagicMock()
    mock_spatial.player_distances.return_value = {"maid_lusya": 5.0}  # Игрок в 5 метрах

    sub = NpcDialogueSubscriber(
        memory_manager=MagicMock(),
        relationship_store=MagicMock(),
        avatar_service=mock_avatar,
        spatial_query_provider=lambda: mock_spatial,
        campaign_id_provider=lambda: "test_campaign"
    )

    # Событие: Люся говорит Борко
    event = SimpleNamespace(
        source="maid_lusya",
        timestamp=1,
        payload={"target_id": "borko", "text": "Привет, Борко", "tone": "FRIENDLY", "topic": "greeting"}
    )

    sub.on_npc_spoke(event)

    # Проверяем, что реплика записана в журнал игрока
    mock_avatar.append_journal.assert_called_once_with(
        campaign_id="test_campaign", speaker="maid_lusya", text="Привет, Борко"
    )


def test_eavesdrop_out_of_range():
    """Тест: Если игрок дальше 8м, реплика НЕ попадает в журнал."""
    from app.services.events.npc_dialogue_subscriber import NpcDialogueSubscriber

    mock_avatar = MagicMock()
    mock_spatial = MagicMock()
    mock_spatial.player_distances.return_value = {"maid_lusya": 15.0}  # Игрок слишком далеко

    sub = NpcDialogueSubscriber(
        memory_manager=MagicMock(),
        relationship_store=MagicMock(),
        avatar_service=mock_avatar,
        spatial_query_provider=lambda: mock_spatial,
        campaign_id_provider=lambda: "test_campaign"
    )

    event = SimpleNamespace(
        source="maid_lusya",
        timestamp=1,
        payload={"target_id": "borko", "text": "Привет, Борко", "tone": "FRIENDLY", "topic": "greeting"}
    )

    sub.on_npc_spoke(event)

    # Журнал не должен быть вызван
    mock_avatar.append_journal.assert_not_called()


@pytest.mark.asyncio
async def test_player_recognition_persists_in_run_turn():
    """Тест: Проверяет, что run_turn вызывает commit_tick_result, сохраняя player_recognition."""
    from app.services.game_loop import GameLoop
    from app.models.schemas import ChatTurnRequest, PlayerAction

    # Мокируем GameLoop, оставляя только тестируемую логику
    loop = GameLoop.__new__(GameLoop)
    loop.scene_manager = MagicMock()
    loop.scene_manager._tick_campaign_id = "test_camp"
    loop.avatar_service = MagicMock()
    loop._tick_orch = MagicMock()
    
    # Имитируем, что ядро вернуло состояние с player_recognition
    _fresh_scene = {"player_recognition": {"maid_lusya": {"confidence": 1.0}}}
    loop._tick_orch.execute.return_value = SimpleNamespace(
        final_scene_state=_fresh_scene,
        all_npcs_raw=[],
        world_snapshot=None,
        observed_facts=[]
    )

    # Мокируем остальной pipeline
    loop._run_pipeline = MagicMock(return_value=SimpleNamespace(
        shared_context=SimpleNamespace(scene_state=_fresh_scene, player_target_id="maid_lusya"),
        dm_result={"dm_response": "test"},
        observed_facts=[]
    ))
    loop._build_traces = MagicMock(return_value=[])
    loop.dm_agent = MagicMock()
    loop.dm_agent.stream_narrate = MagicMock()

    req = ChatTurnRequest(
        campaign_id="test_camp",
        world_id="w1",
        location="tavern",
        actions=[PlayerAction(player_name="Tester", action="Привет")]
    )

    # Запускаем run_turn
    with patch('app.services.memory.rce.extract_speech_events', return_value=[]):
        await loop.run_turn(req)

    # Проверяем, что commit_tick_result был вызван с правильным scene_state
    loop.scene_manager.commit_tick_result.assert_called_once()
    _args, _kwargs = loop.scene_manager.commit_tick_result.call_args
    committed_scene = _kwargs.get("result_snapshot") or _args[1]
    
    assert "player_recognition" in committed_scene
    assert committed_scene["player_recognition"]["maid_lusya"]["confidence"] == 1.0