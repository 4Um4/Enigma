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
    SpatialTransitionMode,
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
            # ADR-TRAV-NOOP: cause="traversal_complete" — это факт ЗАВЕРШЕНИЯ движения, не начало нового.
            # Legacy apply_changes (scene_state_manager.py:1300-1324) уже сделал: snap local_position + transition MOVING→COMPLETED.
            # Shadow compiler НЕ должен создавать новый traversal — он должен только зафиксировать spatial resolution.
            if getattr(change, "cause", "") == "traversal_complete":
                result = self._compile_traversal_completion(snapshot, change)
            else:
                # State-based Idempotency: если NPC уже на целевом узле — это NOOP.
                # Не зависит от cause (traversal_complete, teleport, sync и т.д.).
                # Инвариант: current_state == target_state => отсутствие причинной структуры.
                _current_pos = getattr(change.traversal_proposal, "source_node", "") if change.traversal_proposal else ""
                if _current_pos and _current_pos == change.value:
                    logger.debug(
                        f"[SHADOW_COMPILER] NOOP: target={change.target} "
                        f"field=position value={change.value} (already at target node)"
                    )
                    return None
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

    def _compile_traversal_completion(
        self, snapshot: WorldSnapshot, change: SceneChange
    ) -> Optional[ThickSceneChange]:
        """ADR-TRAV-NOOP: Compilation of traversal_complete SceneChange.

        Legacy apply_changes (scene_state_manager.py:1300-1324) уже сделал:
          1. entry["position"] = change.value (semantic position snap)
          2. entry["local_position"] = node.x, node.y (geometric snap)
          3. transition MOVING → COMPLETED (FSM)

        Shadow compiler НЕ создаёт новый traversal. Возвращает ThickSceneChange
        с traversal.status="COMPLETED" — это факт завершения, не начало движения.

        Без этого guard'а shadow будет компилировать "position change" как новое
        перемещение → phantom traversal → бесконечный цикл (BUG-PHANTOM-TRAV).
        """
        svc = snapshot.spatial_service
        if svc is None:
            logger.warning("[SHADOW_COMPILER] traversal_complete: no spatial service")
            return None

        target_loc = getattr(change, "target_location_id", "") or snapshot.location_id
        target_node_id = change.value

        # ADR-O-201.4: Cross-location traversal completion (boundary transition)
        # Если цель в другой локации, текущий svc (текущей локации) её не найдёт.
        # Делегируем в _compile_boundary_snap, который умеет делать snap без поиска в графе.
        if target_loc != snapshot.location_id:
            return self._compile_boundary_snap(snapshot, change, None, target_loc, svc)

        # Lookup target node (same logic as _compile_position_change)
        node = svc.get_node(target_node_id) or svc.get_node(
            f"{target_loc}:{target_node_id}"
        )
        if node is None:
            # ADR-O-314: Если целевой узел не найден (невалидный boundary target),
            # фолбэчим на entrance локации, чтобы NPC не завис и не ломал snapshot.
            fallback_node_id = f"{target_loc}:entrance"
            node = svc.get_node(fallback_node_id)
            if node is None:
                logger.warning(
                    f"[SHADOW_COMPILER] traversal_complete: node not found: {target_node_id} (fallback {fallback_node_id} also missing)"
                )
                return None
            logger.warning(
                f"[SHADOW_COMPILER] traversal_complete: node {target_node_id} not found, fallback to {fallback_node_id}"
            )
            target_node_id = fallback_node_id

        target_xy = (node.x, node.y)
        # Source = same as target — movement completed, NPC is AT target
        source_xy = target_xy

        return ThickSceneChange(
            change_type=change.type.value,
            target=change.target,
            field=change.field,
            value=change.value,
            cause=change.cause,  # "traversal_complete"
            tick=change.tick,
            target_local_xy=getattr(change, "target_local_xy", None),
            spatial=SpatialResolution(
                source_location=snapshot.location_id,
                target_location=snapshot.location_id,
                source_node=getattr(change.traversal_proposal, "source_node", "") if change.traversal_proposal else "",
                target_node="",
                source_xy=(0.0, 0.0),
                target_xy=target_xy,
            ),
            motion=MotionPlan(
                is_teleport=True,  # snap, not movement
                is_path_blocked=False,
                waypoints=(),
                distance=0.0,
                duration_ticks=0,
                speed=0.0,
            ),
            traversal=None,  # ADR-TRAV-FSM: SSM owns lifecycle. traversal_complete = snap, no contract.
        )

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
            target_local_xy=getattr(change, "target_local_xy", None),
            target_location_id=getattr(change, "target_location_id", ""),
        )

    def _compile_local_position_change(
        self, snapshot: WorldSnapshot, change: SceneChange
    ) -> ThickSceneChange:
        """NPC_POSITION field='local_position' — прямой xy update, без traversal."""
        target_loc = getattr(change, "target_location_id", "") or snapshot.location_id
        _target_node = ""  # Микро-перемещение не меняет узел
        _target_xy: Tuple[float, float] = (0.0, 0.0)
        if isinstance(change.value, dict):
            _target_xy = (
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
                target_location=target_loc,
                source_node=getattr(change.traversal_proposal, "source_node", "") if change.traversal_proposal else "",
                target_node=_target_node,
                source_xy=(0.0, 0.0),
                target_xy=_target_xy,
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
        target_loc = getattr(change, "target_location_id", "") or snapshot.location_id

        # E2: Spatial service из snapshot (НЕ build_for_location!)
        svc = snapshot.spatial_service
        if svc is None:
            logger.warning("[SHADOW_COMPILER] No spatial service in snapshot")
            return None

        # E3: Node lookup — ONLY for same-location movement
        # Cross-location: target node is in a different location's graph,
        # current svc cannot resolve it. SceneChange already carries
        # target_local_xy from MovementEngine (authoritative source).
        if target_loc != snapshot.location_id:
            return self._compile_boundary_snap(snapshot, change, None, target_loc, svc)

        node = svc.get_node(change.value) or svc.get_node(
            f"{target_loc}:{change.value}"
        )
        if node is None:
            logger.warning(
                f"[SHADOW_COMPILER] Node not found: {change.value} loc={target_loc}"
            )
            return None

        # E5-E16: Same-location movement

        return self._compile_same_location_movement(snapshot, change, node, svc)

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
        # S-142 FIX: Кросс-локационный перенос (snap) не является traversal.
        _explicit_target_loc = getattr(change, "target_location_id", "")
        # S-142.2: Доверяем cause от MovementEngine (SSOT физики). 
        # Если он пометил change как cross_loc_materialize — это snap, даже если snapshot desync'нут.
        _is_cross_loc_snap = "cross_loc_materialize" in getattr(change, "cause", "")
        
        if _is_cross_loc_snap or (_explicit_target_loc and _explicit_target_loc != snapshot.location_id):
            _target_loc = _explicit_target_loc or snapshot.location_id
            
            # S-142.1: Честный source_xy из snapshot. Нельзя подставлять (0.0, 0.0) — это ложный факт.
            _src_xy = (0.0, 0.0)
            _npc_pos = snapshot.npc_positions.get(change.target, {})
            _lp = _npc_pos.get("local_position")
            if isinstance(_lp, dict) and isinstance(_lp.get("x"), (int, float)):
                _src_xy = (float(_lp["x"]), float(_lp["y"]))

            # Формируем spatial без source_node, так как мы покинули старую локацию
            spatial = SpatialResolution(
                source_location=snapshot.location_id,
                target_location=_target_loc,
                source_node="",
                target_node=change.value,
                source_xy=_src_xy,
                target_xy=getattr(change, "target_local_xy", (0.0, 0.0)),
            )
            return ThickSceneChange(
                change_type=change.type.value,
                target=change.target,
                field=change.field,
                value=change.value,
                cause=change.cause,
                tick=change.tick,
                target_local_xy=getattr(change, "target_local_xy", None),
                target_location_id=_target_loc,
                spatial=spatial,
                motion=MotionPlan(
                    is_teleport=True,
                    is_path_blocked=False,
                    waypoints=(),
                    distance=0.0,
                    duration_ticks=0,
                    speed=0.0,
                ),
                traversal=None, # ADR-TRAV-FSM: Snap не создаёт traversal
                boundary=BoundaryResolution(
                    is_boundary=True,
                    neighbor_chunk=_target_loc,
                    entry_node=change.value,
                ),
            )

        # E18-E19: Boundary resolution (из snapshot, не из live query)
        is_boundary = False
        neighbor_chunk = ""
        entry_node = ""

        # Проверяем по NodeRole если доступен
        from app.models.spatial_contracts import NodeRole

        if hasattr(node, "role") and node.role == NodeRole.BOUNDARY:
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

        # S140: Если target_location_id задан явно и отличается от текущей — это boundary transition.
        # Запрещаем fallback на snapshot.location_id, чтобы избежать ложных is_boundary=True.
        _explicit_target_loc = getattr(change, "target_location_id", "")
        if _explicit_target_loc and _explicit_target_loc != snapshot.location_id:
            if not neighbor_chunk:
                neighbor_chunk = _explicit_target_loc
            if not entry_node:
                entry_node = f"{_explicit_target_loc}:entry_west"
            is_boundary = True

        # Cross-location: node is None — use SceneChange data
        # (authoritative: MovementEngine already resolved coordinates)
        _target_node = node.node_id if node else change.value
        target_loc = getattr(change, "target_location_id", "") or snapshot.location_id
        # FIX: getattr возвращает None, если атрибут существует, но равен None.
        # Используем 'or' для fallback на (0.0, 0.0), чтобы избежать None в SpatialResolution.
        _target_xy = (
            (node.x, node.y)
            if node
            else (getattr(change, "target_local_xy", None) or (0.0, 0.0))
        )

        return ThickSceneChange(
            change_type=change.type.value,
            target=change.target,
            field=change.field,
            value=change.value,
            cause=change.cause,
            tick=change.tick,
            target_local_xy=getattr(change, "target_local_xy", None),
            target_location_id=target_loc,
            spatial=SpatialResolution(
                source_location=snapshot.location_id,
                target_location=target_loc,
                source_node=getattr(change.traversal_proposal, "source_node", "") if change.traversal_proposal else "",
                target_node=_target_node,
                source_xy=(0.0, 0.0),
                target_xy=_target_xy,
            ),
            boundary=BoundaryResolution(
                is_boundary=is_boundary,
                neighbor_chunk=neighbor_chunk,
                entry_node=entry_node,
            ),
            # ADR-TRAV-FSM: SSM owns lifecycle. Boundary snap = materialization, no traversal contract.
            traversal=None,
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
        source_node = getattr(change.traversal_proposal, "source_node", "") if change.traversal_proposal else ""
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
            source_node=getattr(change.traversal_proposal, "source_node", "") if change.traversal_proposal else "",
            target_node=node.node_id,
            source_xy=source_xy,
            target_xy=target_xy,
        )

        if is_teleport:
            # ADR-O-323: Макро-телепорт (смена узла с нулевой дистанцией) требует TraversalContract.
            # Это устраняет Semantic Drift: Legacy создаёт Traversal(duration=0), Shadow тоже должен.
            if change.field == "position":
                proposal = getattr(change, "traversal_proposal", None)
                if proposal:
                    traversal_fields = {
                        "npc_id": proposal.npc_id,
                        "from_node": proposal.source_node,
                        "target_node": proposal.target_node,
                        "path_waypoints": [list(wp) for wp in proposal.path_waypoints],
                        "speed": proposal.speed,
                        "started_tick": proposal.planned_tick,
                        "duration_ticks": proposal.duration_ticks,
                        "locomotion": "WALK",
                        "status": "MOVING",
                        "current_waypoint_idx": 0,
                    }
                    traversal = TraversalContract(status="NEW", fields=traversal_fields)
                    return ThickSceneChange(
                        change_type=change.type.value,
                        target=change.target,
                        field=change.field,
                        value=change.value,
                        cause=change.cause,
                        tick=change.tick,
                        target_local_xy=getattr(change, "target_local_xy", None),
                        spatial=spatial,
                        motion=MotionPlan(
                            is_teleport=True,
                            is_path_blocked=False,
                            waypoints=tuple(tuple(wp) for wp in proposal.path_waypoints),
                            distance=proposal.distance,
                            duration_ticks=proposal.duration_ticks,
                            speed=proposal.speed,
                        ),
                        traversal=traversal,
                        spatial_mode=SpatialTransitionMode.INTERPOLATED,
                    )
            # Микро-перемещение (field="local_position") — traversal не нужен
            return ThickSceneChange(
                change_type=change.type.value,
                target=change.target,
                field=change.field,
                value=change.value,
                cause=change.cause,
                tick=change.tick,
                target_local_xy=getattr(change, "target_local_xy", None),
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
        # ADR-DRIFT-D: _compile_full_movement теперь может вернуть None
        # (parity with legacy когда path blocked and no valid route)
        result = self._compile_full_movement(
            snapshot, change, node, svc, spatial, source_xy, target_xy
        )
        if result is None:
            # Path blocked, no valid route — parity with legacy
            logger.debug(
                f"[SHADOW_COMPILER] npc={change.target} "
                f"no traversal created (path blocked, no route)"
            )
        return result

    def _compile_full_movement(
        self,
        snapshot: WorldSnapshot,
        change: SceneChange,
        node: Any,
        svc: Any,
        spatial: SpatialResolution,
        source_xy: Tuple[float, float],
        target_xy: Tuple[float, float],
    ) -> Optional[ThickSceneChange]:
        """E11-E16: Pathfinding, distance, duration, traversal creation.

        ADR-DRIFT-D: Path blocked parity with legacy apply_change.
        Legacy: _create_traversal = False when blocked, True only when
        find_path returns intermediate nodes. Shadow previously created
        traversal unconditionally → Causal Drift D (legacy=False vs shadow=True).
        Fix: shadow must return None when blocked and no valid path found.
        """
        # E11: Wall blocking check (из snapshot, не из live scene_state)
        is_path_blocked = self._check_wall_blocking(snapshot, source_xy, target_xy)

        # E12-E13: Pathfinding + waypoint assembly
        # ADR-O-323 (Fix Rule 120 Drift): Shadow Compiler больше НЕ вычисляет путь.
        # MovementPlanner (Layer 1) уже сделал это и прикрепил TraversalProposal к SceneChange.
        # Любая попытка пересчёта здесь приводит к рассинхрону (Rule 120 Drift).

        # Восстанавливаем target_loc, который был случайно удалён другим архитектором
        target_loc = getattr(change, "target_location_id", "") or snapshot.location_id

        proposal = getattr(change, "traversal_proposal", None)

        if not proposal:
            # Если это макро-перемещение, но нет proposal — это Causal Violation.
            if change.field == "position":
                # Явный сигнал EquivalenceViolation (Class D - Causal)
                logger.error(
                    f"[EQUIVALENCE_VIOLATION][MISSING_PROPOSAL] npc={change.target} "
                    f"field={change.field} cause={change.cause} "
                    f"Macro movement requires TraversalProposal (ADR-O-323 violation)"
                )
                return None
            # Для микро-перемещений proposal не требуется
            logger.debug(
                f"[SHADOW_COMPILER] npc={change.target} no proposal (non-macro movement)"
            )
            return None

        # Независимая валидация инвариантов TraversalProposal
        is_valid, reason = self._validate_traversal_proposal(proposal, change, spatial, source_xy, target_xy)
        if not is_valid:
            # Явный сигнал EquivalenceViolation (Class D - Causal)
            logger.error(
                f"[EQUIVALENCE_VIOLATION][PROPOSAL_INVALID] npc={change.target} "
                f"reason={reason}"
            )
            return None

        # Валидация пройдена — формируем projection на основе проверенного proposal
        motion = MotionPlan(
            is_teleport=False,
            is_path_blocked=False, # ADR-O-323: Shadow не вычисляет blockage, валидируется в _validate_traversal_proposal
            waypoints=tuple(tuple(wp) for wp in proposal.path_waypoints),
            distance=proposal.distance,
            duration_ticks=proposal.duration_ticks,
            speed=proposal.speed,
        )

        # Формируем traversal_fields для ThickSceneChange на основе proposal
        traversal_fields = {
            "npc_id": proposal.npc_id,
            "from_node": proposal.source_node,
            "target_node": proposal.target_node,
            "path_waypoints": [list(wp) for wp in proposal.path_waypoints],
            "speed": proposal.speed,
            "started_tick": proposal.planned_tick,
            "duration_ticks": proposal.duration_ticks,
            "locomotion": "WALK",
            "status": "MOVING",
            "current_waypoint_idx": 0,
        }

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
            target_local_xy=getattr(change, "target_local_xy", None),
            spatial=spatial,
            motion=motion,
            traversal=traversal,
            spatial_mode=SpatialTransitionMode.INTERPOLATED,
        )

    def _validate_traversal_proposal(
        self,
        proposal: Any,
        change: SceneChange,
        spatial: Any,
        source_xy: Tuple[float, float],
        target_xy: Tuple[float, float],
    ) -> Tuple[bool, str]:
        """ADR-O-323: Независимая валидация инвариантов TraversalProposal.

        Проверяет:
        1. Совпадение source/target с запрошенными
        2. Геометрическую валидность waypoints (начало/конец)
        3. Консистентность distance и duration_ticks
        4. Stale detection (topology_version)
        """
        # 1. Source / Target совпадают
        if proposal.source_node != spatial.source_node:
            return False, f"SOURCE_MISMATCH prop={proposal.source_node} actual={spatial.source_node}"
        if proposal.target_node != change.value:
            return False, f"TARGET_MISMATCH prop={proposal.target_node} requested={change.value}"

        # 2. Геометрическая валидность (без дублирования pathfinding)
        prop_wps = [list(wp) for wp in proposal.path_waypoints]
        if len(prop_wps) < 2:
            return False, "WAYPOINTS_TOO_SHORT"
        # ADR-O-323: Повышенная толерантность для START/END waypoint.
        # EventCompiler может интерполировать позицию (Ghost Interpolation), опережая Legacy local_position.
        if abs(prop_wps[0][0] - source_xy[0]) > 2.0 or abs(prop_wps[0][1] - source_xy[1]) > 2.0:
            return False, f"START_WAYPOINT_MISMATCH prop={prop_wps[0]} actual={list(source_xy)}"
        if abs(prop_wps[-1][0] - target_xy[0]) > 2.0 or abs(prop_wps[-1][1] - target_xy[1]) > 2.0:
            return False, f"END_WAYPOINT_MISMATCH prop={prop_wps[-1]} actual={list(target_xy)}"

        # 3. Distance и Duration консистентны (геометрическая проверка)
        calc_distance = 0.0
        for i in range(len(prop_wps) - 1):
            dx = prop_wps[i][0] - prop_wps[i+1][0]
            dy = prop_wps[i][1] - prop_wps[i+1][1]
            calc_distance += math.hypot(dx, dy)
        if abs(proposal.distance - calc_distance) > 1.0:
            return False, f"DISTANCE_MISMATCH prop={proposal.distance:.2f} calc={calc_distance:.2f}"
        expected_duration = max(1, math.ceil(proposal.distance / proposal.speed)) if proposal.speed > 0 else 1
        if proposal.duration_ticks != expected_duration:
            return False, f"DURATION_MISMATCH prop={proposal.duration_ticks} expected={expected_duration}"

        # 4. Topology Version
        current_topology_version = getattr(spatial, "_topology_version", 0)
        if proposal.topology_version != current_topology_version:
            return False, f"STALE_TOPOLOGY prop={proposal.topology_version} current={current_topology_version}"

        return True, "OK"

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
        exact_xy = getattr(change, "target_local_xy", None)
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
        h = hashlib.sha256(f"{rng_seed}:{npc_id}:{node_id}".encode()).hexdigest()
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
                source_xy[0],
                source_xy[1],
                target_xy[0],
                target_xy[1],
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

    # ADR-O-323: _get_source_node восстановлен, так как он нужен для проверки BUG_V_GUARD
    # и вычисления source_xy в Shadow-пайплайне.
    def _get_source_node(self, snapshot: WorldSnapshot, change: SceneChange) -> Optional[str]:
        """Извлекает source_node из SceneChange или snapshot."""
        # Приоритет 1: TraversalProposal (если есть)
        if hasattr(change, "traversal_proposal") and change.traversal_proposal:
            return change.traversal_proposal.source_node
        # Приоритет 2: Позиция NPC в snapshot (state_t)
        npc_data = snapshot.npc_positions.get(change.target)
        if npc_data:
            return npc_data.get("position", "")
        return None

    @staticmethod
    def _euclidean_distance(a: Tuple[float, float], b: Tuple[float, float]) -> float:
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
