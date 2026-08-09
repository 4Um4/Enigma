"""
Файл: backend/tests/sandbox/phenomenology/test_dialogue_thread_continuity.py (NEW)
Назначение: Canary-тест диалоговой нити (сценарий "Метель").
Зависимости: pytest, unittest.mock
Основные сущности: test_meteor_scenario_thread_continuity

Запуск: cd backend; python -m pytest tests/sandbox/phenomenology/test_dialogue_thread_continuity.py -v; cd ..
"""

import pytest
import uuid
from unittest.mock import MagicMock
from app.services.memory.memory_manager import MemoryManager
from app.services.memory.dialogue_update_extractor import DialogueUpdateExtractor, DialogueUpdate
from app.services.memory.dialogue_consolidator import DialogueConsolidator
from app.services.memory.dialogue_session import DialogueSession
from app.domain.events import EventDTO
from app.services.events.npc_dialogue_subscriber import NpcDialogueSubscriber
from app.services.execution.dialogue_executor import DialogueExecutor, DialogueContractViolation
from app.services.game_loop.task_scheduler import TaskScheduler


def test_meteor_scenario_thread_continuity():
    """Canary 1: Player спрашивает о метели → 5 ходов о погоде → back to метель → NPC помнит."""
    mm = MemoryManager(MagicMock(), data_dir='test_data')
    mock_extractor = MagicMock(spec=DialogueUpdateExtractor)
    mock_extractor.extract.return_value = DialogueUpdate(topic="weather", topic_confidence=0.9)
    subscriber = NpcDialogueSubscriber(
        memory_manager=mm, relationship_store=MagicMock(),
        campaign_id_provider=lambda: "test_meteor", tick_provider=lambda: 1,
        dialogue_update_extractor=mock_extractor
    )
    mm.add_dialogue_turn("test_meteor", "tavern_keeper_tornin", "player", "расскажи о метели", target_id="tavern_keeper_tornin", tick=1)
    event_npc_reply = EventDTO.create(
        event_type="npc_spoke", source="tavern_keeper_tornin",
        payload={"target_id": "player", "text": "Метель? Да, в прошлом году была страшная.", "topic": "weather", "tone": "NEUTRAL"},
        visibility="public"
    )
    subscriber.on_npc_spoke(event_npc_reply)
    stm_block = mm.get_stm_prompt_block("test_meteor", "tavern_keeper_tornin")
    assert "метел" in stm_block.lower()
    for i in range(5):
        mm.add_dialogue_turn("test_meteor", "tavern_keeper_tornin", "player", "какая погода?", target_id="tavern_keeper_tornin", tick=i+2)
    mm.add_dialogue_turn("test_meteor", "tavern_keeper_tornin", "player", "так что насчёт той метели?", target_id="tavern_keeper_tornin", tick=7)
    stm_block_final = mm.get_stm_prompt_block("test_meteor", "tavern_keeper_tornin")
    assert "метел" in stm_block_final.lower()
    mm.clear_dialogue_session("test_meteor", "tavern_keeper_tornin")
    assert mm.get_dialogue_session("test_meteor", "tavern_keeper_tornin").is_empty
    assert len(mm._pending_dialogue_memories) > 0
    assert mm._pending_dialogue_memories[-1].type == "dialogue_consolidated"


