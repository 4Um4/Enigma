# path: C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\social\propagation.py
"""
ФАЗА 4: Social Propagation — слухи доходят до непрямо воспринимающих NPC.

SocialEngine.propagate() вызывается после PerceptionFilter.
Возвращает List[StateDeltas] — оркестратор применяет через Phase 8.

Назначение: ФАЗА 4 — Social Propagation, слухи между NPC через SocialEngine
Зависимости: logging, app.models.state_delta.StateDeltas
Основные сущности: propagate_social_rumors

TODO: мигрировать в отдельный модуль, чтобы не тянуть SocialEngine в game_loop.py. SocialEngine — сложная подсистема, которая может расти и развиваться независимо от game_loop. В идеале game_loop должен знать только про интерфейс SocialEngine, а не про его внутреннюю структуру. Вынесение в отдельный модуль улучшит модульность и
тестируемость кода, а также позволит легче вносить изменения в SocialEngine без риска сломать game_loop.
"""

import logging
from typing import Any, List, Tuple

from app.models.state_delta import DeltaDomain, EmotionPayload, SocialPayload, StateDeltas

logger = logging.getLogger(__name__)


def propagate_social_rumors(
    social_engine: Any,
    social_tick: int,
    shared_context: Any,
    events: list | None = None,
) -> Tuple[int, List[StateDeltas]]:
    """Пропагация слухов от свидетелей к непрямым наблюдателям.

    Чистая функция: не мутирует all_npcs_raw и tick_ctx.
    Возвращает (updated_social_tick, List[StateDeltas]).
    Оркестратор применяет дельты в _apply_phase8_result().
    """
    _target_id = getattr(shared_context, 'player_target_id', '') if shared_context else ''

    # Канонический путь: intensity из EventDTO.payload (Устав §2.1)
    # Агрегация через max() — инфляция слухов недопустима (Стратегическое правило 5)
    _intensity: float = 0.0
    _event_type: str = ""
    _actor_id: str = "player"
    if events:
        for _ev in events:
            _ev_intensity = _ev.payload.get("intensity", 0.0)
            if _ev_intensity > _intensity:
                _intensity = float(_ev_intensity)
                _event_type = _ev.payload.get("action_type", _ev.type)
                _actor_id = _ev.source

    # Fallback: legacy путь через dm_result.event_context
    if _intensity == 0.0:
        _dm_res = shared_context.python_engines_result.get("dm_result") if hasattr(shared_context, "python_engines_result") else None
        if _dm_res and _dm_res.event_context:
            _intensity = _dm_res.event_context.intensity
            _event_type = _dm_res.event_context.event_type
            _actor_id = _dm_res.event_context.actor_id

    if not social_engine or not _target_id or _intensity < social_engine.MIN_ORIGIN_INTENSITY:
        return social_tick, []

    social_tick += 1

    # Свидетели = NPC, получившие прямую вербализацию
    _witness_ids = {
        c.get("npc_id")
        for c in (shared_context.npc_contexts or [])
        if c.get("npc_id")
    }

    _social_results = social_engine.propagate(
        event_type=_event_type,
        intensity=_intensity,
        actor=_actor_id,
        target=_target_id,
        witnesses=list(_witness_ids - {_target_id}),
        current_tick=social_tick,
    )

    deltas: List[StateDeltas] = []

    if _social_results:
        for pr in _social_results:
            # Не перезаписываем прямых свидетелей
            if pr.npc_id in _witness_ids:
                continue

            # v2: Разделяем на EMOTION (stress) и SOCIAL (trust)
            # SocialEngine дельты в диапазоне ~0-1, NPCState — 0-100
            if pr.stress_delta != 0.0:
                deltas.append(StateDeltas(
                    npc_id=pr.npc_id,
                    # v1 backward compat
                    stress_delta=pr.stress_delta * 100,
                    # v2 domain-tagged payload
                    domain=DeltaDomain.EMOTION,
                    payload=EmotionPayload(stress_delta=pr.stress_delta * 100),
                    source="social_propagation",
                ))

            if pr.trust_delta != 0.0:
                deltas.append(StateDeltas(
                    npc_id=pr.npc_id,
                    # v1 backward compat
                    social_target=_actor_id,
                    trust_delta=pr.trust_delta * 100,
                    # v2 domain-tagged payload
                    domain=DeltaDomain.SOCIAL,
                    target=_actor_id,
                    payload=SocialPayload(trust_delta=pr.trust_delta * 100),
                    source="social_propagation",
                ))
            logger.debug(
                f"[SOCIAL] {pr.npc_id}: "
                f"trust{pr.trust_delta:+.3f} "
                f"stress{pr.stress_delta:+.3f} "
                f"({pr.rumor.hop} hops)"
            )

    # Чистая функция: не мутируем shared_context.
    # Социальные результаты доступны оркестратору через Phase8Result.deltas

    return social_tick, deltas