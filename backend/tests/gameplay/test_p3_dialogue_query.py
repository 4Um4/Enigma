# path: /project/backend/tests/gameplay/test_p3_dialogue_query.py
# Назначение: M1/P3 — гейт семантического входного провода: QUESTION-акт +
#   SubjectRef-ось (коррекция Мастера: без ASK_*-склейки). Инварианты:
#   N1 (не-вопрос != QUESTION), N2 (акт переживает нерезолв),
#   A/A (идентичный парс), 10 ТЗ-фраз. Без LLM (fast-path).
# Зависимости: app.services.input.intent_compressor (fast-path, offline)
# Основные сущности: test_p3_*
import pytest

from app.domain.epistemology import SpeechAct
from app.domain.subject_ref import SubjectKind
from app.services.input.intent_compressor import (
    IntentCompressor,
    extract_subject,
    _is_question,
)


def _compress(text: str):
    """Fast-path парс без LLM (lemmas+ACTION_LEMMAS). Offline-гейт P3."""
    c = IntentCompressor(llm_client=None)
    return c._fast_path_parse(text)


CASES = [
    # (фраза, expect_question, expect_kind, expect_id_contains)
    ("Что ты знаешь о Люсе?", True, SubjectKind.NPC, "maid_lusya"),
    ("Ты видел что-нибудь странное?", True, SubjectKind.UNKNOWN, None),
    ("Почему Горан нервничает?", True, SubjectKind.UNKNOWN, None),
    ("Расскажи про тот караван", True, SubjectKind.CANON_TOPIC, "borko_negligence"),
    ("Что ты знаешь о подвалe таверны?", True, SubjectKind.CANON_TOPIC, None),
    ("Кто платит тебе деньги?", True, SubjectKind.UNKNOWN, None),
]


@pytest.mark.parametrize("text,expect_q,kind,sid", CASES)
def test_p3_question_with_subject(text, expect_q, kind, sid):
    f = _compress(text)
    if not expect_q:
        assert f is None or f.speech_act is not SpeechAct.QUESTION
        return
    assert f is not None, f"fast-path не распознал вопрос: {text!r}"
    assert f.speech_act is SpeechAct.QUESTION
    assert f.subject_kind == kind.value
    if sid:
        assert sid in (f.subject_id or "")


def test_p3_n1_not_a_question():
    """N1: чистое действие — не QUESTION (слабые «что» без '?' не считают)."""
    f = _compress("наливаю пиво")
    assert f is None or f.speech_act is not SpeechAct.QUESTION, (
        f"N1 FAIL: «наливаю пиво» стало QUESTION ({f and f.speech_act})"
    )


def test_p3_n2_question_survives_resolution_failure():
    """N2: акт независим от резолва — неизвестный предмет сохраняет hint."""
    f = _compress("Ты видел что-нибудь странное?")
    assert f is not None
    assert f.speech_act is SpeechAct.QUESTION
    assert f.subject_kind == SubjectKind.UNKNOWN.value
    assert f.subject_hint  # hint пережил нерезолв


def test_p3_aa_identical_parse():
    """A/A (анти-CFG): повторный парс — идентичное поле."""
    for text, _, _, _ in CASES:
        a = _compress(text)
        b = _compress(text)
        assert (a is None) == (b is None)
        if a is not None:
            assert a.model_dump(exclude={"confidence"}) == b.model_dump(
                exclude={"confidence"}
            ), f"A/A дрейф: {text!r}"


def test_p3_extractor_deterministic():
    """Экстрактор детерминирован и LLM-независим (тот же вход = тот же SubjectRef)."""
    for text in ("Что ты знаешь о Люсе?", "Расскажи про караван",
                 "Почему Горан нервничает?"):
        a = extract_subject(text)
        b = extract_subject(text)
        assert a == b, f"недетерминизм: {text!r}"


def test_p3_is_question_gate():
    """N1-механика: сильные/средние индикаторы; «кто/что» только с '?'."""
    assert _is_question({"спросить"}, "расскажи")
    assert _is_question({"почему"}, "почему он молчит")
    assert _is_question({"видел"}, "ты видел")
    assert not _is_question({"пиво", "наливаю"}, "наливаю пиво")
    assert not _is_question({"что"}, "что наливаю")  # без '?'
    assert _is_question({"что"}, "что наливаю?")
