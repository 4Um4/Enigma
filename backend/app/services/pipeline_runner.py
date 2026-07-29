# -*- coding: utf-8 -*-
"""
Pipeline Runner — Изоляция Pure Reducer (NpcTickPipeline.run) и Commit Bridge.

path: backend/app/services/pipeline_runner.py
Назначение: Выполнение чистого ядра симуляции и перенос результатов в _TickContext.
Зависимости: app.domain.tick, app.services.npc.npc_tick_pipeline, app.services.drf_bus, app.models.npc_state, app.models.state_delta
Основные сущности: build_tick_state, run_pipeline, build_npc_contexts_from_intents
"""

import logging
from typing import Any, Dict, List, Optional

from app.domain.tick import TickMutation, create_tick_state
from app.services.drf_bus import DRFExecutionContext
from app.services.npc.npc_tick_pipeline import NpcTickPipeline

logger = logging.getLogger(__name__)


def build_tick_state(
    ctx: Any,
    alive_npcs: List[dict],
    effective_drives_map: Dict[str, Any],
    pe_mods_map: Dict[str, Dict[str, float]],
    memory_weights_map: Dict[str, Any],
    narrative_cache_map: Dict[str, Any],
    social_modifiers_map: Dict[str, Any],
    reputation_modifiers_map: Dict[str, Any],
    economic_profiles_map: Dict[str, Any],
    crystallized_beliefs_map: Dict[str, Any],
    identity_traits_map: Dict[str, Any],
    spatial_service: Optional[Any] = None,  # P5 FIX: Явная инъекция от оркестратора
    spatial_query: Optional[Any] = None,    # P5 FIX: Явная инъекция от оркестратора
    l1_chronicle: Optional[Any] = None,     # V8-PSY-1 FIX: Инъекция L1Chronicle
) -> Any:
    """Сборка immutable TickState (causal snapshot) для NpcTickPipeline.run()."""
    _dm_ctx = None
    for interv in ctx.interventions:
        if interv.source == "player" and "dm_ctx" in interv.payload:
            _dm_ctx = interv.payload["dm_ctx"]
            break

    _svc = ctx.npc_services
    _tick_state = create_tick_state(
        tick_id=ctx.tick_number,
        campaign_id=ctx.campaign_id,
        scene_state=ctx.scene_state,
        all_npcs_raw=alive_npcs,
        effective_drives_map=effective_drives_map,
        pe_modifiers_map=pe_mods_map,
        interventions=ctx.interventions,
        hub_event=_dm_ctx.hub_event if _dm_ctx else None,
        player_target_id=_dm_ctx.player_target_id if _dm_ctx else None,
        action_type=_dm_ctx.action_type if _dm_ctx else "idle",
        raw_input=_dm_ctx.raw_input if _dm_ctx else "",
        is_session_start=_dm_ctx.is_session_start if _dm_ctx else False,
        nearby_npcs=_dm_ctx.nearby_npcs if _dm_ctx else ctx.all_npcs_raw,
        line_of_sight=_dm_ctx.line_of_sight
        if _dm_ctx
        else {n.get("id", n.get("npc_id")): True for n in ctx.all_npcs_raw},
        scene_continuity=_dm_ctx.scene_continuity if _dm_ctx else None,
        spatial_events=_dm_ctx.spatial_events if _dm_ctx else [],
        drf_tick_id=ctx.tick_number,
        memory_weights_map=memory_weights_map,
        narrative_cache_map=narrative_cache_map,
        social_modifiers_map=social_modifiers_map,
        reputation_modifiers_map=reputation_modifiers_map,
        economic_profiles_map=economic_profiles_map,
        crystallized_beliefs_map=crystallized_beliefs_map,
        identity_traits_map=identity_traits_map,
        relationship_store=_svc.relationship_store if _svc else None,
        spatial_service=spatial_service or (_svc.spatial_service if _svc and hasattr(_svc, "spatial_service") else None),
        spatial_query=spatial_query or (_svc.spatial_query if _svc and hasattr(_svc, "spatial_query") else None),
        npc_topics=ctx.npc_topics,
        response_targets=ctx.response_targets,
        l1_chronicle=l1_chronicle, # V8-PSY-1 FIX
    )
    return _tick_state


