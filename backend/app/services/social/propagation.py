# path: C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\social\propagation.py
"""
ФАЗА 4: Social Propagation — слухи доходят до непрямо воспринимающих NPC.

SocialEngine.propagate() вызывается после PerceptionFilter.
Дельты (trust, stress) пишутся в npc dicts напрямую.

Назначение: ФАЗА 4 — Social Propagation, слухи между NPC через SocialEngine
Зависимости: logging
Основные сущности: propagate_social_rumors
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def propagate_social_rumors(
    social_engine: Any,
    social_tick: int,
    shared_context: Any,
    all_npcs_raw: list[dict],
    tick_ctx: Any,
) -> int:
    """Пропагация слухов от свидетелей к непрямым наблюдателям.

    Возвращает обновлённый social_tick.
    Мутирует all_npcs_raw (trust/stress) и tick_ctx.prop_dirty.
    """
    _dm_res = shared_context.python_engines_result.get("dm_result") if hasattr(shared_context, "python_engines_result") else None
    _target_id = shared_context.player_target_id

    if not social_engine or not _dm_res or not _dm_res.event_context or not _target_id:
        return social_tick

    _evt = _dm_res.event_context
    if _evt.intensity < social_engine.MIN_ORIGIN_INTENSITY:
        return social_tick

    social_tick += 1

    # Свидетели = NPC, получившие прямую вербализацию
    _witness_ids = {
        c.get("npc_id")
        for c in (shared_context.npc_contexts or [])
        if c.get("npc_id")
    }

    _social_results = social_engine.propagate(
        event_type=_evt.event_type,
        intensity=_evt.intensity,
        actor=_evt.actor_id,
        target=_target_id,
        witnesses=list(_witness_ids - {_target_id}),
        current_tick=social_tick,
    )

    if _social_results:
        for pr in _social_results:
            # Не перезаписываем прямых свидетелей
            if pr.npc_id in _witness_ids:
                continue
            for _npc_d in all_npcs_raw:
                if _npc_d.get("id") == pr.npc_id:
                    _rc = _npc_d.setdefault("relationship_cache", {})
                    _rc["trust"] = max(-100.0, min(
                        100.0,
                        _rc.get("trust", 0.0) + pr.trust_delta * 100,
                    ))
                    _cur_stress = _npc_d.get("stress", 0.0)
                    _npc_d["stress"] = max(0.0, min(
                        100.0,
                        _cur_stress + pr.stress_delta * 100,
                    ))
                    tick_ctx.prop_dirty = True
                    logger.debug(
                        f"[SOCIAL] {pr.npc_id}: "
                        f"trust{pr.trust_delta:+.3f} "
                        f"stress{pr.stress_delta:+.3f} "
                        f"({pr.rumor.hop} hops)"
                    )
                    break

        shared_context.social_propagation = _social_results

    return social_tick