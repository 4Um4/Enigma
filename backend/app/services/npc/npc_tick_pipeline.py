# path: C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\npc\npc_tick_pipeline.py
"""
Чистые функции NPC пайплайна (Фазы 3-6).

Без self, без побочных эффектов кроме логирования.
Мутируют только переданные state_l2 / npc_dict — не трогают внешние сервисы.


Назначение: Чистые функции NPC пайплайна — без self, без побочных эффектов кроме логгирования
Зависимости: logging, app.services.resolution, app.services.reaction, app.services.npc, app.services.verbalization, app.models
Основные сущности: BASE_IMPORTANCE, apply_perception_memory, create_memory_event, build_verbalization_context, run_npc_pipeline
"""

import copy
import logging
import math
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from app.domain.tick import TickMutation, TickState
from app.services.npc.legacy_delta_adapter import LegacyStateDeltaAdapter
from app.services.spatial.spatial_runtime import line_of_sight, sound_reach

if TYPE_CHECKING:
    from app.services.npc.kernel_rng import KernelRNG
from app.services.npc.domain_phases import (
    age_temporary_drives,
    compute_economy,
    reset_session_state,
    resolve_physical_attack,
    tick_conditions,
)
from app.services.npc.kernel_rng import KernelRNG

logger = logging.getLogger(__name__)

def _resolve_proactive_target(
    intent_value: str,
    npc_id: str,
    intent_target: str | None,
    scene_state: dict,
    spatial_service: Any,
    location_id: str,
) -> str | None:
    """Возвращает target_node для proactive movement intent."""
    if not spatial_service:
        return None

    # 1. Явный target_id — резолвим его позицию через граф
    if intent_target and intent_target != "player":
        target_pos = scene_state.get("npc_positions", {}).get(intent_target, {})
        lp = target_pos.get("local_position")
        if lp:
            _node_ref = spatial_service.get_nearest(
                zone_id=location_id,
                origin_xy=(lp.get("x", 0), lp.get("y", 0)),
            )
            if _node_ref:
                return getattr(_node_ref, "node_id", str(_node_ref))

    # 2. Резолвим по intent type через NodeRole
    from app.models.spatial_contracts import NodeRole
    _INTENT_TO_ROLE = {
        "request_service": NodeRole.BAR,
        "offer_job": NodeRole.BAR,
        "block_path": NodeRole.ENTRANCE,
        "ambush": NodeRole.DEFAULT,
        "change_role": NodeRole.WORKBENCH,
    }
    if intent_value in _INTENT_TO_ROLE:
        _node_ref = spatial_service.resolve_node(_INTENT_TO_ROLE[intent_value])
        if _node_ref:
            return getattr(_node_ref, "node_id", str(_node_ref))

    # 3. Социальные intents — к ближайшему NPC
    if intent_value in ("seek_ally", "call_for_help", "spread_rumor", "talk"):
        npc_positions = scene_state.get("npc_positions", {})
        my_pos = npc_positions.get(npc_id, {}).get("local_position", {"x": 0, "y": 0})
        nearest_npc_id = None
        nearest_dist = float("inf")
        for other_id, other_data in npc_positions.items():
            if other_id == npc_id or other_id == "player":
                continue
            other_pos = other_data.get("local_position", {})
            if not other_pos:
                continue
            dx = other_pos.get("x", 0) - my_pos.get("x", 0)
            dy = other_pos.get("y", 0) - my_pos.get("y", 0)
            dist = (dx * dx + dy * dy) ** 0.5
            if dist < nearest_dist:
                nearest_dist = dist
                nearest_npc_id = other_id
        if nearest_npc_id:
            other_pos = npc_positions[nearest_npc_id].get("local_position", {})
            _node_ref = spatial_service.get_nearest(
                zone_id=location_id,
                origin_xy=(other_pos.get("x", 0), other_pos.get("y", 0)),
            )
            if _node_ref:
                return getattr(_node_ref, "node_id", str(_node_ref))
    return None


