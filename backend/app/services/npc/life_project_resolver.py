"""
path: backend/app/services/npc/life_project_resolver.py
Назначение: L2.7 LifeProject Resolver. Вычисляет смену жизненного направления при кризисе идентичности.
Зависимости: app.models.npc_state
Основные сущности: LifeProjectResolver
"""

from typing import Optional

from app.models.npc_state import NPCState


class LifeProjectResolver:
    """
    L2.7: Принимает решение о смене LifeDirection (жизненной стратегии).
    Запускается ТОЛЬКО при identity_crisis = True (stage = deformation).
    """

    # Временная карта переходов.
    # В будущем будет вычисляться из убеждений (L2.5), травм и CoreOrientation (L0).
    _CRISIS_TRANSITIONS = {
        "family_builder": "isolation",
        "wealth_creator": "survival",
        "warrior": "revenge",
        "knowledge_seeker": "hermit",
        "ruler": "revenge",
        "survival": "isolation",
    }

    # Стабильные кризисные состояния (дальше не меняются без нового проекта)
    _CRISIS_STATES = {"isolation", "revenge", "hermit"}

    @staticmethod
    def resolve(state: NPCState) -> Optional[str]:
        """
        Если NPC в кризисе, определяет новое направление.
        Возвращает новое направление или None (если менять не нужно).
        """
        current_dir = getattr(state, "life_direction", "survival")

        # Если NPC уже в кризисном состоянии, не меняем его бесконечно
        if current_dir in LifeProjectResolver._CRISIS_STATES:
            return None

        # Иначе вычисляем кризисный вектор на основе текущего направления
        return LifeProjectResolver._CRISIS_TRANSITIONS.get(current_dir, "isolation")
