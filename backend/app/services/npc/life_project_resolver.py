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
    L2.7: Управляет FSM жизненного проекта (LifeProjectState).
    ADR-O-317: Смена проекта — это процесс, а не мгновенный акт.
    Стадия LOST означает экзистенциальную пустоту (рост stress).
    """

    # Временная карта переходов.
    _CRISIS_TRANSITIONS = {
        "family_builder": "isolation",
        "wealth_creator": "survival",
        "warrior": "revenge",
        "knowledge_seeker": "hermit",
        "ruler": "revenge",
        "survival": "isolation",
    }

    @staticmethod
    def resolve(state: NPCState, identity_crisis: bool) -> None:
        """
        Продвигает FSM жизненного проекта.
        Вызывается каждый тик в phases/decision.py.
        """
        current_state = getattr(state, "life_project_state", "ACTIVE")

        if current_state == "ACTIVE":
            if identity_crisis:
                state.life_project_state = "COLLAPSING"

        elif current_state == "COLLAPSING":
            # Переход в экзистенциальную пустоту
            state.life_project_state = "LOST"

        elif current_state == "LOST":
            # Рост стресса от отсутствия смысла
            state.stress = min(100.0, state.stress + 10.0)
            # Боль заставляет искать новый смысл
            if state.stress >= 90.0:
                state.life_project_state = "SEARCHING"

        elif current_state == "SEARCHING":
            # Вычисление нового вектора
            current_proj = getattr(state, "life_project", "survival")
            state.life_project = LifeProjectResolver._CRISIS_TRANSITIONS.get(current_proj, "isolation")
            state.life_project_state = "COMMITTED"

        elif current_state == "COMMITTED":
            # Обретя новый смысл, NPC возвращается к активной жизни
            state.life_project_state = "ACTIVE"
