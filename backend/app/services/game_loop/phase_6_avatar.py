# path: C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\game_loop\phase_6_avatar.py
"""
ФАЗА 6: Обновление аватара игрока — реакция на NPC интенты.

NPC attack → stress + урон, intimidate → stress, help → stress reduction.
Вызывается после PerceptionFilter, когда npc_contexts уже отфильтрованы.

Назначение: ФАЗА 6 — обновление аватара игрока по реакциям NPC (стресс, эмоция, урон)
Зависимости: logging
Основные сущности: update_avatar_from_npc_intents
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def update_avatar_from_npc_intents(
    avatar_service: Any,
    campaign_id: str,
    player_name: str,
    npc_contexts: list[dict],
    emotion_tag_cls: Any,
) -> None:
    """Обновляет аватар игрока на основе интентов NPC.

    Вызывается ПОСЛЕ PerceptionFilter — npc_contexts уже отфильтрованы
    по воспринимающим NPC.
    """
    if not player_name or not npc_contexts:
        return
    try:
        _avatar_state = avatar_service.load_state(campaign_id, player_name)
        _avatar_changed = False

        for _npc_ctx in npc_contexts:
            _npc_intent = _npc_ctx.get("decision_result")
            if not _npc_intent:
                continue
            _intent_val = getattr(_npc_ctx["decision_result"], "intent", None)  # noqa: ENIGMA002
            if _intent_val is None:
                continue

            if _intent_val.value == "attack":
                object.__setattr__(_avatar_state, "stress", min(100.0, _avatar_state.stress + 5.0))
                if _avatar_state.emotion in (
                    emotion_tag_cls.NEUTRAL,
                    emotion_tag_cls.HAPPY,
                ):
                    object.__setattr__(_avatar_state, "emotion", emotion_tag_cls.FEARFUL)
                _avatar_changed = True

                # ADR-0015, ADR-0021: Урон аватару от NPC теперь рассчитывается
                # через CombatSubscriber → ImpactEngine в Фазе 8 (Layered Reduction).
                # Прямая мутация HP аватара здесь запрещена.
            elif _intent_val.value == "intimidate":
                object.__setattr__(_avatar_state, "stress", min(100.0, _avatar_state.stress + 2.0))
                if _avatar_state.emotion == emotion_tag_cls.NEUTRAL:
                    object.__setattr__(_avatar_state, "emotion", emotion_tag_cls.SUSPICIOUS)
                _avatar_changed = True
            elif _intent_val.value == "help":
                object.__setattr__(_avatar_state, "stress", max(0.0, _avatar_state.stress - 3.0))
                if _avatar_state.emotion in (
                    emotion_tag_cls.FEARFUL,
                    emotion_tag_cls.SAD,
                ):
                    object.__setattr__(_avatar_state, "emotion", emotion_tag_cls.NEUTRAL)
                _avatar_changed = True

        if _avatar_changed:
            avatar_service.save_state(campaign_id, _avatar_state)
            logger.warning(
                f"[AVATAR] stress={_avatar_state.stress:.1f} emotion={_avatar_state.emotion.value if hasattr(_avatar_state.emotion, 'value') else _avatar_state.emotion}"
            )
    except Exception as _av_err:
        logger.warning(f"[AVATAR] update error: {_av_err}")


def avatar_to_prompt(state) -> dict:
    """Формирует краткое описание состояния аватара для DM промпта."""
    wounds_str = "нет"
    if state.wounds:
        wounds_str = ", ".join(
            f"{w.body_part}({w.severity if isinstance(w.severity, str) else w.severity.value})"
            for w in state.wounds
        )
    conds_str = "нет"
    if state.conditions:
        conds_str = ", ".join(
            f"{k}({v.severity:.0%})" for k, v in state.conditions.items()
        )
    return {
        "hp": f"{state.effective_hp}/{state.effective_max_hp}"
        if state.effective_max_hp > 0
        else "не задано",
        "stress": round(state.stress, 1),
        "emotion": state.emotion.value
        if hasattr(state.emotion, "value")
        else str(state.emotion),
        "will_state": state.will_state.value
        if hasattr(state.will_state, "value")
        else str(state.will_state),
        "posture": state.posture,
        "wounds": wounds_str,
        "conditions": conds_str,
        "identity_integrity": round(state.identity_integrity, 2),
        "life_status": (state.body_state or {}).get("life_status", "ALIVE")
        if hasattr(state, "body_state")
        else "ALIVE",
    }
