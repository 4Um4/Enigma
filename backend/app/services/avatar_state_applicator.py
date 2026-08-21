"""
path: /project/backend/app/services/avatar_state_applicator.py
Назначение: P0-B (S208) — канонический владелец runtime-мутаций NPCState аватара
            игрока. GameLoop — оркестратор, не писатель (ownership model).
Зависимости: app.models.npc_state (NPCState, BODY_STATE_DISABLED_DATA)
Основные сущности: AvatarStateApplicator
"""

from __future__ import annotations

import logging
from typing import Any

from app.models.npc_state import BODY_STATE_DISABLED_DATA, NPCState

logger = logging.getLogger(__name__)


class AvatarStateApplicator:
    """Каноническая граница мутации runtime-состояния аватара игрока.

    Ownership model (S208, P0):
      - Construction/restore      → PlayerAvatarService (NPCState(...), self-write)
      - Runtime full-sync         → ЭТОТ класс (whitelist: body_state, stress, emotion)
      - Trade money-дельты        → StateApplicator (существующий путь, TRADE_FIX)
      - GameLoop                  → оркестрирует, запрашивает применение, НЕ пишет

    Двойной бухгалтерии нет: whitelist NPCState._ALLOWED_WRITERS дополнен
    ТОЛЬКО этим модулем (узко, по полям) — см. патч в npc_state.py.
    """

    @staticmethod
    def apply_pipeline_result(
        avatar_state: NPCState,
        updated_avatar_dict: dict[str, Any],
    ) -> None:
        """Фазовый write-back: применяет pipeline-результат к аватару.

        Заменяет прямые присвоения game_loop:1777-1788. Семантика сохранена
        байт-в-байт (body_state full-sync, hp→current_hp, DISABLED-ветка).
        """
        if "body_state" in updated_avatar_dict:
            avatar_state.body_state = updated_avatar_dict["body_state"]
        if "hp" in updated_avatar_dict:
            if avatar_state.body_state:
                avatar_state.body_state["current_hp"] = updated_avatar_dict.get(
                    "hp", updated_avatar_dict.get("current_hp", 0)
                )
            else:
                avatar_state.body_state = dict(BODY_STATE_DISABLED_DATA)
                avatar_state.body_state["current_hp"] = updated_avatar_dict["hp"]

    @staticmethod
    def apply_reaction(
        avatar_state: NPCState,
        stress_delta: float = 0.0,
        emotion: Any = None,
    ) -> None:
        """P0-C: реакция аватара на интенты NPC (бывший object.__setattr__
        в phase_6_avatar). Границы значений соблюдаются вызывающим."""
        if stress_delta:
            avatar_state.stress = min(100.0, max(0.0, avatar_state.stress + stress_delta))
        if emotion is not None:
            avatar_state.emotion = emotion