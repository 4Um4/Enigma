# backend/tests/test_decision_hub_goal_boost.py
"""
Smoke-тест: Проверяет, что жизненный проект (life_project) даёт буст к проактивным интентам.
P5-03: Поле profile.goal удалено. DecisionHub теперь использует state.life_project.
"""
import pytest
from app.models.npc_profile import NPCProfileL0, PsycheBase
from app.models.npc_state import EmotionTag, NPCState, WillState
from app.services.events.event_types import EventType
from app.services.npc.decision_hub import DecisionHub, EventContext


@pytest.fixture
def hub() -> DecisionHub:
    return DecisionHub(seed=42)

@pytest.fixture
def profile() -> NPCProfileL0:
    return NPCProfileL0(
        id="test_npc",
        name="Тестовый NPC",
        tier="major",
        drives_base={"control": 0.4, "significance": 0.3, "fear": 0.1, "desire": 0.6},
        psyche_base=PsycheBase(willpower=70, breakpoint=80, loyalty_base=50),
        voice_profile="Тестовый голос",
    )

@pytest.fixture
def world_tick_event() -> EventContext:
    return EventContext(
        event_type=EventType.WORLD_TICK,
        actor_id="test_actor",
        witness_count=0,
        distance=10.0,
        intensity=0.0
    )

class TestDecisionHubGoalBoost:
    def test_goal_provides_boost_to_proactive_intents(
        self,
        hub: DecisionHub,
        profile: NPCProfileL0,
        world_tick_event: EventContext
    ):
        """Если есть life_project, скор проактивных интентов должен быть выше."""
        # Состояние с активным жизненным проектом
        state_with_project = NPCState(npc_id="test_npc", will_state=WillState.FREE, emotion=EmotionTag.NEUTRAL)
        state_with_project.life_project = "wealth_creator"
        state_with_project.life_project_state = "ACTIVE"

        # Состояние без проекта (survival по умолчанию)
        state_without_project = NPCState(npc_id="test_npc", will_state=WillState.FREE, emotion=EmotionTag.NEUTRAL)
        state_without_project.life_project = "survival"
        state_without_project.life_project_state = "ACTIVE"

        from app.domain.identity_events import EffectiveDrives
        effective_drives = EffectiveDrives.from_dict(profile.drives_base)

        result_with_project = hub.compute(
            state=state_with_project,
            personality=profile,
            effective_drives=effective_drives,
            event=world_tick_event
        )

        result_without_project = hub.compute(
            state=state_without_project,
            personality=profile,
            effective_drives=effective_drives,
            event=world_tick_event
        )

        # Проверяем, что хотя бы один проактивный интент получил буст
        proactive_intents = ["block_path", "ambush", "seek_ally", "offer_job", "request_service", "spread_rumor", "call_for_help", "change_role"]

        boosted_count = 0
        for intent in proactive_intents:
            score_with = result_with_project.scores_trace.get(intent, 0.0)
            score_without = result_without_project.scores_trace.get(intent, 0.0)
            if score_with > score_without:
                boosted_count += 1

        assert boosted_count > 0, "Наличие life_project должно увеличивать скор хотя бы одного проактивного интента"
