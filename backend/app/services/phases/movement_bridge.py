# -*- coding: utf-8 -*-
"""
Phases/Movement Bridge — Изоляция Block 5 (Movement Bridge).

path: backend/app/services/phases/movement_bridge.py
Назначение: Каузальный мост: когнитивные решения → пространственное движение.
Зависимости: app.services.spatial.movement_engine, app.domain.movement
Основные сущности: process_movement_intents
"""

import logging
from typing import Any, List

logger = logging.getLogger(__name__)


def process_movement_intents(
    movement_intents: List[Any], ctx: Any, orchestrator: Any
) -> None:
    """Обрабатывает movement_intents через MovementEngine и применяет SceneChange.

    Мутирует ctx.scene_state через orchestrator._apply_with_shadow_observation.
    """
    if not movement_intents:
        return

    from app.domain.movement import LocalSteeringGoal
    from app.services.spatial.movement_engine import MovementEngine

    _merged_intents = []
    _per_npc = {}
    for i in movement_intents:
        _nid = getattr(i, "npc_id", None)
        if _nid:
            _per_npc.setdefault(_nid, []).append(i)
        else:
            _merged_intents.append(i)

    for _nid, _intents in _per_npc.items():
        if len(_intents) > 1:
            _intents.sort(key=lambda x: isinstance(x, LocalSteeringGoal))
        _merged_intents.extend(_intents)

    _spatial_svc = orchestrator._resolve_spatial_service(ctx)
    if _spatial_svc:
        # ADR-O-330: Адаптер для SpatialTargetIntent (SA-2, SA-4, SA-5)
        from app.services.spatial.spatial_target_resolver import SpatialTargetResolver
        from app.domain.spatial_target import TargetResolutionStatus, SpatialResolutionMode
        from app.domain.movement import LocalSteeringGoal

        resolver = SpatialTargetResolver(_spatial_svc)
        _npc_positions = ctx.scene_state.get("npc_positions", {})
        _resolved_intents = []
        
        for intent in _merged_intents:
            if hasattr(intent, 'target_intent') and intent.target_intent:
                resolved = resolver.resolve(
                    intent.target_intent,
                    npc_positions=_npc_positions,
                    actor_id=intent.actor_id,
                    location_id=getattr(intent, 'location_id', None)
                )
                
                if resolved.resolution_status != TargetResolutionStatus.RESOLVED:
                    logger.warning(f"[MOVEMENT_BRIDGE] Target resolution failed for {intent.actor_id}: {resolved.resolution_reason}")
                    continue  # SA-4: Неразрешённая цель отбрасывается
                
                if resolved.mode == SpatialResolutionMode.NAV_NODE:
                    # Конвертируем в старый макро-интент
                    intent.target_node_id = resolved.anchor_node_id
                    _resolved_intents.append(intent)
                elif resolved.mode == SpatialResolutionMode.LOCAL_POSITION:
                    if resolved.position is None:
                        logger.error("[MOVEMENT_BRIDGE] RESOLVED LOCAL_POSITION without position")
                        continue
                    # Конвертируем в микро-интент (LOD0)
                    micro_goal = LocalSteeringGoal(
                        actor_id=intent.actor_id,
                        local_target_xy=resolved.position,
                        reason=intent.reason,
                        priority=intent.priority
                    )
                    _resolved_intents.append(micro_goal)
            else:
                _resolved_intents.append(intent)
        
        _merged_intents = _resolved_intents

        orchestrator._apply_drf_scoring_overlay(_merged_intents, ctx)
        me = MovementEngine()
        me.set_spatial_service(_spatial_svc)
        spatial_changes = me.process_intents(
            _merged_intents,
            tick=ctx.tick_number,
            npc_positions=ctx.scene_state.get("npc_positions", {}),
            campaign_id=ctx.campaign_id,
            scene_state=ctx.scene_state,
        )
        if spatial_changes and orchestrator._scene_manager:
            orchestrator._apply_with_shadow_observation(
                ctx, spatial_changes, phase_label="CAUSAL_BRIDGE"
            )
    else:
        logger.error(
            "[SPATIAL_AUTHORITY] SpatialService missing in Phase 5 (Movement Bridge)"
        )
