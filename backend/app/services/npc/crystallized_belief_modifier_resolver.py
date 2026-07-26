"""
path: backend/app/services/npc/crystallized_belief_modifier_resolver.py
Назначение: Конвертация L2.5 убеждений в модификаторы для DecisionHub.
Зависимости: backend/app/domain/identity_events.py
Основные сущности: CrystallizedBeliefModifierResolver
"""

from typing import Dict, List

from app.domain.identity_events import CrystallizedBelief
from app.models.npc_state import Intent


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
                mods[Intent.FLEE.value] = mods.get(Intent.FLEE.value, 0.0) + fear_mod
                mods[Intent.WARN.value] = mods.get(Intent.WARN.value, 0.0) + (fear_mod * 0.5)
                mods[Intent.APPROACH.value] = mods.get(Intent.APPROACH.value, 0.0) - fear_mod

            # Доверие к источнику (trust) -> повышает приоритет TALK и HELP
            elif belief.trait == "trust":
                trust_mod = belief.weight * 0.5
                mods[Intent.TALK.value] = mods.get(Intent.TALK.value, 0.0) + trust_mod
                mods[Intent.HELP.value] = mods.get(Intent.HELP.value, 0.0) + trust_mod
                mods[Intent.ATTACK.value] = mods.get(Intent.ATTACK.value, 0.0) - trust_mod

        return mods
