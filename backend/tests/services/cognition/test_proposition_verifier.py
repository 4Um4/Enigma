"""
path: /backend/tests/services/cognition/test_proposition_verifier.py
Назначение: P5-B4 — контракты семантической верификации Proposition ↔ LLM-текст.

Покрывает 4 сценария Master'а:
  1. CORRECT (Master случай 1): LLM действительно сообщает «player X оскорбил Y» → YES
  2. SILENCE (Master случай 2): LLM не затрагивает proposition → NO
  3. NEGATION (Master случай 3): LLM явно отрицает proposition → NO
  4. DISTORTION (Master случай 4): LLM говорит про другой объект → NO

Дополнительно покрывает условия A/B/C/D из Master review:
  A (порядок/timeout): timeout исключение → fail-closed
  C (отрицания в store): polarity=False корректно обрабатывается
  D (ошибка verifier): LLM failure / пустой ответ / неоднозначный verdict → NO
"""
from __future__ import annotations

import pytest

from app.services.cognition.proposition_verifier import (
    PassthroughVerifier,
    PropositionVerifier,
)


class _StubLLM:
    """LLM-клиент, который возвращает предзаготовленный ответ или бросает исключение."""

    def __init__(
        self,
        response: str = "YES",
        *,
        fail: bool = False,
        fail_with_timeout: bool = False,
    ):
        self._response = response
        self._fail = fail
        self._fail_with_timeout = fail_with_timeout
        self.calls: list[tuple[str, dict]] = []

    def complete(
        self,
        prompt: str,
        *,
        max_tokens: int = 16,
        timeout: float | None = None,
    ) -> str:
        self.calls.append((prompt, {"max_tokens": max_tokens, "timeout": timeout}))
        if self._fail_with_timeout:
            raise TimeoutError(f"LLM timed out after {timeout}s (test stub)")
        if self._fail:
            raise RuntimeError("LLM unavailable (test stub)")
        return self._response


PROP_INSULT = {
    "subject": "Open_road",
    "predicate": "INSULTED",
    "object": "tornin",
    "polarity": True,
}


def test_correct_transmission_returns_true():
    """Master случай 1: LLM-реплика действительно сообщает proposition → YES."""
    text = (
        "Торнин, я слышала от Люси, что этот Open_road оскорбил вас "
        "за спиной. Говорил неприятные вещи."
    )
    llm = _StubLLM("YES")
    verifier = PropositionVerifier(llm)

    confirmed = verifier.verify(PROP_INSULT, text)

    assert confirmed is True
    assert len(llm.calls) == 1
    prompt_text = llm.calls[0][0]
    assert "Open_road" in prompt_text
    assert "tornin" in prompt_text
    assert llm.calls[0][1]["timeout"] is not None


def test_silence_returns_false():
    """Master случай 2: LLM-реплика говорит о погоде → proposition не затронут → NO."""
    text = (
        "Сегодня славная погода, не правда ли? "
        "Я слышала, лорд мэр устраивает бал на следующей неделе."
    )
    llm = _StubLLM("NO")
    verifier = PropositionVerifier(llm)

    confirmed = verifier.verify(PROP_INSULT, text)

    assert confirmed is False


def test_negation_returns_false():
    """Master случай 3: LLM-реплика явно отрицает proposition → NO."""
    text = (
        "Торнин, не верьте слухам. Ничего подобного не было — "
        "Open_road вас не оскорблял, это кто-то напутал."
    )
    llm = _StubLLM("NO")
    verifier = PropositionVerifier(llm)

    confirmed = verifier.verify(PROP_INSULT, text)

    assert confirmed is False


def test_distortion_returns_false():
    """Master случай 4: LLM-реплика говорит про другой объект → искажение → NO."""
    text = "Я слышала, что Open_road оскорбил горана. Вот негодяй!"
    llm = _StubLLM("NO")
    verifier = PropositionVerifier(llm)

    confirmed = verifier.verify(PROP_INSULT, text)

    assert confirmed is False


