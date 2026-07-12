"""
path: /project/backend/app/services/phases/motion.py
Назначение: Инкапсуляция логики непрерывного движения (ETKE-IK v1).
Зависимости: app.services.motion.motion_pipeline, app.domain.motion_core, app.services.spatial.world_topology_provider
Основные сущности: process_continuous_motion
"""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def process_continuous_motion(
    ctx: Any, orchestrator: Any, _spatial_svc: Optional[Any] = None
) -> None:
    """ETKE-IK v1: Непрерывная кинематика (SteeringResolver + MotionIntegrator).

    Если у NPC есть DriveVector и нет активного MovementIntent,
    его позиция вычисляется через непрерывное поле возможностей.
    """
    from app.core.constants import ETKE_IK_SUBSTEP_DT
    from app.domain.motion_core import (
        BodySchema,
        DriveVector,
        MotionPrimitive,
        TracePayload,
    )
    from app.services.motion.motion_pipeline import (
        CollisionAvoidance,
        MotionIntegrator,
        SteeringResolver,
    )
    from app.services.scene_change import ChangeType, SceneChange

    npc_positions = ctx.scene_state.get("npc_positions", {})
    active_traversals = ctx.scene_state.get("active_traversals", {})
    continuous_changes = []

    # S91: Используем персистентный провайдер уровня экземпляра (стигмергия)
    wtp = orchestrator._topology_provider
    wtp.set_spatial_service(_spatial_svc)

    # TODO: В будущем LifeEngine будет класть DriveVector в npc_state.
    # Пока читаем заглушку (если её нет — пропускаем).
    for npc_data in ctx.all_npcs_raw:
        npc_id = npc_data.get("id", npc_data.get("npc_id", ""))
        if not npc_id or npc_id in active_traversals:
            continue

        dv_raw = npc_data.get("drive_vector")
        if not dv_raw:
            # ADR-ETKE-ACT1 FIX: Нет давления — нет движения.
            # Обнуляем накопленную скорость, чтобы избежать дрейфа от прошлых кадров.
            pos_data = npc_positions.get(npc_id, {})
            if pos_data.get("velocity", (0.0, 0.0)) != (0.0, 0.0):
                continuous_changes.append(
                    SceneChange(
                        type=ChangeType.NPC_STATE,
                        target=npc_id,
                        field="velocity",
                        value=(0.0, 0.0),
                        cause="etke_braking",
                        tick=ctx.tick_number,
                    )
                )
            continue

        # ETKE-IK v2: Чтение MotionPrimitive (4-й элемент, fallback на approach)
        _prim_name = dv_raw[3] if len(dv_raw) > 3 else "approach"
        drive = DriveVector(
            direction=(dv_raw[0], dv_raw[1]),
            intensity=dv_raw[2],
            primitive=MotionPrimitive(_prim_name),
        )

        pos_data = npc_positions.get(npc_id, {})
        current_pos = pos_data.get("local_position", {"x": 0.0, "y": 0.0})
        current_vel = pos_data.get("velocity", (0.0, 0.0))
        current_exertion = pos_data.get("exertion_level", 0.0)

        body = BodySchema()

        affordance = wtp.query_affordance_field(
            ctx.scene_state.get("location_id", ""),
            (current_pos.get("x", 0.0), current_pos.get("y", 0.0)),
        )

        # ETKE-IK v2: Реактивная коррекция направления перед вычислением скорости
        _pos_tuple = (current_pos.get("x", 0.0), current_pos.get("y", 0.0))
        _loc_id = ctx.scene_state.get("location_id", "")
        # S91: Передаём позиции всех NPC для избегания столкновений
        drive = CollisionAvoidance.apply(
            drive=drive,
            pos=_pos_tuple,
            topology=wtp,
            region=_loc_id,
            npc_positions=npc_positions,
            current_npc_id=npc_id,
        )

        new_vel = SteeringResolver.resolve(
            drive=drive,
            body=body,
            affordance=affordance,
            current_velocity=current_vel,
            dt=ETKE_IK_SUBSTEP_DT,
        )

        new_pos = MotionIntegrator.integrate(
            position=(current_pos.get("x", 0.0), current_pos.get("y", 0.0)),
            velocity=new_vel,
            body=body,
            affordance=affordance,
            dt=ETKE_IK_SUBSTEP_DT,
        )

        new_exertion = MotionIntegrator.compute_exertion(
            velocity=new_vel, body=body, current_exertion=current_exertion, dt=0.1
        )

        # S91: Эмит стигмергического следа (movement_density)
        _zone_id = (
            _spatial_svc.get_zone_id(new_pos[0], new_pos[1]) if _spatial_svc else None
        )
        if _zone_id:
            _trace = TracePayload(
                region=_loc_id,
                zone_id=_zone_id,
                trace_type="movement_density",  # Толпа создает сопротивление
                magnitude=0.1,  # Небольшая величина, накапливается со временем
                created_tick=ctx.tick_number,
                ttl=50,  # След остывает за 50 тиков
                source_id=npc_id,
            )
            orchestrator._dynamic_field.apply_trace(_trace)

        continuous_changes.append(
            SceneChange(
                type=ChangeType.NPC_POSITION,
                target=npc_id,
                field="local_position",
                value={"x": new_pos[0], "y": new_pos[1]},
                cause="etke_continuous_motion",
                tick=ctx.tick_number,
            )
        )
        continuous_changes.append(
            SceneChange(
                type=ChangeType.NPC_STATE,
                target=npc_id,
                field="velocity",
                value=new_vel,
                cause="etke_continuous_motion",
                tick=ctx.tick_number,
            )
        )
        continuous_changes.append(
            SceneChange(
                type=ChangeType.NPC_STATE,
                target=npc_id,
                field="exertion_level",
                value=new_exertion,
                cause="etke_continuous_motion",
                tick=ctx.tick_number,
            )
        )

    if continuous_changes and orchestrator._scene_manager:
        orchestrator._apply_with_shadow_observation(
            ctx, continuous_changes, phase_label="ETKE_CONTINUOUS"
        )
        logger.debug(
            f"[ETKE] Processed continuous motion for {len(continuous_changes) // 3} NPCs"
        )
