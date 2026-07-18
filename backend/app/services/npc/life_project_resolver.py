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
    def resolve(state: NPCState, identity_pressure: float) -> None:
        """
        Продвигает FSM жизненного проекта на основе эфемерного Identity Pressure.
        Вызывается каждый тик в phases/decision.py.
        """
        current_state = getattr(state, "life_project_state", "ACTIVE")

        if current_state == "ACTIVE":
            # Кризис от Угрозы: высокое давление ломает текущий смысл
            if identity_pressure > 80.0:
                state.life_project_state = "COLLAPSING"
            # Кризис от Успеха: давление спало, личность цела — стабилизатор достигнут
            # (Survival — это перманентный проект, он не завершается)
            elif identity_pressure < 10.0 and state.identity_integrity > 0.9 and state.life_project != "survival":
                state.life_project_state = "COMPLETED"

        elif current_state == "COMPLETED":
            # P1: Vitality decay. Stress grows as the agent lacks a successor project.
            state.stress = min(100.0, state.stress + 5.0)
            if state.stress >= 90.0:
                state.life_project_state = "LOST"

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
