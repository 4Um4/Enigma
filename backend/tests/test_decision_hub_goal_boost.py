# backend/tests/test_decision_hub_goal_boost.py
"""
Smoke-тест: Проверяет, что долгосрочная цель (goal) даёт буст к проактивным интентам.
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
def profile_with_goal() -> NPCProfileL0:
    return NPCProfileL0(
        id="test_npc",
        name="Тестовый NPC",
        tier="major",
        drives_base={"control": 0.4, "significance": 0.3, "fear": 0.1, "desire": 0.6},
        psyche_base=PsycheBase(willpower=70, breakpoint=80, loyalty_base=50),
        voice_profile="Тестовый голос",
        goal="Стать главой гильдии"
    )

@pytest.fixture
def profile_without_goal() -> NPCProfileL0:
    return NPCProfileL0(
        id="test_npc",
        name="Тестовый NPC",
        tier="major",
        drives_base={"control": 0.4, "significance": 0.3, "fear": 0.1, "desire": 0.6},
        psyche_base=PsycheBase(willpower=70, breakpoint=80, loyalty_base=50),
        voice_profile="Тестовый голос",
        goal=""
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
        profile_with_goal: NPCProfileL0,
        profile_without_goal: NPCProfileL0,
        world_tick_event: EventContext
    ):
        """Если есть goal, скор проактивных интентов должен быть выше."""
        state = NPCState(npc_id="test_npc", will_state=WillState.FREE, emotion=EmotionTag.NEUTRAL)

        from app.domain.identity_events import EffectiveDrives
        # Используем эффективные драйвы (равные базовым для теста)
        effective_drives = EffectiveDrives.from_dict(profile_with_goal.drives_base)

        result_with_goal = hub.compute(
            state=state,
            personality=profile_with_goal,
            effective_drives=effective_drives,
            event=world_tick_event
        )

        result_without_goal = hub.compute(
            state=state,
            personality=profile_without_goal,
            effective_drives=effective_drives,
            event=world_tick_event
        )

        # Проверяем, что хотя бы один проактивный интент получил буст
        proactive_intents = ["block_path", "ambush", "seek_ally", "offer_job", "request_service", "spread_rumor", "call_for_help", "change_role"]

        boosted_count = 0
        for intent in proactive_intents:
            score_with = result_with_goal.scores_trace.get(intent, 0.0)
            score_without = result_without_goal.scores_trace.get(intent, 0.0)
            if score_with > score_without:
                boosted_count += 1

        assert boosted_count > 0, "Наличие цели (goal) должно увеличивать скор хотя бы одного проактивного интента"
