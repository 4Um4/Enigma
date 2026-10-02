"""path: /project/backend/tests/micro/test_fast_incomplete_question.py

Назначение: Canonicalization/arbitration boundary (вердикт Мастера):
    однопредложенный вопрос без semantic_acts = incomplete → LLM slow-path.
    Контроль: утверждение без acts — complete; вопрос с acts — complete
    (без повторного вызова); физические действия — прежний критерий зоны.
Зависимости: app.services.input.intent_compressor, app.domain.intent_profile.
Запуск: cd backend; python -m pytest tests/micro/test_fast_incomplete_question.py -v; cd ..
"""

from app.domain.intent_profile import ActionType, IntentSemanticField, SpeechAct
from app.services.input.intent_compressor import IntentCompressor


def _field(action=ActionType.DIALOGUE, acts=None, speech_act="question", raw="вопрос?"):
    """IntentSemanticField: speech_act — канонический SpeechAct-enum."""
    return IntentSemanticField(
        action=action,
        raw_text=raw,
        speech_act=SpeechAct(speech_act) if speech_act else None,
        semantic_acts=acts or [],
    )


def test_question_without_acts_is_incomplete():
    c = IntentCompressor.__new__(IntentCompressor)  # без LLM-клиента
    f = _field()
    assert c._fast_incomplete(f, {}) is True


def test_assert_without_acts_is_complete():
    c = IntentCompressor.__new__(IntentCompressor)
    f = _field(speech_act="assert", raw="утверждение")
    assert c._fast_incomplete(f, {}) is False


def test_question_with_acts_is_complete():
    c = IntentCompressor.__new__(IntentCompressor)
    f = _field(acts=[{"type": "QUESTION", "params": {"topic": "provenance"}}])
    assert c._fast_incomplete(f, {}) is False