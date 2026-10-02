"""path: /project/backend/tests/micro/test_dm_raw_leak_lock.py

Назначение: Пакет C (вердикт Мастера) — regression-замок инварианта C:
    ни одно поле PlayerAction (raw player text) не попадает в DM-промпт.
    Имя из SELF_INTRODUCTION не доходит (знание NPC — через cognition
    DMFrame); содержимое ASSERT-claim не доходит; деградация без projection
    нейтральна; AST-гвард: в dm_agent.py нет интерполяции сырых полей.
Зависимости: app.agents.dm_agent, pathlib, ast.
Запуск: cd backend; python -m pytest tests/micro/test_dm_raw_leak_lock.py -v; cd ..
"""

import ast
from pathlib import Path

from app.agents.dm_agent import DmAgent


class _PA:
    """Минимальный PlayerAction-контракт (player_name/action)."""

    def __init__(self, player_name: str, action: str) -> None:
        self.player_name = player_name
        self.action = action


def _projection(acts, target="merchant_goran"):
    return {
        "action": "DIALOGUE",
        "target": target,
        "semantic_action": "DIALOGUE",
        "semantic_acts": acts,
    }


def test_self_intro_name_not_leaked():
    out = DmAgent._presentation_safe_actions(
        {"player_intent_projection": _projection(
            [{"type": "SELF_INTRODUCTION", "params": {"name": "Гобен"}}]
        )},
        [_PA("player", "Я Гобен")],
    )
    assert "Гобен" not in out
    assert "представление себя" in out


def test_assert_claim_content_not_leaked():
    out = DmAgent._presentation_safe_actions(
        {"player_intent_projection": _projection(
            [{"type": "ASSERT", "params": {"claim": "Я слуга этого дома"}}]
        )},
        [_PA("player", "Я слуга этого дома")],
    )
    assert "слуга этого дома" not in out


def test_no_projection_degrades_without_raw():
    out = DmAgent._presentation_safe_actions(
        {}, [_PA("player", "Я Гобен")]
    )
    assert "Гобен" not in out
    assert out != ""


def test_ast_no_raw_interpolation_in_dm_agent():
    """AST-гвард: в dm_agent.py нет интерполяции сырых полей action."""
    src_path = (
        Path(__file__).resolve().parents[2] / "app" / "agents" / "dm_agent.py"
    )
    src = src_path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):  # f-string
            for value in node.values:
                if isinstance(value, ast.FormattedValue):
                    frag = ast.unparse(value.value)
                    assert "a.action" not in frag, (
                        f"Инвариант C нарушен: raw a.action интерполируется "
                        f"в DM-промпт (dm_agent.py:{node.lineno})"
                    )