# -*- coding: utf-8 -*-
"""
EventCompiler — единственная симуляция мира (ADR-O-201, ФАЗА 0).

Читает из замороженного снимка (WorldSnapshot), вычисляет физику события,
возвращает полный контракт (ThickSceneChange).

НЕ мутирует мир. НЕ вызывает SpatialService.build_for_location().
НЕ вызывает Python random. Только детерминированные вычисления.

Правила (ADR-O-201):
  Rule 117: ❌ SpatialService query внутри apply_changes → EventCompiler
  Rule 118: ❌ RNG внутри apply_changes → deterministic jitter
  Rule 119: ❌ Pathfinding внутри apply_changes → EventCompiler
  Rule 120: ❌ Traversal creation внутри apply_changes → TraversalContract
  Rule 121: ❌ Geometry compute внутри apply_changes → SpatialResolution
  Rule 122: ❌ Direct state mutation before apply_changes → never here
"""
from __future__ import annotations

import hashlib
import logging
import math
from typing import Any, Dict, List, Optional, Tuple

from app.models.thick_scene_change import (
    BoundaryResolution,
    MotionPlan,
    SpatialResolution,
    ThickSceneChange,
    TraversalContract,
)
from app.models.world_snapshot import WorldSnapshot
from app.services.scene_change import ChangeType, SceneChange

logger = logging.getLogger(__name__)


