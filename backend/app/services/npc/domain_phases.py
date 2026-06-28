# path: backend/app/services/npc/domain_phases.py
"""
Доменные фазы NPC тика — физика, условия, экономика, реакции.

Вынесены из npc_tick_pipeline.py чтобы разделить cognition (чистые решения)
и domain (физические последствия, условия, экономика).

По Уставу §3: доменная логика не живёт внутри cognition loop.
Каждая функция — отдельная фаза, вызываемая оркестратором.

Назначение: Доменные фазы NPC тика (physical, conditions, economy, reactions)
Зависимости: logging, app.services.resolution, app.services.reaction, app.services.npc, app.services.economy, app.models
Основные сущности: resolve_physical_attack, tick_conditions, age_temporary_drives, compute_economy, resolve_reactions

TODO: по мере роста доменных фаз может потребоваться реорганизация в отдельные модули (physical.py, conditions.py, etc).
TODO: унификация возвращаемых данных — сейчас разные фазы возвращают разные структуры, стоит стандартизировать для удобства оркестратора.
TODO: добавить типизацию возвращаемых данных для каждой функции, чтобы облегчить интеграцию и отладку.
TODO: расширить логирование для каждой фазы — сейчас логируются только ключевые события, стоит добавить больше деталей для отладки (например, входные данные, промежуточные результаты).
"""

import logging
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# ── Константы ──────────────────────────────────────────────────────────────────

PHYSICAL_EVENTS = frozenset({
    "player_attacks", "player_steals", "player_grapples",
    "player_casts", "player_shoots",
})

HANDS_OCCUPIED_ACTIVITIES = frozenset({
    "serving", "working", "crafting", "cooking", "serving_tables", "cleaning_tables",
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

    # ADR-0015, ADR-0021: Вся физика и урон перенесены в CombatSubscriber → ImpactEngine
    # и обрабатываются в Фазе 8 (Layered Reduction).
    # Рефлексы и урон больше не вычисляются здесь.
    return state_l2, None


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


# ── Economy ───────────────────────────────────────────────────────────────────

def compute_economy(
    npc_id: str,
    eco_profile: Any,
    state_l2: Any,
    current_activity: str = "",
) -> Dict[str, Any]:
    """Фаза 2.4-ECO: экономические модификаторы от потребностей.

    Вынесено из inline-блока в npc_tick_pipeline.py.
    Возвращает dict с ключами: modifiers (dict), stress (float), reason (str).
    Мутирует state_l2.stress при экономическом стрессе.
    """
    _result: Dict[str, Any] = {"modifiers": {}, "stress": 0.0, "reason": ""}
    if not eco_profile:
        return _result

    try:
        from app.services.economy.need_engine import NeedEngine
        from app.services.economy.economic_modifier import EconomicModifier
        from app.services.economy.stress_calculator import calculate_economic_stress

        _ne = NeedEngine()
        _drives = _ne.tick(eco_profile, current_activity=current_activity)
        _em = EconomicModifier()
        _eco_result = _em.calculate(eco_profile, _drives)
        _eco_modifiers = _eco_result.modifiers
        if _eco_modifiers:
            logger.warning(f"[ECO] {npc_id}: {len(_eco_modifiers)} mods, drives={_eco_result.active_drives}")
        _result["modifiers"] = _eco_modifiers or {}

        # Стресс от экономики/потребностей (единый расчёт)
        _eco_stress, _eco_reason = calculate_economic_stress(eco_profile, _ne)
        if _eco_stress > 0:
            state_l2.stress = min(100.0, state_l2.stress + _eco_stress)
            logger.warning(f"[ECO] {npc_id}: +{_eco_stress:.3f} ({_eco_reason})")
            _result["stress"] = _eco_stress
            _result["reason"] = _eco_reason
    except Exception as _eco_e:
        logger.warning(f"[ECO] Error (non-blocking): {_eco_e}")

    return _result


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