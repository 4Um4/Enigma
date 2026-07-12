"""
path: backend/app/services/npc/crystallized_belief_modifier_resolver.py
Назначение: Конвертация L2.5 убеждений в модификаторы для DecisionHub.
Зависимости: backend/app/domain/identity_events.py
Основные сущности: CrystallizedBeliefModifierResolver
"""

from typing import Any, List, Dict
from app.domain.identity_events import CrystallizedBelief


class CrystallizedBeliefModifierResolver:
    """
    Переводит CrystallizedBelief (source_id, trait, weight)
    в модификаторы intent-score (Dict[str, float]).
    """

    def resolve(self, beliefs: List[CrystallizedBelief]) -> Dict[str, float]:
        """
        Вычислить модификаторы на основе кристаллизованных убеждений.

        Returns:
            Dict[str, float]: Модификаторы для DecisionHub (intent -> delta).
        """
        mods: Dict[str, float] = {}

        for belief in beliefs:
            # Страх к источнику (fear) -> повышает приоритет FLEE и WARN
            if belief.trait == "fear":
                fear_mod = belief.weight * 0.5  # Нормализованный вес
                mods["FLEE"] = mods.get("FLEE", 0.0) + fear_mod
                mods["WARN"] = mods.get("WARN", 0.0) + (fear_mod * 0.5)
                mods["APPROACH"] = mods.get("APPROACH", 0.0) - fear_mod

            # Доверие к источнику (trust) -> повышает приоритет TALK и HELP
            elif belief.trait == "trust":
                trust_mod = belief.weight * 0.5
                mods["TALK"] = mods.get("TALK", 0.0) + trust_mod
                mods["HELP"] = mods.get("HELP", 0.0) + trust_mod
                mods["ATTACK"] = mods.get("ATTACK", 0.0) - trust_mod

        return mods