class NpcTickPipeline:
    """
    TZ-09: Execution Kernel as Pure Deterministic Reducer.

    Инварианты (внедрены в S97, ADR-TZ10-1):
    - НИКАКИХ вызовов MemoryManager, StateApplicator или SQLite внутри.
    - НИКАКИХ скрытых мутаций состояния.
    - Принимает TickState, возвращает TickMutation.
    """

    @staticmethod
    def run(
        state: TickState,
        drf_ctx: Optional[Any] = None,
        rng_factory: Optional[Callable[[str], "KernelRNG"]] = None,
    ) -> TickMutation:
        """TZ-10: Pure Deterministic Reducer. Сервисы исключены (Strangulation Pattern)."""
        from app.models.npc_state import NPCIdentityL1, compute_drive_modifiers
        from app.services.events.event_types import EventType
        from app.services.npc.decision_hub import DecisionHub, EventContext
        from app.services.npc.interpretation_engine import InterpretationEngine
        from app.services.npc.npc_loader import (
            load_l2_state_from_runtime_dict,
            load_profile_from_legacy_json,
        )
        from app.services.npc.state_applicator import StateApplicator

        _attack_target = (
            state.player_target_id
            if state.action_type in ("player_attacks", "PLAYER_ATTACKED", "combat")
            else None
        )

        _is_player_turn = state.hub_event is not None
        _idle_pressure_updates: Dict[Any, float] = {} # V8-SOC-5 FIX
        
        # V8-SOC-5 FIX: Константы для аккумуляции давления
        from app.core.constants import IDLE_PRESSURE_ACCUM_RATE, IDLE_PRESSURE_DECAY_RATE
        _npcs_to_process = state.nearby_npcs if _is_player_turn else state.all_npcs_raw

        logger.debug(
            f"[SHI_TRACE_2] NpcTickPipeline.run ENTERED. is_player_turn={_is_player_turn} npcs_to_process={len(_npcs_to_process or [])} nearby_npcs={len(state.nearby_npcs or [])} all_npcs={len(state.all_npcs_raw or [])}"
        )

        communication_intents: List[Any] = []
        movement_intents: List[Any] = []
        npc_deltas: List[Any] = []
        _l1_events: List[Any] = []
        memory_events: List[Any] = []

        for npc in _npcs_to_process:
            npc_id = npc.get("npc_id") or npc.get("id")
            _los = (
                state.line_of_sight.get(npc_id, False) if state.line_of_sight else False
            )
            _is_attack_target = npc_id == _attack_target

            # S1 FIX: Используем deepcopy для проверки слуха, чтобы избежать мутации оригинального npc
            state_l2 = load_l2_state_from_runtime_dict(copy.deepcopy(dict(npc))) if npc_id else None

            if npc_id and (_is_player_turn and not (_los or _is_attack_target)):
                # P1-02: NPC не видит, но может слышать.
                # Если NPC в радиусе слуха, он записывает обобщённое событие в память, но пропускает DecisionHub.
                _npc_pos_dict = npc.get("local_position", {"x": 0.0, "y": 0.0})
                _npc_pos = (_npc_pos_dict.get("x", 0.0), _npc_pos_dict.get("y", 0.0))
                _player_pos_dict = state.scene_state.get("npc_positions", {}).get("player", {}).get("local_position", {"x": 0.0, "y": 0.0})
                _player_pos = (_player_pos_dict.get("x", 0.0), _player_pos_dict.get("y", 0.0))
                _dist_to_player = math.hypot(_npc_pos[0] - _player_pos[0], _npc_pos[1] - _player_pos[1])
                _has_sound = sound_reach(15.0, state.scene_state) >= _dist_to_player

                if _has_sound and state.hub_event and state_l2 is not None:
                    _p_target = state.player_target_id or "player"
                    try:
                        _mem_evt = apply_perception_memory(
                            None,
                            state_l2,
                            state.hub_event,
                            npc_id,
                            _p_target,
                            "(обрывки разговора)", # Обобщённый текст для слуха
                            state.campaign_id,
                            spatial_query=state.spatial_query,
                        )
                        if _mem_evt:
                            memory_events.append(_mem_evt)
                    except Exception as _perc_mem_err:
                        logger.warning(
                            f"[MEMORY] hearing perception apply failed for {npc_id}: {_perc_mem_err}"
                        )
                continue

            _npc_drf_ctx = drf_ctx.for_npc(npc_id) if drf_ctx else None

            _npc_profile = None
            for _n in state.all_npcs_raw:
                if _n.get("id") == npc_id or _n.get("npc_id") == npc_id:
                    _npc_profile = _n
                    break

            if not _npc_profile:
                continue

            # Deep copy замороженного снимка для безопасной мутации легаси-кодом
            _npc_dict_for_write = copy.deepcopy(dict(_npc_profile))
            profile_l0 = load_profile_from_legacy_json(_npc_dict_for_write)
            state_l2 = load_l2_state_from_runtime_dict(_npc_dict_for_write)

            # TZ-10: Чтение preloaded narrative_cache из TickState
            _sqlite_cache = state.narrative_cache_map.get(npc_id)
            if _sqlite_cache is not None:
                state_l2.narrative_cache = _sqlite_cache

            age_temporary_drives(state_l2, _npc_dict_for_write, npc_id)

            state_l2, _reflex_constraints = resolve_physical_attack(
                npc_id=npc_id,
                npc_profile=_npc_dict_for_write,
                npc_dict_for_write=_npc_dict_for_write,
                state_l2=state_l2,
                action_type=state.action_type,
                target_id=state.player_target_id or "player",
                current_tick=state.tick_id,
                scene_continuity=state.scene_continuity,
                scene_state=copy.deepcopy(state.scene_state),
                relationship_store=state.relationship_store,
            )

            state_l2 = tick_conditions(
                state_l2, _npc_dict_for_write, state.tick_id, state.scene_continuity
            )
            reset_session_state(state_l2, npc_id, state.is_session_start)

            # TZ-10: Чтение preloaded memory weights из TickState
            _mem_weights = state.memory_weights_map.get(npc_id, {})
            if _mem_weights:
                try:
                    # S128 FIX: _mem_weights теперь граф Dict[str, Dict[str, float]].
                    # Применяем player отдельно, так как его нет в nearby_npcs.
                    _player_weights = _mem_weights.get("player", {})
                    if _player_weights:
                        state_l2.relationship_cache.setdefault("player", {}).update(
                            _player_weights
                        )

                    # ADR-O-331: Safe Position Extraction. local_position может быть dict {"x":, "y":} или tuple (x, y).
                    _raw_pos = state_l2.local_position if hasattr(state_l2, "local_position") else (0.0, 0.0)
                    _npc_pos = (_raw_pos.get("x", 0.0), _raw_pos.get("y", 0.0)) if isinstance(_raw_pos, dict) else tuple(_raw_pos)

                    for _nearby_npc in state.nearby_npcs:
                        _nearby_id = _nearby_npc.get("npc_id") or _nearby_npc.get("id")
                        if _nearby_id and _nearby_id != npc_id:
                            _raw_target = _nearby_npc.get("local_position", _npc_pos)
                            _target_pos = (_raw_target.get("x", 0.0), _raw_target.get("y", 0.0)) if isinstance(_raw_target, dict) else tuple(_raw_target)
                            _dist = math.hypot(_npc_pos[0] - _target_pos[0], _npc_pos[1] - _target_pos[1])
                            _has_los = line_of_sight(_dist, state.scene_state, _npc_pos[0], _npc_pos[1], _target_pos[0], _target_pos[1])
                            _has_sound = sound_reach(15.0, state.scene_state) >= _dist
                            if not _has_los and not _has_sound:
                                continue
                            _npc_weights = _mem_weights.get(_nearby_id, {})
                            state_l2.relationship_cache.setdefault(
                                _nearby_id, {}
                            ).update(_npc_weights)
                except Exception as _mem_e:
                    logger.error(
                        f"[MEMORY] get_weights failed for {npc_id}: {_mem_e}",
                        exc_info=True,
                    )

            # TZ-10: Сборка memory_events для отложенного применения (без I/O внутри run)
            if state.hub_event:
                try:
                    _mem_evt = apply_perception_memory(
                        None,
                        state_l2,
                        state.hub_event,
                        npc_id,
                        state.player_target_id or "player",
                        state.raw_input,
                        state.campaign_id,
                        spatial_query=state.spatial_query,
                    )
                    if _mem_evt:
                        memory_events.append(_mem_evt)
                except Exception as _perc_mem_err:
                    logger.warning(
                        f"[MEMORY] perception apply failed for {npc_id}: {_perc_mem_err}"
                    )

            try:
                from app.services.npc.belief_transition_engine import (
                    BeliefTransitionEngine,
                )

                _event_for_belief = (
                    state.hub_event
                    if state.hub_event
                    else EventContext(
                        event_type=EventType.WORLD_TICK,
                        actor_id=npc_id,
                        success=True,
                        intensity=0.2,
                        distance=0.0,
                        witness_count=0,
                        location=state.scene_state.get("location_id", ""),
                        scene_flags=set(state.scene_state.get("active_flags", [])),
                        scene_facts=[],
                    )
                )
                BeliefTransitionEngine().integrate(
                    state_l2, _event_for_belief, state.tick_id
                )
            except Exception as _belief_err:
                logger.warning(
                    f"[BELIEF] belief update failed for {npc_id}: {_belief_err}"
                )

            # ADR-O-208: L3-P2. InterpretationEngine использует эфемерную проекцию (L3).
            _ed = state.effective_drives_map.get(npc_id)
            _drives_for_interp = _ed.values if _ed else profile_l0.drives_base
            _event_for_interp = (
                state.hub_event
                if state.hub_event
                else EventContext(
                    event_type=EventType.WORLD_TICK,
                    actor_id=npc_id,
                    success=True,
                    intensity=0.2,
                    distance=0.0,
                    witness_count=0,
                    location=state.scene_state.get("location_id", ""),
                    scene_flags=set(state.scene_state.get("active_flags", [])),
                    scene_facts=[],
                )
            )
            interpretation = InterpretationEngine().compute(
                state=state_l2, event=_event_for_interp, drives_base=_drives_for_interp
            )

            # TZ-10: Чтение preloaded identity traits из TickState
            _identity_traits = state.identity_traits_map.get(npc_id, {})
            _identity = NPCIdentityL1(npc_id=npc_id, active_traits=_identity_traits)

            # TZ-10: Чтение preloaded social modifiers из TickState
            _social_mods = state.social_modifiers_map.get(npc_id, {})

            # TZ-10: Чтение preloaded economic profile из TickState
            _eco_profile = state.economic_profiles_map.get(npc_id)
            _current_activity = npc.get("routine", {}).get("current", "")
            _eco_result = compute_economy(
                npc_id, _eco_profile, state_l2, _current_activity
            )
            _all_modifiers = {**interpretation.score_modifiers}
            if _eco_modifiers := _eco_result["modifiers"]:
                for _intent, _mod in _eco_modifiers.items():
                    _all_modifiers[_intent] = _all_modifiers.get(_intent, 0.0) + _mod

            # TZ-10: Чтение preloaded reputation modifier из TickState
            _rep_modifiers_for_hub = state.reputation_modifiers_map.get(npc_id)

            # TODO (Фаза 2 / Эпоха 7): Интеграция ExpectationStore (Active Inference).
            # Здесь должен вызываться PEModifierResolver().resolve(expectation)
            # для добавления drive_modifiers на основе ожиданий NPC (награда/угроза).
            # Ожидания (EMA) хранятся в ExpectationStore (SQLite, Single Writer).

            # TODO (Фаза 2 / Эпоха 7): Интеграция PerceptionEngine (Социальный статус).
            # Здесь должен вызываться assess_status(state.player_markers) и
            # get_social_permissions() для формирования модификаторов для DecisionHub.
            # Например: низкий статус игрока → буст ATTACK/IGNORE, высокий → буст OBEY/TRADE.

            _drive_modifiers_for_hub = None
            _drives = getattr(state_l2, "temporary_drives", [])
            if _drives:
                _drive_mods = compute_drive_modifiers(_drives)
                if _drive_mods:
                    _drive_modifiers_for_hub = _drive_mods

            from app.services.npc.belief_modifier_resolver import BeliefModifierResolver

            # Сбор belief-модификаторов в изолированный слой (R7 + R8).
            # R7 (событийный) и R8 (кристаллизованный) описывают частично одно и то же
            # явление (страх/угроза от источника). Простое сложение даёт нелинейное
            # усиление — доминирующий сигнал должен поглощать слабый, а не удваивать его.
            _belief_layer_mods: Dict[str, float] = {}

            _belief_mods = BeliefModifierResolver().resolve(state_l2.beliefs)
            if _belief_mods:
                for _bk, _bv in _belief_mods.items():
                    _belief_layer_mods[_bk] = _bv

            # TZ-10: Чтение preloaded crystallized beliefs из TickState
            _crystallized_beliefs = state.crystallized_beliefs_map.get(npc_id, [])
            if _crystallized_beliefs:
                from app.services.npc.crystallized_belief_modifier_resolver import (
                    CrystallizedBeliefModifierResolver,
                )

                _crystallized_mods = CrystallizedBeliefModifierResolver().resolve(
                    _crystallized_beliefs
                )
                if _crystallized_mods:
                    for _ck, _cv in _crystallized_mods.items():
                        _existing = _belief_layer_mods.get(_ck, 0.0)
                        # Dominant-take-all: берём значение с большей абсолютной величиной.
                        # Это предотвращает двойной подсчёт страха/угрозы от одного источника,
                        # когда R7 (событийный DANGER) и R8 (кристаллизованный fear) активны одновременно.
                        if abs(_cv) > abs(_existing):
                            _belief_layer_mods[_ck] = _cv

            # Применяем объединённые belief-модификаторы к base drives (если есть).
            if _belief_layer_mods:
                if _drive_modifiers_for_hub:
                    for _bk, _bv in _belief_layer_mods.items():
                        _drive_modifiers_for_hub[_bk] = round(
                            _drive_modifiers_for_hub.get(_bk, 0.0) + _bv, 4
                        )
                else:
                    _drive_modifiers_for_hub = _belief_layer_mods

            from app.services.npc.topic_extractor import extract_topic

            # S129: Bridge 7 — Если Фаза 4 уже сформировала тему ответа, используем её.
            _topic = state.npc_topics.get(npc_id)
            _response_target = state.response_targets.get(npc_id)

            if not _topic:
                _topic = extract_topic(
                    event_type=_event_for_interp.event_type.value
                    if hasattr(_event_for_interp.event_type, "value")
                    else str(_event_for_interp.event_type),
                    scene_facts=_event_for_interp.scene_facts,
                    raw_input=state.raw_input,
                )

            _dir = getattr(
                getattr(state_l2, "perceptual_kernel", None), "recent_directive", None
            ) or (
                isinstance(_npc_dict_for_write, dict)
                and _npc_dict_for_write.get("perceptual_kernel", {}).get(
                    "recent_directive"
                )
            )
            if _dir:
                _topic = "разговор" if _dir.get("is_obedience") else "угроза"

            from app.services.cfrm.pressure_translator import (
                translate_kernel_to_context,
            )

            _body = getattr(state_l2, "body_state", None)
            _kernel = getattr(state_l2, "perceptual_kernel", None)
            _social_input_ema = getattr(state_l2, "social_input_ema", 0.0)
            _psyche = getattr(state_l2, "psyche", {})
            _greg = (
                _psyche.get("gregariousness", 0.5) if isinstance(_psyche, dict) else 0.5
            )
            # ADR-O-208: L3-P2. DecisionContext использует корректную сигнатуру pressure_translator.
            _decision_ctx = (
                translate_kernel_to_context(
                    _kernel,
                    body_state=_body,
                    social_input_ema=_social_input_ema,
                    gregariousness=_greg,
                )
                if _kernel
                else None
            )

            _effective_drives = state.effective_drives_map.get(npc_id)
            if _effective_drives is None:
                continue

            # V8-PSY-FIX: Если NPC должен спать, подавляем проактивные интенты и FLEE,
            # чтобы он не повышал стресс и мог уснуть (GAP9 контракт).
            # SLEEP_FIX_V3 #1: Проверяем _scheduled_activity (из schedule + game_time),
            # а не routine["current"]. LifeEngine делает early return при active
            # traversal, и routine["current"] не обновляется — но NPC всё равно
            # ДОЛЖЕН спать по расписанию. Используем тот же алгоритм, что и
            # LifeEngine (хелперы _parse_game_time, _time_to_minutes, _in_time_range).
            from app.services.npc.life_engine import (
                _parse_game_time,
                _time_to_minutes,
                _in_time_range,
            )
            _game_time_str = _parse_game_time(state.scene_state)
            _game_minutes = _time_to_minutes(_game_time_str)
            _schedule = _npc_dict_for_write.get("routine", {}).get("schedule", {})
            _scheduled_activity = next(
                (act for _range, act in _schedule.items()
                 if _in_time_range(_range, _game_minutes)),
                "",
            )
            _should_sleep = (
                _scheduled_activity in ("sleeping", "resting", "спит")
                or _current_activity in ("sleeping", "resting", "спит")
            )
            if _should_sleep:
                from app.services.npc.decision_hub import PROACTIVE_INTENTS
                for _p_intent in PROACTIVE_INTENTS:
                    _p_key = getattr(_p_intent, "value", _p_intent)
                    _all_modifiers[_p_key] = _all_modifiers.get(_p_key, 0.0) - 10.0
                _all_modifiers["flee"] = _all_modifiers.get("flee", 0.0) - 10.0


            # KERNEL-ISOLATION: DecisionHub получает deterministic RNG через единую фабрику.
            _rng = KernelRNG(tick=state.tick_id, npc_id=npc_id)
            _all_npc_ids = [
                n.get("npc_id") for n in state.all_npcs_raw if n.get("npc_id")
            ]
            decision = DecisionHub(rng=_rng).compute(
                state=state_l2,
                personality=profile_l0,
                effective_drives=_effective_drives,
                event=_event_for_interp,
                identity=_identity,
                eco_modifiers=_all_modifiers or None,
                social_modifiers=_social_mods or None,
                reputation_modifiers=_rep_modifiers_for_hub,
                drive_modifiers=_drive_modifiers_for_hub or None,
                reflex_constraints=_reflex_constraints,
                topic=_topic,
                decision_ctx=_decision_ctx,
                spatial_query=state.spatial_query,
                all_npc_ids=_all_npc_ids,
                pending_response_target=_response_target, # S129: Bridge 7
                relationship_store=state.relationship_store, # S135: SSOT
                campaign_id=state.campaign_id, # S135: SSOT
            )
            # SHI-FIX: логируем решение для CDS в строгом формате (pattern_registry.py:22).
            # Без этого SHI=0% (симуляция работает, но невидима).
            _evt_type = getattr(state.hub_event, "event_type", "unknown")
            logger.warning(
                f"[DECISION_HUB] {npc_id}: intent=Intent.{decision.intent.value} score={decision.score:.3f} event={_evt_type}"
            )

            # V8-SOC-5 FIX: Накопление idle_pressure
            _key = (state.campaign_id, npc_id)
            _current_pressure = state.idle_pressure_map.get(_key, 0.0)
            _intent_val = decision.intent.value if decision.intent else "none"
            if decision.intent and _intent_val != "idle":
                _pressure_delta = decision.score * IDLE_PRESSURE_ACCUM_RATE
            else:
                _pressure_delta = -_current_pressure * IDLE_PRESSURE_DECAY_RATE
            _new_pressure = max(0.0, min(1.0, _current_pressure + _pressure_delta))
            _idle_pressure_updates[_key] = _new_pressure

            _is_move_command = False
            if state.hub_event:
                _payload = getattr(state.hub_event, "payload", {})
                if (
                    isinstance(_payload, dict)
                    and _payload.get("semantic_action") == "MOVE"
                ):
                    _target_ref = _payload.get("target_reference", "").lower()
                    npc_name = _npc_dict_for_write.get("name", "").lower()
                    npc_id_lower = npc_id.lower()
                    _name_words = [w for w in npc_name.split() if len(w) >= 3]
                    if _target_ref in ("player", ""):
                        _is_move_command = True
                    elif (
                        _target_ref in npc_name
                        or _target_ref in npc_id_lower
                        or any(
                            _target_ref in w or w in _target_ref for w in _name_words
                        )
                    ):
                        _is_move_command = True

            if _is_move_command and decision.intent.value != "approach":
                import dataclasses

                from app.models.npc_state import Intent

                new_result = dataclasses.replace(
                    decision.decision, intent=Intent.APPROACH, intent_target="player"
                )
                decision = dataclasses.replace(decision, decision=new_result)

            if decision.communication is not None:
                communication_intents.append(decision.communication)

            _intent_value = decision.intent.value if decision.intent else ""

            if _intent_value not in {"approach", "flee", "seek_ally", "offer_job", "request_service", "call_for_help", "spread_rumor", "block_path", "ambush", "talk", "change_role"}:
                if _is_move_command:
                    _intent_value = "approach"
                    decision.decision.intent_target = "player"

            _MOVE_INTENTS = {"approach", "flee", "seek_ally", "offer_job", "request_service", "call_for_help", "spread_rumor", "block_path", "ambush", "change_role"} # V8-SOC-8 FIX: убран "talk"
            # S-143 FIX: Sleep non-interruptible. Если NPC спит, блокируем реактивные движения.
            _current_routine = _npc_dict_for_write.get("routine", {})
            
            if _intent_value == "attack":
                from app.domain.communication import CommunicationIntent, ExposureLevel

                _emotion_raw = getattr(state_l2, "emotion", "angry")
                _attack_emotion = getattr(_emotion_raw, "value", _emotion_raw)
                _attack_intent = CommunicationIntent(
                    speaker=npc_id,
                    audience=decision.intent_target or "player",
                    topic="attack",
                    intent_type="attack",
                    emotional_state=_attack_emotion,
                    exposure_level=ExposureLevel.from_semantic("shout"),
                    semantic_action="ATTACK",
                    target_id=decision.intent_target or "player",
                )
                communication_intents.append(_attack_intent)
            else:
                # BUG-CORE-005 FIX: Добавлена else-ветвь для всех movement-capable intents (approach, flee, и т.д.).
                # Ранее не-спящие NPC с intent=approach/flee/seek_ally просто дропали movement_intent.
                # SLEEP_FIX_V3 #2: reactive SLEEP_GUARD проверяет _should_sleep
                # (вычислен выше в V3-1), а не routine["current"]. NPC в transit
                # тоже защищён от реактивных движений.
                if _intent_value in _MOVE_INTENTS and _should_sleep:
                    logger.info(f"[SLEEP_GUARD] npc={npc_id} scheduled=sleeping, blocking reactive movement={_intent_value}")
                    _intent_value = "idle"
                    import dataclasses
                    from app.models.npc_state import Intent
                    decision = dataclasses.replace(decision, decision=dataclasses.replace(decision.decision, intent=Intent.IDLE))

                if _intent_value in _MOVE_INTENTS:
                    _movement = _resolve_reactive_movement(
                        npc_id=npc_id,
                        intent=_intent_value,
                        intent_target=decision.intent_target or "player",
                        scene_state=copy.deepcopy(state.scene_state),
                        location_id=state.scene_state.get("location_id", ""),
                        spatial_service=state.spatial_service,
                        spatial_query=state.spatial_query,
                        drf_ctx=_npc_drf_ctx,
                    )
                    if not _movement:
                        if state.spatial_service:
                            try:
                                _target_node = _resolve_proactive_target(
                                    intent_value=_intent_value,
                                    npc_id=npc_id,
                                    intent_target=decision.intent_target,
                                    scene_state=copy.deepcopy(state.scene_state),
                                    spatial_service=state.spatial_service,
                                    location_id=state.scene_state.get("location_id", ""),
                                )
                                logger.debug(f"[PROACTIVE_MOVE] npc={npc_id} intent={_intent_value} target_node={_target_node}")
                                if _target_node:
                                    from app.domain.movement import MacroMovementGoal
                                    _movement = MacroMovementGoal(
                                        actor_id=npc_id,
                                        target_node_id=_target_node,
                                        reason=f"proactive_{_intent_value}",
                                        body_capabilities=state_l2.body_capabilities
                                    )
                            except Exception as _e:
                                logger.exception(f"[PROACTIVE_MOVE_ERROR] npc={npc_id} intent={_intent_value}: {_e}")
                        else:
                            logger.warning(f"[PROACTIVE_MOVE_SKIP] npc={npc_id} intent={_intent_value} reason=spatial_query is None")
                    if _movement:
                        movement_intents.append(_movement)

            # S1 FIX (Pure Reducer): Сборка npc_deltas напрямую из DecisionResult.
            # StateApplicator удалён из ядра. Мутация relationship_store и l1_chronicle
            # будет выполнена TickOrchestrator'ом при применении TickMutation.
            
            # TODO (Фаза 2 / Эпоха 7): Интеграция ResolutionEngine.
            # Здесь будет вызов ResolutionEngine().resolve(state, profile, expected_success)
            # и передача ResolutionOutcome в формирование TickMutation (вместо applicator.apply).
            if decision.deltas:
                npc_deltas.extend(decision.deltas)
                # Генерируем L1-событие для этого NPC, так как у него есть дельта (Causal Provenance)
                from app.domain.identity_events import TraitDriftEvent
                _l1_events.append(TraitDriftEvent(
                    tick_id=state.tick_id,
                    target_id=npc_id,
                    source_id="world_tick",
                    effect_value=0.0,
                    observation_weight=0.1
                ))

            # Сборка memory_events для отложенного применения
            try:
                _mem_evt = create_memory_event(
                    memory_manager=None, # NpcTickPipeline — pure reducer, MemoryManager применяется в Фазе 3
                    state_l2=state_l2, # Используем pre-decision state
                    decision=decision,
                    npc_id=npc_id,
                    hub_event=_event_for_interp,
                    player_target_id=state.player_target_id or "player",
                    player_text=state.raw_input,
                    scene_state=copy.deepcopy(state.scene_state),
                    campaign_id=state.campaign_id,
                )
                if _mem_evt:
                    memory_events.append(_mem_evt)
            except Exception as e:
                logger.warning(f"[MEMORY_EVENT] create_memory_event failed for {npc_id}: {e}")
        
        return TickMutation(
            npc_deltas=npc_deltas,
            communication_intents=communication_intents,
            movement_intents=movement_intents,
            l1_drift_events=_l1_events,
            memory_events=memory_events,
            idle_pressure_updates=_idle_pressure_updates, # V8-SOC-5 FIX
        )


