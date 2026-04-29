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
            _intent_val = getattr(_npc_ctx["decision_result"], "intent", None)
            if _intent_val is None:
                continue

            if _intent_val.value == "attack":
                _avatar_state.stress = min(100.0, _avatar_state.stress + 5.0)
                if _avatar_state.emotion in (emotion_tag_cls.NEUTRAL, emotion_tag_cls.HAPPY):
                    _avatar_state.emotion = emotion_tag_cls.FEARFUL
                _avatar_changed = True

                # Физический урон: NPC атакует игрока через PhysicalResolver
                try:
                    from app.services.resolution.physical_resolver import PhysicalResolver

                    _npc_real = _npc_ctx.get("real_state", {})
                    _npc_combat = _npc_real.get("combat_stats", {})
                    _npc_damage = _npc_combat.get("damage", "1d4")
                    _npc_atk_bonus = _npc_combat.get("attack_bonus", 2)

                    _player_sheet = avatar_service.load_sheet(campaign_id, player_name)
                    _player_ac = _player_sheet.ac

                    # Резолвим только если игрок жив и имеет HP
                    if _avatar_state.max_hp > 0 and _avatar_state.hp > 0:
                        _phys_resolver = PhysicalResolver()
                        _phys_outcome = _phys_resolver.resolve_attack(
                            attack_bonus=_npc_atk_bonus,
                            target_ac=_player_ac,
                            damage_formula=_npc_damage,
                            attacker_id=_npc_ctx["npc_id"],
                        )
                        if _phys_outcome.hit and _phys_outcome.damage > 0:
                            _avatar_state.hp = max(0, _avatar_state.hp - _phys_outcome.damage)
                            _avatar_changed = True
                            _npc_id = _npc_ctx["npc_id"]
                            logger.warning(
                                f"[AVATAR_DAMAGE] {_npc_id} → player: "
                                f"dmg={_phys_outcome.damage} crit={_phys_outcome.critical} "
                                f"hp={_avatar_state.hp}/{_avatar_state.max_hp}"
                            )
                        else:
                            _npc_id = _npc_ctx["npc_id"]
                            logger.warning(f"[AVATAR_DAMAGE] {_npc_id} → player: MISS")
                except Exception as _phys_err:
                    logger.error(f"[AVATAR_DAMAGE] error: {_phys_err}", exc_info=True)
            elif _intent_val.value == "intimidate":
                _avatar_state.stress = min(100.0, _avatar_state.stress + 2.0)
                if _avatar_state.emotion == emotion_tag_cls.NEUTRAL:
                    _avatar_state.emotion = emotion_tag_cls.SUSPICIOUS
                _avatar_changed = True
            elif _intent_val.value == "help":
                _avatar_state.stress = max(0.0, _avatar_state.stress - 3.0)
                if _avatar_state.emotion in (emotion_tag_cls.FEARFUL, emotion_tag_cls.SAD):
                    _avatar_state.emotion = emotion_tag_cls.NEUTRAL
                _avatar_changed = True

        if _avatar_changed:
            avatar_service.save_state(campaign_id, _avatar_state)
            logger.warning(f"[AVATAR] stress={_avatar_state.stress:.1f} emotion={_avatar_state.emotion.value}")
    except Exception as _av_err:
        logger.warning(f"[AVATAR] update error: {_av_err}")