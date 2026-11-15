"""Source-gate: FLEE-DEDUP guard в commitment_arbiter.py (RT-LLM-01)."""

from pathlib import Path
import pytest

ARB = Path(__file__).resolve().parents[3] / "backend" / "app" / "services" / "action" / "commitment_arbiter.py"


@pytest.fixture(scope="module")
def arb_src() -> str:
    if not ARB.is_file():
        pytest.fail(f"arbiter not found at {ARB}")
    return ARB.read_text(encoding="utf-8")


def test_flee_dedup_marker_present(arb_src: str) -> None:
    assert "ARBITER_FLEE_DEDUP" in arb_src, "FLEE-DEDUP log marker missing"
    assert "FLEE_REDUNDANT_SAME_ZONE" in arb_src, "FLEE-DEDUP reason missing"
    assert 'candidate_source == "reactive:flee"' in arb_src, "flee-guard missing"


def test_flee_dedup_before_supersede(arb_src: str) -> None:
    dedup_pos = arb_src.find("ARBITER_FLEE_DEDUP")
    supersede_pos = arb_src.find("reason=PRIORITY_SUPERSEDE")
    assert dedup_pos > 0, "FLEE-DEDUP not found"
    assert supersede_pos > 0, "PRIORITY_SUPERSEDE not found"
    assert dedup_pos < supersede_pos, "FLEE-DEDUP must precede supersede block"


def test_flee_dedup_returns_reject(arb_src: str) -> None:
    src = arb_src
    anchor = src.find("ARBITER_FLEE_DEDUP")
    block = src[anchor:anchor + 1200]
    assert "VERDICT_REJECT" in block, "FLEE-DEDUP must return REJECT, not INTERRUPT"
    assert "VERDICT_INTERRUPT" not in block[:block.find(")")] if ")" in block else True, "FLEE-DEDUP must not INTERRUPT"