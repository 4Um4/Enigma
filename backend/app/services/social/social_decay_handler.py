# -*- coding: utf-8 -*-
"""
path: backend/app/services/social/social_decay_handler.py
Назначение: Time-driven дрейф trust/affection → base значения.
Зависимости: math, app.models.idle_tick, app.models.state_delta
Основные сущности: SocialDecayHandler

Контракт:
- Чистая функция: не мутирует NPC данные.
- Возвращает List[StateDeltas] с social_target для каждого таргета.
- Closing drift: если |base - current| < EPSILON → drift = base - current.
  Это гарантирует достижение равновесия без микро-осцилляций.

TODO:
- в будущем можно добавить отдельные контракты для разных типов idle-обработчиков (например, для репутационного дрейфа, для социальных связей и т.д.), чтобы обеспечить более строгую типизацию и ясность в коде. Но на начальном этапе достаточно общего протокола IdleTickHandler, который может обрабатывать любые аспекты NPC state, не мутируя исходные данные и возвращая дельты для применения. Это позволит нам гибко добавлять новые механики в фазу 0.5 без необходимости менять контракт каждого обработчика.
- важно, что эти обработчики не мутируют all_npcs_raw, а возвращают List[StateDeltas], который оркестратор применяет через StateApplicator.apply_batch(). Это обеспечивает чистоту данных и предсказуемость изменений в NPC state, а также позволяет легко отслеживать и логировать изменения, вызванные каждым обработчиком.
"""
from __future__ import annotations

import logging
from typing import List

from app.models.idle_tick import NPCStateSnapshot
from app.models.state_delta import DeltaDomain, SocialPayload, StateDeltas

logger = logging.getLogger(__name__)

# --- Константы дрейфа ---
SOCIAL_DECAY_RATE: float = 0.01  # 1% дрейфа за тик к базовому значению
SOCIAL_DECAY_EPSILON: float = 0.001  # порог closing drift


class SocialDecayHandler:
    """Дрейф trust/affection → base значения.

    Для каждого NPC: перебирает relationship_cache,
    вычисляет (base - current) * RATE,
    возвращает StateDeltas с social_target.
    """

    name: str = "social_decay"

    def handle(
        self,
        npcs: List[NPCStateSnapshot],
        campaign_id: str,
        current_tick: int,
    ) -> List[StateDeltas]:
        """Чистая функция: дрейф trust → base значения с closing drift."""
        results: List[StateDeltas] = []

        for npc in npcs:
            npc_id = npc.get("npc_id", "")
            if not npc_id:
                continue

            rel_cache = npc.get("relationship_cache", {})
            base_vals = npc.get("base_values", {})

            for target, rel_data in rel_cache.items():
                # Пропускаем записи без доверия
                if not isinstance(rel_data, dict):
                    continue

                current_trust = float(rel_data.get("trust", 0.0))
                current_fear = float(rel_data.get("fear", 0.0))
                # Базовое значение: из base_vals, из rel_data, или текущее (нет дрейфа)
                base_trust = float(
                    base_vals.get(target, rel_data.get("base_trust", current_trust))
                )
                # Fear drift к нулю — страх не должен застревать навсегда
                base_fear = 0.0

                trust_drift = (base_trust - current_trust) * SOCIAL_DECAY_RATE
                fear_drift = (base_fear - current_fear) * SOCIAL_DECAY_RATE

                # Closing drift для trust
                if abs(base_trust - current_trust) < SOCIAL_DECAY_EPSILON:
                    trust_drift = base_trust - current_trust

                # Closing drift для fear
                if abs(current_fear) < SOCIAL_DECAY_EPSILON:
                    fear_drift = -current_fear

                # Нет разницы — нет дрейфа
                if abs(trust_drift) < 1e-9 and abs(fear_drift) < 1e-9:
                    continue

                results.append(
                    StateDeltas(
                        npc_id=npc_id,
                        # v1 backward compat
                        social_target=target,
                        trust_delta=round(trust_drift, 6),
                        fear_delta=round(fear_drift, 6),
                        # v2 domain-tagged payload
                        domain=DeltaDomain.SOCIAL,
                        target=target,
                        payload=SocialPayload(
                            trust_delta=round(trust_drift, 6),
                            fear_delta=round(fear_drift, 6),
                        ),
                        source="social_decay",
                    )
                )

        if results:
            logger.debug(
                f"[SOCIAL_DECAY] {campaign_id} tick={current_tick}: "
                f"{len(results)} drift deltas"
            )

        return results
