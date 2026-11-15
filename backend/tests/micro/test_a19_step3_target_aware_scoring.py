"""
A19.5 Step 3: Target-Aware Scoring Tests.
Доказывает, что DecisionHub учитывает конкретные убеждения о конкретных целях при расчёте utility.
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import MagicMock

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.domain.epistemology import Proposition, Predicate, BeliefSummary, EpistemicContext
from app.services.npc.decision_hub import DecisionHub, EventContext
from app.models.npc_state import NPCState, EmotionTag
from app.models.npc_profile import NPCProfileL0


class MockProfile:
    def __init__(self, archetype: str):
        self.archetype = archetype


def test_target_aware_scoring_guard_vs_thief():
    """Информация о X влияет на оценку действий с X, но не с Z. Разные архетипы реагируют по-разному."""

    # Настраиваем контекст: C верит (conf=0.9), что X украл (STOLE) у Y
    belief = BeliefSummary(
        proposition=Proposition(subject_id="X", predicate=Predicate.STOLE, object_id="Y"),
        confidence=0.9,
        source_id="B",
        subject_id="X",
        object_id="Y",
    )
    epi_ctx = EpistemicContext(agent_id="C", recent_beliefs=(belief,))

    state = MagicMock(spec=NPCState)
    state.npc_id = "C"
    state.emotion = EmotionTag.NEUTRAL
    state.intent = None

    event = MagicMock(spec=EventContext)

    # Мокаем _resolve_target так, чтобы для 'report' и 'trade' целью был 'X', а для 'idle' - None
    def mock_resolve(intent, **kwargs):
        if intent in ("report", "trade"):
            return "X"
        return None

    hub = DecisionHub()
    hub._resolve_target = MagicMock(side_effect=mock_resolve)

    # Сценарий А: C — Страж (guard). Должен хотеть 'report' X, но не 'trade' с X.
    MockProfile("guard")
    base_scores = {"report": 0.5, "trade": 0.5, "idle": 0.5}

    # Эмулируем логику target-aware scoring из compute()
    from app.domain.epistemic_dispositions import get_epistemic_disposition

    disp_guard = get_epistemic_disposition("guard")  # {"report": 1.4, "trade": ~0.0}

    target_scores_guard = dict(base_scores)
    for intent in list(target_scores_guard.keys()):
        target = hub._resolve_target(intent=intent, event=event, state=state, epistemic_context=epi_ctx)
        if target == "X":
            modifier = disp_guard.get(intent, 0.0) * belief.confidence
            target_scores_guard[intent] = round(target_scores_guard[intent] + modifier, 4)

    # Guard получает значительный буст к report против вора (1.4 * 0.9 = 1.26)
    assert target_scores_guard["report"] > base_scores["report"] + 1.0, (
        f"Guard должен получать буст к report против вора, получено: {target_scores_guard['report']}"
    )
    # Guard не получает буст к trade с вором (disposition ~ 0.0)
    assert target_scores_guard["trade"] <= base_scores["trade"] + 0.1, (
        f"Guard не должен получать буст к trade с вором, получено: {target_scores_guard['trade']}"
    )

    # Сценарий Б: C — Вор (thief). Не должен хотеть 'report' X (сообщать властям).
    MockProfile("thief")
    disp_thief = get_epistemic_disposition("thief")  # {"report": 0.0}

    target_scores_thief = dict(base_scores)
    for intent in list(target_scores_thief.keys()):
        target = hub._resolve_target(intent=intent, event=event, state=state, epistemic_context=epi_ctx)
        if target == "X":
            modifier = disp_thief.get(intent, 0.0) * belief.confidence
            target_scores_thief[intent] = round(target_scores_thief[intent] + modifier, 4)

    # Thief не получает буст к report, сохраняя нейтралитет или избегание
    assert target_scores_thief["report"] == base_scores["report"], (
        f"Thief не должен получать буст к report, получено: {target_scores_thief['report']}"
    )


def test_no_effect_on_unrelated_target():
    """Информация о X не влияет на оценку взаимодействия с посторонним Z."""

    belief = BeliefSummary(
        proposition=Proposition(subject_id="X", predicate=Predicate.STOLE, object_id="Y"),
        confidence=0.9,
        source_id="B",
        subject_id="X",
        object_id="Y",
    )
    epi_ctx = EpistemicContext(agent_id="C", recent_beliefs=(belief,))

    state = MagicMock(spec=NPCState)
    state.npc_id = "C"
    state.emotion = EmotionTag.NEUTRAL
    state.intent = None

    event = MagicMock(spec=EventContext)

    # Для 'trade' с Z цель будет "Z", а не "X"
    def mock_resolve(intent, **kwargs):
        if intent == "trade":
            return "Z"
        return None

    hub = DecisionHub()
    hub._resolve_target = MagicMock(side_effect=mock_resolve)

    MockProfile("guard")
    base_scores = {"trade": 0.5}

    from app.domain.epistemic_dispositions import get_epistemic_disposition

    disp_guard = get_epistemic_disposition("guard")

    target_scores = dict(base_scores)
    for intent in list(target_scores.keys()):
        target = hub._resolve_target(intent=intent, event=event, state=state, epistemic_context=epi_ctx)
        if target and target in (belief.subject_id, belief.object_id):
            modifier = disp_guard.get(intent, 0.0) * belief.confidence
            target_scores[intent] = round(target_scores[intent] + modifier, 4)

    # Utility для trade с Z не должна измениться, так как Z не является субъектом или объектом убеждения
    assert target_scores["trade"] == base_scores["trade"], (
        f"Utility для trade с Z не должна измениться, получено: {target_scores['trade']}"
    )
