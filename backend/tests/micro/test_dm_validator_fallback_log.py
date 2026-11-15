"""Source-gate: DM validator fallback reason logging."""

from pathlib import Path
import pytest

RV = Path(__file__).resolve().parents[3] / "backend" / "app" / "services" / "verbalization" / "response_validator.py"


@pytest.fixture(scope="module")
def src() -> str:
    if not RV.is_file():
        pytest.fail(f"missing {RV}")
    return RV.read_text(encoding="utf-8")


def test_logger_import(src: str) -> None:
    assert "import logging" in src, "logging import missing"
    assert "logger = logging.getLogger(__name__)" in src, "logger missing"


def test_fallback_log_present(src: str) -> None:
    assert "_DM_VALIDATOR_LOG" in src, "marker missing"
    assert "reason={reason}" in src, "reason interpolation missing"


def test_fallback_log_inside_method(src: str) -> None:
    i = src.find("def _fallback")
    j = src.find("_DM_VALIDATOR_LOG")
    assert i > 0 and j > i, "log must be inside _fallback method"
