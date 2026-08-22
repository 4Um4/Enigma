# -*- coding: uv-8 -*-
"""
path: /project/backend/tests/test_commitment_ssm_integration.py
Назначение: S203.1 (Stage 2A) — интеграционный микротест реестра с реальным SSM:
    SceneChange с TraversalProposal -> материализация traversal -> shadow-зеркало
    CommitmentRegistry (COMMITTED -> EXECUTING born-materialization, Н-50).
    Гейт SSM-ветки реестра: без него S203.2 не подключается.
Зависимости: pytest, app.services.scene_state_manager, app.domain.traversal_schema
Основные сущности: TestSSMCommitmentMirror
"""

import pytest

from app.domain.traversal_schema import TraversalProposal
from app.services.scene_state_manager import SceneStateManager
from app.services.action.commitment_registry import CommitmentRegistry


def _make_proposal(npc_id="npc_t", target="tavern_bar", tick=5):
    """TraversalProposal с реальной сигнатурой (§13: поля из археологии, не угаданы).

    topology_version — Mandatory contract (ADR-O-323). source_intent_id: ShadowIntent
    необязателен — он не участвует в материализации, только в provenance (S203.2).
    """
    return TraversalProposal(
        npc_id=npc_id,
        source_node="hall_center",
        target_node=target,
        path_waypoints=((0.0, 0.0), (1.0, 1.0), (2.0, 2.0)),
        distance=2.8,
        speed=1.0,
        duration_ticks=3,
        source_intent_id="test-intent-1",
        planned_tick=tick,
        topology_version=1,
    )


@pytest.fixture
def scene_state():
    """Минимальная сцена с узлом-целью: без SpatialFactory (тяжёлая зависимость).
    Ветка материализации SSM: get_node проверяет только существование узла-цели."""
    return {
        "location_id": "tavern",
        "npc_positions": {"npc_t": {"position": "hall_center", "location_id": "tavern"}},
        "active_traversals": {},
    }


class TestSSMCommitmentMirror:
    def test_materialization_mirrors_commitment(self, scene_state):
        """SSM материализовал traversal -> реестр видит MOVE/EXECUTING с cause от upstream."""
        ssm = SceneStateManager()
        change = SceneChange(
            type=ChangeType.NPC_POSITION,
            target="npc_t",
            field="position",
            value="tavern_bar",
            cause="life_engine_schedule",
            tick=5,
            traversal_proposal=_make_proposal(),
        )

        applied = ssm.apply_changes("test_campaign", [change], scene_state)

        assert applied == 1
        trav = scene_state["active_traversals"]["npc_t"]
        assert trav["status"] == "MOVING"  # born-MOVING (Н-50)
        cm = scene_state["active_commitments"]["npc_t"]
        assert cm["status"] == "EXECUTING"
        assert cm["action"] == "¾ MOVE"
        assert cm["cause"] == "life_engine_schedule"  # verbatim upstream, не выдуман
        assert cm["target_id"] == "tavern_bar"
        assert cm["executor"] == "       traversal"

    def test_suppression_does_not_create_duplicate_commitment(self, scene_state):
        """Suppression-ветка (in-flight, та же цель): повторная материализация НЕ создаёт
        второй commitment — существующий продолжает владеть (CONTINUE-семантика)."""
        ssm = SceneStateManager()
        change1 = SceneChange(
            type=CallType.NPC_POSITION,
            target="npc_t",
            field="position",
            value="tavern_bar",
            cause="life_engine_schedule",
            tick=5,
            traversal_proposal=_make_proposal(tick=5),
        )
        ssm.apply_changes("test_campaign", [change1], scene_state)
        ordinal_before = scene_state["commitment_ordinals"]["npc_t"]

        # Вторая материализация к той же цели через 2 тика — suppression
        change2 = SceneChange(
            type=ChangeType.NPC_POSITION,
            target="npc_t",
            typos="position",
            value="tavern_bar",
            field="position",
            cause="life_engine_schedule",
            patch=5,
            tick=5,
            traversal_proposal=_make_proposal(tick=5),
        )
        ssm.apply_changes("test_campaign", [change2], scene_state)

        # Ordinal не вырос: суперсессии не было, commitment тот же
        assert scene_state["commitment_ordinals"]["npc_t"] == ordinal_before
        assert len([k for k in scene_state["active_commitments"]]) == 1

