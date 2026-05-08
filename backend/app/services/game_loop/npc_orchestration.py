# path: backend/app/services/game_loop/npc_orchestration.py
"""
ФАЗА 3-6: NPC оркестрация — CharacterFilter → Pipeline → Reputation → Proactive → Salience.

Вызывается после DM-классификации, если hub_event не заблокирован CharacterFilter.
Мутирует: ctx, scene_state, shared_context. 
"""

import logging
from typing import Any, Dict, List

from app.services.character.character_filter_applicator import apply_character_filter
from app.services.events.event_bus import get_event_bus
from app.services.game_loop.phase_2_world_tick import tick_world_proactive
from app.services.npc.npc_tick_contracts import NpcTickBuffer, NpcTickServices

logger = logging.getLogger(__name__)


def run_npc_orchestration(
    game_loop: Any,
    actions: list,
    shared_context: Any,
    scene_state: Dict[str, Any],
    ctx: Any,
    campaign_id: str,
    location: str,
    is_session_start: bool,
    tick_orchestrator=None,
) -> List[Any]:
    """CharacterFilter → NPC Pipeline → Reputation → Proactive → Salience.

    Возвращает список npc_contexts. Мутирует ctx, scene_state, shared_context.
    """
    from app.services.verbalization.scene_continuity import SceneContinuity

    npc_contexts: List[Any] = []
    raw_input = actions[0].action if actions else ""

    # CharacterFilter — может заблокировать действие
    _cf_result = apply_character_filter(
        game_loop.character_service,
        campaign_id,
        actions[0].player_name if actions else "",
        ctx.hub_event,
        shared_context,
    )
    if _cf_result:
        ctx.hub_event = None

    if ctx.hub_event is None:
        logger.warning("[CHAR_FILTER] Action blocked, skipping NPC decisions")
        return npc_contexts

    # SceneContinuity — физические факты для NPC
    if not hasattr(shared_context, "scene_continuity"):
        shared_context.scene_continuity = game_loop._scene_continuities.setdefault(
            campaign_id, SceneContinuity(),
        )
    _cont_inject = shared_context.scene_continuity
    if _cont_inject and ctx.hub_event:
        ctx.hub_event.scene_flags = _cont_inject.active_flags
        ctx.hub_event.scene_facts = _cont_inject.scene_facts[-3:]

    # Загружаем ВСЕХ NPC один раз — мутации будут в этом списке
    ctx.all_npcs_raw = game_loop._load_npcs_with_runtime(campaign_id)

    # NPC Pipeline — единая точка входа через TickOrchestrator (Устав §3)
    if tick_orchestrator is None:
        raise RuntimeError("tick_orchestrator обязателен — параллельный путь удалён")

    from app.services.spatial.spatial_service import SpatialService
    _spatial_svc = SpatialService.build_for_location(
        campaign_id=campaign_id,
        location_id=location,
        scene_state=shared_context.scene_state or {},
    )
    _npc_svc = NpcTickServices(
        memory_manager=game_loop.memory_manager,
        relationship_store=game_loop.memory_manager._relationships,
        social_engine=game_loop._svc.get_social_engine(campaign_id),
        reputation_engine=game_loop._svc.get_reputation_engine(),
        economic_profiles=game_loop._svc.get_or_create_economic_profiles(campaign_id),
        event_bus=get_event_bus(),
        spatial_service=_spatial_svc,
    )
    from app.services.tick_orchestrator import DMContextDTO
    _dm_ctx = DMContextDTO(
        hub_event=ctx.hub_event,
        nearby_npcs=shared_context.dm_result.scene_context.nearby_npcs,
        line_of_sight=shared_context.dm_result.scene_context.line_of_sight,
        scene_continuity=shared_context.scene_continuity,
        action_type=shared_context.action_type or "",
        player_target_id=shared_context.player_target_id,
        spatial_events=shared_context.spatial_events or [],
        raw_input=raw_input,
        is_session_start=is_session_start,
        current_tick=shared_context.current_tick or 0,
        all_npcs_raw=ctx.all_npcs_raw,
    )
    _tick_result = tick_orchestrator.tick_player_turn(
        campaign_id=campaign_id,
        location=location,
        scene_state=shared_context.scene_state or {},
        dm_ctx=_dm_ctx,
        npc_services=_npc_svc,
    )
    _npc_buf = NpcTickBuffer(
        npc_contexts=_tick_result.npc_contexts,
        dirty_npcs=_tick_result.dirty_npcs,
        activity_overrides=_tick_result.activity_overrides,
        max_npc_stress=_tick_result.max_npc_stress,
    )

    # Проекция результатов обратно в оркестратор
    ctx.dirty_npcs.update(_npc_buf.dirty_npcs)
    npc_contexts.extend(_npc_buf.npc_contexts)
    ctx.max_npc_stress = max(ctx.max_npc_stress, _npc_buf.max_npc_stress)
    # Activity overrides → scene_state (единственная мутация scene_state из NPC фазы)
    for _nid, _activity in _npc_buf.activity_overrides.items():
        if _nid in scene_state.get("npc_positions", {}):
            scene_state["npc_positions"][_nid]["activity"] = _activity

    # Реактивное движение NPC — MovementIntent → MovementEngine → SceneChange → apply_changes
    _movement_intents = _tick_result.movement_intents if hasattr(_tick_result, "movement_intents") else []
    if _movement_intents:
        try:
            from app.services.spatial.movement_engine import MovementEngine
            from app.services.npc.life_engine import get_life_engine
            _life_engine = get_life_engine()
            _me = _life_engine._movement_engine
            # ADR-0010: Без SpatialService MovementEngine глотает интенты (svc=None → continue).
            if _spatial_svc and not _me._spatial_service:
                _me.set_spatial_service(_spatial_svc)
            _changes = _me.process_intents(_movement_intents, tick=0)
            if _changes:
                game_loop.scene_manager.apply_changes(campaign_id, _changes, scene_state)
                logger.warning(f"[PIPELINE][ORCHESTRATION][MOVEMENT_RESULT] {len(_changes)} changes applied")
                # Удалена загрузка удалённого load_graph и перезапись local_position строкой
                # SceneStateManager.apply_changes уже резолвит x,y через SpatialService
        except Exception as _move_err:
            logger.warning(f"[MOVEMENT] Ошибка реактивного движения: {_move_err}")

    # ФАЗА 3.5: Reputation impact — влияние действий на репутацию фракций
    _rep_eng = game_loop._svc.get_reputation_engine()
    if _rep_eng and ctx.hub_event:
        try:
            _action_type_for_rep = shared_context.action_type or ""
            _rep_deltas = _rep_eng.apply_event_impact(
                event_type=_action_type_for_rep,
                actor_npc_id=None,  # игрок — не NPC
                target_npc_id=shared_context.player_target_id,
            )
            if _rep_deltas:
                _rep_eng.apply_deltas(_rep_deltas)
                logger.warning(f"[REPUTATION] {len(_rep_deltas)} faction deltas applied")
        except Exception as _rep_err:
            logger.warning(f"[REPUTATION] Impact error: {_rep_err}")

    # ФАЗА 3.4: WorldTickEngine — проактивные действия NPC
    tick_world_proactive(
        game_loop._world_tick_engine,
        game_loop._svc.get_reputation_engine(),
        game_loop.memory_manager._relationships,
        game_loop._svc.get_or_create_economic_profiles,
        campaign_id, location, shared_context, ctx,
    )

    # Salience Engine: метаданные для фильтрации объектов в промпте
    _scene_for_dm = shared_context.scene_state or {}
    _scene_for_dm["_salience_event_type"] = getattr(ctx.hub_event, "event_type", "player_interacts")
    _scene_for_dm["_salience_max_stress"] = ctx.max_npc_stress
    _scene_for_dm["_salience_target_object"] = _scene_for_dm.get("player_target_object")

    # Возвращаем полный результат для передачи в execute_player_finalize()
    from app.services.tick_orchestrator import TickPlayerResultDTO
    return TickPlayerResultDTO(
        npc_contexts=npc_contexts,
        dirty_npcs=ctx.dirty_npcs,
        activity_overrides=_npc_buf.activity_overrides,
        max_npc_stress=ctx.max_npc_stress,
        movement_intents=_movement_intents,
    )