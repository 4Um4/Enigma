"""
Файл: backend/app/services/spatial/traversal_transition_kernel.py
Назначение: Оценивает физическую возможность перехода (TransitionCandidate) для конкретного тела (BodyCapabilities).
"""

from __future__ import annotations

import logging
from typing import List, Optional

from app.domain.traversal import BodyCapabilities, TransitionCandidate, TraversalFeasibility, TraversalMode

logger = logging.getLogger(__name__)

class TraversalTransitionKernel:
    """Оценивает возможность локального перехода для конкретного тела.

    В отличие от TraversabilityEvaluator (который оценивает прямую проходимость WALK),
    этот kernel оценивает сложные переходы (JUMP, CLIMB), требующие изменения режима движения.
    """

    def evaluate_transition(
        self,
        candidate: TransitionCandidate,
        body: BodyCapabilities
    ) -> TraversalFeasibility:
        """Проверяет, может ли тело преодолеть геометрический кандидат на переход."""

        if candidate.mode == TraversalMode.JUMP:
            return self._evaluate_jump(candidate, body)

        # В будущем: CLIMB, CRAWL
        return TraversalFeasibility(
            possible=False,
            mode=TraversalMode.NONE,
            reason=f"UNSUPPORTED_TRANSITION_MODE_{candidate.mode.name}"
        )

    def _evaluate_jump(
        self,
        candidate: TransitionCandidate,
        body: BodyCapabilities
    ) -> TraversalFeasibility:
        """Физика прыжка: высота препятствия и горизонтальная дистанция."""

        if not body.can_jump:
            return TraversalFeasibility(
                possible=False, mode=TraversalMode.JUMP,
                reason="MISSING_CAPABILITY", required_capability="can_jump"
            )

        # 1. Проверка высоты препятствия
        if candidate.obstacle_height > body.max_jump_height:
            return TraversalFeasibility(
                possible=False, mode=TraversalMode.JUMP,
                reason="OBSTACLE_TOO_HIGH",
                available_clearance=candidate.obstacle_height - body.max_jump_height,
                required_capability="max_jump_height"
            )

        # 2. Проверка горизонтальной дистанции перехода
        # (расстояние от точки входа до точки выхода)
        if candidate.horizontal_distance > body.max_jump_distance:
            return TraversalFeasibility(
                possible=False, mode=TraversalMode.JUMP,
                reason="GAP_TOO_WIDE",
                available_clearance=candidate.horizontal_distance - body.max_jump_distance,
                required_capability="max_jump_distance"
            )

        # 3. В будущем: проверка vertical_delta (если прыжок вверх/вниз)

        return TraversalFeasibility(
            possible=True,
            mode=TraversalMode.JUMP,
            required_capability="can_jump",
            available_clearance=candidate.trajectory_clearance
        )
