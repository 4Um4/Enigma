# -*- coding: utf-8 -*-
"""
Phases/Decision — Изоляция Block 4 (Behavior Evaluation).

path: backend/app/services/phases/decision.py
Назначение: Расчёт BreakProgressEngine и BehaviorMask для NPC.
Зависимости: app.services.npc.break_progress_engine, app.models.npc_state, app.models.behavior_mask, app.models.will, app.domain.identity_events
Основные сущности: evaluate_behavior_and_identity
"""

import logging
from typing import Any, Dict, List, Optional

from app.domain.identity_events import TraitDriftEvent
from app.models.behavior_mask import BehaviorMask, BehaviorMaskState
from app.models.npc_state import NPCState, NPCStateAdapter
from app.models.will import WillState
from app.services.npc.break_progress_engine import BreakProgressEngine

logger = logging.getLogger(__name__)


def evaluate_behavior_and_identity(
    npc_states: List[Dict[str, Any]],
    campaign_id: str,
    tick_number: int,
    game_day: int,
    memory_manager: Any,
    l1_chronicle: Optional[Any],
) -> None:
    """Выполняет расчёт слома воли (BreakProgress) и поведенческой маски (BehaviorMask).

    Мутирует npc_states in-place (записывает identity_integrity, will_state, behavior_mask).
    Записывает TraitDriftEvent в l1_chronicle (если передан).
    """
    # 1. Сбор identity_traits для L1Chronicle
    identities: Dict[str, Dict[str, float]] = {}
    if memory_manager:
        for npc_dict in npc_states:
            if npc_id := npc_dict.get("id"):
                if traits := memory_manager.get_identity_traits(campaign_id, npc_id):
                    identities[npc_id] = traits

    # 2. Расчёт для каждого NPC
    for npc_dict in npc_states:
        npc_id = npc_dict.get("id")
        if not npc_id:
            continue

        try:
            _npc_state = NPCStateAdapter.from_legacy(npc_dict)
            _willpower = (
                getattr(_npc_state.psyche, "willpower", 50.0)
                if hasattr(_npc_state, "psyche")
                else 50.0
            )

            # ADR-S86.3: Расчёт слома воли
            _break_deltas = BreakProgressEngine.calculate(
                state=_npc_state,
                willpower=_willpower,
                recent_failures=getattr(_npc_state, "recent_failures", 0),
                support_present=getattr(_npc_state, "support_present", False),
            )

            _npc_state.identity_integrity = max(
                0.0,
                min(
                    1.0,
                    _npc_state.identity_integrity
                    + _break_deltas.identity_integrity_delta,
                ),
            )
            _npc_state.pressure_resistance = max(
                0.0,
                min(
                    1.0,
                    _npc_state.pressure_resistance
                    + _break_deltas.pressure_resistance_delta,
                ),
            )

            if _break_deltas.will_state_override is not None:
                _npc_state.will_state = _break_deltas.will_state_override

            # L2.7: LifeProjectResolver — продвигаем FSM жизненного проекта каждый тик
            from app.services.npc.life_project_resolver import LifeProjectResolver
            _old_state = getattr(_npc_state, "life_project_state", "ACTIVE")
            LifeProjectResolver.resolve(_npc_state, _break_deltas.identity_crisis)
            if _old_state != _npc_state.life_project_state:
                logger.info(f"[LIFE_PROJECT] NPC {npc_id} FSM переход: {_old_state} -> {_npc_state.life_project_state} (Проект: {_npc_state.life_project})")

            # ADR-O-208: Сохраняем вычисленные дельты обратно в npc_dict
            NPCState.write_to_legacy(_npc_state, npc_dict)

            # L1Chronicle: Фиксация давления и идентичности
            if l1_chronicle is not None:
                _affect = _npc_state.affective_load * 100
                _events_to_log: List[TraitDriftEvent] = []

                if _affect > 10.0:
                    _events_to_log.append(
                        TraitDriftEvent(
                            tick_id=tick_number,
                            target_id=npc_id,
                            source_id=f"break_progress:{_break_deltas.stage}",
                            effect_value=-0.01,
                            observation_weight=1.0,
                            event_type="pressure",
                        )
                    )

                if _affect > 10.0 or _break_deltas.identity_integrity_delta < 0:
                    _events_to_log.append(
                        TraitDriftEvent(
                            tick_id=tick_number,
                            target_id=npc_id,
                            source_id=f"break_progress:{_break_deltas.stage}",
                            effect_value=_break_deltas.identity_integrity_delta,
                            observation_weight=1.0,
                            event_type="identity",
                        )
                    )
                    _events_to_log.append(
                        TraitDriftEvent(
                            tick_id=tick_number,
                            target_id=npc_id,
                            source_id=f"break_progress:{_break_deltas.stage}",
                            effect_value=-0.01,
                            observation_weight=1.0,
                            event_type="will",
                        )
                    )

                if _events_to_log:
                    l1_chronicle.commit_tick_buffer(_events_to_log, tick_number)

                if _break_deltas.will_state_override is not None:
                    l1_chronicle.commit_tick_buffer(
                        [
                            TraitDriftEvent(
                                tick_id=tick_number,
                                target_id=npc_id,
                                source_id=f"break_progress:{_break_deltas.stage}",
                                effect_value=-0.1,
                                observation_weight=1.0,
                                event_type="will_state",
                            )
                        ],
                        tick_number,
                    )

            # ADR-S86.4: Расчёт BehaviorMask (гистерезисный социальный слой)
            _rel_cache = getattr(_npc_state, "relationship_cache", {})
            _player_rel = (
                _rel_cache.get("player", {}) if isinstance(_rel_cache, dict) else {}
            )
            _trust = _player_rel.get("trust", 0.0)
            _fear = _player_rel.get("fear", 0.0) * 100
            _has_hidden = bool(getattr(_npc_state, "hidden_truth", None))

            _new_mask, _mask_intensity = BehaviorMask.NONE, 0.0
            if _npc_state.will_state == WillState.BROKEN:
                _new_mask, _mask_intensity = BehaviorMask.COLLAPSE, 0.8
            elif _fear > 60 and _trust < 0 and _willpower > 40:
                _new_mask, _mask_intensity = (
                    BehaviorMask.FAKE_SUBMISSION,
                    min(0.7, _fear / 100),
                )
            elif _trust < -50 and _fear < 30 and _has_hidden:
                _new_mask, _mask_intensity = (
                    BehaviorMask.BETRAYAL,
                    min(0.6, abs(_trust) / 100),
                )

            if _new_mask != _npc_state.behavior_mask.mask:
                _npc_state.behavior_mask = BehaviorMaskState(
                    mask=_new_mask, intensity=_mask_intensity, applied_at_day=game_day
                )

            # Прямая мутация npc_dict для Fast Path (serializers)
            npc_dict["identity_integrity"] = _npc_state.identity_integrity
            npc_dict["pressure_resistance"] = _npc_state.pressure_resistance
            npc_dict["will_state"] = (
                _npc_state.will_state.value
                if hasattr(_npc_state.will_state, "value")
                else _npc_state.will_state
            )
            npc_dict["behavior_mask"] = _npc_state.behavior_mask.mask.value
            npc_dict["behavior_mask_intensity"] = _npc_state.behavior_mask.intensity

        except Exception as e:
            logger.error(f"[BREAK_PROGRESS] failed for {npc_id}: {e}")
            raise


