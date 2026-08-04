# path: backend/app/services/spatial/traversal_execution_system.py
"""
TraversalExecutionSystem — вычисляет текущую позицию NPC на основе TraversalState.
Реализация ADR-O-315: Движение — это процесс во времени, координата — производная.
"""

import logging
import math
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)


class TraversalExecutionSystem:
    """Продвигает TraversalState и проецирует его в local_position (Derived State).
    S132.1: Segment-Aware Execution. Учитывает segment_modes (WALK/JUMP) для честной кинематики.
    """

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

            # S134.1: Жёсткая валидация кинематического контракта.
            segment_modes = trav.get("segment_modes")
            segment_arc_heights = trav.get("segment_arc_heights")

            modes_missing = segment_modes is None
            arcs_missing = segment_arc_heights is None

            if modes_missing and arcs_missing:
                # A. Legacy fallback для старых сохранений без сегментов
                logger.warning(f"[TRAV_EXEC] Legacy traversal for {npc_id}, synthesizing WALK.")
                expected_segs = max(0, len(waypoints) - 1)
                segment_modes = ["WALK"] * expected_segs
                segment_arc_heights = [0.0] * expected_segs
            elif modes_missing or arcs_missing:
                # C. Partial corruption — игра должна упасть громко
                from app.errors import SimulationIntegrityError
                raise SimulationIntegrityError(
                    invariant_id="INV-TRAV-CONTRACT",
                    message=f"Partial contract corruption for {npc_id}: one of segment_modes/arc_heights is missing",
                    suspect_files=["backend/app/services/spatial/movement_engine.py"],
                    file=__file__, line=48,
                )
            elif len(segment_modes) != len(waypoints) - 1 or len(segment_arc_heights) != len(waypoints) - 1:
                # B. Invalid length — игра должна упасть громко
                from app.errors import SimulationIntegrityError
                raise SimulationIntegrityError(
                    invariant_id="INV-TRAV-CONTRACT",
                    message=f"Kinematic contract violated for {npc_id}: len(segment_modes) != len(waypoints)-1",
                    suspect_files=["backend/app/services/spatial/movement_engine.py", "backend/app/domain/traversal_schema.py"],
                    file=__file__, line=57,
                )

            if not waypoints:
                continue

            elapsed_ticks = current_tick - started_tick

            if elapsed_ticks >= duration_ticks:
                # Маршрут завершён — Snap на финальную точку
                target_xy = waypoints[-1]
                npc_positions.setdefault(npc_id, {}).update({"local_position": {
                    "x": target_xy[0],
                    "y": target_xy[1],
                    "z": 0.0,  # S132.1: Завершение прыжка — возврат на землю
                }})
                # BUG-SPATIAL-026 FIX: Используем transition_traversal() FSM вместо прямой мутации.
                from app.domain.traversal_schema import transition_traversal
                if not transition_traversal(trav, "COMPLETED"):
                    logger.error(f"[TRAV_EXEC_FSM] Failed to transition to COMPLETED for npc={npc_id}")
                completed_npcs.append(npc_id)
                logger.debug(
                    f"[TRAV_EXEC] COMPLETED: npc={npc_id} snapped to {target_xy}"
                )
            else:
                # Маршрут активен — интерполяция по пути
                progress = elapsed_ticks / duration_ticks if duration_ticks > 0 else 1.0
                pos, seg_idx = TraversalExecutionSystem._interpolate_path(
                    waypoints, progress, segment_modes, segment_arc_heights
                )
                if pos:
                    npc_positions.setdefault(npc_id, {}).update({"local_position": {
                        "x": pos[0],
                        "y": pos[1],
                        "z": pos[2],  # S132.1: Z-координата для прыжков
                    }})
                    # Обновляем current_waypoint_idx для фронтенда
                    trav["current_waypoint_idx"] = seg_idx

        # Очистка завершённых маршрутов (SSM владеет lifecycle, но мы помогаем избежать зомби)
        for npc_id in completed_npcs:
            # SSM FSM должен обработать COMPLETED -> cleanup.
            # Пока просто логируем, чтобы SSM мог убрать запись, если он запущен.
            pass

    @staticmethod
    def resolve(
        npc_id: str, scene_state: Dict[str, Any], current_tick: int
    ) -> Tuple[float, float]:
        """Чистая функция: возвращает текущую мировую позицию NPC (x, y)."""
        trav = scene_state.get("active_traversals", {}).get(npc_id)
        if trav and trav.get("status") == "MOVING":
            started_tick = trav.get("started_tick", current_tick)
            duration_ticks = trav.get("duration_ticks", 1)
            waypoints = trav.get("path_waypoints", [])
            segment_modes = trav.get("segment_modes", [])
            segment_arc_heights = trav.get("segment_arc_heights", [])
            if not segment_modes or len(segment_modes) != len(waypoints) - 1:
                segment_modes = ["WALK"] * max(1, len(waypoints) - 1)
                segment_arc_heights = [0.0] * max(1, len(waypoints) - 1)

            if waypoints:
                elapsed_ticks = current_tick - started_tick
                if elapsed_ticks >= duration_ticks:
                    return (waypoints[-1][0], waypoints[-1][1])
                progress = elapsed_ticks / duration_ticks if duration_ticks > 0 else 1.0
                pos, _ = TraversalExecutionSystem._interpolate_path(
                    waypoints, progress, segment_modes, segment_arc_heights
                )
                if pos:
                    return (pos[0], pos[1])

        # Fallback на кэшированную позицию
        lp = (
            scene_state.get("npc_positions", {})
            .get(npc_id, {})
            .get("local_position", {})
        )
        return (lp.get("x", 0.0), lp.get("y", 0.0))

    @staticmethod
    def _interpolate_path(
        waypoints: List[Any],
        progress: float,
        segment_modes: List[str],
        segment_arc_heights: List[float]
    ) -> Tuple[Tuple[float, float, float], int]:
        """S132.1: Интерполяция вдоль пути с учётом сегментов (WALK/JUMP).
        Возвращает ((x, y, z), current_segment_index).
        """
        if not waypoints:
            return ((0.0, 0.0, 0.0), 0)
        if len(waypoints) == 1:
            return ((waypoints[0][0], waypoints[0][1], 0.0), 0)

        total_dist = 0.0
        segment_dists = []
        for i in range(len(waypoints) - 1):
            dx = waypoints[i + 1][0] - waypoints[i][0]
            dy = waypoints[i + 1][1] - waypoints[i][1]
            d = math.hypot(dx, dy)
            segment_dists.append(d)
            total_dist += d

        if total_dist == 0:
            return ((waypoints[0][0], waypoints[0][1], 0.0), 0)

        target_dist = total_dist * progress
        current_dist = 0.0

        for i, seg_dist in enumerate(segment_dists):
            if current_dist + seg_dist >= target_dist:
                seg_progress = (
                    (target_dist - current_dist) / seg_dist if seg_dist > 0 else 0.0
                )

                # S132.1: Линейная интерполяция для X и Y (работает для обоих режимов)
                x = waypoints[i][0] + (waypoints[i + 1][0] - waypoints[i][0]) * seg_progress
                y = waypoints[i][1] + (waypoints[i + 1][1] - waypoints[i][1]) * seg_progress

                # S132.1: Вычисление Z (высоты) в зависимости от режима сегмента
                mode = segment_modes[i] if i < len(segment_modes) else "WALK"
                if mode == "JUMP":
                    # Параболическая траектория: z(t) = 4 * h * t * (1 - t)
                    # где h - максимальная высота прыжка, t - локальный прогресс сегмента [0..1]
                    arc_h = segment_arc_heights[i] if i < len(segment_arc_heights) else 1.0
                    z = 4.0 * arc_h * seg_progress * (1.0 - seg_progress)
                else:
                    z = 0.0 # WALK - движение по земле

                return ((x, y, z), i)

            current_dist += seg_dist

        return ((waypoints[-1][0], waypoints[-1][1], 0.0), len(segment_dists) - 1)
