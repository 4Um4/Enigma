"""
Тесты целеполагания для SPREAD_RUMOR (Social Propagation).
Доказывают корректность фильтрации по расстоянию, trust и детерминированному выбору.
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import MagicMock

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.domain.epistemology import EpistemicContext
from app.services.npc.decision_hub import DecisionHub


def test_spread_rumor_selects_single_trusted_candidate_in_range():
    """Сценарий: Один доступный NPC с trust > 0 в радиусе слышимости."""
    hub = DecisionHub()
    state = MagicMock()
    state.npc_id = "npc_B"

    # Mock spatial_query
    spatial_query = MagicMock()
    spatial_query.distance = MagicMock(side_effect=lambda a, b: 5.0 if b == "npc_C" else 999.0)

    # Mock _get_rel_value
    hub._get_rel_value = MagicMock(side_effect=lambda s, t, attr: 50.0 if t == "npc_C" and attr == "trust" else 0.0)

    all_npcs = ["npc_A", "npc_B", "npc_C"]

    target = hub._resolve_target(
        intent="spread_rumor", event=MagicMock(), state=state, spatial_query=spatial_query, all_npc_ids=all_npcs
    )

    assert target == "npc_C", f"Ожидался npc_C, получен {target}"


def test_spread_rumor_returns_none_if_no_trusted_candidates():
    """Сценарий: Нет кандидатов с trust > 0."""
    hub = DecisionHub()
    state = MagicMock()
    state.npc_id = "npc_B"

    spatial_query = MagicMock()
    spatial_query.distance = MagicMock(return_value=5.0)  # Все в радиусе

    # Все имеют trust <= 0
    hub._get_rel_value = MagicMock(return_value=-10.0)

    all_npcs = ["npc_A", "npc_B", "npc_C"]

    target = hub._resolve_target(
        intent="spread_rumor", event=MagicMock(), state=state, spatial_query=spatial_query, all_npc_ids=all_npcs
    )

    assert target is None, f"Ожидался None, получен {target}"


def test_spread_rumor_tie_breaks_by_npc_id_when_equal_trust():
    """A21.2: Равный trust у npc_A и npc_C -> детерминированный tie-break по npc_id (ascending) -> npc_A."""
    hub = DecisionHub()
    state = MagicMock()
    state.npc_id = "npc_B"

    spatial_query = MagicMock()
    spatial_query.distance = MagicMock(return_value=5.0)

    # npc_A и npc_C имеют trust > 0
    def mock_rel(s, t, attr):
        if attr == "trust" and t in ("npc_A", "npc_C"):
            return 20.0
        return 0.0

    hub._get_rel_value = MagicMock(side_effect=mock_rel)

    all_npcs = ["npc_A", "npc_B", "npc_C"]

    target = hub._resolve_target(
        intent="spread_rumor", event=MagicMock(), state=state, spatial_query=spatial_query, all_npc_ids=all_npcs
    )

    assert target == "npc_A", f"A21.2: равный trust -> tie-break по npc_id -> npc_A, получен {target}"


def test_spread_rumor_excludes_self_and_out_of_range():
    """Сценарий: Сам говорящий и дальние NPC исключаются."""
    hub = DecisionHub()
    state = MagicMock()
    state.npc_id = "npc_B"

    spatial_query = MagicMock()
    # npc_A далеко, npc_C близко
    spatial_query.distance = MagicMock(side_effect=lambda a, b: 999.0 if b == "npc_A" else 5.0)

    # У всех trust > 0
    hub._get_rel_value = MagicMock(return_value=50.0)

    all_npcs = ["npc_A", "npc_B", "npc_C"]

    target = hub._resolve_target(
        intent="spread_rumor", event=MagicMock(), state=state, spatial_query=spatial_query, all_npc_ids=all_npcs
    )

    # npc_B исключён (self), npc_A исключён (distance), остаётся только npc_C
    assert target == "npc_C", f"Ожидался npc_C, получен {target}"


def test_spread_rumor_handles_spatial_query_error_gracefully():
    """Сценарий: Ошибка spatial_query не приводит к падению, кандидат исключается."""
    hub = DecisionHub()
    state = MagicMock()
    state.npc_id = "npc_B"

    spatial_query = MagicMock()
    spatial_query.distance = MagicMock(side_effect=Exception("Spatial error"))

    hub._get_rel_value = MagicMock(return_value=50.0)
    all_npcs = ["npc_A", "npc_B", "npc_C"]

    target = hub._resolve_target(
        intent="spread_rumor", event=MagicMock(), state=state, spatial_query=spatial_query, all_npc_ids=all_npcs
    )

    assert target is None, f"Ожидался None при ошибке spatial, получен {target}"


def test_spread_rumor_selects_highest_trust_when_unequal():
    """A21.2: Неравный trust -> выбирается кандидат с максимальным trust (npc_C=50 > npc_A=20)."""
    hub = DecisionHub()
    state = MagicMock()
    state.npc_id = "npc_B"

    spatial_query = MagicMock()
    spatial_query.distance = MagicMock(return_value=5.0)

    def mock_rel(s, t, attr):
        if attr == "trust":
            return {"npc_A": 20.0, "npc_C": 50.0}.get(t, 0.0)
        return 0.0

    hub._get_rel_value = MagicMock(side_effect=mock_rel)
    all_npcs = ["npc_A", "npc_B", "npc_C"]

    target = hub._resolve_target(
        intent="spread_rumor", event=MagicMock(), state=state, spatial_query=spatial_query, all_npc_ids=all_npcs
    )

    assert target == "npc_C", f"A21.2: должен выбрать npc_C (trust=50 > 20), получен {target}"
