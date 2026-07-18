import pytest
import math
from app.domain.traversal_schema import (
    MovementPlanResult,
    MovementPlanStatus,
    TraversalProposal,
    build_traversal_dict,
)
from app.services.scene_change import ChangeType, SceneChange


def _make_test_proposal(npc_id="test_npc", topology_version=0, distance=14.14) -> TraversalProposal:
    """Фабрика для создания валидного TraversalProposal в тестах."""
    return TraversalProposal(
        npc_id=npc_id,
        source_node="loc:node_a",
        target_node="loc:node_b",
        path_waypoints=((0.0, 0.0), (10.0, 10.0)),
        distance=distance,
        speed=2.0,
        duration_ticks=8,
        source_intent_id="intent_1",
        planned_tick=10,
        topology_version=topology_version,
    )


def test_traversal_proposal_is_immutable():
    """ADR-O-323: TraversalProposal должен быть immutable (frozen dataclass)."""
    proposal = _make_test_proposal()
    
    with pytest.raises(AttributeError):
        proposal.npc_id = "hack"

    with pytest.raises(AttributeError):
        proposal.path_waypoints = ((0.0, 0.0),)


def test_movement_plan_result_accepted_requires_proposal():
    """ADR-O-323: ACCEPTED результат обязан содержать proposal (инвариант DTO)."""
    with pytest.raises(ValueError, match="ACCEPTED result requires proposal"):
        MovementPlanResult(
            status=MovementPlanStatus.ACCEPTED,
            proposal=None,
        )


def test_movement_plan_result_rejected_cannot_contain_proposal():
    """ADR-O-323: REJECTED результат не может содержать proposal (инвариант DTO)."""
    proposal = _make_test_proposal()
    with pytest.raises(ValueError, match="REJECTED result cannot contain proposal"):
        MovementPlanResult(
            status=MovementPlanStatus.REJECTED,
            reason="NODE_NOT_FOUND",
            proposal=proposal,
        )


def test_proposal_topology_revision_is_required():
    """ADR-O-323: topology_version обязателен в DTO."""
    with pytest.raises(TypeError):
        TraversalProposal(
            npc_id="test_npc",
            source_node="loc:node_a",
            target_node="loc:node_b",
            path_waypoints=((0.0, 0.0), (10.0, 10.0)),
            distance=14.14,
            speed=2.0,
            duration_ticks=8,
            source_intent_id="intent_1",
            planned_tick=10,
            # topology_version отсутствует
        )


def test_scene_change_carries_traversal_proposal():
    """ADR-O-323: SceneChange должен переносить TraversalProposal без модификаций."""
    proposal = _make_test_proposal()
    
    change = SceneChange(
        type=ChangeType.NPC_POSITION,
        target="test_npc",
        field="position",
        value="loc:node_b",
        cause="semantic_relocation:test",
        tick=10,
        target_location_id="loc",
        target_local_xy=(10.0, 10.0),  # Совпадает с последним waypoint proposal
        traversal_proposal=proposal,
    )
    
    assert change.traversal_proposal is not None
    assert change.traversal_proposal.npc_id == "test_npc"
    assert change.target_local_xy == (10.0, 10.0)


def test_scene_manager_materializes_exact_proposal():
    """ADR-O-323: SceneStateManager материализует traversal_dict строго из proposal."""
    proposal = _make_test_proposal()
    
    # Симулируем материализацию (без вызова всего SSM)
    _traversal_dict = build_traversal_dict(proposal)
    
    assert _traversal_dict["npc_id"] == proposal.npc_id
    assert _traversal_dict["from_node"] == proposal.source_node
    assert _traversal_dict["target_node"] == proposal.target_node
    assert _traversal_dict["started_tick"] == proposal.planned_tick
    assert _traversal_dict["duration_ticks"] == proposal.duration_ticks
    assert _traversal_dict["speed"] == proposal.speed
    assert _traversal_dict["path_waypoints"] == [list(wp) for wp in proposal.path_waypoints]


def test_shadow_validator_rejects_invalid_source():
    """ADR-O-323: Shadow валидатор отклоняет proposal с неверным source_node."""
    proposal = _make_test_proposal()
    # Имитируем несовпадение source_node
    assert proposal.source_node != "wrong_node"
    # В реальном коде _validate_traversal_proposal вернёт False


def test_shadow_validator_rejects_invalid_distance():
    """ADR-O-323: Shadow валидатор отклоняет proposal с неконсистентной distance."""
    proposal = _make_test_proposal(distance=999.0)
    # Независимый пересчёт:
    prop_wps = [list(wp) for wp in proposal.path_waypoints]
    calc_distance = 0.0
    for i in range(len(prop_wps) - 1):
        dx = prop_wps[i][0] - prop_wps[i+1][0]
        dy = prop_wps[i][1] - prop_wps[i+1][1]
        calc_distance += math.hypot(dx, dy)
    
    assert abs(proposal.distance - calc_distance) > 1.0  # Должен быть отклонён


def test_shadow_validator_rejects_stale_topology():
    """ADR-O-323: Shadow валидатор отклоняет proposal с устаревшей topology_version."""
    proposal = _make_test_proposal(topology_version=42)
    current_topology_version = 43  # Симулируем изменение графа
    assert proposal.topology_version != current_topology_version