"""
path: /project/backend/app/services/phases/simulation.py
Назначение: Инкапсуляция логики Фазы 0 (LifeEngine, MovementEngine, Traversals).
Зависимости: app.services.npc.life_engine, app.services.spatial.movement_engine
Основные сущности: run_phase_0_simulation
"""

from __future__ import annotations
from typing import Any, Optional
import logging

logger = logging.getLogger(__name__)


def run_phase_0_simulation(ctx: Any, orchestrator: Any) -> None:
    """LifeEngine: need-driven, schedule, random events. Чистый Python.
    
    Применяет изменения сразу — phase 5 (Decision) должен видеть свежий state.
    Передаёт TransitTracker в MovementEngine для регистрации новых путей.
    """
    from app.services.tick_utils import get_npc_runtime_path
    
    engine = orchestrator._get_life_engine()
    runtime_path = get_npc_runtime_path(ctx.campaign_id)
    _trav_keys = sorted(ctx.scene_state.get("active_traversals", {}).keys())
    _pos_keys = sorted(ctx.scene_state.get("npc_positions", {}).keys())
    logger.debug(f"[NPC_SET] tick={ctx.tick_number} traversals={_trav_keys} positions={_pos_keys}")
    
    # ADR-048: Авторитетный SpatialService берется из единого резолвера
    _spatial_svc = orchestrator._resolve_spatial_service(ctx)
    if _spatial_svc:
        engine.set_spatial_service(_spatial_svc)
    
    # DRF: Инъекция единой причинной шины в LifeEngine
    engine.set_claim_bus(ctx.drf_bus)
    logger.debug(f"[DRF_BIND_LIFE] bus_id={id(ctx.drf_bus)}")
    changes, life_intents = engine.tick(ctx.campaign_id, ctx.scene_state, runtime_path=runtime_path)
    logger.debug(f"[GATE_A] tick={ctx.tick_number} life_intents={len(life_intents)} cognitive_changes={len(changes or [])}")
    ctx.scene_changes = changes or []
    # Заполняем полные стейты для фаз 3-6, 10 (Устав §3.1)
    ctx.npc_states = engine.get_npc_states(ctx.campaign_id)
    # ADR-002: Единый мутатор работает с all_npcs_raw. В idle-пути это те же данные, что и npc_states
    # ADR-030: Сохраняем аватара игрока, если он был передан в контексте (от GameLoop),
    # так как LifeEngine не кэширует аватара.
    if ctx.npc_states:
        _player_entry = next((n for n in ctx.all_npcs_raw if n.get("npc_id") == "player"), None)
        ctx.all_npcs_raw = ctx.npc_states
        if _player_entry:
            ctx.all_npcs_raw = [n for n in ctx.all_npcs_raw if n.get("npc_id") != "player"]
            ctx.all_npcs_raw.append(_player_entry)
    else:
        ctx.all_npcs_raw = ctx.npc_states
    if changes and orchestrator._scene_manager:
        orchestrator._apply_with_shadow_observation(ctx, changes, phase_label="IDLE_COGNITIVE")
        logger.debug(f"[TICK_ORCH] Фаза 0: {len(changes)} cognitive changes от LifeEngine")
    
    # ADR-049: LifeEngine De-godification. Замыкание контура локомоции.
    # Намерения расписания обрабатываются через MovementEngine, порождая TraversalState.
    if life_intents:
        # DRF: Претензии уже собраны напрямую в ctx.claim_field через Side-Channel Bus
        from app.services.spatial.movement_engine import MovementEngine
        _loc_id = ctx.scene_state.get("location_id", "")
        if _loc_id and _spatial_svc:
            me = MovementEngine()
            me.set_spatial_service(_spatial_svc)
            spatial_changes = me.process_intents(
                life_intents, tick=ctx.tick_number,
                npc_positions=ctx.scene_state.get("npc_positions", {}),
                campaign_id=ctx.campaign_id, scene_state=ctx.scene_state
            )
            logger.debug(f"[GATE_B2] tick={ctx.tick_number} spatial_changes={len(spatial_changes or [])} from_intents={len(life_intents)}")
            if spatial_changes and orchestrator._scene_manager:
                orchestrator._apply_with_shadow_observation(ctx, spatial_changes, phase_label="IDLE_SPATIAL")
                logger.info(f"[TICK_ORCH] Фаза 0: {len(spatial_changes)} spatial changes from {len(life_intents)} LifeEngine intents")

    # ADR-019: Фаза 0.75 — Authoritative Traversal Lifecycle.
    # Бэкенд не интерполирует пиксели, но владеет жизненным циклом перемещения.
    orchestrator._process_traversals(ctx)
    
    # ETKE-IK v1: Непрерывное движение (параллельная ветка).
    # Обрабатывает DriveVector для NPC без активных макро-транзитов.
    orchestrator._process_continuous_motion(ctx, _spatial_svc)