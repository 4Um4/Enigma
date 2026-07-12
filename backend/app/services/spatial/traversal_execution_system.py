# path: backend/app/services/spatial/traversal_execution_system.py
"""
TraversalExecutionSystem — вычисляет текущую позицию NPC на основе TraversalState.
Реализация ADR-O-315: Движение — это процесс во времени, координата — производная.
"""

import logging
import math
from typing import List, Dict, Any, Tuple

logger = logging.getLogger(__name__)


class TraversalExecutionSystem:
    """Продвигает TraversalState и проецирует его в local_position (Derived State)."""

    @staticmethod
    def advance(scene_state: Dict[str, Any], current_tick: int) -> None:
        """Вызывается в Фазе 0.5. Продвигает все активные маршруты."""
        traversals = scene_state.get("active_traversals", {})
        if not traversals:
            return

        logger.debug(
            f"[TRAV_EXEC_ADVANCE] tick={current_tick} active_traversals={list(traversals.keys())}"
        )

        npc_positions = scene_state.setdefault("npc_positions", {})
        completed_npcs = []

        for npc_id, trav in traversals.items():
            if trav.get("status") != "MOVING":
                continue

            started_tick = trav.get("started_tick", current_tick)
            duration_ticks = trav.get("duration_ticks", 1)
            waypoints = trav.get("path_waypoints", [])

            if not waypoints:
                continue

            elapsed_ticks = current_tick - started_tick

            if elapsed_ticks >= duration_ticks:
                # Маршрут завершён — Snap на финальную точку
                target_xy = waypoints[-1]
                npc_positions.setdefault(npc_id, {})["local_position"] = {
                    "x": target_xy[0],
                    "y": target_xy[1],
                }
                trav["status"] = "COMPLETED"
                completed_npcs.append(npc_id)
                logger.debug(
                    f"[TRAV_EXEC] COMPLETED: npc={npc_id} snapped to {target_xy}"
                )
            else:
                # Маршрут активен — интерполяция по пути
                progress = elapsed_ticks / duration_ticks if duration_ticks > 0 else 1.0
                pos = TraversalExecutionSystem._interpolate_path(waypoints, progress)
                if pos:
                    npc_positions.setdefault(npc_id, {})["local_position"] = {
                        "x": pos[0],
                        "y": pos[1],
                    }
                    # Обновляем current_waypoint_idx для фронтенда
                    trav["current_waypoint_idx"] = (
                        TraversalExecutionSystem._get_current_wp_idx(
                            waypoints, progress
                        )
                    )

        # Очистка завершённых маршрутов (SSM владеет lifecycle, но мы помогаем избежать зомби)
        for npc_id in completed_npcs:
            # SSM FSM должен обработать COMPLETED -> cleanup.
            # Пока просто логируем, чтобы SSM мог убрать запись, если он запущен.
            pass

    @staticmethod
    def resolve(
        npc_id: str, scene_state: Dict[str, Any], current_tick: int
    ) -> Tuple[float, float]:
        """Чистая функция: возвращает текущую мировую позицию NPC."""
        trav = scene_state.get("active_traversals", {}).get(npc_id)
        if trav and trav.get("status") == "MOVING":
            started_tick = trav.get("started_tick", current_tick)
            duration_ticks = trav.get("duration_ticks", 1)
            waypoints = trav.get("path_waypoints", [])
            if waypoints:
                elapsed_ticks = current_tick - started_tick
                if elapsed_ticks >= duration_ticks:
                    return waypoints[-1]
                progress = elapsed_ticks / duration_ticks if duration_ticks > 0 else 1.0
                pos = TraversalExecutionSystem._interpolate_path(waypoints, progress)
                if pos:
                    return pos

        # Fallback на кэшированную позицию
        lp = (
            scene_state.get("npc_positions", {})
            .get(npc_id, {})
            .get("local_position", {})
        )
        return (lp.get("x", 0.0), lp.get("y", 0.0))

    @staticmethod
    def _interpolate_path(waypoints: List[Any], progress: float) -> Tuple[float, float]:
        """Линейная интерполяция вдоль пути."""
        if not waypoints:
            return (0.0, 0.0)
        if len(waypoints) == 1:
            return (waypoints[0][0], waypoints[0][1])

        total_dist = 0.0
        segment_dists = []
        for i in range(len(waypoints) - 1):
            dx = waypoints[i + 1][0] - waypoints[i][0]
            dy = waypoints[i + 1][1] - waypoints[i][1]
            d = math.hypot(dx, dy)
            segment_dists.append(d)
            total_dist += d

        if total_dist == 0:
            return (waypoints[0][0], waypoints[0][1])

        target_dist = total_dist * progress
        current_dist = 0.0

        for i, seg_dist in enumerate(segment_dists):
            if current_dist + seg_dist >= target_dist:
                seg_progress = (
                    (target_dist - current_dist) / seg_dist if seg_dist > 0 else 0.0
                )
                x = (
                    waypoints[i][0]
                    + (waypoints[i + 1][0] - waypoints[i][0]) * seg_progress
                )
                y = (
                    waypoints[i][1]
                    + (waypoints[i + 1][1] - waypoints[i][1]) * seg_progress
                )
                return (x, y)
            current_dist += seg_dist

        return (waypoints[-1][0], waypoints[-1][1])

    @staticmethod
    def _get_current_wp_idx(waypoints: List[Any], progress: float) -> int:
        """Возвращает индекс текущего waypoint для фронтенда."""
        if not waypoints:
            return 0
        idx = int(progress * (len(waypoints) - 1))
        return min(idx, len(waypoints) - 1)
