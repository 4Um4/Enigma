"""
Запуск: 
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
    return BodyCapabilities(radius=0.5, can_jump=True, max_jump_height=1.0, max_jump_distance=3.0)

def test_pure_walk_no_obstacles(planner, body):
    query = TraversalQuery(
        source_pose=Pose(0, 0),
        target_pose=Pose(5, 5),
        body=body
    )
    geometry = LocalGeometry()
    plan = planner.compile_plan(query, geometry)
    
    assert plan.possible is True
    assert len(plan.segments) == 1
    assert plan.segments[0].mode == TraversalMode.WALK

def test_partial_intersection_radius_blocks_walk(planner, body):
    # Препятствие на расстоянии 0.3 от прямой линии. Radius = 0.5. Должно блокировать WALK.
    query = TraversalQuery(
        source_pose=Pose(0, 0),
        target_pose=Pose(10, 0),
        body=body
    )
    obs = Obstacle(id="obs1", x=5.0, y=0.3, w=1.0, h=1.0, height=0.5)
    geometry = LocalGeometry(obstacles=(obs,))
    
    plan = planner.compile_plan(query, geometry)
    
    # WALK должен быть заблокирован, но JUMP возможен
    assert plan.possible is True
    assert any(s.mode == TraversalMode.JUMP for s in plan.segments)

def test_multiple_obstacles_and_sequence(planner, body):
    # Два препятствия на пути
    query = TraversalQuery(
        source_pose=Pose(0, 0),
        target_pose=Pose(20, 0),
        body=body
    )
    obs1 = Obstacle(id="A", x=5.0, y=0.0, w=1.0, h=1.0, height=0.5)
    obs2 = Obstacle(id="B", x=15.0, y=0.0, w=1.0, h=1.0, height=0.5)
    geometry = LocalGeometry(obstacles=(obs1, obs2))
    
    plan = planner.compile_plan(query, geometry)
    
    assert plan.possible is True
    # Ожидаемая последовательность: WALK -> JUMP -> WALK -> JUMP -> WALK
    assert len(plan.segments) == 5
    assert plan.segments[0].mode == TraversalMode.WALK
    assert plan.segments[1].mode == TraversalMode.JUMP
    assert plan.segments[1].obstacle_id == "A"
    assert plan.segments[2].mode == TraversalMode.WALK
    assert plan.segments[3].mode == TraversalMode.JUMP
    assert plan.segments[3].obstacle_id == "B"
    assert plan.segments[4].mode == TraversalMode.WALK

def test_jump_too_high_blocks_plan(planner, body):
    query = TraversalQuery(
        source_pose=Pose(0, 0),
        target_pose=Pose(10, 0),
        body=body
    )
    obs = Obstacle(id="wall", x=5.0, y=0.0, w=1.0, h=1.0, height=2.0) # Выше max_jump_height
    geometry = LocalGeometry(obstacles=(obs,))
    
    plan = planner.compile_plan(query, geometry)
    
    assert plan.possible is False
    assert plan.reason == "OBSTACLE_TOO_HIGH"
    assert plan.required_capability == "max_jump_height"