# ── Константы ──────────────────────────────────────────────────────────────────

BASE_IMPORTANCE: dict[str, float] = {
    "TALK": 0.6,
    "TRADE": 0.7,
    "HELP": 0.8,
    "ATTACK": 0.9,
    "FLEE": 0.8,
    "GIVE": 0.5,
    "ASK": 0.5,
    "THREATEN": 0.85,
    "OBSERVE": 0.3,
}


# ── Session reset ─────────────────────────────────────────────────────────────
# ── ConditionEngine ───────────────────────────────────────────────────────────

# ── Temporary drives aging ───────────────────────────────────────────────────

# ── Reaction resolver ────────────────────────────────────────────────────────

# ── Memory event creation ───────────────────────────────────────────────────


def apply_perception_memory(
    memory_manager: Any,
    state_l2: Any,
    hub_event: Any,
    npc_id: str,
    player_target_id: str,
    player_text: str,
    campaign_id: str,
    spatial_query: Optional[Any] = None,
) -> Any:
    """ФАЗА 3 (§3.1): Запись восприятия события в память NPC ДО DecisionHub.

    DecisionHub должен видеть СВЕЖИЙ state — NPC помнит что произошло (Устав §3.1, §7.7).
    Важно: не использует decision — он ещё не принят.
    Возвращает обновлённый state_l2.
    """
    from app.domain.events import EventDTO

    _evt_type = hub_event.event_type if hub_event else ""
    _evt_actor = hub_event.actor_id or "player" if hub_event else "player"
    _has_target = bool(player_target_id)

    # Базовая важность по типу события — без decision (ещё не принято)
    _importance = 0.4
    if _evt_type in ("npc_interacts_npc", "npc_proximity_close"):
        _importance = 0.6
    elif _evt_type == "player_interacts" and _has_target:
        _importance = 0.5

    _summary = (
        f"{_evt_actor} → {player_target_id}: {player_text[:60]}"
        if _has_target
        else f"{_evt_actor}: {player_text[:60]}"
    )
    _emotion = (
        getattr(state_l2.emotion, "value", "neutral") if state_l2.emotion else "neutral"
    )

    _evt_dto = EventDTO.create(
        event_type=_evt_type,
        source=_evt_actor,
        payload={
            "npc_id": npc_id,
            "target_id": player_target_id,
            "action_type": "perception",
            "emotion_tag": _emotion,
            "summary": _summary,
            "importance": _importance,
            "npc_stress": getattr(state_l2, "stress", 0.0),
        },
        persistence_level="working",
    )
    # ADR-TZ09-1: NpcTickPipeline.run() — pure reducer. I/O запрещено.
    # Возвращаем EventDTO для отложенного применения в pipeline_runner.py (Фаза 3).
    return _evt_dto


