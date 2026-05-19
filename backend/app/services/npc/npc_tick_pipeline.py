# path: C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\npc\npc_tick_pipeline.py
"""
Чистые функции NPC пайплайна (Фазы 3-6).

Без self, без побочных эффектов кроме логирования.
Мутируют только переданные state_l2 / npc_dict — не трогают внешние сервисы.


Назначение: Чистые функции NPC пайплайна — без self, без побочных эффектов кроме логгирования
Зависимости: logging, app.services.resolution, app.services.reaction, app.services.npc, app.services.verbalization, app.models
Основные сущности: BASE_IMPORTANCE, apply_perception_memory, create_memory_event, build_verbalization_context, run_npc_pipeline
"""

import logging
from typing import Any, Optional

from app.services.npc.legacy_delta_adapter import LegacyStateDeltaAdapter
from app.services.npc.domain_phases import (
    HANDS_OCCUPIED_ACTIVITIES,
    PHYSICAL_EVENTS,
    resolve_physical_attack,
    reset_session_state,
    tick_conditions,
    age_temporary_drives,
    compute_economy,
    resolve_reactions,
)

logger = logging.getLogger(__name__)

# ── Константы ──────────────────────────────────────────────────────────────────

BASE_IMPORTANCE: dict[str, float] = {
    "TALK": 0.6, "TRADE": 0.7, "HELP": 0.8,
    "ATTACK": 0.9, "FLEE": 0.8, "GIVE": 0.5,
    "ASK": 0.5, "THREATEN": 0.85, "OBSERVE": 0.3,
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
    _emotion = getattr(state_l2.emotion, "value", "neutral") if state_l2.emotion else "neutral"

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
    state_l2 = memory_manager.apply(
        event=_evt_dto,
        npc_state=state_l2,
        campaign_id=campaign_id,
        spatial_query=spatial_query,
    )
    return state_l2


def create_memory_event(
    memory_manager: Any,
    state_l2: Any,
    decision: Any,
    npc_id: str,
    hub_event: Any,
    player_target_id: str,
    player_text: str,
    scene_state: dict,
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

    if _evt_type in ("npc_interacts_npc", "npc_proximity_close"):
        _summary = f"{_evt_actor} → {_evt_target}: {_intent_val}"
        _importance = 0.6
    elif _evt_type == "player_interacts" and _has_target:
        _summary = f"{_evt_actor} → {_evt_target}: {player_text[:60]}"
        _base = BASE_IMPORTANCE.get(_intent_upper, 0.4)
        # ADR-013: Деградационный шлюз v2 -> v1
        _legacy_d = LegacyStateDeltaAdapter.collapse(decision.deltas)
        _emotion_boost = min(abs(_legacy_d.emotion_delta) / 5.0, 1.0) * 0.3
        _importance = min(_base + _emotion_boost, 1.0)
    elif _has_target and _intent_upper in (
        "TALK", "TRADE", "HELP", "ATTACK", "FLEE", "GIVE", "ASK", "THREATEN",
    ):
        _summary = f"{_evt_actor} → {_evt_target}: {player_text[:60]}"
        _base = BASE_IMPORTANCE.get(_intent_upper, 0.0)
        _emotion_boost = min(abs(_legacy_d.emotion_delta) / 5.0, 1.0) * 0.3
        _importance = min(_base + _emotion_boost, 1.0)

    if _importance is not None:
        _emotion = getattr(state_l2.emotion, "value", "neutral") if state_l2.emotion else "neutral"
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
        state_l2 = memory_manager.apply(
            event=_evt_dto,
            npc_state=state_l2,
            campaign_id=campaign_id,
            spatial_query=spatial_query,
        )
    return state_l2


# ── Verbalization context builder ───────────────────────────────────────────

def build_verbalization_context(
    memory_manager: Any,
    profile_l0: Any,
    state_for_llm: Any,
    decision: Any,
    hub_event: Any,
    raw_input: str,
    campaign_id: str = "",
    topic: str = "",
) -> Any:
    """Упаковка данных NPC в VerbalizationContext для LLM-промпта."""
    from app.services.verbalization.state_interpreter import StateInterpreter
    from app.services.npc.topic_extractor import extract_topic
    from app.services.verbalization.verbalization_context import (
        VerbalizationContext, generate_emotional_nuance,
    )

    _drives_raw = profile_l0.drives_base
    if isinstance(_drives_raw, dict) and _drives_raw:
        _dominant_drive = max(_drives_raw.items(), key=lambda x: x[1])[0]
    else:
        _dominant_drive = "desire"

    _scene_hint = raw_input[:500].strip() if raw_input else ""
    _interpreter = StateInterpreter()

    # Этап 3.5-3.6 + 5: Recall с поддержкой секретов
    _pressure = memory_manager.get_dialogue_pressure(campaign_id, profile_l0.id) if campaign_id else 0
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

    return VerbalizationContext(
        npc_id=profile_l0.id,
        npc_name=profile_l0.name,
        tier=profile_l0.tier,
        emotion=state_for_llm.emotion.value,
        will_state=state_for_llm.will_state.value,
        intent=decision.intent.value,
        intent_target=decision.intent_target,
        topic=topic,
        scene_hint=_scene_hint,
        emotional_nuance=generate_emotional_nuance(state_for_llm),
        speech_style=_dominant_drive,
        voice_profile=profile_l0.voice_profile,
        backstory=profile_l0.backstory,
        author_notes=profile_l0.author_notes,
        can_speak=_interpreter.derive_can_speak(state_for_llm.posture, state_for_llm.conditions),
        can_move=_interpreter.derive_can_move(state_for_llm.posture, state_for_llm.conditions, state_for_llm.hp),
        gender=profile_l0.gender,
        narrative_hints=state_for_llm.narrative_cache,
        recalled_facts=tuple(_recalled),
        suppressed_secrets=tuple(_suppressed),
    )


# ────────────────────────────────────────────────────────────────────────────
# ОСНОВНОЙ ЦИКЛ NPC (Вариант C: Input/Buffer/Services)
# ────────────────────────────────────────────────────────────────────────────

def run_npc_pipeline(
    inp: "NpcTickInput",
    buf: "NpcTickBuffer",
    svc: "NpcTickServices",
) -> "NpcTickBuffer":
    """Основной цикл NPC: профиль → модификаторы → DecisionHub → StateApplicator → память.

    Читает из inp, мутирует buf, использует svc.
    Legacy-мутации _npc_dict_for_write сохранены для совместимости с commit_tick.
    Оркестратор НЕ должен вызывать если hub_event is None (CharacterFilter заблокировал).
    """
    from app.services.npc.npc_loader import load_profile_from_legacy_json, load_l2_state_from_runtime_dict
    from app.services.npc.decision_hub import DecisionHub
    from app.services.npc.interpretation_engine import InterpretationEngine
    from app.models.npc_state import NPCIdentityL1, NPCState, compute_drive_modifiers
    from app.services.npc.state_applicator import StateApplicator
    from app.services.npc.npc_tick_contracts import _INTENT_TO_ACTIVITY

    hub_event = inp.hub_event

    for npc in inp.nearby_npcs:
        npc_id = npc.get("npc_id")
        if npc_id and inp.line_of_sight.get(npc_id, False):

            # 1. Ищем профиль NPC в уже загруженном списке
            _npc_profile = None
            for _n in inp.all_npcs_raw:
                if _n.get("id") == npc_id or _n.get("npc_id") == npc_id:
                    _npc_profile = _n
                    break
            if not _npc_profile:
                logger.warning(f"[GAME_LOOP] Profile not found for {npc_id}")
                continue
            # Сохраняем ссылку на dict для записи после StateApplicator
            _npc_dict_for_write = _npc_profile

            # 2. Мост: Грязный Dict -> Чистые L0/L2 типы
            profile_l0 = load_profile_from_legacy_json(_npc_profile)
            state_l2 = load_l2_state_from_runtime_dict(_npc_profile)

            # 2b. SQLite — runtime truth (Закон 4.2.1)
            # Если в SQLite есть воспоминания — приоритет над JSON
            _sqlite_cache = svc.memory_manager.load_narrative_from_sqlite(
                inp.campaign_id, npc_id,
            )
            if _sqlite_cache is not None:
                state_l2.narrative_cache = _sqlite_cache

            # Фаза 4-ROLE.2: Aging temporary drives (каждый тик)
            age_temporary_drives(state_l2, _npc_dict_for_write, npc_id)

            # ── ПРИЧИННЫЙ СЛОЙ: Physical Resolution (до DecisionHub) ──
            state_l2, _reflex_constraints = resolve_physical_attack(
                npc_id=npc_id,
                npc_profile=_npc_profile,
                npc_dict_for_write=_npc_dict_for_write,
                state_l2=state_l2,
                action_type=inp.action_type,
                target_id=inp.player_target_id,
                current_tick=inp.current_tick,
                scene_continuity=inp.scene_continuity,
                scene_state=inp.scene_state,
                relationship_store=svc.relationship_store,
            )

            # ── ПРИЧИННЫЙ СЛОЙ: ConditionEngine (всегда, не только PHYSICAL) ──
            state_l2 = tick_conditions(
                state_l2, _npc_dict_for_write,
                inp.current_tick,
                inp.scene_continuity,
            )

            # Сброс динамического состояния при старте новой сессии
            reset_session_state(state_l2, npc_id, inp.is_session_start)

            # 1.5. Обогащаем relationship_cache из MemoryManager (РАЗРЫВ #1 закрыт)
            try:
                mem_weights = svc.memory_manager.get_weights_for_decision(
                    campaign_id=inp.campaign_id,
                    npc_id=npc_id,
                    target_id="player",
                )
                state_l2.relationship_cache.update(mem_weights)
            except Exception as _mem_e:
                logger.error(f"[MEMORY] get_weights failed for {npc_id}: {_mem_e}", exc_info=True)

            # ФАЗА 3 (§3.1): Восприятие → память ДО DecisionHub (Устав §7.7)
            try:
                state_l2 = apply_perception_memory(
                    svc.memory_manager, state_l2, hub_event, npc_id,
                    inp.player_target_id, inp.raw_input, inp.campaign_id,
                    spatial_query=svc.spatial_query,
                )
            except Exception as _perc_mem_err:
                logger.warning(f"[MEMORY] perception apply failed for {npc_id}: {_perc_mem_err}")

            # 1.6. CognitiveDistortion: модификаторы для DecisionHub (ШАГ C.1)
            # Distortion НЕ искажает state — возвращает модификаторы score
            interpretation = InterpretationEngine().compute(
                state=state_l2, event=hub_event, drives_base=profile_l0.drives_base
            )

            # 2. Этап 5: Запуск DecisionHub с L1 чертами + distortion модификаторы
            _identity_traits = svc.memory_manager.get_identity_traits(
                campaign_id=inp.campaign_id,
                npc_id=npc_id,
            )
            _identity = NPCIdentityL1(
                npc_id=npc_id,
                active_traits=_identity_traits,
            )

            # ФАЗА 3.2: социальные модификаторы (ревность, защита союзника)
            _social_mods = {}
            try:
                if svc.social_engine:
                    # ADR-048: Spatial Authority. Единственный путь — через SpatialQueryService.
                    # Чтение player_distances из scene_state ЗАПРЕЩЕНО (ADR-048 Этап 1).
                    _spatial_query = svc.spatial_query
                    if _spatial_query:
                        _player_dists_snap = _spatial_query.player_distances(list(svc.social_engine.all_npc_ids))
                    else:
                        _player_dists_snap = {}
                    _extra_evt_types = [sp.event_type for sp in inp.spatial_events] if inp.spatial_events else None
                    _social_mods = svc.social_engine.compute_social_modifiers(
                        npc_id=npc_id,
                        player_distances=_player_dists_snap,
                        event_type=hub_event.event_type,
                        event_target=inp.player_target_id,
                        extra_event_types=_extra_evt_types,
                    )
            except Exception as e:
                logger.warning(f"[GAME_LOOP] Ошибка decision_hub.compute: {e}")

            # Фаза 2.4-ECO: экономические модификаторы от потребностей
            _eco_profile = svc.economic_profiles.get(npc_id)
            _eco_result = compute_economy(npc_id, _eco_profile, state_l2)
            # Объединяем все модификаторы для DecisionHub
            _all_modifiers = {**interpretation.score_modifiers}
            if _eco_modifiers := _eco_result["modifiers"]:
                for _intent, _mod in _eco_modifiers.items():
                    _all_modifiers[_intent] = _all_modifiers.get(_intent, 0.0) + _mod

            # Фаза 3.5: Reputation modifiers
            _rep_modifiers_for_hub = None
            if svc.reputation_engine:
                _rep_mod = svc.reputation_engine.compute_reputation_modifier(npc_id)
                if _rep_mod:
                    _rep_modifiers_for_hub = _rep_mod

            # Фаза 4-ROLE.2: TemporaryDrive modifiers
            _drive_modifiers_for_hub = None
            _drives = getattr(state_l2, "temporary_drives", [])
            if _drives:
                _drive_mods = compute_drive_modifiers(_drives)
                if _drive_mods:
                    _drive_modifiers_for_hub = _drive_mods

            # Фаза 4 (§3.2): TopicExtractor — ДО DecisionHub
            from app.services.npc.topic_extractor import extract_topic
            _topic = extract_topic(
                event_type=hub_event.event_type.value if hasattr(hub_event.event_type, "value") else str(hub_event.event_type),
                scene_facts=hub_event.scene_facts,
                raw_input=inp.raw_input,
            )
            
            # ADR-057: Topic Injection. Если внимание захвачено директивой, тема = реакция на неё.
            # COGNITIVE OVERLAY: Читаем директиву из raw dict (npc_dict), если state_l2 ещё не обновился
            _dir = getattr(getattr(state_l2, 'perceptual_kernel', None), 'recent_directive', None) \
                or (isinstance(npc_dict, dict) and npc_dict.get("perceptual_kernel", {}).get("recent_directive"))
            
            if _dir:
                _topic = "разговор" if _dir.get("is_obedience") else "угроза"

            # S28: Замыкание каузального контура. Чтение геометрии восприятия
            from app.domain.decision_context import DecisionContext
            _decision_ctx = None
            if hasattr(state_l2, 'perceptual_kernel') and state_l2.perceptual_kernel:
                _decision_ctx = DecisionContext.from_kernel(state_l2.perceptual_kernel)

            decision = DecisionHub().compute(
                state=state_l2,
                personality=profile_l0,
                event=hub_event,
                identity=_identity,
                eco_modifiers=_all_modifiers or None,
                social_modifiers=_social_mods or None,
                reputation_modifiers=_rep_modifiers_for_hub,
                drive_modifiers=_drive_modifiers_for_hub,
                reflex_constraints=_reflex_constraints,
                topic=_topic,
                decision_ctx=_decision_ctx, # Передаём геометрию давления
            )

            # ADR-035: Reactive Spatial Command Reflex.
            # Если игрок приказал NPC двигаться (через Semantic Bridge или raw_input), 
            # перехватываем решение DecisionHub и заставляем NPC подойти.
            if decision.intent.value not in ("approach", "flee"):
                _is_move_command = False
                
                # Путь 1: Semantic Bridge (если payload содержит semantic_action)
                _payload = getattr(hub_event, 'payload', {})
                if isinstance(_payload, dict) and _payload.get("semantic_action") == "MOVE":
                    _target_ref = _payload.get("target_reference", "").lower()
                    npc_name = npc_dict.get("name", "").lower()
                    npc_id_lower = npc_id.lower()
                    if _target_ref and (_target_ref in npc_name or _target_ref in npc_id_lower):
                        _is_move_command = True
                
                # Путь 2: Raw Text Reflex (Fallback по тексту команды)
                if not _is_move_command and inp.raw_input:
                    content = inp.raw_input.lower()
                    npc_name = npc_dict.get("name", "").lower()
                    npc_id_lower = npc_id.lower()
                    
                    _MOVE_VERBS = ["подойди", "подойти", "иди", "подой", "подходи", "приди", "приходи", "сюда"]
                    name_mentioned = any(n in content for n in [npc_name, npc_id_lower] if n)
                    move_requested = any(v in content for v in _MOVE_VERBS)
                    
                    if name_mentioned and move_requested:
                        _is_move_command = True

                if _is_move_command:
                    from app.domain.decision import Intent
                    decision.intent = Intent.APPROACH
                    decision.intent_target = "player"
                    logger.warning(f"[REFLEX_MOVE] npc={npc_id} forced APPROACH by player command")

            # CommunicationIntent → buffer, публикация через Фазу 6 оркестратора (Устав §5.1)
            if decision.communication is not None:
                buf.communication_intents.append(decision.communication)
                # DEPRECATED: published_events — оставлен для обратной совместимости
                buf.published_events.append(decision.communication)

            # MovementIntent — реактивное движение NPC (APPROACH, FLEE и др.)
            # DecisionHub решает ЧТО делать, MovementEngine решит КАК (координаты)
            from app.domain.movement import MacroMovementGoal, LocalSteeringGoal
            _intent_value = decision.intent.value if decision.intent else ""
            
            # ADR-035: Реактивный перехват пространственных команд.
            # Если игрок приказал "MOVE" (или просто использовал глагол приближения), NPC реагирует мгновенно.
            if _intent_value not in {"approach", "flee"}:
                _move_triggered = False
                
                # Путь 1: Проверяем hub_event на наличие семантики (если Слой 1 пробросил данные)
                if hasattr(inp, 'hub_event') and inp.hub_event:
                    _payload = inp.hub_event.payload if hasattr(inp.hub_event, 'payload') else inp.hub_event.get("payload", {})
                    if _payload.get("semantic_action") == "MOVE":
                        target_ref = _payload.get("target_reference", "").lower()
                        if target_ref:
                            # ADR-048: Spatial Authority — имя NPC через QueryService, не scene_state
                            _sq = svc.spatial_query if svc else None
                            npc_data = _sq.get_entity_position(npc_id) if _sq else inp.scene_state.get("npc_positions", {}).get(npc_id, {})
                            npc_display_name = npc_data.get("name", npc_data.get("display_name", "")).lower()
                            npc_id_lower = npc_id.lower()
                            if target_ref in npc_display_name or target_ref in npc_id_lower:
                                _move_triggered = True
                
                # Путь 2: Hardcoded Text Reflex (Fallback по raw_input, если NLP не пробросило payload)
                if not _move_triggered and hasattr(inp, 'raw_input') and inp.raw_input:
                    content = inp.raw_input.lower()
                    # ADR-048: Spatial Authority — имя NPC через QueryService, не scene_state
                    _sq = svc.spatial_query if svc else None
                    npc_data = _sq.get_entity_position(npc_id) if _sq else inp.scene_state.get("npc_positions", {}).get(npc_id, {})
                    npc_display_name = npc_data.get("name", npc_data.get("display_name", "")).lower()
                    npc_id_lower = npc_id.lower()
                    
                    _MOVE_VERBS = ["подойди", "подойти", "иди", "подой", "подходи", "приди", "приходи"]
                    name_mentioned = any(n in content for n in [npc_display_name, npc_id_lower] if n)
                    move_requested = any(v in content for v in _MOVE_VERBS)
                    
                    if name_mentioned and move_requested:
                        _move_triggered = True

                if _move_triggered:
                    _intent_value = "approach"
                    decision.intent_target = "player"
                    logger.warning(f"[REFLEX_MOVE] npc={npc_id} triggered APPROACH by player command")

            _MOVE_INTENTS = {"approach", "flee"}  # Расширять: seek_ally и т.д.
            if _intent_value in _MOVE_INTENTS:
                _movement = _resolve_reactive_movement(
                    npc_id=npc_id,
                    intent=_intent_value,
                    intent_target=decision.intent_target or "player",
                    scene_state=inp.scene_state,
                    location_id=inp.location,
                    spatial_service=svc.spatial_service if svc else None,
                    spatial_query=svc.spatial_query if svc else None,
                )
                if _movement:
                    buf.movement_intents.append(_movement)

            # 3. StateApplicator: Вычисляем реальные последствия (Read -> Write)
            state_to_use_for_llm = state_l2
            try:
                applicator = StateApplicator(relationship_store=svc.relationship_store)
                state_to_use_for_llm = applicator.apply(
                    state=state_l2,
                    result=decision,
                    campaign_id=inp.campaign_id,
                )
                # Собираем недавние события NPC для DecisionHub (память = контекст)
                hub_event.npc_recent = []
                if hasattr(state_to_use_for_llm, "narrative_cache"):
                    for e in state_to_use_for_llm.narrative_cache:
                        if hasattr(e, "summary") and e.npc_id == npc_id and e.summary:
                            hub_event.npc_recent.append(e.summary)
                            if len(hub_event.npc_recent) >= 3:
                                break
                # Salience: обновляем max_stress для фильтрации объектов
                buf.max_npc_stress = max(buf.max_npc_stress, getattr(state_to_use_for_llm, "stress", 0.0))

                # ФАЗА 1: NPC становятся живыми — запоминаем взаимодействия
                try:
                    state_to_use_for_llm = create_memory_event(
                        svc.memory_manager,
                        state_l2=state_to_use_for_llm,
                        decision=decision,
                        npc_id=npc_id,
                        hub_event=hub_event,
                        player_target_id=inp.player_target_id,
                        player_text=inp.raw_input,
                        scene_state=inp.scene_state,
                        campaign_id=inp.campaign_id,
                        spatial_query=svc.spatial_query,
                    )
                except Exception as _mem_err:
                    logger.warning(f"[MEMORY] apply failed for {npc_id}: {_mem_err}")

                # ЗАМЫКАНИЕ: Записываем состояние в dict ПОСЛЕ всех мутаций (legacy)
                NPCState.write_to_legacy(state_to_use_for_llm, _npc_dict_for_write)
                buf.dirty_npcs.add(id(_npc_dict_for_write))

                # Activity override — оркестратор применит в scene_state ПОСЛЕ фазы
                _new_activity = _INTENT_TO_ACTIVITY.get(state_to_use_for_llm.intent.value, "")
                if _new_activity:
                    buf.activity_overrides[npc_id] = _new_activity
                
                # Спринт 30: Проброс Cognitive Freeze (initiative_suppression) во фронтенд
                if hasattr(state_to_use_for_llm, 'perceptual_kernel') and state_to_use_for_llm.perceptual_kernel is not None:
                    buf.initiative_suppressions[npc_id] = state_to_use_for_llm.perceptual_kernel.initiative_suppression
            except Exception as e:
                logger.warning(f"[DM_FACADE] StateApplicator failed for {npc_id}, using raw state: {e}")

            # 3.5 Reaction Layer: DecisionResult → MicroEvents (ШАГ 0.5)
            _micro_events = resolve_reactions(
                decision, hub_event, state_to_use_for_llm,
                _npc_dict_for_write, npc_id,
            )

            # 4. Упаковка в VerbalizationContext (Enum -> Строки для LLM)
            verb_ctx = build_verbalization_context(
                svc.memory_manager, profile_l0, state_to_use_for_llm, decision,
                hub_event, inp.raw_input,
                campaign_id=inp.campaign_id,
                topic=_topic,
            )

            # Формируем единый контекст NPC
            _stress_d = 0.0
            _trust_d = 0.0
            try:
                _legacy_d = LegacyStateDeltaAdapter.collapse(decision.deltas)
                _stress_d = getattr(_legacy_d, "stress_delta_effective", _legacy_d.stress_delta)
                _trust_d = _legacy_d.trust_delta
            except Exception as e:
                logger.warning(f"[DM_FACADE] Failed to parse deltas for {npc_id}: {e}")

            # Scene Event Layer: NPC видит все события в сцене
            _perceived = inp.scene_state.get("raw_scene_events", [])
            buf.npc_contexts.append({
                "npc_id": npc_id,
                "tier": profile_l0.tier,
                "profile_l0": profile_l0,           # ФАЗА 0: для voice/backstory/author_notes
                "verbalization_ctx": verb_ctx,       # КЛЮЧ: Переключает агента на путь R3!
                "decision_result": decision,          # Для будущего StateApplicator
                "distortion_bias": interpretation.bias,  # Для ProjectionLayer (речь)
                "real_state": _npc_dict_for_write,    # Legacy dict для ProjectionLayer
                "trust_delta": _trust_d,              # Для StateApplicator
                "stress_delta": _stress_d,            # Для StateApplicator
                "micro_events": _micro_events,        # ШАГ 0.5: физические реакции
                "perceived_events": _perceived,       # Scene Event Layer: что NPC воспринимает
            })

    return buf


# ─────────────────────────────────────────────────────────────────────────
# Мост: DecisionResult → MovementIntent (реактивное движение NPC)
# ─────────────────────────────────────────────────────────────────────────

def _resolve_reactive_movement(
    npc_id: str,
    intent: str,
    intent_target: Optional[str],
    scene_state: dict,
    location_id: str,
    spatial_service: Optional[Any] = None,
    spatial_query: Optional[Any] = None,  # ADR-048: Authoritative Spatial Spine
) -> Optional["MovementIntent"]:
    """Конвертирует пространственный intent в MovementIntent.

    DecisionHub решает ЧТО (approach), эта функция решает КУДА (целевой узел графа).
    MovementEngine потом резолвит узел в {x, y}.

    Поддерживаемые интенты:
    - approach: идёт к intent_target (игрок/NPC) → ближайший к цели узел графа
    - flee: уходит от intent_target → find_furthest_node от позиции угрозы
    
    Если передан spatial_service (v1.2), использует его. Иначе fallback на load_graph.
    ADR-048: Если передан spatial_query, чтение позиций идёт ТОЛЬКО через него.
    """
    from app.domain.movement import LocalSteeringGoal, MacroMovementGoal, PRIORITY_NEEDS
    from app.services.spatial.location_graph import load_graph

    # ADR-048: Spatial Authority. Единственный источник пространственной истины.
    # Чтение npc_positions из scene_state ЗАПРЕЩЕНО для decisions (ADR-048 Этап 1).
    def _pos(eid: str) -> dict:
        if spatial_query:
            return spatial_query.get_entity_position(eid) or {}
        return scene_state.get("npc_positions", {}).get(eid, {})

    # Текущий узел NPC
    npc_entry = _pos(npc_id)
    current_node = npc_entry.get("position", "")

    # ADR-045: Макро-зона цели берется НАПРЯМУЮ из position, без поиска по координатам.
    target_node_id: Optional[str] = None
    _target_id = intent_target or "player"

    if intent == "approach":
        # ADR-048: Игрок внедрен как npc_id="player" (ADR-031), его позиция находится в npc_positions.
        # player_spatial удален. denormalize_id удален.
        target_entry = _pos(_target_id)
        target_node_id = target_entry.get("position")

        if not target_node_id:
            # Если макро-узел не найден, пробуем резолвить через координаты (local_position)
            lp = target_entry.get("local_position", {})
            target_x = lp.get("x")
            target_y = lp.get("y")
            if target_x is not None and target_y is not None and spatial_service:
                nearest_ref = spatial_service.get_nearest(zone_id=location_id, origin_xy=(target_x, target_y))
                if nearest_ref:
                    # ADR-008: denormalize_id удален. Извлекаем канонический ID напрямую.
                    target_node_id = getattr(nearest_ref, 'canonical_id', getattr(nearest_ref, 'node_id', str(nearest_ref)))
            if not target_node_id:
                logger.warning(f"[APPROACH_NAV] target={_target_id} not found in npc_positions! Movement blocked.")
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
            logger.warning(f"[FLEE_NAV] threat={_target_id} not found in npc_positions! Flee blocked.")
            return None

        if threat_x is not None and threat_y is not None:
            if spatial_service:
                furthest_ref = spatial_service.get_furthest(zone_id=location_id, origin_xy=(threat_x, threat_y))
                if furthest_ref:
                    # ADR-008: denormalize_id удален. Используем канонический ID напрямую.
                    target_node_id = getattr(furthest_ref, 'canonical_id', getattr(furthest_ref, 'node_id', str(furthest_ref)))
            else:
                try:
                    graph = load_graph(location_id)
                    target_node_id = graph.find_furthest_node(threat_x, threat_y)
                except Exception:
                    pass

            if target_node_id and target_node_id != current_node:
                print(f"[TRACE][INTENT_CREATED] npc={npc_id} intent=reactive:flee target_node={target_node_id}")
                return MacroMovementGoal(npc_id=npc_id, target_node_id=target_node_id, from_node_id=current_node, location_id=location_id, reason="reactive:flee", priority=PRIORITY_NEEDS)
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
            print(f"[TRACE][INTENT_CREATED] npc={npc_id} intent=micro_snap:{intent} target_node={current_node} target_xy=({target_x},{target_y})")
            # Возвращаем канонический current_node для трассировки, сравнение было по базе
            return LocalSteeringGoal(npc_id=npc_id, local_target_xy=(target_x, target_y), reason=f"micro_snap:{intent}", priority=PRIORITY_NEEDS)
        
        if intent == "flee":
            # Для побега из той же зоны ищем другой узел
            logger.info(f"[PIPELINE][REACTIVE_MOVEMENT][FLEE_MICRO] npc={npc_id} пытается бежать из своей зоны")
        else:
            logger.warning(f"[PIPELINE][REACTIVE_MOVEMENT][SKIP] npc={npc_id} already at target macro-zone {current_base}, no local coords")
            return None

    if not target_node_id:
        logger.warning(f"[PIPELINE][REACTIVE_MOVEMENT][SKIP] npc={npc_id} target_node_id is None")
        return None
    
    logger.warning(f"[PIPELINE][REACTIVE_MOVEMENT][CREATE] npc={npc_id} target_node={target_node_id} from_node={current_node}")
    print(f"[TRACE][INTENT_CREATED] npc={npc_id} intent=reactive:{intent} target_node={target_node_id}")
    return MacroMovementGoal(npc_id=npc_id, target_node_id=target_node_id, from_node_id=current_node, location_id=location_id, reason=f"reactive:{intent}", priority=PRIORITY_NEEDS)