def assemble_preloaded_data(ctx: Any, alive_npcs: list) -> tuple:
    """Сборка preloaded данных для Pure Reducer (вынос I/O из run)."""
    _svc = ctx.npc_services
    _memory_weights_map = {}
    _narrative_cache_map = {}
    _social_modifiers_map = {}
    _reputation_modifiers_map = {}
    _economic_profiles_map = {}
    _crystallized_beliefs_map = {}
    _identity_traits_map = {}

    if _svc:
        for n in alive_npcs:
            _nid = n.get("id") or n.get("npc_id")
            if not _nid:
                continue

            if _svc.memory_manager:
                _memory_weights_map[_nid] = (
                    _svc.memory_manager.get_weights_for_decision(
                        campaign_id=ctx.campaign_id, npc_id=_nid, target_id="player"
                    )
                )
                _narrative_cache_map[_nid] = (
                    _svc.memory_manager.load_narrative_from_sqlite(
                        ctx.campaign_id, _nid
                    )
                )
                _identity_traits_map[_nid] = _svc.memory_manager.get_identity_traits(
                    campaign_id=ctx.campaign_id, npc_id=_nid
                )

            if _svc.social_engine:
                _social_modifiers_map[_nid] = (
                    _svc.social_engine.compute_social_modifiers(npc_id=_nid)
                )

            if _svc.reputation_engine:
                _reputation_modifiers_map[_nid] = (
                    _svc.reputation_engine.compute_reputation_modifier(npc_id=_nid)
                )

            if hasattr(_svc, "economic_profiles"):
                _economic_profiles_map[_nid] = _svc.economic_profiles.get(_nid)

            _cstore = getattr(_svc, "crystallized_belief_store", None)
            if _cstore:
                _crystallized_beliefs_map[_nid] = _cstore.get_beliefs(npc_id=_nid)

    return (
        _memory_weights_map,
        _narrative_cache_map,
        _social_modifiers_map,
        _reputation_modifiers_map,
        _economic_profiles_map,
        _crystallized_beliefs_map,
        _identity_traits_map,
    )