def create_memory_event(
    memory_manager: Any,
    state_l2: Any,
    decision: Any,
    npc_id: str,
    hub_event: Any,
    player_target_id: str,
    player_text: str,
    scene_state: Dict[str, Any],
    campaign_id: str,
    spatial_query: Optional[Any] = None,
) -> Any:
    """ФАЗА 1: NPC становятся живыми — запоминаем взаимодействия.

    Вычисляет importance, создаёт EventDTO, применяет через MemoryManager.
    Возвращает обновлённый state_l2 (память может его мутировать).
    """
    from app.domain.events import EventDTO

    _evt_type = hub_event.event_type if hub_event else ""
    _evt_actor = hub_event.actor_id or "player" if hub_event else "player"
    _evt_target = player_target_id or ""
    _intent_val = getattr(decision.intent, "value", "") if decision.intent else ""
    _intent_upper = _intent_val.upper() if _intent_val else ""
    _has_target = bool(_evt_target)

    _importance = None
    _summary = ""

    # ADR-013: Деградационный шлюз v2 -> v1 — вычисляем ДО ветвления
    # Иначе _legacy_d не определена в третьем elif → UnboundLocalError → память мертва
    _legacy_d = LegacyStateDeltaAdapter.collapse(decision.deltas)

    if _evt_type in ("npc_interacts_npc", "npc_proximity_close"):
        _summary = f"{_evt_actor} → {_evt_target}: {_intent_val}"
        _importance = 0.6
    elif _evt_type == "player_interacts" and _has_target:
        _summary = f"{_evt_actor} → {_evt_target}: {player_text[:60]}"
        _base = BASE_IMPORTANCE.get(_intent_upper, 0.4)
        _emotion_boost = min(abs(_legacy_d.emotion_delta) / 5.0, 1.0) * 0.3
        _importance = min(_base + _emotion_boost, 1.0)
    elif _has_target and _intent_upper in (
        "TALK",
        "TRADE",
        "HELP",
        "ATTACK",
        "FLEE",
        "GIVE",
        "ASK",
        "THREATEN",
    ):
        _summary = f"{_evt_actor} → {_evt_target}: {player_text[:60]}"
        _base = BASE_IMPORTANCE.get(_intent_upper, 0.0)
        _emotion_boost = min(abs(_legacy_d.emotion_delta) / 5.0, 1.0) * 0.3
        _importance = min(_base + _emotion_boost, 1.0)

    if _importance is not None:
        _emotion = (
            getattr(state_l2.emotion, "value", "neutral")
            if state_l2.emotion
            else "neutral"
        )
        _evt_dto = EventDTO.create(
            event_type=_evt_type,
            source=_evt_actor,
            payload={
                "npc_id": npc_id,
                "target_id": _evt_target,
                "action_type": _intent_upper,
                "emotion_tag": _emotion,
                "summary": _summary,
                "importance": _importance,
                "npc_stress": getattr(state_l2, "stress", 0.0),
                "scene_state": scene_state,
            },
            persistence_level="session",
        )
        # S186 FIX: Pure Reducer. MemoryManager.apply() вызывается в pipeline_runner.py (Фаза 3).
        # Здесь только создаём EventDTO для отложенного применения.
        return _evt_dto
    return None


