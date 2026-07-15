# backend/tests/test_state_applicator_pipeline.py
# python -m pytest backend/tests/test_state_applicator_pipeline.py -v --tb=short
"""
Интеграционный тест: замкнутый цикл
DecisionHub → StateApplicator → NPCState.write_to_legacy → dict обновлён
"""

from unittest.mock import MagicMock

from app.domain.identity_events import EffectiveDrives

_MOCK_DRIVES = EffectiveDrives.from_dict({"control": 0.5, "significance": 0.5, "fear": 0.5, "desire": 0.5})

from app.models.npc_state import EmotionTag, Intent, NPCState, WillState
from app.models.state_delta import DeltaDomain, EmotionPayload
from app.services.npc.decision_hub import DecisionResult, StateDeltas
from app.services.npc.state_applicator import StateApplicator


def test_pipeline_stress_increases_in_dict():
    """Стресс NPC должен увеличиться в legacy dict после StateApplicator."""
    # 1. Исходное состояние
    state = NPCState(
        npc_id="test_npc",
        stress=10.0,
        emotion=EmotionTag.NEUTRAL,
        will_state=WillState.FREE,
    )

    # 2. stress_delta — INPUT (запрашиваемое изменение), не stress_delta_effective (OUTPUT)
    deltas = StateDeltas(
        npc_id="test_npc",
        domain=DeltaDomain.EMOTION,
        payload=EmotionPayload(stress_delta=15.0),
    )
    result = DecisionResult(
        npc_id="test_npc",
        intent=Intent.FLEE,
        intent_target="player",
        score=0.8,
        deltas=[deltas],
        scores_trace={},
        narrative_fact=None,
    )

    # 3. StateApplicator (мок для relationship_store)
    mock_rel = MagicMock()
    applicator = StateApplicator(relationship_store=mock_rel)
    new_state = applicator.apply(
        state=state,
        result=result,
        campaign_id="test_campaign",
    )

    # 4. Проверяем что stress увеличился
    assert new_state.stress > 10.0, f"Expected stress > 10.0, got {new_state.stress}"

    # 5. Записываем в legacy dict
    legacy_dict = {
        "id": "test_npc",
        "psyche": {"stress": 10, "state": "free", "trauma_flags": []},
        "social_stats": {"trust": 0.5, "fear_of_player": 0.0, "debt": 0},
    }
    NPCState.write_to_legacy(new_state, legacy_dict)

    # 6. Проверяем что legacy dict обновлён
    assert legacy_dict["psyche"]["stress"] > 10.0


def test_pipeline_intent_written_to_dict():
    """Intent NPC должен записаться в legacy dict."""
    state = NPCState(
        npc_id="test_npc",
        stress=0.0,
        will_state=WillState.FREE,
    )

    deltas = StateDeltas()
    result = DecisionResult(
        npc_id="test_npc",
        intent=Intent.FLEE,
        intent_target="player",
        score=0.8,
        deltas=[deltas],
        scores_trace={},
        narrative_fact=None,
    )

    applicator = StateApplicator(relationship_store=MagicMock())
    new_state = applicator.apply(state=state, result=result, campaign_id="test")

    # Intent должен быть установлен
    assert new_state.intent == Intent.FLEE
