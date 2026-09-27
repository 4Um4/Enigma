# path: backend/tests/sandbox/micro/test_recognition_and_eavesdrop.py
"""
Тесты для S128 FIX: Персистенция player_recognition и механика Eavesdrop.
Проверяет, что имя NPC не сбрасывается после idle_tick и что подслушанные реплики попадают в журнал.

Запуск: cd backend; python -m pytest tests/sandbox/micro/test_recognition_and_eavesdrop.py -v
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.models.pipeline_context import PipelineContext


def test_eavesdrop_into_journal():
    """Тест: Если игрок в радиусе 8м, реплика NPC-NPC попадает в журнал аватара."""
    from app.services.events.npc_dialogue_subscriber import NpcDialogueSubscriber

    # Моки
    mock_avatar = MagicMock()
    mock_spatial = MagicMock()
    mock_spatial.player_distances.return_value = {"maid_lusya": 5.0}  # Игрок в 5 метрах
    # F2-гейт (:174-182): резолв актора идёт через _npc_positions. БЕЗ
    # явного словаря MagicMock автогенерирует truthy-атрибут без
    # __contains__ ('borko' not in MagicMock → True) → non-actor skip.
    # Явные позиции делают 'borko' актором + кормят INV-NPC-NAME резолв.
    mock_spatial._npc_positions = {
        "maid_lusya": {"name": "Люся", "local_position": {"x": 3.0, "y": 0.0}},
        "borko": {"name": "Борко", "local_position": {"x": 5.0, "y": 0.0}},
        "player": {"name": "ВВорг", "local_position": {"x": 8.0, "y": 0.0}},
    }

    sub = NpcDialogueSubscriber(
        memory_manager=MagicMock(),
        relationship_store=MagicMock(),
        avatar_service=mock_avatar,
        spatial_query_provider=lambda: mock_spatial,
        campaign_id_provider=lambda: "test_campaign",
        tick_provider=lambda: 0,  # H-01: callable()->int; тест не передавал —
        # негардированный вызов провайдера = TypeError, проглоченный try
    )

    # Событие: Люся говорит Борко
    event = SimpleNamespace(
        source="maid_lusya",
        timestamp=1,
        payload={"target_id": "borko", "text": "Привет, Борко", "tone": "FRIENDLY", "topic": "greeting"}
    )

    sub.on_npc_spoke(event)

    # Проверяем запись в журнал: call_args-подмножество (S292 добавил
    # channel/event_id/tick — точный матч легаси-вида невозможен).
    mock_avatar.append_journal.assert_called_once()
    _call = mock_avatar.append_journal.call_args
    assert _call.kwargs["campaign_id"] == "test_campaign"
    assert _call.kwargs["speaker"] == "Люся"  # INV-NPC-NAME: резолв из npc_positions
    assert _call.kwargs["text"] == "Привет, Борко"
    assert _call.kwargs["channel"] == "overheard"


def test_eavesdrop_out_of_range():
    """Тест: Если игрок дальше 8м, реплика НЕ попадает в журнал."""
    from app.services.events.npc_dialogue_subscriber import NpcDialogueSubscriber

    mock_avatar = MagicMock()
    mock_spatial = MagicMock()
    mock_spatial.player_distances.return_value = {"maid_lusya": 15.0}  # Игрок слишком далеко (>10м)

    sub = NpcDialogueSubscriber(
        memory_manager=MagicMock(),
        relationship_store=MagicMock(),
        avatar_service=mock_avatar,
        spatial_query_provider=lambda: mock_spatial,
        campaign_id_provider=lambda: "test_campaign",
        tick_provider=lambda: 0,  # H-01: callable()->int; тест не передавал —
        # негардированный вызов провайдера = TypeError, проглоченный try
    )

    event = SimpleNamespace(
        source="maid_lusya",
        timestamp=1,
        payload={"target_id": "borko", "text": "Привет, Борко", "tone": "FRIENDLY", "topic": "greeting"}
    )

    sub.on_npc_spoke(event)

    # Журнал не должен быть вызван
    mock_avatar.append_journal.assert_not_called()


def test_player_recognition_persists_in_run_turn():
    """Тест: Проверяет, что run_turn вызывает commit_tick_result, сохраняя player_recognition."""
    from app.models.schemas import ChatTurnRequest, PlayerAction
    from app.services.game_loop import GameLoop

    # Мокируем GameLoop, оставляя только тестируемую логику
    loop = GameLoop.__new__(GameLoop)
    loop.scene_manager = MagicMock()
    loop.scene_manager._tick_campaign_id = "test_camp"
    loop.avatar_service = MagicMock()
    loop._tick_orch = MagicMock()
    loop.system_requirements = MagicMock()
    loop.system_requirements.check.return_value = SimpleNamespace(meets=True, details={})
    loop._session_started_campaigns = set()
    loop.memory_manager = MagicMock()
    loop.memory_manager.persist_dm_response.return_value = "test_journal_id"
    loop.get_current_tick = MagicMock(return_value=0)
    
    # Имитируем, что ядро вернуло состояние с player_recognition
    _fresh_scene = {"player_recognition": {"maid_lusya": {"confidence": 1.0}}}
    loop._tick_orch.execute.return_value = SimpleNamespace(
        final_scene_state=_fresh_scene,
        all_npcs_raw=[],
        world_snapshot=None,
        observed_facts=[]
    )

    # Мокируем остальной pipeline (используем AsyncMock, так как run_turn вызывает await)
    import time
    from unittest.mock import AsyncMock
    # S-эпоха: run_turn делегирует в self._turn_pipeline.execute(...)
    # (game_loop.py:1421), а не в легаси _run_pipeline/run_agent_safe.
    # setattr — обходит статическую проверку типов (Pylance: SimpleNamespace
    # ≠ TurnPipeline; runtime-мок легален для изолированного теста).
    object.__setattr__(loop, "_turn_pipeline", SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(
            shared_context=PipelineContext(
                campaign_id="test_camp",
                world_id="w1",
                location="tavern",
                scene_state=_fresh_scene,
                player_state={},
                player_target_id="maid_lusya",
                will_conflict_data=None
            ),
            dm_result={"dm_response": "test"},
            observed_facts=[],
            world_tick_meta={"events": []},
            rules_result={},
            npc_result={},
            start_ms=int(time.time() * 1000)
        ))),
    )
    loop._build_traces = MagicMock(return_value=[])
    loop.dm_agent = MagicMock()
    loop.dm_agent.stream_narrate = MagicMock()
    
    # Мокируем TaskScheduler, чтобы избежать ленивой инициализации с зависимостями
    loop._get_task_scheduler = MagicMock()
    loop._get_task_scheduler.return_value.get_recent_dialogues.return_value = []

    req = ChatTurnRequest(
        campaign_id="test_camp",
        world_id="w1",
        location="tavern",
        actions=[PlayerAction(player_name="Tester", action="Привет")]
    )

    # Запускаем run_turn
    import asyncio
    from unittest.mock import AsyncMock
    with patch('app.services.memory.rce.extract_speech_events', return_value=[]), \
         patch('app.services.game_loop.game_loop.run_agent_safe', new=AsyncMock(return_value={"dm_response": "test"})), \
         patch('app.services.game_loop.turn_pipeline.run_agent_safe', new=AsyncMock(return_value={"dm_response": "test"})):
        asyncio.run(loop.run_turn(req))

    # Проверяем, что commit_tick_result был вызван с правильным scene_state
    loop.scene_manager.commit_tick_result.assert_called_once()
    _args, _kwargs = loop.scene_manager.commit_tick_result.call_args
    committed_scene = _kwargs.get("result_snapshot") or _args[1]
    
    assert "player_recognition" in committed_scene
    assert committed_scene["player_recognition"]["maid_lusya"]["confidence"] == 1.0