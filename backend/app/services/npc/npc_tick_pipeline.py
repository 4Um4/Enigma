# path: C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\npc\npc_tick_pipeline.py
"""
Чистые функции NPC пайплайна (Фазы 3-6).

Без self, без побочных эффектов кроме логирования.
Мутируют только переданные state_l2 / npc_dict — не трогают внешние сервисы.


Назначение: Чистые функции NPC пайплайна — без self, без побочных эффектов кроме логгирования
Зависимости: logging, app.services.resolution, app.services.reaction, app.services.npc, app.services.verbalization, app.models
Основные сущности: HANDS_OCCUPIED_ACTIVITIES, BASE_IMPORTANCE, PHYSICAL_EVENTS, reset_session_state, tick_conditions, age_temporary_drives, resolve_reactions, resolve_physical_attack, create_memory_event, build_verbalization_context
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

# ── Константы ──────────────────────────────────────────────────────────────────

HANDS_OCCUPIED_ACTIVITIES = frozenset({
    "serving", "working", "crafting", "cooking", "serving_tables", "cleaning_tables",
})

BASE_IMPORTANCE: dict[str, float] = {
    "TALK": 0.6, "TRADE": 0.7, "HELP": 0.8,
    "ATTACK": 0.9, "FLEE": 0.8, "GIVE": 0.5,
    "ASK": 0.5, "THREATEN": 0.85, "OBSERVE": 0.3,
}

PHYSICAL_EVENTS = frozenset({
    "player_attacks", "player_steals", "player_grapples",
    "player_casts", "player_shoots",
})


# ── Physical resolution ──────────────────────────────────────────────────────

def resolve_physical_attack(
    npc_id: str,
    npc_profile: dict,
    npc_dict_for_write: dict,
    state_l2: Any,
    action_type: str,
    target_id: str,
    current_tick: int,
    scene_continuity: Any,
    scene_state: dict,
    relationship_store: Any,
) -> tuple:
    """Physical Resolution: игрок атакует NPC — урон, рефлексы, факты сцены.

    Возвращает (state_l2, reflex_constraints) — constraints для DecisionHub.
    Если действие не физическое или NPC не цель — возвращает (state_l2, None).
    """
    if action_type not in PHYSICAL_EVENTS or npc_id != target_id or state_l2.max_hp <= 0:
        return state_l2, None

    _reflex_constraints = None
    try:
        from app.services.resolution.physical_resolver import PhysicalResolver
        from app.services.reaction.reflex_resolver import ReflexResolver
        from app.services.npc.state_applicator import StateApplicator

        _combat = npc_profile.get("combat_stats", {})
        _resolver = PhysicalResolver()
        _phys_outcome = _resolver.resolve_attack(
            attack_bonus=2,
            target_ac=_combat.get("ac", 10),
            damage_formula=_combat.get("damage", "1d4"),
            attacker_id="player",
        )

        _applicator = StateApplicator(relationship_store=relationship_store)
        state_l2, _ = _applicator.apply_physical(
            state=state_l2,
            outcome=_phys_outcome,
            current_tick=current_tick,
        )
        from app.models.npc_state import NPCState
        NPCState.write_to_legacy(state_l2, npc_dict_for_write)

        _reflex = ReflexResolver()
        _reflex_result = _reflex.resolve(
            outcome=_phys_outcome,
            npc_id=npc_id,
            current_hp=state_l2.hp,
            max_hp=state_l2.max_hp,
        )

        if _reflex_result.has_constraint:
            for sig in _reflex_result.decision_signals:
                if sig.signal_type == "constraint" and sig.constraint:
                    _reflex_constraints = sig.constraint.to_dict()

        if _phys_outcome.hit and scene_continuity:
            _npc_display_name = npc_profile.get("name", npc_id)
            _los = (scene_state or {}).get("line_of_sight", {})
            _witnesses = [nid for nid, vis in _los.items() if vis and nid != npc_id]
            _vis_tag = "на глазах у присутствующих " if _witnesses else ""
            _fact = f"Игрок {_vis_tag}ударил {_npc_display_name}: {_phys_outcome.damage} урона ({_phys_outcome.damage_type.value})"
            if _phys_outcome.critical:
                _fact += ", КРИТИЧЕСКИЙ УДАР"
            scene_continuity.add_fact(_fact)

        if _reflex_result.scene_events:
            _phys_labels = {
                "flinched": "дрогнул(а)",
                "staggered": "отшатнулся(лся) от удара",
                "cry_of_pain": "вскрикнул(а) от боли",
                "blood_spatter": "появилась кровь",
                "weapon_dropped_force": "выронил(а) оружие от удара",
                "fell_to_ground": "упал(а) на землю",
            }
            _desc_parts = []
            for _me in _reflex_result.scene_events:
                _label = _phys_labels.get(_me.event_type.value, _me.event_type.value)
                _desc_parts.append(_label)
                if scene_continuity:
                    scene_continuity.add_event(f"{_me.event_type.value}_{_me.npc_id}")
            if _desc_parts and scene_continuity:
                _existing = scene_continuity.scene_facts[-1] if scene_continuity.scene_facts else ""
                scene_continuity.scene_facts[-1] = _existing + ", " + ", ".join(_desc_parts)

    except Exception as _phys_err:
        logger.error(f"[PHYSICAL] Error (non-blocking): {_phys_err}", exc_info=True)

    return state_l2, _reflex_constraints


# ── Session reset ─────────────────────────────────────────────────────────────

def reset_session_state(state_l2: Any, npc_id: str, is_session_start: bool) -> None:
    """Сброс динамического состояния при старте новой сессии.

    R8: stale emotion_tag даёт +0.35 к FLEE — без сброса NPC
    начинают убегать от нового игрока из-за старой эмоции.
    Stress НЕ сбрасывается — копится от событий.
    """
    if not is_session_start:
        return
    from app.models.npc_state import Intent, EmotionTag
    from app.models.behavior_mask import BehaviorMaskState

    state_l2.intent_duration = 0
    state_l2.intent_formed_at = 0
    state_l2.emotion_delta = 0.0
    state_l2.intent = Intent.IDLE
    state_l2.emotion = EmotionTag.NEUTRAL
    state_l2.behavior_mask = BehaviorMaskState()
    logger.warning(f"[SESSION_RESET] {npc_id}: emotion=NEUTRAL mask=NONE")


# ── ConditionEngine ───────────────────────────────────────────────────────────

def tick_conditions(
    state_l2: Any,
    npc_dict_for_write: dict,
    current_tick: int,
    scene_continuity: Any,
) -> Any:
    """ConditionEngine: тик условий (яд, болезнь, etc).

    Возвращает обновлённый state_l2 — может быть пересоздан при изменении HP.
    """
    if not state_l2.conditions:
        return state_l2
    try:
        from app.services.npc.condition_engine import ConditionEngine
        _cond_changes, _cond_events = ConditionEngine().tick(
            state=state_l2,
            current_tick=current_tick,
        )
        for _sc in _cond_changes:
            if _sc.field == "hp":
                state_l2 = state_l2.__class__(
                    **{**state_l2.__dict__, "hp": max(0, state_l2.hp + _sc.delta)}
                )
                from app.models.npc_state import NPCState
                NPCState.write_to_legacy(state_l2, npc_dict_for_write)
        if _cond_events and scene_continuity:
            for _me in _cond_events:
                scene_continuity.add_event(f"{_me.event_type.value}_{_me.npc_id}")
    except Exception as _cond_err:
        logger.warning(f"[CONDITION] Error (non-blocking): {_cond_err}")
    return state_l2


# ── Temporary drives aging ───────────────────────────────────────────────────

def age_temporary_drives(state_l2: Any, npc_dict_for_write: dict, npc_id: str) -> None:
    """Фаза 4-ROLE.2: aging temporary drives — истекшие удаляются."""
    _drives = getattr(state_l2, "temporary_drives", [])
    if not _drives:
        return
    from app.models.npc_state import age_drives
    _aged = age_drives(_drives)
    if hasattr(state_l2, "__dict__"):
        state_l2.temporary_drives = _aged
        npc_dict_for_write["temporary_drives"] = [
            {
                "drive_type": d.drive_type,
                "urgency": d.urgency,
                "reason": d.reason,
                "source_npc_id": d.source_npc_id,
                "tick_born": d.tick_born,
                "tick_age": d.tick_age,
            }
            for d in _aged
        ]
    if len(_aged) != len(_drives):
        logger.warning(f"[DRIVE] {npc_id}: {len(_drives)}→{len(_aged)} drives (expired)")


# ── Reaction resolver ────────────────────────────────────────────────────────

def resolve_reactions(
    decision: Any,
    hub_event: Any,
    state_for_llm: Any,
    npc_dict_for_write: dict,
    npc_id: str,
) -> list:
    """Reaction Layer: DecisionResult → MicroEvents.

    Без этого DecisionHub говорит "испуган", но ничего не визуализируется.
    """
    try:
        from app.services.reaction.reaction_resolver import ReactionResolver
        _resolver = ReactionResolver()
        _composure = 1.0 - state_for_llm.stress / 100.0
        _current_activity = npc_dict_for_write.get("routine", {}).get("current", "")
        _hands_occupied = _current_activity in HANDS_OCCUPIED_ACTIVITIES
        _micro_events = _resolver.resolve(
            decision=decision,
            event=hub_event,
            composure=_composure,
            hands_occupied=_hands_occupied,
            current_activity=_current_activity,
        )
        logger.warning(
            f"[REACTION] {npc_id}: composure={_composure:.2f} "
            f"hands={_hands_occupied} act='{_current_activity}' "
            f"events={[e.event_type.value for e in _micro_events]}"
        )
        return _micro_events
    except Exception as e:
        logger.warning(f"[REACTION] Failed for {npc_id}: {e}")
        return []


# ── Memory event creation ───────────────────────────────────────────────────

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
        _emotion_boost = min(abs(decision.deltas.emotion_delta) / 5.0, 1.0) * 0.3
        _importance = min(_base + _emotion_boost, 1.0)
    elif _has_target and _intent_upper in (
        "TALK", "TRADE", "HELP", "ATTACK", "FLEE", "GIVE", "ASK", "THREATEN",
    ):
        _summary = f"{_evt_actor} → {_evt_target}: {player_text[:60]}"
        _base = BASE_IMPORTANCE.get(_intent_upper, 0.0)
        _emotion_boost = min(abs(decision.deltas.emotion_delta) / 5.0, 1.0) * 0.3
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

    _topic = extract_topic(
        event_type=hub_event.event_type.value if hasattr(hub_event.event_type, "value") else str(hub_event.event_type),
        scene_facts=hub_event.scene_facts,
        raw_input=raw_input,
    )

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
        topic=_topic,
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