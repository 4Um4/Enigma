from __future__ import annotations

# backend/app/services/npc/belief_modifier_resolver.py
"""
Read-path эпистемического слоя.

Конвертирует убеждения → модификаторы для DecisionHub.
Отделён от BeliefState (тупой контейнер) и от pipeline (знает только о beliefs).

Паттерн:
    BeliefState → BeliefModifierResolver → Dict[intent, float]
    → сливается с drive_modifiers в pipeline
    → DecisionHub.compute(drive_modifiers=...)

Не создаёт новый пайплайн — встраивается в существующий drive_modifiers.
"""


from typing import TYPE_CHECKING, Dict

if TYPE_CHECKING:
    from app.models.npc.beliefs import BeliefState

from app.models.npc.beliefs import BeliefType


class BeliefModifierResolver:
    """
    Конвертирует убеждения в модификаторы intent-score.

    Один экземпляр — один вызов — один словарь модификаторов.
    Не хранит состояние.
    """

    def resolve(self, beliefs: "BeliefState") -> Dict[str, float]:
        """
        Вычислить модификаторы из текущих убеждений.

        Возвращает: {intent_str: delta} — тот же формат что drive_modifiers.
        Пустой dict если убеждения не накоплены.
        """
        mods: Dict[str, float] = {}

        self._apply_danger(beliefs, mods)
        self._apply_player_hostile(beliefs, mods)

        return mods

    # ──────────────────────────────────────────────────────────────────────

    def _apply_danger(
        self,
        beliefs: "BeliefState",
        mods: Dict[str, float],
    ) -> None:
        """
        DANGER → усиливает flee и observe, ослабляет approach.
        Порог 0.15: слабые убеждения не влияют на поведение.
        """
        danger = beliefs.get(BeliefType.DANGER)
        if not danger or danger.value < 0.15:
            return

        weight = round(danger.value * danger.confidence, 4)
        mods["flee"] = round(mods.get("flee", 0.0) + weight * 0.25, 4)
        mods["observe"] = round(mods.get("observe", 0.0) + weight * 0.10, 4)
        mods["approach"] = round(mods.get("approach", 0.0) - weight * 0.15, 4)

    def _apply_player_hostile(
        self,
        beliefs: "BeliefState",
        mods: Dict[str, float],
    ) -> None:
        """
        PLAYER_HOSTILE → усиливает flee и warn, подавляет trade и approach.
        Порог 0.2: нужно накопленное убеждение.
        """
        hostile = beliefs.get(BeliefType.PLAYER_HOSTILE)
        if not hostile or hostile.value < 0.20:
            return

        weight = round(hostile.value * hostile.confidence, 4)
        mods["flee"] = round(mods.get("flee", 0.0) + weight * 0.20, 4)
        mods["warn"] = round(mods.get("warn", 0.0) + weight * 0.15, 4)
        mods["trade"] = round(mods.get("trade", 0.0) - weight * 0.20, 4)
        mods["approach"] = round(mods.get("approach", 0.0) - weight * 0.10, 4)
