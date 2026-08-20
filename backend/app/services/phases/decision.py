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
from app.models.npc_state import NPCState, NPCStateAdapter, EmotionTag
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
    economic_profiles_map: Optional[Dict[str, Any]] = None,
    social_modifiers_map: Optional[Dict[str, Any]] = None,
    relationship_store: Optional[Any] = None,  # Шаг 1.1: SSOT для trust/fear
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
            # V8-PSY-19 FIX: Инкремент tick_age и удаление истёкших temporary_drives
            from app.models.npc_state import age_drives
            object.__setattr__(_npc_state, "temporary_drives", age_drives(_npc_state.temporary_drives))

            # V8-PSY-2 FIX: Willpower читается из NPCPersonality (L0), а не из несуществующего psyche
            _personality = getattr(_npc_state, "personality", None)  # noqa: ENIGMA002
            _willpower = getattr(_personality, "willpower", 50.0) if _personality else 50.0

            # Шаг 1.1: Вычисление social_pressure на основе реальных trust и fear из RelationshipStore (SSOT)
            _social_pressure = 0.0
            _support_present = False # V8-PSY-7 FIX: вычисляем наличие союзников
            if relationship_store:
                _rels = relationship_store.get_all_for_source(campaign_id, npc_id)
                if _rels:
                    # Берём минимальный trust и максимальный fear по всем связям NPC
                    _min_trust = min((v.get("trust", 0.0) for v in _rels.values()), default=0.0)
                    _max_fear = max((v.get("fear", 0.0) for v in _rels.values()), default=0.0)

                    # V8-MEM-4 FIX: Шкала RelationshipStore: -100..100, где 0.0 - нейтральное.
                    # Давление растёт при падении trust ниже 0.
                    # trust=0 -> pressure=0, trust=-50 -> pressure=10, trust=-100 -> pressure=20
                    _trust_pressure = max(0.0, -_min_trust) / 100.0 * 20.0
                    _social_pressure += min(20.0, _trust_pressure)

                    # Давление растёт при росте fear выше 0.
                    # fear=0 -> pressure=0, fear=50 -> pressure=10, fear=100 -> pressure=20
                    _fear_pressure = max(0.0, _max_fear) / 100.0 * 20.0
                    _social_pressure += min(20.0, _fear_pressure)

                    logger.info(f"[BREAK_PROGRESS] npc={npc_id} trust_min={_min_trust:.1f} fear_max={_max_fear:.1f} social_pressure={_social_pressure:.1f}")

                    # Эмерджентные эмоции: высокое давление -> ANGRY/FEARFUL
                    # Порог снижен до 5.0, чтобы даже moderate pressure вызывало раздражение
                    if _social_pressure > 5.0:
                        object.__setattr__(_npc_state, "emotion", EmotionTag.FEARFUL if _max_fear > 50.0 else EmotionTag.ANGRY)
                        logger.info(f"[EMOTION_EMERGENT] npc={npc_id} emotion={_npc_state.emotion.value} (social_pressure={_social_pressure:.1f})")

                    # V8-PSY-7 FIX: Поддержка есть, если у NPC есть хотя бы один союзник (trust > 50)
                    for _rel in _rels.values():
                        if _rel.get("trust", 0.0) > 50.0:
                            _support_present = True
                            break

            # ADR-S86.3: Расчёт слома воли
            _break_deltas = BreakProgressEngine.calculate(
                state=_npc_state,
                willpower=_willpower,
                recent_failures=getattr(_npc_state, "recent_failures", 0),
                support_present=_support_present, # V8-PSY-7 FIX: передаём вычисленное значение
                social_pressure=_social_pressure,
            )

            object.__setattr__(_npc_state, "identity_integrity", max(
                0.0,
                min(
                    1.0,
                    _npc_state.identity_integrity
                    + _break_deltas.identity_integrity_delta,
                ),
            ))
            object.__setattr__(_npc_state, "pressure_resistance", max(
                0.0,
                min(
                    1.0,
                    _npc_state.pressure_resistance
                    + _break_deltas.pressure_resistance_delta,
                ),
            ))
            object.__setattr__(_npc_state, "recent_failures", max(0, _npc_state.recent_failures + _break_deltas.recent_failures_delta))

            if _break_deltas.will_state_override is not None:
                object.__setattr__(_npc_state, "will_state", _break_deltas.will_state_override)

            # L2.7: LifeProjectResolver — продвигаем FSM жизненного проекта каждый тик
            from app.services.npc.life_project_resolver import LifeProjectResolver
            _old_state = getattr(_npc_state, "life_project_state", "ACTIVE")

            LifeProjectResolver.resolve(_npc_state, _break_deltas.identity_pressure, tick=tick_number)
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
            _rel_cache = getattr(_npc_state, "relationship_cache", {})  # noqa: ENIGMA002
            _player_rel = (
                _rel_cache.get("player", {}) if isinstance(_rel_cache, dict) else {}
            )
            
            # V8-PSY-6 FIX: Гидратация relationship_cache актуальными значениями из RelationshipStore
            if relationship_store and not _player_rel:
                _rels = relationship_store.get_all_for_source(campaign_id, npc_id)
                _player_data = _rels.get("player", {}) if isinstance(_rels, dict) else {}
                if _player_data:
                    _player_rel = {
                        "trust": _player_data.get("trust", 0.0),
                        "fear": _player_data.get("fear", 0.0),
                    }

            _trust = _player_rel.get("trust", 0.0)
            _fear = _player_rel.get("fear", 0.0) * 100
            _has_hidden = bool(getattr(_npc_state, "hidden_truth", None))  # noqa: ENIGMA002

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
                object.__setattr__(_npc_state, "behavior_mask", BehaviorMaskState(
                    mask=_new_mask, intensity=_mask_intensity, applied_at_day=game_day
                ))

            # V8-PSY-18 FIX: Удалены root-level writes. write_to_legacy() уже корректно
            # сохраняет эти поля в psyche sub-dict, который читает from_legacy.

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

    # Вычисляем player_distances один раз для всех NPC (SpatialQueryService - pure reader)
    _spatial_query = getattr(ctx.shared_context, "spatial_query", None) if ctx.shared_context else None  # noqa: ENIGMA001, ENIGMA002
    if _spatial_query is None:
        logger.debug("SpatialQueryService missing in shared_context (decision.py). Falling back to scene_state reader.")
    if not _spatial_query and ctx.scene_state:
        from app.services.spatial.spatial_query_service import SpatialQueryService
        _spatial_query = SpatialQueryService(
            npc_positions=ctx.scene_state.get("npc_positions", {}),
            scene_state=ctx.scene_state,
        )
    _npc_ids = [n.get("id") or n.get("npc_id") for n in alive_npcs]
    _player_dists = _spatial_query.player_distances(_npc_ids) if _spatial_query else {}

    if _svc:
        for n in alive_npcs:
            _nid = n.get("id") or n.get("npc_id")
            if not _nid:
                continue

            if _svc.memory_manager:
                # S128 FIX: Загружаем граф отношений для всех alive NPC, а не только player.
                _target_ids = [n.get("id") or n.get("npc_id") for n in alive_npcs]
                if "player" not in _target_ids:
                    _target_ids.append("player")
                _memory_weights_map[_nid] = (
                    _svc.memory_manager.get_weights_for_decision(
                        campaign_id=ctx.campaign_id, npc_id=_nid, target_ids=_target_ids
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
                    _svc.social_engine.compute_social_modifiers(
                        npc_id=_nid,
                        player_distances=_player_dists,
                        event_type=getattr(ctx.shared_context, "action_type", None) or "idle"  # noqa: ENIGMA002
                    )
                )

            if _svc.reputation_engine:
                _reputation_modifiers_map[_nid] = (
                    _svc.reputation_engine.compute_reputation_modifier(npc_id=_nid)
                )

            if hasattr(_svc, "economic_profiles"):
                _economic_profiles_map[_nid] = _svc.economic_profiles.get(_nid)

            _cstore = getattr(_svc, "crystallized_belief_store", None)  # noqa: ENIGMA002
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
