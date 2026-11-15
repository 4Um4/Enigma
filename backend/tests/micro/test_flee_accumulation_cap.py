"""Source-gate: FLEE accumulation cap (RT-LLM-02)."""

from pathlib import Path
import pytest

CRYS = (
    Path(__file__).resolve().parents[3]
    / "backend"
    / "app"
    / "services"
    / "npc"
    / "crystallized_belief_modifier_resolver.py"
)
BELIEF = Path(__file__).resolve().parents[3] / "backend" / "app" / "services" / "npc" / "belief_modifier_resolver.py"


@pytest.fixture(scope="module")
def crys_src() -> str:
    if not CRYS.is_file():
        pytest.fail(f"missing {CRYS}")
    return CRYS.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def belief_src() -> str:
    if not BELIEF.is_file():
        pytest.fail(f"missing {BELIEF}")
    return BELIEF.read_text(encoding="utf-8")


def test_crystallized_cap_present(crys_src: str) -> None:
    assert "_FEAR_MOD_CAP" in crys_src, "crystallized cap missing"
    assert "min(_new_flee, _FEAR_MOD_CAP)" in crys_src, "cap not applied"


def test_belief_cap_present(belief_src: str) -> None:
    assert "_BELIEF_FLEE_CAP" in belief_src, "belief cap missing"
    assert 'mods["flee"] = round(min(mods["flee"], _BELIEF_FLEE_CAP), 4)' in belief_src, "cap not applied"


def test_crystallized_value(crys_src: str) -> None:
    import re

    m = re.search(r"_FEAR_MOD_CAP:\s*float\s*=\s*([\d.]+)", crys_src)
    assert m, "cap value not found"
    assert 0.1 <= float(m.group(1)) <= 1.0, f"cap {m.group(1)} out of range"


def test_belief_value(belief_src: str) -> None:
    import re

    m = re.search(r"_BELIEF_FLEE_CAP:\s*float\s*=\s*([\d.]+)", belief_src)
    assert m, "cap value not found"
    assert 0.1 <= float(m.group(1)) <= 1.0, f"cap {m.group(1)} out of range"