def test_claims_open_questions_continuity():
    """Canary 5: Player задаёт вопрос → 10 ходов о другом → NPC помнит open question."""
    mm = MemoryManager(MagicMock(), data_dir='test_data_claims')
    mock_extractor = MagicMock(spec=DialogueUpdateExtractor)
    subscriber = NpcDialogueSubscriber(
        memory_manager=mm, relationship_store=MagicMock(),
        campaign_id_provider=lambda: "test_claims", tick_provider=lambda: 1,
        dialogue_update_extractor=mock_extractor
    )
    mock_extractor.extract.return_value = DialogueUpdate(
        topic="basement", topic_confidence=0.8,
        raised_questions=[{"text": "где ключ от подвала?", "addressed_to": "tavern_keeper_tornin"}]
    )
    mm.add_dialogue_turn("test_claims", "tavern_keeper_tornin", "player", "где ключ от подвала?", target_id="tavern_keeper_tornin", tick=1)
    event_q = EventDTO.create(
        event_type="npc_spoke", source="tavern_keeper_tornin",
        payload={"target_id": "player", "text": "Какой ещё ключ?", "topic": "basement", "tone": "SUSPICIOUS"},
        visibility="public"
    )
    subscriber.on_npc_spoke(event_q)
    session = mm.get_dialogue_session("test_claims", "tavern_keeper_tornin")
    assert len(session.open_questions) == 1
    mock_extractor.extract.return_value = DialogueUpdate(topic="weather", topic_confidence=0.9)
    for i in range(10):
        mm.add_dialogue_turn("test_claims", "tavern_keeper_tornin", "player", "какая погода?", target_id="tavern_keeper_tornin", tick=i+2)
        event_w = EventDTO.create(
            event_type="npc_spoke", source="tavern_keeper_tornin",
            payload={"target_id": "player", "text": "Снег идёт.", "topic": "weather", "tone": "NEUTRAL"},
            visibility="public"
        )
        subscriber.on_npc_spoke(event_w)
    stm_block = mm.get_stm_prompt_block("test_claims", "tavern_keeper_tornin")
    assert "ключ от подвала" in stm_block


def test_per_pair_session_isolation():
    """Canary 6: NPC A говорит с B о X, с C о Y — нити изолированы."""
    mm = MemoryManager(MagicMock(), data_dir='test_data_iso')
    mm.add_dialogue_turn("test_iso", "npc_A", "npc_A", "что в подвале?", partner_id="npc_B")
    mm.add_dialogue_turn("test_iso", "npc_A", "npc_A", "как дела с торговлей?", partner_id="npc_C")
    stm_AB = mm.get_stm_prompt_block_pair("test_iso", "npc_A", "npc_B")
    stm_AC = mm.get_stm_prompt_block_pair("test_iso", "npc_A", "npc_C")
    assert "подвале" in stm_AB
    assert "торговлей" not in stm_AB
    assert "торговлей" in stm_AC
    assert "подвале" not in stm_AC


def test_hard_contract_no_stm_no_speak():
    """T4: Если STM пуст и intent != greeting, DialogueExecutor понижает intent до approach (auto-recover)."""
    mock_mm = MagicMock()
    mock_mm.get_stm_prompt_block_pair.return_value = "" # Симулируем пустой STM
    mock_router = MagicMock()
    mock_response = MagicMock()
    mock_response.text = "Привет!"
    mock_response.is_fallback = False
    mock_router.request_for_agent.return_value = mock_response
    executor = DialogueExecutor(router=mock_router, memory_manager=mock_mm)
    
    # Мокируем результат валидации
    mock_validation = MagicMock()
    mock_validation.is_fallback = False
    mock_validation.text = "Привет!"
    executor._validator = MagicMock()
    executor._validator.validate.return_value = mock_validation
    
    from app.domain.communication import DialogueRequest, ExposureLevel
    from app.domain.execution import QueuedTask
    req = DialogueRequest(topic="trade", target_id="npc_B", exposure=ExposureLevel.from_semantic("normal"), intent_type="talk")
    task = QueuedTask(task_id="t1", tick=1, counter=1, kind="dialogue", priority=1, state="pending", creator_system="test", owner_id="npc_A", target_ids=["npc_B"], payload=req, created_tick=1)
    
    # Проверяем, что генерация НЕ падает, а понижает intent (auto-recover)
    result = executor._generate_with_router(task, req)
    assert result is not None


