"""
path: /project/backend/app/services/phases/traversal.py
Назначение: Инкапсуляция логики транзитов (Фаза 0.75) и Shadow Observation (Dual Rail).
Зависимости: app.services.scene_state_manager, app.services.projection_engine, app.services.event_compiler
Основные сущности: process_traversals, apply_with_shadow_observation
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def process_traversals(ctx: Any, orchestrator: Any) -> None:
    """Фаза 0.75: Authoritative Traversal Lifecycle (STL Phase 1).
    Traversal НЕ мутирует мир напрямую.
    При завершении он генерирует SceneChange (факт перемещения) и маркирует статус.
    Единый Spatial Commit (apply_changes) схлопнет реальность позже.
    """
    from app.services.scene_change import ChangeType, SceneChange

    traversals = ctx.scene_state.get("active_traversals", {})
    if not traversals:
        return

    current_tick = ctx.scene_state.get("tick", 0)
    completion_changes = []

    for npc_id, trav in list(traversals.items()):
        _status = trav.get("status", "UNKNOWN")
        if _status != "MOVING":
            if ctx.tick_number % 50 == 0:
                logger.debug(f"[GATE_F_SKIP] npc={npc_id} status={_status}")
            continue

        started_tick = trav.get("started_tick", 0)
        duration_ticks = trav.get("duration_ticks", 1)
        expected_arrival_tick = started_tick + duration_ticks

        logger.debug(
            f"[GATE_F] npc={npc_id} current_tick={current_tick} started={started_tick} duration={duration_ticks} expected={expected_arrival_tick} remaining={expected_arrival_tick - current_tick}"
        )

        if current_tick >= expected_arrival_tick:
            # STL: Транзит завершён. Генерируем финальный факт перемещения.
            target_node = trav.get("target_node")
            wp = trav.get("path_waypoints", [])

            # ДОЛГ 6.2: Boundary resolution at completion time (не creation time).
            # Boundary — свойство ФАКТА пересечения, не свойства маршрута.
            # Runtime query к SpatialService в точке факта.
            _is_boundary = False
            _entry_node = target_node
            _target_location_id = ""

            _svc = orchestrator._spatial_service
            if _svc and target_node and _svc.is_boundary_node(target_node):
                _boundary_info = _svc.get_boundary_info(target_node)
                if _boundary_info:
                    _neighbor = _boundary_info.get("neighbor_chunk", "")
                    _entry_hint = _boundary_info.get("entry_node_hint", "")
                    _entry_dir = _boundary_info.get("entry_direction", "")
                    if _neighbor:
                        _is_boundary = True
                        _target_location_id = _neighbor
                        
                        # Приоритет 1: Используем entry_node_hint из boundary_info (SSOT от GraphCompiler).
                        # Это исключает дорогие и ломающиеся запросы к SpatialFactory в рантайме.
                        if _entry_hint:
                            _entry_node = _entry_hint
                        else:
                            # Приоритет 2: Резолв через graph topology новой локации.
                            _current_loc = target_node.split(":")[0] if ":" in target_node else ""
                            try:
                                from app.services.spatial.spatial_factory import SpatialFactory
                                _target_svc = SpatialFactory.build_for_campaign(
                                    ctx.campaign_id, _neighbor, ctx.scene_state
                                )
                                if _target_svc and _current_loc:
                                    _entry_node_obj = _target_svc.get_boundary_to_neighbor(_current_loc)
                                    if _entry_node_obj:
                                        _entry_node = _entry_node_obj.node_id
                                        # Убираем префикс локации, если он есть (SSM ожидает чистый ID)
                                        if ":" in _entry_node:
                                            _entry_node = _entry_node.split(":")[-1]
                            except Exception as e:
                                logger.error(f"[TRAVERSAL_BOUNDARY] Failed to resolve entry_node for {_neighbor}: {e}")

                        logger.info(
                            f"[BOUNDARY_TRANSITION] npc={npc_id} "
                            f"node={target_node} → chunk={_neighbor} "
                            f"entry={_entry_node}"
                        )

            # Факт 1: Каузальная позиция (semantic truth, NO geometry)
            completion_changes.append(
                SceneChange(
                    type=ChangeType.NPC_POSITION,
                    target=npc_id,
                    field="position",
                    value=_entry_node,
                    cause="cross_loc_materialize:traversal_complete" if _is_boundary else "traversal_complete",
                    tick=current_tick,
                    target_location_id=_target_location_id,  # ДОЛГ 6.2
                )
            )

            # Факт 2: Визуальная позиция — только intra-location.
            # ДОЛГ 6.2: Boundary transition НЕ эмитит local_position.
            # SceneChange = semantic event, apply_changes = geometric resolver.
            if not _is_boundary and len(wp) >= 2:
                completion_changes.append(
                    SceneChange(
                        type=ChangeType.NPC_POSITION,
                        target=npc_id,
                        field="local_position",
                        value={"x": wp[-1][0], "y": wp[-1][1]},
                        cause="traversal_complete",
                        tick=current_tick,
                    )
                )

            # ADR-XXX: Traversal Lifecycle — SSM owns status transitions.
            # TickOrchestrator только эмитит факты (SceneChange), не мутирует active_traversals.
            # SSM.apply_change выполнит: position snap → status COMPLETED → zombie cleanup.
            logger.debug(
                f"[TRAVERSAL] Lifecycle emit: npc={npc_id} arrived at {target_node} boundary={_is_boundary}. SceneChanges emitted."
            )

    # ADR-XXX: Zombie cleanup перенесён в SSM.apply_changes (SSOT owner).
    # TickOrchestrator больше не мутирует active_traversals напрямую.

    # STL: Схлопываем реальность через единый commit-point
    if completion_changes and orchestrator._scene_manager:
        apply_with_shadow_observation(
            ctx, orchestrator, completion_changes, phase_label="TRAVERSAL_COMPLETE"
        )
        logger.info(
            f"[STL_COMMIT] Traversal completion: {len(completion_changes)} changes applied"
        )


def apply_with_shadow_observation(
    ctx: Any, orchestrator: Any, changes: list, phase_label: str = ""
) -> int:
    """ФАЗА 1 (ADR-O-201): Legacy + Shadow parallel execution.

    Legacy = AUTHORITATIVE. Shadow = OBSERVER only.
    Нулевое изменение поведения системы.

    Порядок:
    1. Строим snapshot ДО мутации
    2. Shadow компилирует NPC_POSITION changes
    3. Legacy применяет (авторитетный)
    4. Сравниваем результаты через EquivalenceValidator
    """
    from app.models.world_snapshot import WorldSnapshot, build_snapshot
    from app.services.scene_change import ChangeType, SceneChange

    if not changes or not orchestrator._scene_manager:
        return 0

    # ── Shadow compilation (ДО мутации) ─────────────────────────
    _spatial_changes = [
        ch
        for ch in changes
        if isinstance(ch, SceneChange)
        and ch.type == ChangeType.NPC_POSITION
        and ch.field in ("position", "local_position")
    ]

    logger.debug(
        f"[GATE_C] phase={phase_label} total_changes={len(changes)} spatial_candidates={len(_spatial_changes)} has_svc={orchestrator._spatial_service is not None}"
    )
    _snapshot: Optional[WorldSnapshot] = None
    _shadow_results: Dict[str, Any] = {}

    if _spatial_changes and orchestrator._spatial_service:
        try:
            _snapshot = build_snapshot(
                tick=ctx.tick_number,
                campaign_id=ctx.campaign_id,
                location_id=ctx.scene_state.get("location_id", ""),
                spatial_service=orchestrator._spatial_service,
                scene_state=ctx.scene_state,
                rng_seed=ctx.tick_number,
            )
            logger.debug(
                f"[GATE_D1] phase={phase_label} snapshot_created={_snapshot is not None}"
            )
            _compiled_count = 0
            for _ch in _spatial_changes:
                _thick = orchestrator._event_compiler.compile(_snapshot, _ch)
                logger.debug(
                    f"[GATE_D2] phase={phase_label} compiled_thick={_thick is not None}"
                )
                if _thick is not None:
                    _shadow_results[_ch.target] = _thick
                    # CSSE Stage 2: collect ThickSceneChange for projection parity
                    if not hasattr(orchestrator, "_tick_thick_changes"):
                        orchestrator._tick_thick_changes = []
                    orchestrator._tick_thick_changes.append(_thick)
                    _compiled_count += 1
            logger.info(
                f"[DUAL_RAIL][{phase_label}] spatial_changes={len(_spatial_changes)} "
                f"shadow_compiled={_compiled_count} snapshot_id={_snapshot.snapshot_id.hex[:8]}"
            )
        except Exception as _e:
            logger.warning(f"[DUAL_RAIL] Shadow compilation failed: {_e}")

    # ── ADR-O-204 S103: ProjectionEngine записывает физику ДО legacy apply ──
    # Устраняет drift_B: traversal создаётся один раз через shadow path,
    # а не дважды (EventCompiler + SSM).
    if _shadow_results:
        if not hasattr(orchestrator, "_projection_engine"):
            from app.services.projection_engine import ProjectionEngine

            orchestrator._projection_engine = ProjectionEngine()
        for _npc_id, _thick in _shadow_results.items():
            try:
                orchestrator._projection_engine.apply(ctx.scene_state, _thick)
            except Exception as _pe_exc:
                logger.warning(f"[PROJECTION_APPLY] npc={_npc_id} failed: {_pe_exc}")

    # ── Legacy apply (AUTHORITATIVE) ────────────────────────────
    _applied = orchestrator._scene_manager.apply_changes(
        ctx.campaign_id, changes, ctx.scene_state
    )

    # ── Validation (ПОСЛЕ мутации) ──────────────────────────────
    if _shadow_results and _snapshot is not None:
        for _npc_id, _thick in _shadow_results.items():
            orchestrator._validate_shadow_vs_legacy(
                snapshot=_snapshot,
                tick=ctx.tick_number,
                npc_id=_npc_id,
                thick=_thick,
                scene_state=ctx.scene_state,
                phase_label=phase_label,
            )

    logger.debug(
        f"[GATE_E] phase={phase_label} validated={len(_shadow_results) if _shadow_results else 0} applied={_applied}"
    )
    return _applied