# ── Verbalization context builder ───────────────────────────────────────────


# TODO: EXPRESSION LAYER (ADR-TZ05-1). Функция временно размещена здесь, но не является частью симуляционного ядра.
# Подлежит переносу в DM/LLM verbalization слой и переписыванию на observed_state вместо state_for_llm.
# В execution path (run_npc_pipeline) вызов удалён.
def build_verbalization_context(
    memory_manager: Any,
    profile_l0: Any,
    state_for_llm: Any,
    intent_value: str,
    intent_target: Optional[str],
    hub_event: Any,
    raw_input: str,
    campaign_id: str = "",
    topic: str = "",
) -> Any:
    """Упаковка данных NPC в VerbalizationContext для LLM-промпта."""
    from app.services.verbalization.state_interpreter import StateInterpreter
    from app.services.verbalization.verbalization_context import (
        VerbalizationContext,
        generate_emotional_nuance,
    )

    # ADR-139: drives из runtime canonical (state), НЕ из frozen profile.
    # profile_l0.drives_base = seed (Layer 1). state.drives_runtime = current (Layer 2).
    # DecisionHub должен видеть ТЕКУЩИЕ драйвы (с учётом мутаций), не seed.
    # ИСПРАВЛЕНО: аргумент называется state_for_llm, не state. NameError на `state`.
    # ADR-O-208: L3-P2. VerbalizationContext использует эфемерную проекцию (L3).
    _ed = state_for_llm.effective_drives_map.get(profile_l0.id) if hasattr(state_for_llm, 'effective_drives_map') else None
    _drives_raw = _ed.values if _ed else profile_l0.drives_base
    if isinstance(_drives_raw, dict) and _drives_raw:
        _dominant_drive = max(_drives_raw.items(), key=lambda x: x[1])[0]
    else:
        _dominant_drive = "desire"

    _scene_hint = raw_input[:500].strip() if raw_input else ""
    _interpreter = StateInterpreter()
    _npc_desc = _interpreter.interpret(
        state_for_llm
    )  # GAP5 FIX: Витализм — боль и шок перекрывают HP

    # Этап 3.5-3.6 + 5: Recall с поддержкой секретов
    _pressure = (
        memory_manager.get_dialogue_pressure(campaign_id, profile_l0.id)
        if campaign_id
        else 0
    )
    _npc_stress = getattr(state_for_llm, "stress", 0.0)
    _recalled = memory_manager.recall(
        state_for_llm.narrative_cache,
        hidden_from_id="player",
        pressure=_pressure,
        npc_stress=_npc_stress,
    )
    _suppressed = memory_manager.get_suppressed_secrets(
        state_for_llm.narrative_cache,
    )

    # Инвариант 2: Намерение → Физика. LLM знает о движении только через этот флаг.
    _movement_intents = {"APPROACH", "FLEE", "RETREAT", "FOLLOW", "PATROL"}
    _is_moving = (
        intent_value in _movement_intents
        and _interpreter.derive_can_move(
            state_for_llm.posture, state_for_llm.conditions, state_for_llm.effective_hp
        )
    )

    return VerbalizationContext(
        npc_id=profile_l0.id,
        npc_name=profile_l0.name,
        tier=profile_l0.tier,
        emotion=state_for_llm.emotion.value,
        will_state=state_for_llm.will_state.value,
        physical_state=_npc_desc.physical_state,  # GAP5 FIX: Витализм
        intent=intent_value,
        intent_target=intent_target,
        topic=topic,
        scene_hint=_scene_hint,
        emotional_nuance=generate_emotional_nuance(state_for_llm),
        speech_style=_dominant_drive,
        voice_profile=profile_l0.voice_profile,
        backstory=profile_l0.backstory,
        author_notes=profile_l0.author_notes,
        can_speak=_interpreter.derive_can_speak(
            state_for_llm.posture, state_for_llm.conditions
        ),
        can_move=_interpreter.derive_can_move(
            state_for_llm.posture, state_for_llm.conditions, state_for_llm.effective_hp
        ),
        # Инвариант 2: LLM не может галлюцинировать движение без TraversalState
        is_moving=_is_moving,
        movement_intent=decision.intent.value if _is_moving else "",
        gender=profile_l0.gender,
        narrative_hints=state_for_llm.narrative_cache,
        recalled_facts=tuple(_recalled),
        suppressed_secrets=tuple(_suppressed),
    )


