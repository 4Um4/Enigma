"""
path: backend/tests/sandbox/micro/test_r8_continue_gate.py
Назначение: R8 — сужение continue-гейта: союз «и» больше не перехватывает приказы в CONTINUE; явное «продолжай» работает
Зависимости: app.services.input.intent_compressor
Основные сущности: IntentCompressor._fast_path_parse

Запуск: cd backend; python -m pytest tests/sandbox/micro/test_r8_continue_gate.py -v --tb=short; cd ..
"""
from unittest.mock import MagicMock

from app.services.input.intent_compressor import IntentCompressor


def _comp():
    return IntentCompressor(llm_client=MagicMock())


def _session():
    s = MagicMock()
    s.is_empty = False
    s.thread_id = "t1"
    return s


def test_union_no_longer_hijacks_order():
    # Живой кейс R8: приказ с союзом при живой сессии был CONTINUE
    result = _comp()._fast_path_parse("Подойди сюда и поговори со мной", _session())
    assert result.conversation_continuation != "CONTINUE"
    assert result.speech_act is None or result.speech_act.value != "continue"


def test_explicit_continue_still_works():
    result = _comp()._fast_path_parse("продолжай", _session())
    assert result.conversation_continuation == "CONTINUE"