def run_pipeline(
    state: Any, drf_ctx: "DRFExecutionContext", rng_factory: Any
) -> TickMutation:
    """Вызов Pure Reducer (NpcTickPipeline.run)."""
    return NpcTickPipeline.run(state=state, drf_ctx=drf_ctx, rng_factory=rng_factory)


def build_npc_contexts_from_intents(ctx: Any, mutation: TickMutation) -> None:
    """Commit Bridge: Перенос результатов TickMutation в ctx и сборка npc_contexts.

    Без этого R3_DIRECT получает 0 decisions → DM видит пустой мир → "Ничего не произошло".
    """
    ctx.communication_intents = mutation.communication_intents or []
    ctx.movement_intents = mutation.movement_intents or []
    ctx.significant_events = mutation.npc_deltas or []

    # Применение L1 Drift Events (Append-only Chronicle)
    _svc = ctx.npc_services
    if mutation.l1_drift_events and _svc and _svc.memory_manager:
        for _event in mutation.l1_drift_events:
            _svc.memory_manager.l1_chronicle.append(_event)

    # Применение Memory Events (STM/L2 update)
    if mutation.memory_events and _svc and _svc.memory_manager:
        from app.models.npc_state import NPCState
        from app.services.npc.npc_loader import load_l2_state_from_runtime_dict

        _spatial_query = getattr(ctx.shared_context, "spatial_query", None) if ctx.shared_context else None
        if not _spatial_query and ctx.scene_state:
            from app.services.spatial.spatial_query_service import SpatialQueryService
            _spatial_query = SpatialQueryService(
                npc_positions=ctx.scene_state.get("npc_positions", {}),
                scene_state=ctx.scene_state,
            )

        # BUG-AUDIT-11 (Фаза 2): Эпистемический барьер.
        # NPC не должен писать в память то, чего не видел/слышал (телепатия).
        from app.services.npc.perception_filter import filter_perceiving_npcs

        # Собираем ID всех живых NPC для фильтрации
        _all_npc_ids = [n.get("npc_id", n.get("id")) for n in ctx.all_npcs_raw if n.get("npc_id", n.get("id"))]

        # BUG-DL-06: Применяем отложенные диалоговые события (из предыдущего тика)
        _pending_dialogue_events = _svc.memory_manager.drain_pending_dialogue_memories()
        for _mem_evt in _pending_dialogue_events:
            _npc_id = _mem_evt.payload.get("npc_id")
            if not _npc_id:
                continue
            _npc_dict = next((n for n in ctx.all_npcs_raw if n.get("npc_id") == _npc_id or n.get("id") == _npc_id), None)
            if not _npc_dict:
                continue
            try:
                _npc_state = load_l2_state_from_runtime_dict(_npc_dict)
                _npc_state = _svc.memory_manager.apply(
                    event=_mem_evt,
                    npc_state=_npc_state,
                    campaign_id=ctx.campaign_id,
                    spatial_query=_spatial_query,
                )
                NPCState.write_to_legacy(_npc_state, _npc_dict)
            except Exception as e:
                logger.warning(f"[PIPELINE_RUNNER] Pending dialogue apply failed for {_npc_id}: {e}")

        for _mem_evt in mutation.memory_events:
            _npc_id = _mem_evt.payload.get("npc_id")
            if not _npc_id:
                continue

            # Проверка Line-of-Sight и hearing-radius через SpatialQueryService
            _perceiving_npcs = filter_perceiving_npcs(
                npc_ids=_all_npc_ids,
                event=_mem_evt,
                scene_state=ctx.scene_state,
                spatial_query=_spatial_query,
            )
            if _npc_id not in _perceiving_npcs:
                logger.debug(f"[EPISTEMIC_FILTER] NPC {_npc_id} пропущен: не воспринимает событие {_mem_evt.type}")
                continue

            _npc_dict = next((n for n in ctx.all_npcs_raw if n.get("npc_id") == _npc_id or n.get("id") == _npc_id), None)
            if not _npc_dict:
                continue
            try:
                _npc_state = load_l2_state_from_runtime_dict(_npc_dict)
                _npc_state = _svc.memory_manager.apply(
                    event=_mem_evt,
                    npc_state=_npc_state,
                    campaign_id=ctx.campaign_id,
                    spatial_query=_spatial_query,
                )
                NPCState.write_to_legacy(_npc_state, _npc_dict)
            except Exception as e:
                logger.warning(f"[PIPELINE_RUNNER] Memory apply failed for {_npc_id}: {e}")

    if not ctx.communication_intents:
        return

    from dataclasses import dataclass

    from app.models.delta_payloads import IdentityPayload
    from app.models.npc_state import Intent as NpcIntent
    from app.models.npc_state import personality_from_legacy
    from app.models.state_delta import DeltaDomain, StateDeltas

    @dataclass
    class _DecisionResultAdapter:
        """Адаптер CommunicationIntent → интерфейс DecisionResult для R3_DIRECT."""

        npc_id: str
        intent: Any
        intent_target: str = "player"
        score: float = 0.5
        deltas: Any = None
        communication: Any = None
        decision: Any = None
        narrative_fact: Optional[str] = None
        micro_event: Optional[str] = None

    for _intent in ctx.communication_intents:
        _speaker = getattr(_intent, "speaker", "") or getattr(_intent, "npc_id", "")
        if not _speaker:
            continue
        _npc_dict = next(
            (
                n
                for n in ctx.all_npcs_raw
                if n.get("npc_id") == _speaker or n.get("id") == _speaker
            ),
            None,
        )
        if not _npc_dict:
            continue
        _profile_l0 = personality_from_legacy(_npc_dict)
        _topic = getattr(_intent, "topic", "") or getattr(_intent, "intent_type", "")
        _intent_type_str = getattr(_intent, "intent_type", "диалог").lower()
        _npc_intent = NpcIntent.TALK
        try:
            if "угроз" in _intent_type_str or "threat" in _intent_type_str:
                _npc_intent = NpcIntent.THREATEN
            elif "atan" in _intent_type_str or "attack" in _intent_type_str:
                _npc_intent = NpcIntent.ATTACK
            elif "бег" in _intent_type_str or "flee" in _intent_type_str:
                _npc_intent = NpcIntent.FLEE
        except Exception as e:
            logger.warning(f"[B5-FIX] silent failure suppressed: {e}")
        _empty_deltas = StateDeltas(
            npc_id=_speaker,
            domain=DeltaDomain.IDENTITY,
            payload=IdentityPayload(),
            source="communication_intent_adapter",
        )
        _adapter = _DecisionResultAdapter(
            npc_id=_speaker,
            intent=_npc_intent,
            intent_target=getattr(_intent, "target_id", "player") or "player",
            score=0.5,
            deltas=_empty_deltas,
            communication=_intent,
            decision=None,
        )
        ctx.npc_contexts.append(
            {
                "npc_id": _speaker,
                "tier": _profile_l0.tier if _profile_l0 else "minor",
                "profile_l0": _profile_l0,
                "topic": _topic,
                "decision_result": _adapter,
                "observed_state": {
                    "name": _npc_dict.get("name", _speaker),
                    "description": _npc_dict.get("description", ""),
                    "narrative_cache": _npc_dict.get("narrative_cache", []),
                },
                "micro_events": [],
                "perceived_events": [],
                "communication_intent": _intent,
            }
        )
