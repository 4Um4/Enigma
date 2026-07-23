"""
Файл: backend/app/services/spatial/transition_topology_solver.py
Назначение: Вычисляет геометрию локального перехода (точки входа/выхода, дистанция, высота) на основе конфликта тела с препятствием.
"""

from __future__ import annotations

import logging
import math
from typing import List, Optional, Tuple

from app.domain.traversal import Obstacle, Pose, TransitionCandidate, TraversalMode
from app.services.spatial.geometry_kernel import point_in_expanded_rect, segments_intersect

logger = logging.getLogger(__name__)

class TransitionTopologySolver:
    """Вычисляет геометрию локального перехода (entry/exit) через препятствие."""

    def solve_jump_candidates(
        self,
        source_pose: Pose,
        target_pose: Pose,
        blocking_obstacles: List[Tuple[Obstacle, float]],
        body_radius: float
    ) -> List[TransitionCandidate]:
        """Строит кандидаты на переход (JUMP) для всех блокирующих препятствий.
        Точки входа/выхода вычисляются относительно Collision Envelope (AABB + body_radius).
        """
        candidates = []
        src = (source_pose.x, source_pose.y)
        tgt = (target_pose.x, target_pose.y)
        
        for obs, clearance in blocking_obstacles:
            # Если источник или цель уже внутри Collision Envelope (AABB + radius) — переход невозможен (глубокое проникновение)
            if point_in_expanded_rect(src, obs.x, obs.y, obs.w, obs.h, body_radius) or \
               point_in_expanded_rect(tgt, obs.x, obs.y, obs.w, obs.h, body_radius):
                continue
                
            # Строим расширенный AABB (Collision Envelope)
            exp_x = obs.x - body_radius
            exp_y = obs.y - body_radius
            exp_w = obs.w + 2 * body_radius
            exp_h = obs.h + 2 * body_radius
            
            entry_point = self._get_rect_boundary_intersection(src, tgt, exp_x, exp_y, exp_w, exp_h, nearest_to_src=True)
            exit_point = self._get_rect_boundary_intersection(src, tgt, exp_x, exp_y, exp_w, exp_h, nearest_to_src=False)
            
            if not entry_point or not exit_point:
                continue
                
            horiz_dist = math.dist(entry_point, exit_point)
            
            candidates.append(TransitionCandidate(
                mode=TraversalMode.JUMP,
                obstacle_id=obs.id,
                entry_pose=Pose(entry_point[0], entry_point[1], source_pose.z),
                exit_pose=Pose(exit_point[0], exit_point[1], target_pose.z),
                horizontal_distance=horiz_dist,
                vertical_delta=target_pose.z - source_pose.z,
                obstacle_height=obs.height,
                trajectory_clearance=clearance
            ))
            
        # Сортируем кандидатов по удалённости точки входа от source
        candidates.sort(key=lambda c: (c.entry_pose.x - src[0])**2 + (c.entry_pose.y - src[1])**2)
        return candidates

    def _get_rect_boundary_intersection(
        self, 
        src: Tuple[float, float], 
        tgt: Tuple[float, float], 
        rx: float, ry: float, rw: float, rh: float,
        nearest_to_src: bool
    ) -> Optional[Tuple[float, float]]:
        """Находит точку пересечения отрезка src-tgt с границей AABB."""
        corners = [(rx, ry), (rx+rw, ry), (rx+rw, ry+rh), (rx, ry+rh)]
        intersections = []
        
        for i in range(4):
            c1 = corners[i]
            c2 = corners[(i+1)%4]
            if segments_intersect(src, tgt, c1, c2):
                denom = (c2[1]-c1[1])*(tgt[0]-src[0]) - (c2[0]-c1[0])*(tgt[1]-src[1])
                if abs(denom) < 1e-9: continue
                ua = ((c2[0]-c1[0])*(src[1]-c1[1]) - (c2[1]-c1[1])*(src[0]-c1[0])) / denom
                if 0.0 <= ua <= 1.0:
                    ix = src[0] + ua * (tgt[0] - src[0])
                    iy = src[1] + ua * (tgt[1] - src[1])
                    intersections.append((ix, iy))
                    
        if not intersections:
            return None
            
        if nearest_to_src:
            return min(intersections, key=lambda p: (p[0]-src[0])**2 + (p[1]-src[1])**2)
        else:
            return min(intersections, key=lambda p: (p[0]-tgt[0])**2 + (p[1]-tgt[1])**2)