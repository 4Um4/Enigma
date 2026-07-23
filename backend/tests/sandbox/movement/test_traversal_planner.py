"""
Запуск: cd backend; python -m pytest tests/sandbox/movement/test_traversal_planner.py -v; cd ..
"""

import pytest
from app.domain.traversal import (
    BodyCapabilities, LocalGeometry, Obstacle, Pose, TraversalMode, TraversalQuery, WallSegment
)
from app.services.spatial.local_traversal_planner import LocalTraversalPlanner

@pytest.fixture
def planner():
    return LocalTraversalPlanner()

@pytest.fixture
def body():
    return BodyCapabilities(radius=0.5, can_jump=True, max_jump_height=1.0, max_jump_distance=3.0, movement_speed=2.0)

@pytest.fixture
def walk_jump_modes():
    return (TraversalMode.WALK, TraversalMode.JUMP)

def test_pure_walk_no_obstacles(planner, body, walk_jump_modes):
    query = TraversalQuery(
        source_pose=Pose(0, 0),
        target_pose=Pose(5, 5),
        body=body,
        allowed_modes=walk_jump_modes
    )
    geometry = LocalGeometry()
    plan = planner.compile_plan(query, geometry)
    
    assert plan.possible is True
    assert len(plan.segments) == 1
    assert plan.segments[0].mode == TraversalMode.WALK

def test_partial_intersection_radius_blocks_walk(planner, body, walk_jump_modes):
    query = TraversalQuery(
        source_pose=Pose(0, 0),
        target_pose=Pose(10, 0),
        body=body,
        allowed_modes=walk_jump_modes
    )
    obs = Obstacle(id="obs1", x=5.0, y=0.3, w=1.0, h=1.0, height=0.5)
    geometry = LocalGeometry(obstacles=(obs,))
    
    plan = planner.compile_plan(query, geometry)
    
    assert plan.possible is True
    assert any(s.mode == TraversalMode.JUMP for s in plan.segments)

def test_multiple_obstacles_and_sequence(planner, body, walk_jump_modes):
    query = TraversalQuery(
        source_pose=Pose(0, 0),
        target_pose=Pose(20, 0),
        body=body,
        allowed_modes=walk_jump_modes
    )
    obs1 = Obstacle(id="A", x=5.0, y=0.0, w=1.0, h=1.0, height=0.5)
    obs2 = Obstacle(id="B", x=15.0, y=0.0, w=1.0, h=1.0, height=0.5)
    geometry = LocalGeometry(obstacles=(obs1, obs2))
    
    plan = planner.compile_plan(query, geometry)
    
    assert plan.possible is True
    assert len(plan.segments) == 5
    assert plan.segments[0].mode == TraversalMode.WALK
    assert plan.segments[1].mode == TraversalMode.JUMP
    assert plan.segments[1].obstacle_id == "A"
    assert plan.segments[2].mode == TraversalMode.WALK
    assert plan.segments[3].mode == TraversalMode.JUMP
    assert plan.segments[3].obstacle_id == "B"
    assert plan.segments[4].mode == TraversalMode.WALK

def test_jump_too_high_blocks_plan(planner, body, walk_jump_modes):
    query = TraversalQuery(
        source_pose=Pose(0, 0),
        target_pose=Pose(10, 0),
        body=body,
        allowed_modes=walk_jump_modes
    )
    obs = Obstacle(id="wall", x=5.0, y=0.0, w=1.0, h=1.0, height=2.0)
    geometry = LocalGeometry(obstacles=(obs,))
    
    plan = planner.compile_plan(query, geometry)
    
    assert plan.possible is False
    assert plan.reason == "OBSTACLE_TOO_HIGH"
    assert plan.required_capability == "max_jump_height"

# --- НОВЫЕ ТЕСТЫ (Контрактная матрица) ---

def test_jump_too_far_blocks_plan(planner, walk_jump_modes):
    body_far = BodyCapabilities(radius=0.5, can_jump=True, max_jump_height=1.0, max_jump_distance=0.5)
    query = TraversalQuery(
        source_pose=Pose(0, 0),
        target_pose=Pose(10, 0),
        body=body_far,
        allowed_modes=walk_jump_modes
    )
    obs = Obstacle(id="wide_obs", x=5.0, y=0.0, w=2.0, h=1.0, height=0.5)
    geometry = LocalGeometry(obstacles=(obs,))
    
    plan = planner.compile_plan(query, geometry)
    
    assert plan.possible is False
    assert plan.reason == "GAP_TOO_WIDE"
    assert plan.required_capability == "max_jump_distance"