# ─────────────────────────────────────────────────────────────────────────
# Мост: DecisionResult → MovementIntent (реактивное движение NPC)
# ─────────────────────────────────────────────────────────────────────────


def _resolve_reactive_movement(
    npc_id: str,
    intent: str,
    intent_target: Optional[str],
    scene_state: Dict[str, Any],
    location_id: str,
    spatial_service: Optional[Any] = None,
    spatial_query: Optional[Any] = None,  # ADR-048: Authoritative Spatial Spine
    drf_ctx: Optional[
        Any
    ] = None,  # DRF: scoped causal execution context (DRFExecutionContext)
) -> Optional["MovementIntent"]:
    """Конвертирует пространственный intent в MovementIntent.

    DecisionHub решает ЧТО (approach), эта функция решает КУДА (целевой узел графа).
    MovementEngine потом резолвит узел в {x, y}.

    Поддерживаемые интенты:
    - approach: идёт к intent_target (игрок/NPC) → ближайший к цели узел графа
    - flee: уходит от intent_target → find_furthest_node от позиции угрозы

    ADR-102: Единственный источник графа — SpatialService. load_graph удалён.
    ADR-048: Если передан spatial_query, чтение позиций идёт ТОЛЬКО через него.
    """
    from app.domain.movement import (
        PRIORITY_REACTIVE,
        LocalSteeringGoal,
        MacroMovementGoal,
    )

    # ADR-048: Spatial Authority. Единственный источник пространственной истины.
    # Чтение npc_positions из scene_state ЗАПРЕЩЕНО для decisions (ADR-048 Этап 1).
    def _pos(eid: str) -> Dict[str, Any]:
        if spatial_query:
            return spatial_query.get_entity_position(eid) or {}
        return scene_state.get("npc_positions", {}).get(eid, {})

    # Текущий узел NPC
    npc_entry = _pos(npc_id)
    current_node = npc_entry.get("position", "")

    # FIX: Если position пустое (data integrity bug), восстанавливаем из local_position через SpatialService.
    if not current_node and spatial_service:
        _lp = npc_entry.get("local_position", {})
        _x = _lp.get("x")
        _y = _lp.get("y")
        if _x is not None and _y is not None:
            _nearest = spatial_service.get_nearest(
                zone_id=location_id, origin_xy=(_x, _y)
            )
            if _nearest:
                current_node = getattr(_nearest, "node_id", str(_nearest))
                logger.debug(
                    f"[PIPELINE][NAV] npc={npc_id} recovered current_node={current_node} from xy=({_x},{_y})"
                )

    # ADR-045: Макро-зона цели берется НАПРЯМУЮ из position, без поиска по координатам.
    target_node_id: Optional[str] = None
    _target_id = intent_target or "player"

    if intent == "approach":
        # ADR-048: Игрок внедрен как npc_id="player" (ADR-031), его позиция находится в npc_positions.
        # player_spatial удален. denormalize_id удален.
        target_entry = _pos(_target_id)
        # v2.2 Spatial Ontology: Для approach микро-позиция (local_position) приоритетнее макро-узла (position).
        # Макро-узел игрока может быть "entrance", но его local_position указывает точное место.
        lp = target_entry.get("local_position", {})
        target_x = lp.get("x")
        target_y = lp.get("y")
        target_node_id = None
        logger.debug(
            f"[PIPELINE][NAV] npc={npc_id} target_id={_target_id} player_xy=({target_x},{target_y}) position={target_entry.get('position')}"
        )

        # Путь 1: Точное позиционирование через local_position (предпочтительно)
        if target_x is not None and target_y is not None and spatial_service:
            nearest_ref = spatial_service.get_nearest(
                zone_id=location_id, origin_xy=(target_x, target_y)
            )
            if nearest_ref:
                target_node_id = getattr(nearest_ref, "node_id", str(nearest_ref))

        # Путь 2: Fallback на макро-узел (если нет spatial_service или координат)
        if not target_node_id:
            target_node_id = target_entry.get("position")

        logger.warning(
            f"[APPROACH_NAV] npc={npc_id} target={_target_id} resolved_node={target_node_id} has_xy={target_x is not None} xy=({target_x},{target_y}) fallback={target_entry.get('position')}"
        )

        if not target_node_id:
            logger.warning(
                f"[APPROACH_NAV] target={_target_id} not found in npc_positions! Movement blocked."
            )
            return None

    elif intent == "flee":
        # ADR-048: Единый пространственный авторитет. Игрок внедрен как npc_id="player".
        # player_spatial и denormalize_id удалены.
        target_entry = _pos(_target_id)
        if target_entry:
            lp = target_entry.get("local_position", {})
            threat_x = lp.get("x")
            threat_y = lp.get("y")
        else:
            logger.warning(
                f"[FLEE_NAV] threat={_target_id} not found in npc_positions! Flee blocked."
            )
            return None

        if threat_x is not None and threat_y is not None:
            from app.domain.spatial_target import SpatialTargetIntent, SpatialTargetType

            # ADR-O-330: Формируем семантическое намерение убежать (SA-1).
            # Поиск физической цели (макро-узел или микро-позиция) делегирован SpatialTargetResolver.
            flee_intent = SpatialTargetIntent(
                target_type=SpatialTargetType.REGION,
                target_id=None,
                reason="flee",
                confidence=0.9,
                context_ref=_target_id  # ID угрозы
            )
            return MacroMovementGoal(
                actor_id=npc_id,
                target_intent=flee_intent,
                from_node_id=current_node,
                location_id=location_id,
                reason="reactive:flee",
                priority=PRIORITY_REACTIVE,
            )
        return None

    # ADR-045: Проверка на нахождение в одной макро-зоне (нормализация префиксов)
    # Строковое несовпадение "main_hall" и "tavern:main_hall" убивало микро-движение
    current_base = current_node.split(":")[-1] if current_node else ""
    target_base = target_node_id.split(":")[-1] if target_node_id else ""

    if target_base and current_base == target_base:
        # Микро-сближение (LOD0). Цель и NPC в одной зоне — идем к локальным координатам.
        target_entry = _pos(_target_id)
        lp = target_entry.get("local_position", {})
        target_x = lp.get("x")
        target_y = lp.get("y")

        if intent == "approach" and target_x is not None and target_y is not None:
            logger.debug(
                f"[TRACE][INTENT_CREATED] npc={npc_id} intent=micro_snap:{intent} target_node={current_node} target_xy=({target_x},{target_y})"
            )
            # Возвращаем канонический current_node для трассировки, сравнение было по базе
            return LocalSteeringGoal(
                actor_id=npc_id,
                local_target_xy=(target_x, target_y),
                reason=f"micro_snap:{intent}",
                priority=PRIORITY_REACTIVE,
            )

        if intent == "flee":
            # Для побега из той же зоны ищем другой узел
            logger.info(
                f"[PIPELINE][REACTIVE_MOVEMENT][FLEE_MICRO] npc={npc_id} пытается бежать из своей зоны"
            )
        else:
            logger.warning(
                f"[PIPELINE][REACTIVE_MOVEMENT][SKIP] npc={npc_id} already at target macro-zone {current_base}, no local coords"
            )
            return None

    if not target_node_id:
        # Тихий возврат для не-реактивных интентов (seek_ally, offer_job и др.),
        # чтобы они прошли через _resolve_proactive_target без ложного спама.
        return None

    logger.debug(
        f"[PIPELINE][REACTIVE_MOVEMENT][CREATE] npc={npc_id} target_node={target_node_id} from_node={current_node}"
    )
    logger.debug(
        f"[TRACE][INTENT_CREATED] npc={npc_id} intent=reactive:{intent} target_node={target_node_id}"
    )

    # DRF: Испускаем претензию через scoped контекст (авто-привязка npc_id, tick_id)
    _claim = {
        "source": "reactive_cognition",
        "pressure_type": "SURVIVAL" if intent == "flee" else "SOCIAL",
        "vector": intent,
        "energy": 0.9 if intent == "flee" else 0.6,
        "target_node": target_node_id,
        "half_life": 1.0,
    }
    if drf_ctx is not None:
        drf_ctx.emit(_claim)
    logger.debug(
        f"[DRF_EMIT] source=reactive npc={npc_id} tick={drf_ctx.tick_id if drf_ctx else '?'} vector={intent} ctx_bound={drf_ctx is not None}"
    )
    # Передаём претензию вверх через интент (временный хак до внедрения ctx)
    _goal = MacroMovementGoal(
        actor_id=npc_id,
        target_node_id=target_node_id,
        from_node_id=current_node,
        location_id=location_id,
        reason=f"reactive:{intent}",
        priority=PRIORITY_REACTIVE,
        target_local_xy=(target_x, target_y)
        if intent == "approach" and target_x is not None and target_y is not None
        else None,
    )
    # Используем легаси-поле для прокидывания тени, чтобы не ломать DTO
    if not hasattr(_goal, "causal_claims"):
        _goal.causal_claims = []
    _goal.causal_claims.append(_claim)

    return _goal
