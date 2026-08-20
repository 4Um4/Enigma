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
    def resolve(state: NPCState, identity_pressure: float, tick: int = 0) -> None:
        """
        Продвигает FSM жизненного проекта на основе эфемерного Identity Pressure.
        Вызывается каждый тик в phases/decision.py.
        """
        current_state = getattr(state, "life_project_state", "ACTIVE")

        if current_state == "ACTIVE":
            # P5-01: Аккумуляция для COLLAPSING (3 тика подряд > 60)
            if identity_pressure > 60.0:
                _high_ticks = state.state_modifiers.get("high_pressure_ticks", 0.0) + 1.0
                state.state_modifiers["high_pressure_ticks"] = _high_ticks
                if _high_ticks >= 3.0:
                    object.__setattr__(state, "life_project_state", "COLLAPSING")
                    state.state_modifiers["high_pressure_ticks"] = 0.0
            else:
                state.state_modifiers["high_pressure_ticks"] = 0.0
                # P5-01: Кризис от Успеха. Порог 1.0, требование tick > 50.
                if identity_pressure < 1.0 and tick > 50 and state.identity_integrity > 0.9 and state.life_project != "survival":
                    object.__setattr__(state, "life_project_state", "COMPLETED")

        elif current_state == "COMPLETED":
            # P1: Vitality decay. Stress grows as the agent lacks a successor project.
            object.__setattr__(state, "stress", min(100.0, state.stress + 5.0))
            if state.stress >= 90.0:
                object.__setattr__(state, "life_project_state", "LOST")

        elif current_state == "COLLAPSING":
            # Переход в экзистенциальную пустоту
            object.__setattr__(state, "life_project_state", "LOST")

        elif current_state == "LOST":
            # Рост стресса от отсутствия смысла
            object.__setattr__(state, "stress", min(100.0, state.stress + 10.0))
            # Боль заставляет искать новый смысл
            if state.stress >= 90.0:
                object.__setattr__(state, "life_project_state", "SEARCHING")

        elif current_state == "SEARCHING":
            # Вычисление нового вектора
            current_proj = getattr(state, "life_project", "survival")
            object.__setattr__(state, "life_project", LifeProjectResolver._CRISIS_TRANSITIONS.get(current_proj, "isolation"))
            object.__setattr__(state, "life_project_state", "COMMITTED")

        elif current_state == "COMMITTED":
            # Обретя новый смысл, NPC возвращается к активной жизни
            object.__setattr__(state, "life_project_state", "ACTIVE")