def test_missing_jump_capability_blocks_plan(planner, walk_jump_modes):
    body_no_jump = BodyCapabilities(radius=0.5, can_jump=False, max_jump_height=100.0, max_jump_distance=100.0)
    query = TraversalQuery(
        source_pose=Pose(0, 0),
        target_pose=Pose(10, 0),
        body=body_no_jump,
        allowed_modes=walk_jump_modes
    )
    obs = Obstacle(id="obs1", x=5.0, y=0.0, w=1.0, h=1.0, height=0.5)
    geometry = LocalGeometry(obstacles=(obs,))
    
    plan = planner.compile_plan(query, geometry)
    
    assert plan.possible is False
    assert plan.reason == "MISSING_CAPABILITY"
    assert plan.required_capability == "can_jump"

def test_source_inside_collision_envelope_rejects_transition(planner, body, walk_jump_modes):
    query = TraversalQuery(
        source_pose=Pose(4.6, 0.5),
        target_pose=Pose(10, 0.5),
        body=body,
        allowed_modes=walk_jump_modes
    )
    obs = Obstacle(id="obs1", x=5.0, y=0.0, w=1.0, h=1.0, height=0.5)
    geometry = LocalGeometry(obstacles=(obs,))
    
    plan = planner.compile_plan(query, geometry)
    
    assert plan.possible is False

def test_target_inside_collision_envelope_rejects_transition(planner, body, walk_jump_modes):
    query = TraversalQuery(
        source_pose=Pose(0, 0.5),
        target_pose=Pose(6.4, 0.5),
        body=body,
        allowed_modes=walk_jump_modes
    )
    obs = Obstacle(id="obs1", x=5.0, y=0.0, w=1.0, h=1.0, height=0.5)
    geometry = LocalGeometry(obstacles=(obs,))
    
    plan = planner.compile_plan(query, geometry)
    
    assert plan.possible is False

def test_jump_not_allowed_by_query_blocks_plan(planner, body):
    # allowed_modes по умолчанию = (WALK,)
    query = TraversalQuery(
        source_pose=Pose(0, 0),
        target_pose=Pose(10, 0),
        body=body,
        allowed_modes=(TraversalMode.WALK,)
    )
    obs = Obstacle(id="obs1", x=5.0, y=0.0, w=1.0, h=1.0, height=0.5)
    geometry = LocalGeometry(obstacles=(obs,))
    
    plan = planner.compile_plan(query, geometry)
    
    assert plan.possible is False
    assert plan.reason == "JUMP_NOT_ALLOWED"

def test_wall_blocks_all_traversal_modes(planner, body, walk_jump_modes):
    query = TraversalQuery(
        source_pose=Pose(0, 0),
        target_pose=Pose(10, 0),
        body=body,
        allowed_modes=walk_jump_modes
    )
    wall = WallSegment(x1=5.0, y1=-1.0, x2=5.0, y2=1.0)
    geometry = LocalGeometry(walls=(wall,))
    
    plan = planner.compile_plan(query, geometry)
    
    assert plan.possible is False
    assert plan.reason == "WALL_CLEARANCE_BLOCKED"

def test_blocking_obstacle_without_transition_candidate_blocks_plan(planner, body, walk_jump_modes):
    """Каузальный инвариант: blocking obstacle обязан породить transition candidate,
    иначе весь план невозможен (без false positive)."""
    # Source находится внутри expanded envelope (4.5..6.5)
    query = TraversalQuery(
        source_pose=Pose(4.6, 0.5),
        target_pose=Pose(10, 0.5),
        body=body,
        allowed_modes=walk_jump_modes
    )
    obs = Obstacle(id="obs1", x=5.0, y=0.0, w=1.0, h=1.0, height=0.5)
    geometry = LocalGeometry(obstacles=(obs,))
    
    plan = planner.compile_plan(query, geometry)
    
    assert plan.possible is False
    assert plan.reason == "TRANSITION_TOPOLOGY_UNRESOLVED"