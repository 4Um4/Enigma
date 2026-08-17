"""
Файл: backend/tests/sandbox/phenomenology/test_dialogue_context_binding.py
Назначение: Тесты S200 — связывание контекста диалога с IntentCompressor.
Зависимости: pytest, app.services.input.intent_compressor, app.services.memory.dialogue_session
Основные сущности: test_continue_act_with_context, test_continue_act_without_context

Запуск: cd backend; python -m pytest tests/sandbox/phenomenology/test_dialogue_context_binding.py -v; cd ..
"""

import pytest
from app.services.input.intent_compressor import IntentCompressor
from app.services.memory.dialogue_session import DialogueSession

class MockLLMClient:
    """Mock LLM client для изоляции тестов IntentCompressor."""
    async def compress_intent(self, raw_text: str, scene_context: dict, dialogue_session=None) -> dict:
        # В реальности это делает LLM, но для теста Fast Path мы возвращаем None,
        # чтобы проверить, что Fast Path срабатывает ДО LLM.
        return None

@pytest.fixture
def compressor():
    return IntentCompressor(MockLLMClient())

@pytest.fixture
def active_session():
    """Сессия с активным диалогом."""
    session = DialogueSession(npc_id="tavern_keeper_tornin", partner_id="player")
    session.add_turn(speaker="tavern_keeper_tornin", text="И тут я ему и говорю...", tick=1)
    return session

def test_continue_act_with_context(compressor, active_session):
    """Если есть активный диалог и игрок пишет 'продолжай', это SpeechAct.CONTINUE."""
    result = compressor._fast_path_parse("продолжай", active_session)
    
    assert result is not None
    assert result.conversation_continuation == "CONTINUE"
    # Проверяем, что dialogue_thread_id пробросился
    assert result.dialogue_thread == active_session.thread_id

def test_continue_act_without_context(compressor):
    """Если нет активного диалога, 'продолжай' не должно быть CONTINUE."""
    result = compressor._fast_path_parse("продолжай", None)
    
    # Без контекста 'продолжай' не матчится ни на один action в _ACTION_LEMMAS
    # и не должно возвращать CONTINUE
    if result is not None:
        assert result.conversation_continuation != "CONTINUE"
    # Если result is None — это тоже валидно (Fast Path не сработал, пойдёт в LLM)

def test_question_with_context(compressor, active_session):
    """Если есть активный диалог и игрок пишет 'а что?', это должно уйти в LLM (None от Fast Path)."""
    result = compressor._fast_path_parse("а что?", active_session)
    
    # 'что' не является глаголом действия, поэтому Fast Path вернёт None
    # и запрос уйдёт в LLM, которая (благодаря контексту) должна вернуть QUESTION.
    assert result is None

def test_empty_session_does_not_trigger_continue(compressor):
    """Пустая сессия не должна триггерить CONTINUE."""
    empty_session = DialogueSession(npc_id="tavern_keeper_tornin", partner_id="player")
    result = compressor._fast_path_parse("ну?", empty_session)
    
    if result is not None:
        assert result.conversation_continuation != "CONTINUE"