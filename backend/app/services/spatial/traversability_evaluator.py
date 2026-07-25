"""
Назначение: Pure function evaluator. Делегирует построение плана в LocalTraversalPlanner.
"""

from __future__ import annotations

import logging

from app.domain.traversal import TraversalFeasibility, TraversalMode, TraversalQuery
from app.services.spatial.local_traversal_planner import LocalTraversalPlanner

logger = logging.getLogger(__name__)

class TraversabilityEvaluator:
    """Pure function evaluator. Делегирует построение плана в LocalTraversalPlanner."""

    def __init__(self):
        self._planner = LocalTraversalPlanner()

    def evaluate(self, query: TraversalQuery, geometry: "LocalGeometry") -> TraversalFeasibility:
        plan = self._planner.compile_plan(query, geometry)

        if plan.possible:
            # Если план возможен, проверяем, есть ли в нём JUMP.
            # Если есть только WALK — это чистый WALK.
            # Если есть JUMP — возвращаем JUMP.
            modes = {s.mode for s in plan.segments}
            if TraversalMode.JUMP in modes:
                return TraversalFeasibility(possible=True, mode=TraversalMode.JUMP, required_capability="can_jump")
            return TraversalFeasibility(possible=True, mode=TraversalMode.WALK)

        return TraversalFeasibility(
            possible=False,
            mode=TraversalMode.NONE,
            reason=plan.reason or "PLAN_BLOCKED"
        )
