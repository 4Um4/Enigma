"""Source-gate: _QUESTION_2A (ТЗ §2.A) — question-to-player requires pronoun."""
from pathlib import Path
import pytest

RV = Path(__file__).resolve().parents[3] / "backend" / "app" / "services" / "verbalization" / "response_validator.py"


@pytest.fixture(scope="module")
def src() -> str:
    if not RV.is_file():
        pytest.fail(f"missing {RV}")
    return RV.read_text(encoding="utf-8")


def test_pronoun_regex_present(src: str) -> None:
    assert "_PLAYER_PRONOUN_RE" in src, "_PLAYER_PRONOUN_RE missing"
    for p in ("тебя", "тебе", "тобой", "твой", "твоя", "твоё",
              "вы", "вас", "вам", "вами", "ваш", "ваша"):
        assert p in src, f"pronoun {p!r} missing"


def test_old_blanket_check_removed(src: str) -> None:
    i = src.find("def _contains_question_to_player")
    assert i > 0, "method missing"
    j = src.find("def ", i + 10)
    block = src[i:j] if j > 0 else src[i:]
    assert 'return "?" in text' not in block, "blanket '? in text' still present in method"


def test_sentence_split_and_pronoun_search_present(src: str) -> None:
    assert "for sentence in re.split" in src, "sentence split loop missing"
    assert "self._PLAYER_PRONOUN_RE.search(sentence)" in src, "pronoun search missing"