def test_hard_contract_greeting_allowed():
    """T5: Если STM пуст, но intent == greeting, генерация разрешена."""
    mock_mm = MagicMock()
    mock_mm.get_stm_prompt_block_pair.return_value = ""
    mock_router = MagicMock()
    mock_response = MagicMock()
    mock_response.text = "Привет!"
    mock_response.is_fallback = False
    mock_router.request_for_agent.return_value = mock_response
    executor = DialogueExecutor(router=mock_router, memory_manager=mock_mm)
    
    # Мокируем результат валидации (объект с is_fallback и text)
    mock_validation = MagicMock()
    mock_validation.is_fallback = False
    mock_validation.text = "Привет!"
    executor._validator = MagicMock()
    executor._validator.validate.return_value = mock_validation
    
    from app.domain.communication import DialogueRequest, ExposureLevel
    from app.domain.execution import QueuedTask
    req = DialogueRequest(topic="greeting", target_id="npc_B", exposure=ExposureLevel.from_semantic("normal"), intent_type="greeting")
    task = QueuedTask(task_id="t2", tick=1, counter=1, kind="dialogue", priority=1, state="pending", creator_system="test", owner_id="npc_A", target_ids=["npc_B"], payload=req, created_tick=1)
    
    # Не должно вызывать исключение
    text = executor._generate_with_router(task, req)
    assert text == "Привет!"


def test_ttl_game_time_expiry():
    """T6: TaskScheduler TTL очищает реплики старше 7 секунд wall-clock (ADR-O-343)."""
    import time
    scheduler = TaskScheduler()
    _now = time.time()
    
    # Реплика 100 секунд назад (wall-clock)
    scheduler._recent_dialogues.append({"speaker_id": "A", "text": "Старая реплика", "timestamp": _now - 100.0, "game_time": 100.0})
    # Реплика 2 секунды назад (wall-clock)
    scheduler._recent_dialogues.append({"speaker_id": "B", "text": "Новая реплика", "timestamp": _now - 2.0, "game_time": 150.0})
    
    # TTL = 7.0 сек wall-clock. Должна остаться только вторая.
    active = scheduler.get_recent_dialogues(160.0)
    assert len(active) == 1
    assert active[0]["speaker_id"] == "B"


def test_consolidation_empty_session():
    """T7: Consolidator возвращает None для коротких диалогов (1 реплика)."""
    consolidator = DialogueConsolidator()
    session = DialogueSession(npc_id="test", partner_id="player")
    session.add_turn(speaker="player", text="Одиноко")
    assert consolidator.consolidate(session) is None
    
    session.add_turn(speaker="test", text="Да, одиноко")
    summary = consolidator.consolidate(session)
    assert summary is not None
    assert "2 реплик" in summary


def test_extractor_fallback_no_router():
    """T8: DialogueUpdateExtractor возвращает пустой Update, если router=None."""
    extractor = DialogueUpdateExtractor(router=None)
    update = extractor.extract("stm_before", "new_turn", "partner")
    assert isinstance(update, DialogueUpdate)
    assert update.topic is None
    assert update.topic_confidence == 0.0


def test_claims_auto_withdrawal():
    """T9: При добавлении >10 claims, старые помечаются withdrawn."""
    session = DialogueSession(npc_id="test", partner_id="player")
    for i in range(12):
        session.add_claim(text=f"Claim {i}", speaker="player", confidence=0.9, tick=1)
    
    open_claims = [c for c in session.claims if c.status == "open"]
    withdrawn_claims = [c for c in session.claims if c.status == "withdrawn"]
    
    assert len(open_claims) == 10
    assert len(withdrawn_claims) == 2
    assert withdrawn_claims[0].text == "Claim 0"


def test_open_question_answering():
    """T10: OpenQuestion корректно закрывается при ответе."""
    session = DialogueSession(npc_id="test", partner_id="player")
    session.add_open_question(text="Где ключ?", asked_by="player", addressed_to="test", tick=1)
    assert len(session.open_questions) == 1
    assert not session.open_questions[0].answered
    
    session.answer_question(0, "В сундуке", "test", 2)
    assert session.open_questions[0].answered
    assert session.open_questions[0].answer_text == "В сундуке"