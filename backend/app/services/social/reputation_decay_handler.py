# -*- coding: utf-8 -*-
"""
path: backend/app/services/social/reputation_decay_handler.py
Назначение: Time-driven дрейф репутации фракций → base_reputation.
Зависимости: app.models.idle_tick, app.models.state_delta, app.services.social.reputation_engine
Основные сущности: ReputationDecayHandler

Контракт:
- Делегирует в ReputationEngine.compute_decay() — чистый расчёт.
- Возвращает List[StateDeltas] с faction_id + reputation_delta.
- Применение — через StateApplicator.apply_batch() (единственный мутатор).
- nps не используются (фракции не привязаны к конкретным NPC-снапшотам),
  но сигнатура единая для IdleTickHandler.

TODO:
- В будущем можно расширить логику, учитывая дополнительные факторы (например, события в кампании), но сейчас фокус на базовом дрейфе репутации.
"""
from __future__ import annotations


import logging
from typing import Dict, Any, TYPE_CHECKING, List

from app.models.idle_tick import NPCStateSnapshot
from app.models.state_delta import StateDeltas

if TYPE_CHECKING:
    from app.services.social.reputation_engine import ReputationEngine

logger = logging.getLogger(__name__)


class ReputationDecayHandler:
    """Дрейф репутации фракций → base_reputation.

    Делегирует расчёт в ReputationEngine.compute_decay().
    Применение — через StateApplicator (единый мутатор).
    """

    name: str = "reputation_decay"

    def __init__(self, reputation_engine: ReputationEngine) -> None:
        self._engine = reputation_engine

    def handle(
        self,
        npcs: List[NPCStateSnapshot],
        campaign_id: str,
        current_tick: int,
    ) -> List[StateDeltas]:
        """Чистый расчёт дрейфа репутации через ReputationEngine."""
        deltas = self._engine.compute_decay()
        if deltas:
            logger.debug(
                f"[REPUTATION_DECAY] {campaign_id} tick={current_tick}: "
                f"{len(deltas)} faction drift deltas"
            )
        return deltas
