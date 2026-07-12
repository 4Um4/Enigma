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
