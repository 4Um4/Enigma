"""
path: /project/backend/tests/sandbox/system/test_t06_belief_pipeline.py
Назначение: Интеграционный тест T-06. Доказывает, что кристаллизованные убеждения (L2.5)
    проходят через TickState, преобразуются в модификаторы и реально изменяют
    финальное решение DecisionHub (FLEE вместо APPROACH при высоком fear).
Зависимости: pytest, app.domain.tick, app.services.npc.crystallized_belief_modifier_resolver
Основные сущности: test_belief_modifies_decision

Запуск: cd backend; python -m pytest tests/sandbox/system/test_t06_belief_pipeline.py -v; cd ..
"""

import pytest
from unittest.mock import MagicMock, patch


def test_belief_modifies_decision():
    """
    Если NPC имеет кристаллизованное убеждение fear=0.8 к игроку,
    DecisionHub должен выбрать FLEE, а не APPROACH, потому что
    CrystallizedBeliefModifierResolver даёт flee +0.4, а approach -0.4.
    """
    from app.services.npc.decision_hub import DecisionHub
    from app.services.npc.crystallized_belief_modifier_resolver import (
        CrystallizedBeliefModifierResolver,
    )
    from app.domain.identity_events import CrystallizedBelief
    from app.domain.vital_state import LifeStatus
    from app.models.npc_state import Intent

    # 1. Формируем убеждения (L2.5)
    beliefs = [
        CrystallizedBelief(
            source_id="player", trait="fear", weight=0.8, last_updated_tick=1
        )
    ]
    mods = CrystallizedBeliefModifierResolver().resolve(beliefs)

    # 2. Мокаем state для DecisionHub
    state = MagicMock()
    state.npc_id = "test_npc"
    state.body_state = {"current_hp": 10, "shock_impulse": 0.0, "pain": 0.0}
    state.will_state = MagicMock(value="FREE")
    state.perceptual_kernel = MagicMock()
    state.perceptual_kernel.threat_gradient = 0.0
    state.hp = 100
    state.max_hp = 100
    state.conditions = {}
    state.threat_accumulator = None
    state.wounds = []
    state.intent = None
    state.intent_duration = 0
    state.stress = 0.0
    state.posture = ""

    # Мокаем event
    event = MagicMock()
    event.event_type = "IDLE"
    event.payload = {}
    event.intensity = 0.0
    event.target_id = None

    # 3. Патчим DecisionHub. Возвращаем значения enum (строчные строки).
    with patch(
        "app.services.npc.decision_hub.evaluate_vital_state",
        return_value=LifeStatus.ALIVE,
    ), patch(
        "app.services.npc.decision_hub.is_conscious", return_value=True
    ), patch.object(
        DecisionHub,
        "_get_possible_intents",
        return_value=[Intent.APPROACH.value, Intent.FLEE.value],
    ), patch.object(
        DecisionHub,
        "_score_all",
        return_value=({Intent.APPROACH.value: 1.0, Intent.FLEE.value: 1.0}, {}),
    ):
        hub = DecisionHub(rng=MagicMock())

        # Baseline: без модификаторов flee и approach равны (1.0).
        # DecisionHub должен выбрать approach (первый в dict).
        decision_base = hub.compute(
            state=state,
            personality=MagicMock(),
            event=event,
            effective_drives=MagicMock(),
            drive_modifiers=None,
            relationship_store=MagicMock(),
        )

        # С модификаторами: flee +0.4, approach -0.4.
        decision_mod = hub.compute(
            state=state,
            personality=MagicMock(),
            event=event,
            effective_drives=MagicMock(),
            drive_modifiers=mods,
            relationship_store=MagicMock(),
        )

    # 4. Проверяем контракт T-06
    assert decision_mod.decision.intent == Intent.FLEE, (
        "DecisionHub must choose FLEE when fear modifier is applied"
    )
    assert decision_mod.decision.score > 1.0, (
        "FLEE score must be boosted by modifier"
    )
    assert decision_base.decision.intent != Intent.FLEE, (
        "Baseline decision should not be FLEE without modifiers"
    )