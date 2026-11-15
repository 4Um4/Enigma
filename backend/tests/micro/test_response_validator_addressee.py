"""
test_response_validator_addressee.py — ТЗ-v4 P3: ResponseValidator addressee check.

Путь: backend/tests/micro/test_response_validator_addressee.py
Назначение: Unit test for ResponseValidator.addressee check (ТЗ-v4 P3 wiring)
Зависимости: app.services.verbalization.response_validator
Основные сущности: ResponseValidator, ValidationResult

ЗАЧЕМ: S424 implemented _addressee_present + addressee parameter (AVAILABLE, not wired).
S426 P3 wires it: dm_agent passes resolved display name to validate(addressee=).
This test verifies the addressee check works in isolation.
"""

from types import SimpleNamespace

from app.services.verbalization.response_validator import ResponseValidator


def _make_validator() -> ResponseValidator:
    """Construct ResponseValidator with minimal mock contract.

    ResponseValidator accesses only:
    - contract.max_sentences (L183: sentence limit)
    - contract.forbidden_actions (L309: _check_forbidden)
    """
    contract = SimpleNamespace(
        max_sentences=10,
        forbidden_actions=[],
    )
    return ResponseValidator(contract)


def test_addressee_present_passes():
    """Addressee name present in text -> validation passes (no fallback)."""
    v = _make_validator()
    text = "Люся смотрит на игрока. Привет, говорит она."
    result = v.validate(text, addressee="Люся")
    assert not result.is_fallback, f"Expected pass, got fallback: {result.violation}"


def test_addressee_absent_fallback():
    """Addressee name absent from text (different NPC speaks) -> wrong_addressee fallback."""
    v = _make_validator()
    text = "Борко смотрит на игрока. Привет, говорит он."
    result = v.validate(text, addressee="Люся")
    assert result.is_fallback, "Expected fallback (wrong NPC speaks)"
    assert result.violation == "wrong_addressee", f"Expected wrong_addressee, got: {result.violation}"


def test_addressee_none_skips_check():
    """addressee=None -> check skipped, no wrong_addressee false positive."""
    v = _make_validator()
    text = "Борко говорит: Привет."
    result = v.validate(text, addressee=None)
    assert result.violation != "wrong_addressee", "addressee=None should skip addressee check"


def test_addressee_case_insensitive():
    """_addressee_present uses .lower() — case-insensitive match."""
    v = _make_validator()
    assert v._addressee_present("ЛЮСЯ говорит", "люся") is True
    assert v._addressee_present("Люся говорит", "ЛЮСЯ") is True
    assert v._addressee_present("Борко говорит", "люся") is False