def test_empty_text_returns_false_without_llm_call():
    """Пустая реплика → барьер в верификаторе → NO, без LLM-вызова."""
    llm = _StubLLM("YES")
    verifier = PropositionVerifier(llm)

    confirmed = verifier.verify(PROP_INSULT, "")

    assert confirmed is False
    assert llm.calls == [], "LLM не должен вызываться на пустом тексте"


def test_whitespace_only_text_returns_false_without_llm_call():
    """Текст из одних пробелов → тоже считается пустым → NO, без LLM."""
    llm = _StubLLM("YES")
    verifier = PropositionVerifier(llm)

    confirmed = verifier.verify(PROP_INSULT, "   \n\t  ")

    assert confirmed is False
    assert llm.calls == []


def test_llm_runtime_failure_is_fail_closed():
    """LLM-клиент бросает RuntimeError → fail-closed → verify=False (без паники)."""
    llm = _StubLLM("YES", fail=True)
    verifier = PropositionVerifier(llm)

    confirmed = verifier.verify(PROP_INSULT, "Open_road оскорбил вас, Торнин.")

    assert confirmed is False


def test_llm_timeout_is_fail_closed():
    """Master условие A+D: LLM-клиент бросает TimeoutError → fail-closed=False."""
    llm = _StubLLM("YES", fail_with_timeout=True)
    verifier = PropositionVerifier(llm, timeout=2.0)

    confirmed = verifier.verify(PROP_INSULT, "Open_road оскорбил вас, Торнин.")

    assert confirmed is False
    assert llm.calls[0][1]["timeout"] == 2.0


@pytest.mark.parametrize(
    "raw_response,expected",
    [
        ("YES", True),
        ("Yes", True),
        ("yes", True),
        ("  YES  ", True),
        ("ДА", True),
        ("NO", False),
        ("No", False),
        ("НЕТ", False),
        ("FALSE", False),
        ("", False),
        ("MAYBE", False),
        ("I think yes", False),
    ],
)
def test_verdict_parsing(raw_response: str, expected: bool):
    """Парсинг LLM-вердикта устойчив к регистру, пробелам и «мусорным» ответам."""
    llm = _StubLLM(raw_response)
    verifier = PropositionVerifier(llm)

    assert verifier.verify(PROP_INSULT, "Open_road оскорбил вас.") is expected


def test_passthrough_verifier_is_test_only_contract():
    """PassthroughVerifier — legacy-контракт для ЯВНОГО внедрения в P1-P4 тестах."""
    pv = PassthroughVerifier()

    assert pv.verify(PROP_INSULT, "Open_road оскорбил вас.") is True
    assert pv.verify(PROP_INSULT, "") is True
    assert pv.verify({}, "любой текст") is True


def test_negative_polarity_negation_confirmed():
    """Master условие C: polarity=False — реплика, выражающая ОТРИЦАНИЕ → YES."""
    prop_negative = {
        "subject": "Open_road",
        "predicate": "INSULTED",
        "object": "tornin",
        "polarity": False,
    }
    text = "Open_road вас не оскорблял, Торнин. Это клевета."
    llm = _StubLLM("YES")
    verifier = PropositionVerifier(llm)

    confirmed = verifier.verify(prop_negative, text)

    assert confirmed is True
    assert "отрицательное" in llm.calls[0][0]


def test_negative_polarity_confirmation_rejected():
    """Master условие C: polarity=False, но реплика подтверждает отношение → NO."""
    prop_negative = {
        "subject": "Open_road",
        "predicate": "INSULTED",
        "object": "tornin",
        "polarity": False,
    }
    text = "Open_road вас оскорбил, Торнин. Гнусно ругался."
    llm = _StubLLM("NO")
    verifier = PropositionVerifier(llm)

    confirmed = verifier.verify(prop_negative, text)

    assert confirmed is False


def test_positive_polarity_rejects_negating_replica():
    """Master условие C (обратный случай): polarity=True, реплика отрицает → NO."""
    text = "Open_road вас не оскорблял, Торнин. Это клевета."
    llm = _StubLLM("NO")
    verifier = PropositionVerifier(llm)

    confirmed = verifier.verify(PROP_INSULT, text)

    assert confirmed is False
