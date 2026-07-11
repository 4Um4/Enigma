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

    # Контракт _load_npcs_with_runtime (game_loop) уже возвращает полный runtime,
    # включающий аватара игрока как полноправного Actor'а симуляции.
    ctx.all_npcs_raw = game_loop._load_npcs_with_runtime(campaign_id)

    from app.services.spatial.spatial_service import SpatialService
    from app.services.spatial.spatial_query_service import SpatialQueryService
    from app.services.spatial.spatial_factory import SpatialFactory
    _spatial_svc = SpatialFactory.build_for_campaign(
        campaign_id=campaign_id,
        location_id=location,
        scene_state=shared_context.scene_state or {},
    )
    # ADR-048: Authoritative Spatial Spine
    _scene_state = shared_context.scene_state
    if _scene_state is None:
        logger.error("[SCENE_IDENTITY] npc_orchestration: shared_context.scene_state is None! Traversals will be lost.")
        return TickPlayerResultDTO()
    
    # ADR-048: npc_positions.player — авторитетный источник позиции игрока.
    # _update_player_position (scene_init) уже записал актуальные координаты от фронтенда.
    # player_spatial НЕ обновляется (запись запрещена ADR-048 Phase 3) — читать из него ЗАПРЕЩЕНО.
    # Fallback на player_spatial только если фронтенд не прислал позицию (npc_positions.player пуст).
    _player_entry = _scene_state.setdefault("npc_positions", {}).setdefault("player", {})
    _plp = _player_entry.get("local_position") or _scene_state.get("npc_positions", {}).get("player", {}).get("local_position", {})
    if isinstance(_plp, dict) and isinstance(_plp.get("x"), (int, float)):
        if _spatial_svc:
            _p_node_ref = _spatial_svc.get_nearest(zone_id=location, origin_xy=(_plp.get("x", 0.0), _plp.get("y", 0.0)))
            if _p_node_ref:
                _p_node_id = getattr(_p_node_ref, 'node_id', str(_p_node_ref))
                if _p_node_id.startswith(f"{location}:"):
                    _p_node_id = _p_node_id.split(":")[-1]
                _player_entry["position"] = _p_node_id

    _spatial_query = SpatialQueryService(
        npc_positions=_scene_state.get("npc_positions", {}),
        scene_state=_scene_state,
    )
    _npc_svc = NpcTickServices(
        memory_manager=game_loop.memory_manager,
        relationship_store=game_loop.memory_manager._relationships,
        social_engine=game_loop._svc.get_social_engine(campaign_id),
        reputation_engine=game_loop._svc.get_reputation_engine(),
        economic_profiles=game_loop._svc.get_or_create_economic_profiles(campaign_id),
        event_bus=get_event_bus(),
        spatial_service=_spatial_svc,
        spatial_query=_spatial_query,
    )
    from app.services.tick_orchestrator import DMContextDTO
    _pl = getattr(ctx.hub_event, 'payload', '<NO_PAYLOAD>') if ctx.hub_event else '<NO_HUB_EVENT>'
    logger.debug(f"[ARCHAE-ORCH] hub_event id={id(ctx.hub_event) if ctx.hub_event else 0} payload={_pl} event_type={getattr(ctx.hub_event, 'event_type', 'NO_TYPE')}")
    from app.contracts.interventions import InterventionEvent
    # TZ-08 v0.2: Event-driven model. Ядро не знает DMContextDTO.
    # Формируем чистый payload из уже разрешённых данных в shared_context
    _intent_res = getattr(shared_context, 'intent_resolution', None)
    _orig_intent = getattr(_intent_res, 'original_intent', None)
    _params = getattr(_orig_intent, 'parameters', None) if _orig_intent else None
    
    _sem_action = getattr(_params, 'semantic_action', "") if _params else ""
    _target_ref = getattr(_params, 'target_reference', "") if _params else ""
    _target_id = getattr(_params, 'target_id', "") if _params else ""
    
    _intervention = InterventionEvent(
        source="player",
        payload={
            "text": raw_input,
            "player_name": actions[0].player_name if actions else "player",
            "semantic_action": _sem_action,
            "target_id": _target_id or shared_context.player_target_id or "",
            "target_reference": _target_ref or "",
            "tick": shared_context.current_tick or 0,
        },
        tick=shared_context.current_tick or 0,
    )
    _tick_result = tick_orchestrator.execute(
        campaign_id=campaign_id,
        scene_state=shared_context.scene_state,
        tick_number=shared_context.current_tick or 0,
        interventions=[_intervention],
        npc_services=_npc_svc,
        spatial_service=_spatial_svc,
        all_npcs_raw=ctx.all_npcs_raw,
        shared_context=shared_context,
    )
    
    # ADR-311 FIX: Коммит final_scene_state в SceneStateManager.
    # Без этого все мутации ядра (время, traversals, эмоции) теряются в пути игрока.
    _scene_manager = getattr(game_loop, 'scene_manager', None)
    if _tick_result.final_scene_state is not None and _scene_manager:
        if _scene_manager._tick_campaign_id == campaign_id:
            _scene_manager.commit_tick_result(campaign_id, _tick_result.final_scene_state)
            shared_context.scene_state = _tick_result.final_scene_state
        else:
            logger.warning(f"[NPC_ORCH] campaign mismatch in commit: {_scene_manager._tick_campaign_id} vs {campaign_id}")
    
    # SHI-FIX CAUSAL: L1 Фиксация на основе semantic_action (Fast Path).
    _sem_action = ""
    if shared_context.intent_resolution and shared_context.intent_resolution.original_intent:
        _params = shared_context.intent_resolution.original_intent.parameters
        if _params:
            _sem_action = getattr(_params, 'semantic_action', "").upper()
    
    _target_id = shared_context.player_target_id or ""
    _tick = shared_context.current_tick or 0
    
    if _target_id and _sem_action:
        from app.domain.identity_events import TraitDriftEvent
        _l1_events = []
        
        if _sem_action in ("MOVE", "THREATEN", "PERSUADE", "GIVE"):
            _l1_events.append(TraitDriftEvent(tick_id=_tick, target_id=_target_id, source_id="player", effect_value=0.3, observation_weight=1.0, event_type="directive"))
        elif _sem_action == "ATTACK":
            _l1_events.append(TraitDriftEvent(tick_id=_tick, target_id=_target_id, source_id="player", effect_value=-0.9, observation_weight=1.0, event_type="attack"))
            _l1_events.append(TraitDriftEvent(tick_id=_tick, target_id=_target_id, source_id="combat", effect_value=-0.5, observation_weight=1.0, event_type="damage"))
            
        if _l1_events:
            try:
                tick_orchestrator.l1_chronicle.bind_campaign(campaign_id)
                tick_orchestrator.l1_chronicle.commit_tick_buffer(_l1_events, _tick)
                logger.warning(f"[L1_FIXATION] sem_action={_sem_action} → L1: target={_target_id} tick={_tick}")
            except Exception as _l1_err:
                logger.warning(f"[L1_FIXATION] failed: {_l1_err}")
     # TZ-08 v0.2: Чтение Narrative Projection из единого TickResultDTO.
    _npc_buf = NpcTickBuffer(
        npc_contexts=_tick_result.npc_contexts,
        dirty_npcs=getattr(_tick_result, 'dirty_npcs', set()),
        activity_overrides=getattr(_tick_result, 'activity_overrides', {}),
        max_npc_stress=getattr(_tick_result, 'max_npc_stress', 0.0),
    )

    # Проекция результатов обратно в оркестратор
    ctx.dirty_npcs.update(_npc_buf.dirty_npcs)
    npc_contexts.extend(_npc_buf.npc_contexts)
    ctx.max_npc_stress = max(ctx.max_npc_stress, _npc_buf.max_npc_stress)
    # B4-FIX: прямые мутации → SceneChange (CAUSAL_CONTRACT §3).
    from app.services.scene_change import SceneChange, ChangeType
    _scene_manager = getattr(game_loop, 'scene_manager', None)
    if _scene_manager:
        for _nid, _activity in _npc_buf.activity_overrides.items():
            _change = SceneChange(
                type=ChangeType.NPC_METADATA,
                target=_nid,
                field="activity",
                value=_activity,
                cause="npc_orchestration",
            )
            _scene_manager.apply_change(campaign_id, _change, scene_state)
    else:
        logger.warning("[NPC_ORCH] scene_manager not found in game_loop. Metadata changes skipped.")

    # TZ-08 v0.2: movement_intents больше не покидают ядро. Исполняются внутри Фазы 8.

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
        tick_orchestrator=game_loop._tick_orch,  # ADR-O-208: для effective_drives computation
    )

    # Salience Engine: метаданные для фильтрации объектов в промпте
    _scene_for_dm = shared_context.scene_state or {}
    _scene_for_dm["_salience_event_type"] = getattr(ctx.hub_event, "event_type", "player_interacts")
    _scene_for_dm["_salience_max_stress"] = ctx.max_npc_stress
    _scene_for_dm["_salience_target_object"] = _scene_for_dm.get("player_target_object")

    # Возвращаем полный результат для передачи в execute_player_finalize()
    from app.services.tick_orchestrator import TickPlayerResultDTO
    _orch_facts = getattr(_tick_result, 'observed_facts', [])
    logger.debug(f"[DEBUG_ORCH] _tick_result.observed_facts count={len(_orch_facts)}")
    return TickPlayerResultDTO(
        npc_contexts=npc_contexts,
        dirty_npcs=ctx.dirty_npcs,
        activity_overrides=_npc_buf.activity_overrides,
        max_npc_stress=ctx.max_npc_stress,
        observed_facts=_orch_facts,
    )