class EventCompiler:
    """Shadow Compiler (ADR-O-201, ФАЗА 0).

    Вычисляет ThickSceneChange из WorldSnapshot + SceneChange.
    Параллелен legacy pipeline. Не влияет на симуляцию.

    ФАЗА 0: компилирует, логирует, НЕ применяет.
    ФАЗА 1: EquivalenceValidator сравнивает с legacy.
    """

    # Константы — совпадают с legacy apply_change
    _DEFAULT_SPEED: float = 2.0
    _TELEPORT_THRESHOLD: float = 0.1
    _JITTER_RANGE: float = 0.4

    def compile(
        self, snapshot: WorldSnapshot, change: SceneChange
    ) -> Optional[ThickSceneChange]:
        """Компилирует SceneChange → ThickSceneChange.

        Returns None если изменение не может быть скомпилировано
        (узел не найден, нет spatial service).
        Соответствует apply_change returning False.
        """
        # Не-NPC_POSITION — passthrough без spatial вычислений
        if not isinstance(change, SceneChange):
            return None

        if change.type != ChangeType.NPC_POSITION:
            result = self._compile_non_spatial(snapshot, change)
            logger.debug(
                f"[SHADOW_COMPILER] passthrough: type={change.type.value} "
                f"target={change.target}"
            )
            return result

        # NPC_POSITION — полная компиляция
        if change.field == "position":
            result = self._compile_position_change(snapshot, change)
        elif change.field == "local_position":
            result = self._compile_local_position_change(snapshot, change)
        else:
            result = self._compile_non_spatial(snapshot, change)

        if result is not None:
            logger.info(
                f"[SHADOW_COMPILER] compiled: target={change.target} "
                f"field={change.field} cause={change.cause} "
                f"spatial={'yes' if result.spatial else 'no'} "
                f"traversal={result.traversal.status if result.traversal else 'none'}"
            )
        else:
            logger.warning(
                f"[SHADOW_COMPILER] FAILED: target={change.target} "
                f"field={change.field} value={change.value}"
            )

        return result

    # ── Passthrough ───────────────────────────────────────────────

    def _compile_non_spatial(
        self, snapshot: WorldSnapshot, change: SceneChange
    ) -> ThickSceneChange:
        """Не-пространственные изменения — passthrough без физики."""
        return ThickSceneChange(
            change_type=change.type.value,
            target=change.target,
            field=change.field,
            value=change.value,
            cause=change.cause,
            tick=change.tick,
            target_local_xy=getattr(change, 'target_local_xy', None),
            target_location_id=getattr(change, 'target_location_id', ''),
        )

    def _compile_local_position_change(
        self, snapshot: WorldSnapshot, change: SceneChange
    ) -> ThickSceneChange:
        """NPC_POSITION field='local_position' — прямой xy update, без traversal."""
        target_xy: Tuple[float, float] = (0.0, 0.0)
        if isinstance(change.value, dict):
            target_xy = (
                float(change.value.get("x", 0.0)),
                float(change.value.get("y", 0.0)),
            )
        return ThickSceneChange(
            change_type=change.type.value,
            target=change.target,
            field=change.field,
            value=change.value,
            cause=change.cause,
            tick=change.tick,
            spatial=SpatialResolution(
                source_location=snapshot.location_id,
                target_location=snapshot.location_id,
                source_node="",
                target_node="",
                source_xy=(0.0, 0.0),
                target_xy=target_xy,
            ),
            motion=MotionPlan(
                is_teleport=True,
                is_path_blocked=False,
                waypoints=(),
                distance=0.0,
                duration_ticks=0,
                speed=0.0,
            ),
        )

    # ── Main: NPC_POSITION field='position' ───────────────────────

    def _compile_position_change(
        self, snapshot: WorldSnapshot, change: SceneChange
    ) -> Optional[ThickSceneChange]:
        """Полная компиляция NPC_POSITION field='position'.

        Соответствует 20 вычислениям legacy apply_change + _process_traversals.
        """
        # E1: target_loc resolution
        target_loc = getattr(change, 'target_location_id', '') or snapshot.location_id

        # E2: Spatial service из snapshot (НЕ build_for_location!)
        svc = snapshot.spatial_service
        if svc is None:
            logger.warning("[SHADOW_COMPILER] No spatial service in snapshot")
            return None

        # E3: Node lookup
        node = svc.get_node(change.value) or svc.get_node(
            f"{target_loc}:{change.value}"
        )
        if node is None:
            logger.warning(
                f"[SHADOW_COMPILER] Node not found: {change.value} "
                f"loc={target_loc}"
            )
            return None

        # E4 vs E5-E16: Cross-location vs same-location
        if target_loc != snapshot.location_id:
            return self._compile_boundary_snap(snapshot, change, node, target_loc, svc)

        return self._compile_same_location_movement(
            snapshot, change, node, svc
        )

    # ── Boundary Snap (Cross-location, ДОЛГ 6.2) ─────────────────

    def _compile_boundary_snap(
        self,
        snapshot: WorldSnapshot,
        change: SceneChange,
        node: Any,
        target_loc: str,
        svc: Any,
    ) -> ThickSceneChange:
        """E4: Кросс-локационное перемещение — snap без traversal.

        NPC уже завершил движение, материализуем в новом чанке.
        SceneChange = semantic, EventCompiler = geometric resolver.
        """
        # E18-E19: Boundary resolution (из snapshot, не из live query)
        is_boundary = False
        neighbor_chunk = ""
        entry_node = ""

        # Проверяем по NodeRole если доступен
        from app.models.spatial_contracts import NodeRole
        if hasattr(node, 'role') and node.role == NodeRole.BOUNDARY:
            is_boundary = True
            boundary_info = svc.get_boundary_info(node.node_id)
            if boundary_info:
                neighbor_chunk = boundary_info.get("neighbor_chunk", "")
                entry_hint = boundary_info.get("entry_node_hint", "")
                entry_dir = boundary_info.get("entry_direction", "")
                if entry_hint:
                    entry_node = entry_hint
                elif entry_dir and neighbor_chunk:
                    entry_node = f"{neighbor_chunk}:entry_{entry_dir}"
                elif neighbor_chunk:
                    entry_node = f"{neighbor_chunk}:entrance"

        # Если target_location_id задан напрямую (от _process_traversals)
        if target_loc and not neighbor_chunk:
            neighbor_chunk = target_loc

        return ThickSceneChange(
            change_type=change.type.value,
            target=change.target,
            field=change.field,
            value=change.value,
            cause=change.cause,
            tick=change.tick,
            target_local_xy=getattr(change, 'target_local_xy', None),
            target_location_id=target_loc,
            spatial=SpatialResolution(
                source_location=snapshot.location_id,
                target_location=target_loc,
                source_node="",
                target_node=node.node_id,
                source_xy=(0.0, 0.0),
                target_xy=(node.x, node.y),
            ),
            boundary=BoundaryResolution(
                is_boundary=is_boundary,
                neighbor_chunk=neighbor_chunk,
                entry_node=entry_node,
            ),
            # Boundary snap — traversal не нужен (materialization)
            traversal=TraversalContract(
                status="COMPLETED" if change.cause == "traversal_complete" else "",
                fields={},
            ),
        )

    # ── Same-Location Movement ────────────────────────────────────

    def _compile_same_location_movement(
        self,
        snapshot: WorldSnapshot,
        change: SceneChange,
        node: Any,
        svc: Any,
    ) -> Optional[ThickSceneChange]:
        """E5-E16: Движение внутри локации — traversal creation."""
        # BUG_V_GUARD mirror: если source_node == target_node — нет пространственного
        # изменения, traversal не нужен. Legacy apply_change пропускает это через
        # _old_position == change.value check. EventCompiler должен делать то же самое.
        # Без этого guard'а ghost interpolation делает source_xy ≠ target_xy
        # даже когда узел совпадает → ложный traversal → parity mismatch.
        source_node = self._get_source_node(snapshot, change)
        if source_node and source_node == node.node_id:
            # BUG_V_GUARD mirror: NPC уже на целевом узле — нет причинной структуры
            # перемещения. Не создаём ThickSceneChange для "движения без движения".
            # Legacy apply_change тоже пропускает traversal (BUG_V_GUARD).
            # Если движения нет — сущности не существует (принцип ENIGMA).
            logger.debug(
                f"[SHADOW_COMPILER] source_node==target_node: npc={change.target} "
                f"node={node.node_id} — no spatial change"
            )
            return None

        # E5-E7: source_xy (Ghost Position Interpolation + Spatial Recovery)
        source_xy = self._compute_source_xy(snapshot, change, svc)
        # E8-E9: target_xy (target_local_xy or deterministic jitter)
        target_xy = self._compute_target_xy(snapshot, change, node)

        # E10: Teleport check
        dist = self._euclidean_distance(source_xy, target_xy)
        is_teleport = dist < self._TELEPORT_THRESHOLD

        # E4 (same-loc): источник и цель — одна локация
        spatial = SpatialResolution(
            source_location=snapshot.location_id,
            target_location=snapshot.location_id,
            source_node=self._get_source_node(snapshot, change),
            target_node=node.node_id,
            source_xy=source_xy,
            target_xy=target_xy,
        )

        if is_teleport:
            # Микро-перемещение — traversal не нужен
            return ThickSceneChange(
                change_type=change.type.value,
                target=change.target,
                field=change.field,
                value=change.value,
                cause=change.cause,
                tick=change.tick,
                target_local_xy=getattr(change, 'target_local_xy', None),
                spatial=spatial,
                motion=MotionPlan(
                    is_teleport=True,
                    is_path_blocked=False,
                    waypoints=(),
                    distance=0.0,
                    duration_ticks=0,
                    speed=0.0,
                ),
            )

        # E11-E16: Полное движение с pathfinding и traversal
        return self._compile_full_movement(
            snapshot, change, node, svc, spatial, source_xy, target_xy
        )

    def _compile_full_movement(
        self,
        snapshot: WorldSnapshot,
        change: SceneChange,
        node: Any,
        svc: Any,
        spatial: SpatialResolution,
        source_xy: Tuple[float, float],
        target_xy: Tuple[float, float],
    ) -> ThickSceneChange:
        """E11-E16: Pathfinding, distance, duration, traversal creation."""
        # E11: Wall blocking check (из snapshot, не из live scene_state)
        is_path_blocked = self._check_wall_blocking(snapshot, source_xy, target_xy)

        # E12-E13: Pathfinding + waypoint assembly
        waypoints: List[List[float]] = [[source_xy[0], source_xy[1]]]
        if is_path_blocked and svc:
            path = self._find_path(svc, source_xy, node)
            if path and len(path) >= 2:
                # Пропускаем первый (source) и последний (target) —
                # они уже в waypoints
                intermediate = [[pn.x, pn.y] for pn in path[1:-1]]
                waypoints.extend(intermediate)
                logger.info(
                    f"[SHADOW_COMPILER] pathfinding: npc={change.target} "
                    f"via {len(intermediate)} intermediate nodes"
                )
            else:
                logger.warning(
                    f"[SHADOW_COMPILER] path blocked but no path found: "
                    f"npc={change.target}"
                )
        waypoints.append([target_xy[0], target_xy[1]])

        # E14: Distance calculation (сумма сегментов, как legacy)
        distance = self._path_distance(waypoints)

        # E15: Duration calculation
        duration_ticks = max(
            1, math.ceil(distance / self._DEFAULT_SPEED)
        ) if self._DEFAULT_SPEED > 0 else 1

        # E16: Traversal contract (все поля для scene_state)
        current_tick = snapshot.tick
        traversal_fields = {
            "npc_id": change.target,
            "from_node": spatial.source_node or change.value,
            "target_node": change.value,
            "path_waypoints": waypoints,
            "speed": self._DEFAULT_SPEED,
            "started_tick": current_tick,
            "duration_ticks": duration_ticks,
            "locomotion": "WALK",
            "status": "MOVING",
        }

        motion = MotionPlan(
            is_teleport=False,
            is_path_blocked=is_path_blocked,
            waypoints=tuple(tuple(wp) for wp in waypoints),
            distance=distance,
            duration_ticks=duration_ticks,
            speed=self._DEFAULT_SPEED,
        )

        traversal = TraversalContract(
            status="NEW",
            fields=traversal_fields,
        )

        return ThickSceneChange(
            change_type=change.type.value,
            target=change.target,
            field=change.field,
            value=change.value,
            cause=change.cause,
            tick=change.tick,
            target_local_xy=getattr(change, 'target_local_xy', None),
            spatial=spatial,
            motion=motion,
            traversal=traversal,
        )

    # ── Вспомогательные вычисления ────────────────────────────────

    def _compute_source_xy(
        self,
        snapshot: WorldSnapshot,
        change: SceneChange,
        svc: Any,
    ) -> Tuple[float, float]:
        """E5-E7: Вычисление позиции старта NPC.

        Приоритет:
        1. Ghost Position Interpolation (из active traversal)
        2. npc_positions local_position
        3. Spatial Recovery (из узла через svc)
        4. Fallback (0, 0)
        """
        npc_id = change.target

        # E5: Ghost Position Interpolation
        active_travs = snapshot.active_traversals
        if npc_id in active_travs:
            trav = active_travs[npc_id]
            wp = trav.get("path_waypoints", [])
            if len(wp) >= 2:
                started = int(trav.get("started_tick", 0))
                dur = max(1, int(trav.get("duration_ticks", 1)))
                cur_tick = snapshot.tick
                prog = min(1.0, max(0.0, (cur_tick - started) / dur))
                interp_x = wp[0][0] + (wp[-1][0] - wp[0][0]) * prog
                interp_y = wp[0][1] + (wp[-1][1] - wp[0][1]) * prog
                logger.debug(
                    f"[SHADOW_COMPILER] ghost_interp: npc={npc_id} "
                    f"prog={prog:.2f} xy=({interp_x:.1f},{interp_y:.1f})"
                )
                return (interp_x, interp_y)

        # npc_positions local_position
        npc_pos = snapshot.npc_positions.get(npc_id, {})
        lp = npc_pos.get("local_position")
        if isinstance(lp, dict) and isinstance(lp.get("x"), (int, float)):
            return (float(lp["x"]), float(lp["y"]))

        # E6: Spatial Recovery — из узла текущей позиции
        old_position = npc_pos.get("position", "")
        if old_position and svc:
            from_node = svc.get_node(old_position) or svc.get_node(
                f"{snapshot.location_id}:{old_position}"
            )
            if from_node:
                logger.debug(
                    f"[SHADOW_COMPILER] spatial_recovery: npc={npc_id} "
                    f"from_node={from_node.node_id}"
                )
                return (from_node.x, from_node.y)

        # E7: Fallback (0, 0) — устраняется в Gen 3 (perceive_world)
        return (0.0, 0.0)

    def _compute_target_xy(
        self,
        snapshot: WorldSnapshot,
        change: SceneChange,
        node: Any,
    ) -> Tuple[float, float]:
        """E8-E9: Вычисление позиции цели.

        Приоритет:
        1. target_local_xy из SceneChange (для approach)
        2. Node center + deterministic jitter
        """
        # E8: target_local_xy из change
        exact_xy = getattr(change, 'target_local_xy', None)
        if exact_xy and isinstance(exact_xy, (tuple, list)) and len(exact_xy) == 2:
            return (float(exact_xy[0]), float(exact_xy[1]))

        # E9: Deterministic jitter (вместо random.uniform)
        dx, dy = self._deterministic_jitter(
            snapshot.rng_seed, change.target, node.node_id
        )
        return (node.x + dx, node.y + dy)

    def _deterministic_jitter(
        self, rng_seed: int, npc_id: str, node_id: str
    ) -> Tuple[float, float]:
        """Детерминированный jitter на основе seed + npc + node.

        Заменяет random.uniform(-0.4, 0.4) из legacy apply_change.
        Распределение аналогичное, но полностью воспроизводимое.
        Ожидаемый Class A (Cosmetic) drift с legacy.
        """
        h = hashlib.sha256(
            f"{rng_seed}:{npc_id}:{node_id}".encode()
        ).hexdigest()
        v1 = int(h[:8], 16) / 0xFFFFFFFF
        v2 = int(h[8:16], 16) / 0xFFFFFFFF
        return (
            (v1 - 0.5) * self._JITTER_RANGE * 2,
            (v2 - 0.5) * self._JITTER_RANGE * 2,
        )

    def _check_wall_blocking(
        self,
        snapshot: WorldSnapshot,
        source_xy: Tuple[float, float],
        target_xy: Tuple[float, float],
    ) -> bool:
        """E11: Проверка блокировки стеной.

        Читает spatial_walls из snapshot (не из live scene_state).
        """
        try:
            from app.services.spatial.spatial_runtime import is_blocked_by_wall
            # Конструируем минимальный контекст из frozen данных
            _spatial_ctx: Dict[str, Any] = {
                "spatial_walls": snapshot.spatial_walls or [],
                "spatial_obstacles": snapshot.spatial_obstacles or [],
            }
            return is_blocked_by_wall(
                source_xy[0], source_xy[1],
                target_xy[0], target_xy[1],
                _spatial_ctx,
            )
        except Exception as exc:
            logger.warning(f"[SHADOW_COMPILER] wall_check failed: {exc}")
            return False

    def _find_path(
        self, svc: Any, start_xy: Tuple[float, float], target_node: Any
    ) -> Optional[list]:
        """E12: Pathfinding через snapshot's SpatialService."""
        try:
            from app.services.spatial.spatial_service import Urgency
            return svc.find_path(
                start_xy=start_xy,
                target_node=target_node,
                urgency=Urgency.URGENT,
            )
        except Exception as exc:
            logger.warning(f"[SHADOW_COMPILER] find_path failed: {exc}")
            return None

    def _get_source_node(
        self, snapshot: WorldSnapshot, change: SceneChange
    ) -> str:
        """Извлекает source_node из позиции NPC."""
        npc_pos = snapshot.npc_positions.get(change.target, {})
        return npc_pos.get("position", "")

    @staticmethod
    def _euclidean_distance(
        a: Tuple[float, float], b: Tuple[float, float]
    ) -> float:
        """Евклидово расстояние между двумя точками."""
        return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5

    @staticmethod
    def _path_distance(waypoints: List[List[float]]) -> float:
        """E14: Дистанция по маршруту (сумма сегментов)."""
        dist = 0.0
        for i in range(len(waypoints) - 1):
            dx = waypoints[i + 1][0] - waypoints[i][0]
            dy = waypoints[i + 1][1] - waypoints[i][1]
            dist += (dx * dx + dy * dy) ** 0.5
        return dist