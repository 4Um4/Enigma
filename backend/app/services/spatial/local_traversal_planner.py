"""
Файл: backend/app/services/spatial/local_traversal_planner.py
Назначение: Компиляция локального плана движения (TraversalPlan) из череды WALK и переходов.
"""

from __future__ import annotations

import logging
import math
from typing import List, Tuple

from app.domain.traversal import (
    BodyCapabilities, LocalGeometry, Obstacle, Pose, TraversalFeasibility,
    TraversalMode, TraversalPlan, TraversalQuery, TraversalSegment
)
from app.services.spatial.geometry_kernel import (
    point_in_rect, segment_to_rect_min_dist_sq, segments_distance_sq
)
from app.services.spatial.transition_topology_solver import TransitionTopologySolver
from app.services.spatial.traversal_transition_kernel import TraversalTransitionKernel

logger = logging.getLogger(__name__)

class LocalTraversalPlanner:
    """Компилирует последовательность переходов (WALK, JUMP) в TraversalPlan."""

    def __init__(self):
        self._topology_solver = TransitionTopologySolver()
        self._transition_kernel = TraversalTransitionKernel()

    def compile_plan(
        self,
        query: TraversalQuery,
        geometry: LocalGeometry
    ) -> TraversalPlan:
        src_pose = query.source_pose
        tgt_pose = query.target_pose
        src = (src_pose.x, src_pose.y)
        tgt = (tgt_pose.x, tgt_pose.y)
        body = query.body

        # 1. Проверка стен (абсолютная преграда для текущей физики)
        for wall in geometry.walls:
            dist_sq = segments_distance_sq(src, tgt, (wall.x1, wall.y1), (wall.x2, wall.y2))
            if math.sqrt(dist_sq) - body.radius < 0:
                return TraversalPlan(possible=False, reason="WALL_CLEARANCE_BLOCKED")

        # 2. Сбор всех препятствий на пути
        blocking_obstacles: List[Tuple[Obstacle, float]] = []
        for obs in geometry.obstacles:
            dist_sq = segment_to_rect_min_dist_sq(src, tgt, obs.x, obs.y, obs.w, obs.h)
            clearance = math.sqrt(dist_sq) - body.radius
            if clearance < 0:
                blocking_obstacles.append((obs, clearance))

        # 3. Если препятствий нет — чистый WALK
        if not blocking_obstacles:
            return TraversalPlan(
                possible=True, 
                segments=(TraversalSegment(mode=TraversalMode.WALK, start_pose=src_pose, end_pose=tgt_pose),)
            )

        # 4. Построение плана: WALK -> [JUMP -> WALK]*
        candidates = self._topology_solver.solve_jump_candidates(
            src_pose, tgt_pose, blocking_obstacles, body.radius
        )

        segments: List[TraversalSegment] = []
        current_pose = src_pose
        
        for candidate in candidates:
            # Сегмент WALK до точки входа
            if (current_pose.x, current_pose.y) != (candidate.entry_pose.x, candidate.entry_pose.y):
                segments.append(TraversalSegment(
                    mode=TraversalMode.WALK,
                    start_pose=current_pose,
                    end_pose=candidate.entry_pose
                ))
                current_pose = candidate.entry_pose

            # Оценка перехода (JUMP)
            feasibility = self._transition_kernel.evaluate_transition(candidate, body)
            
            if not feasibility.possible:
                return TraversalPlan(
                    possible=False, 
                    reason=feasibility.reason, 
                    segments=tuple(segments),
                    required_capability=feasibility.required_capability,
                    available_clearance=feasibility.available_clearance
                )

            # Сегмент JUMP
            segments.append(TraversalSegment(
                mode=TraversalMode.JUMP,
                start_pose=current_pose,
                end_pose=candidate.exit_pose,
                obstacle_id=candidate.obstacle_id
            ))
            current_pose = candidate.exit_pose

        # Финальный сегмент WALK до цели
        if (current_pose.x, current_pose.y) != tgt:
            segments.append(TraversalSegment(
                mode=TraversalMode.WALK,
                start_pose=current_pose,
                end_pose=tgt_pose
            ))

        return TraversalPlan(possible=True, segments=tuple(segments))