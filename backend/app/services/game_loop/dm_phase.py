# path: backend/app/services/game_loop/dm_phase.py
"""
ФАЗА 1-3: DM классификация + публикация событий.

Обрабатывает действие игрока через DM Orchestrator,
публикует классифицированное событие на EventBus (Устав 5.1),
обновляет STM и продвигает игровое время.

Назначение: ФАЗА 1-3 — DM классификация, spatial events, EventBus publish, STM, продвижение времени
Зависимости: phase_1_input, time_advance, spatial/player_target_pipeline, scene/scene_event_layer, npc/decision_hub
Основные сущности: run_dm_phase
"""

import logging
from typing import Any, Dict, Optional

from app.services.events.event_types import EventType
from app.services.game_loop.time_advance import advance_game_time
from app.services.npc.decision_hub import EventContext as HubEventContext
from app.services.scene.scene_event_layer import emit_and_accumulate_scene_events
from app.services.spatial.player_target_pipeline import (
    build_spatial_data_for_dm,
    detect_and_publish_spatial_transitions,
    extract_player_target,
)

logger = logging.getLogger(__name__)


def run_dm_phase(
    game_loop: Any,
    actions: list,
    shared_context: Any,
    scene_state: Dict[str, Any],
    ctx: Any,
    campaign_id: str,
    location: str,
) -> Optional[Any]:
    """DM классификация + EventBus публикация + STM + время.

    Вызывается внутри try/except в _run_pipeline.
    Возвращает dm_result (может быть None при частичной ошибке).
    Мутирует: shared_context, scene_state, ctx.
    """
    raw_input = actions[0].action if actions else ""

    # Извлечение цели игрока
    try:
        _target = extract_player_target(
            game_loop._load_npcs,
            shared_context.scene_state or {},
            raw_input,
        )
        if _target.target_id:
            shared_context.player_target_id = _target.target_id
            shared_context.player_target_name = _target.target_name
            # BUG-DL-03 FIX: Извлекаем targeted STM block для DM LLM
            try:
                shared_context.npc_stm_block_targeted = game_loop.memory_manager.get_stm_prompt_block(
                    campaign_id=campaign_id, npc_id=_target.target_id
                )
            except Exception:
                shared_context.npc_stm_block_targeted = ""

            # BUG-DLG-010 FIX: ADR L16 Epistemic Boundary — DM-агент НЕ читает L2 narrative_cache.
            # Континуитет должен проявляться через NPC-речь (в STM), а не через прямой доступ DM к скрытой памяти.
            shared_context.npc_l2_memory_block = ""

        # ФАЗА 3.1: Spatial Events — детекция переходов расстояний
        try:
            _prev_dists = game_loop._prev_player_distances.get(campaign_id, {})
            _curr_dists = _target.player_dists or {}
            _spatial_events = detect_and_publish_spatial_transitions(
                _prev_dists,
                _curr_dists,
                location,
                campaign_id,
            )
            if _spatial_events:
                shared_context.spatial_events = _spatial_events
            game_loop._prev_player_distances[campaign_id] = dict(_curr_dists)
        except Exception as _se_err:
            logger.warning(f"[SPATIAL] Transition detection failed: {_se_err}")
    except Exception as _te:
        logger.warning(f"[TARGET] Extract error: {_te}")

    # Spatial data для DM SceneBuilder (ADR-048: передаём SpatialQueryService)
    _scene_for_dm = shared_context.scene_state or {}
    _npc_pos_count = len(_scene_for_dm.get("npc_positions", {}))
    if _npc_pos_count == 0:
        logger.warning(
            f"[DM_PHASE] scene_state has NO npc_positions! scene_state keys={list(_scene_for_dm.keys())[:10]}"
        )
    _spatial_data = build_spatial_data_for_dm(
        location,
        _scene_for_dm,
        spatial_query=getattr(shared_context, "spatial_query", None),
    )

    # R1: DM видит прошлую речь NPC — из DialogueSession
    try:
        _recent_speech = game_loop.memory_manager.get_recent_speech_all_npcs(
            campaign_id
        )
        shared_context.npc_recent_speech = _recent_speech
    except Exception as _rs_err:
        logger.debug(f"[RECENT_SPEECH] error: {_rs_err}")

    # R1: DM видит недавние действия игрока
    shared_context.recent_player_actions = []

    # DM Orchestrator — классификация + обогащение
    dm_result = game_loop.dm_orchestrator.process_player_action(
        raw_input=raw_input,
        player_data=shared_context.player or {},
        player_markers=shared_context.player_markers or [],
        target_npc_id=shared_context.player_target_id,
        spatial_data=_spatial_data,
        current_tick=shared_context.current_tick or 0,
    )
    shared_context.dm_result = dm_result

    # Сохраняем классификацию из Router
    logger.debug(
        f"[DIAG_DM_RESULT] is_valid={dm_result.is_valid} has_event_ctx={dm_result.event_context is not None} error={getattr(dm_result, 'error', None)}"
    )
    if dm_result.event_context:
        shared_context.action_type = dm_result.event_context.event_type
        logger.warning(
            f"[EVENT_TYPE] Router classified as: {dm_result.event_context.event_type}"
        )
        
        # FIX: Пред-проверка дистанции для боя. DM-агент запускается раньше ImpactEngine,
        # поэтому мы должны сообщить ему о промахе заранее, чтобы он не галлюцинировал попадание.
        if "attack" in shared_context.action_type and shared_context.player_target_id:
            _dist = _target.player_dists.get(shared_context.player_target_id, 0.0)
            _MELEE_RANGE = 2.0
            if _dist > _MELEE_RANGE:
                shared_context.combat_data = {
                    shared_context.player_target_id: {
                        "miss": True,
                        "distance": round(_dist, 2),
                        "max_range": _MELEE_RANGE,
                    }
                }
                logger.warning(
                    f"[DM_PHASE] Pre-check: Attack out of range (dist={_dist:.1f}m). Injected combat_data for DM."
                )
            else:
                logger.warning(
                    f"[DM_PHASE] Pre-check: Attack in range (dist={_dist:.1f}m). DM will narrate hit."
                )

    # Rule 47: Инициализация ДО условных веток — Python Scoping Trap
    _sem_payload = {}

    # Публикация + STM + время — только при валидном результате
    if dm_result.is_valid:
        _raw_type = shared_context.action_type or "dialogue"
        # ADR-091 FIX: publish_classified_player_event перенесён в __init__.py
        # ПОСЛЕ установки intent_resolution — иначе _semantic_action=None
        # STM: реплика игрока в сессию целевого NPC
        # P1 ARCH: STM привязывается к Intent target, не к Shadow state.
        _stm_target_id = shared_context.player_target_id
        if _raw_type in ("dialogue", "player_interacts") and _stm_target_id:
            game_loop.memory_manager.add_dialogue_turn(
                campaign_id=campaign_id,
                npc_id=_stm_target_id,
                speaker="player",
                text=raw_input,
                target_id=_stm_target_id,
                intent="dialogue",  # TODO: LLM-classify
                tone="",  # TODO: LLM-classify
                tick=shared_context.current_tick or 0,
            )
            # SHI-FIX LOVE: L1Chronicle emission for dialogue events.
            # Без этого test_love не находит "dialogue" в L1 trace.
            from app.domain.identity_events import TraitDriftEvent

            _tick = shared_context.current_tick or 0
            game_loop._tick_orch.l1_chronicle.commit_tick_buffer(
                [
                    TraitDriftEvent(
                        tick_id=_tick,
                        target_id=_stm_target_id,
                        source_id="player",
                        effect_value=0.1,
                        observation_weight=1.0,
                        event_type="dialogue",
                    )
                ],
                _tick,
            )
        # BUG-DL-08 FIX: STM обнуляется только при реальной смене локации
        if _raw_type in ("move", "stealth"):
            _new_loc = scene_state.get("location_id", "")
            _old_loc = (shared_context.scene_state or {}).get("location_id", "")
            if _new_loc and _old_loc and _new_loc != _old_loc:
                game_loop.memory_manager.clear_all_dialogue_sessions(campaign_id)
        # V8-TICK-3 FIX: Убран двойной счётчик времени. Ядро (tick_orchestrator) уже сдвигает время на 60 сек в Фазе 0.5.
        # advance_game_time(scene_state, _raw_type, raw_input, shared_context)

    # Scene Event Layer — всегда, даже если DM ошибся
    _scene_events = emit_and_accumulate_scene_events(
        action_type=shared_context.action_type or "player_interacts",
        target_id=_sem_payload.get("target_id", ""),
        location_id=location,
        tick=shared_context.current_tick or 0,
        action_text=raw_input,
        scene_state=scene_state,
    )
    shared_context.scene_events = _scene_events

    # HubEvent для NPC фазы — только при валидном DM
    logger.debug(
        f"[DIAG_HUB_ASSIGN] is_valid={dm_result.is_valid} has_scene_ctx={dm_result.scene_context is not None} prev_hub={ctx.hub_event}"
    )
    if dm_result.is_valid and dm_result.scene_context:
        # B5-FIX: мутация → SceneChange (CAUSAL_CONTRACT §3.5).
        if dm_result.scene_context.line_of_sight is not None:
            from app.services.scene_change import ChangeType, SceneChange

            _scene_manager = getattr(game_loop, "scene_manager", None)
            if _scene_manager:
                _los_change = SceneChange(
                    type=ChangeType.SCENE_METADATA,
                    target=location,
                    field="line_of_sight",
                    value=dm_result.scene_context.line_of_sight,
                    cause="dm_phase",
                )
                _scene_manager.apply_change(campaign_id, _los_change, scene_state)
            else:
                logger.warning(
                    "[DM_PHASE] scene_manager not found in game_loop. LoS change skipped."
                )
        # ADR-ACTION-BRIDGE: Гарантируем, что DecisionHub получит EventContext, а не EventDTO.
        # EventDTO имеет поле 'type', EventContext имеет 'event_type' и прямые поля семантики.
        _raw_event = dm_result.event_context
        if isinstance(_raw_event, HubEventContext):
            _base_event = _raw_event
        else:
            _base_event = HubEventContext(
                event_type=EventType(getattr(_raw_event, "type", "player_interacts")),
                actor_id=getattr(_raw_event, "source", "player"),
            )
        # _sem_payload уже инициализирован наверху функции (Rule 47 fix)
        if (
            shared_context
            and hasattr(shared_context, "intent_resolution")
            and shared_context.intent_resolution
        ):
            _params = (
                shared_context.intent_resolution.original_intent.parameters
                if shared_context.intent_resolution.original_intent
                else None
            )
            if _params:
                _sa = getattr(_params, "semantic_action", None)
                _tid = getattr(_params, "target_id", None)
                _tref = getattr(_params, "target_reference", None)
                # ADR-ACTION-BRIDGE: Инъекция семантики в EventContext
                if _sa:
                    _base_event.semantic_action = _sa
                    _sem_payload["semantic_action"] = _sa
                if _tid:
                    _base_event.target_id = _tid
                    _sem_payload["target_id"] = _tid
                if _tref:
                    _sem_payload["target_reference"] = _tref.lower()
        # P1 ARCH: Referential Closure Principle.
        # EventContext отражает ТОЛЬКО Intent.
        # Запрет fallback на shared_context (Ghost Causality).

        _intent_target_id = _sem_payload.get("target_id")

        # P1 ARCH: Referential Closure (§ENIGMA-005) + Incompleteness Semantics (§ENIGMA-006).
        # Запрет fallback на shared_context.
        # Если Intent не дал ID, сохраняем Unresolved Reference.
        import dataclasses

        if _intent_target_id:
            # Intent полностью замкнут — цель известна
            if getattr(_base_event, "target_id", None) is None:
                _base_event = dataclasses.replace(
                    _base_event, target_id=_intent_target_id
                )
            ctx.hub_event = dataclasses.replace(_base_event, payload=_sem_payload)
        else:
            # Intent недоспецифицирован.
            # target_id = None, но payload сохраняет target_reference (например, "люся").
            # Это не "нет цели", это "Неразрешённая ссылка".
            ctx.hub_event = dataclasses.replace(
                _base_event,
                target_id=None,
                payload=_sem_payload,  # _sem_payload содержит semantic_action и target_reference
            )

    return dm_result
