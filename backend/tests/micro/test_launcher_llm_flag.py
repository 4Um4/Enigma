"""Source-gate: ROLLOUT-ON (schema D) for LLM_RESILIENCE_V1 in game_launcher.py.

ТЗ LLM_RESILIENCE_V1 §4.3: явное включение ON + сохранение OFF rollback.
Контракт schema D: пустое/отсутствующее -> ON; явный '0' -> OFF.
"""

from pathlib import Path

import pytest

LAUNCHER = Path(__file__).resolve().parents[3] / "game_launcher.py"
GUARD = 'if not _env.get("LLM_RESILIENCE_V1"):'
ASSIGN = '_env["LLM_RESILIENCE_V1"] = "1"'


@pytest.fixture(scope="module")
def launcher_src() -> str:
    if not LAUNCHER.is_file():
        pytest.fail(f"game_launcher.py not found at {LAUNCHER}")
    return LAUNCHER.read_text(encoding="utf-8")


def test_guarded_on_by_default_present(launcher_src: str) -> None:
    lines = launcher_src.splitlines()
    for i, raw in enumerate(lines):
        if GUARD in raw:
            for j in range(i + 1, len(lines)):
                nxt = lines[j].strip()
                if not nxt or nxt.startswith("#"):
                    continue
                assert ASSIGN in nxt, f"guarded assignment missing right after line {i + 1}; got: {nxt!r}"
                return
    pytest.fail(f"guarded ROLLOUT-ON block not found: {GUARD!r}")


def test_off_rollback_not_bypassed(launcher_src: str) -> None:
    lines = launcher_src.splitlines()
    for i, raw in enumerate(lines):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if '_env["LLM_RESILIENCE_V1"]' not in line or "=" not in line:
            continue
        if line.startswith("if "):
            continue
        prev = None
        for j in range(i - 1, -1, -1):
            p = lines[j].strip()
            if not p or p.startswith("#"):
                continue
            prev = p
            break
        assert prev is not None and GUARD in prev, f"line {i + 1}: unguarded assignment breaks OFF rollback: {line}"


def test_s377_anchor_present(launcher_src: str) -> None:
    lines = launcher_src.splitlines()
    for i, raw in enumerate(lines):
        if GUARD in raw:
            context = "\n".join(lines[max(0, i - 8) : i])
            assert "S377" in context or "ROLLOUT-ON" in context, (
                "missing S377/ROLLOUT-ON anchor comment above the guarded block"
            )
            return
    pytest.fail("guarded ROLLOUT-ON block not found")
