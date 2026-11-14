from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.domain.communication import CommunicationIntent, ExposureLevel
from app.domain.execution import TaskKind, TaskPriority, TaskState
from app.domain.intent_profile import ActionType, IntentSemanticField
from app.domain.intent_profiles import (
    requires_dialogue_context,
    requires_llm_materialization,
)
from app.services.game_loop.phase_1_input import (
    project_intent_to_hub_event,
    resolve_player_intent,
)
from app.services.game_loop.game_loop import (
    _append_direct_reply_reactions,
    _filter_direct_reply_rce_reactions,
)
from app.services.npc.decision_hub import DecisionHub, EventContext
from app.services.npc.npc_tick_pipeline import _ensure_direct_player_reply
from app.services.game_loop.task_scheduler import TaskScheduler


_NPC_ID = "tavern_keeper_tornin"


def _dialogue_resolution(target: str):
    return resolve_player_intent(
        raw_action="говорю с Торнином",
        action_type="player_interacts",
        target=target,
        player_dict=None,
        scene_context=None,
        semantic_field=IntentSemanticField(
            action=ActionType.DIALOGUE,
            raw_text="говорю с Торнином",
            target="Торнин" if target else "",
        ),
    )


def _event(
    *,
    event_type: str = "player_interacts",
    target_id: str | None = _NPC_ID,
    semantic_action: str = "DIALOGUE",
) -> EventContext:
    return EventContext(
        event_type=event_type,
        actor_id="player",
        target_id=target_id,
        semantic_action=semantic_action,
        payload={
            "target_id": target_id,
            "semantic_action": semantic_action,
        },
    )


def test_hub_event_uses_canonical_intent_target_not_deprecated_parameter():
    resolution = _dialogue_resolution(_NPC_ID)
    assert resolution.original_intent.parameters.target_id == ""

    projected = project_intent_to_hub_event(
        EventContext(
            event_type="player_interacts",
            actor_id="player",
            target_id="stale_target",
            payload={"target_id": "stale_target", "preserved": True},
        ),
        resolution,
    )

    assert projected.target_id == _NPC_ID
    assert projected.payload["target_id"] == _NPC_ID
    assert projected.semantic_action == "DIALOGUE"
    assert projected.payload["preserved"] is True


def test_unresolved_intent_clears_stale_hub_target():
    projected = project_intent_to_hub_event(
        _event(target_id="stale_target"),
        _dialogue_resolution(""),
    )

    assert projected.target_id is None
    assert "target_id" not in projected.payload


def test_explicit_player_dialogue_does_not_fabricate_reply_without_decision():
    state = SimpleNamespace(
        hub_event=_event(),
        raw_input="Привет, Торнин!",
    )
    intents = []

    _ensure_direct_player_reply(
        state, _NPC_ID, SimpleNamespace(emotion="curious"), intents
    )

    assert intents == []


def test_direct_player_dialogue_routes_npc_verbal_intent_to_player():
    hub = DecisionHub.__new__(DecisionHub)
    state = SimpleNamespace(npc_id=_NPC_ID)

    resolved_target = hub._resolve_target(
        intent="talk",
        event=_event(),
        state=state,
    )

    assert resolved_target == "player"


def test_explicit_player_dialogue_normalizes_decision_created_reply():
    state = SimpleNamespace(
        hub_event=_event(),
        raw_input="Привет, Торнин!",
    )
    existing_npc_to_npc = CommunicationIntent(
        speaker=_NPC_ID,
        audience="maid_lusya",
        topic="работа",
        intent_type="talk",
        emotional_state="нейтрально",
        exposure_level=ExposureLevel.from_semantic("normal"),
    )
    decision_reply = CommunicationIntent(
        speaker=_NPC_ID,
        audience="player",
        topic="исходная тема",
        intent_type="talk",
        emotional_state="curious",
        exposure_level=ExposureLevel.from_semantic("normal"),
    )
    intents = [existing_npc_to_npc, decision_reply]

    _ensure_direct_player_reply(
        state, _NPC_ID, SimpleNamespace(emotion="curious"), intents
    )
    _ensure_direct_player_reply(
        state, _NPC_ID, SimpleNamespace(emotion="curious"), intents
    )

    assert len(intents) == 2
    assert intents[0] is existing_npc_to_npc
    reply = intents[1]
    assert reply.speaker == _NPC_ID
    assert reply.audience == "player"
    assert reply.target_id == "player"
    assert reply.intent_type == "player_reply"
    assert reply.topic == "Привет, Торнин!"


@pytest.mark.parametrize(
    "event_type,target_id,semantic_action",
    [
        ("player_interacts", None, "DIALOGUE"),
        ("player_interacts", _NPC_ID, "MOVE"),
        ("world_tick", _NPC_ID, "DIALOGUE"),
        ("player_interacts", "maid_lusya", "DIALOGUE"),
    ],
)
def test_nonverbal_idle_or_other_target_does_not_create_reply(
    event_type, target_id, semantic_action
):
    state = SimpleNamespace(
        hub_event=_event(
            event_type=event_type,
            target_id=target_id,
            semantic_action=semantic_action,
        ),
        raw_input="действие игрока",
    )
    intents = []

    _ensure_direct_player_reply(
        state,
        _NPC_ID,
        SimpleNamespace(emotion="neutral"),
        intents,
    )

    assert intents == []


def test_player_reply_is_first_turn_llm_dialogue_without_stm_requirement():
    assert requires_llm_materialization("player_reply") is True
    assert requires_dialogue_context("player_reply") is False


def test_rce_reply_from_addressed_npc_is_not_duplicated():
    reactions = [
        "Торнин Серебряная Луна: Старый ответ из повествования.",
        "tavern_keeper_tornin: ещё одна старая реплика",
        "Люся: Я здесь.",
    ]

    filtered = _filter_direct_reply_rce_reactions(
        reactions,
        _NPC_ID,
        "Торнин Серебряная Луна",
    )

    assert filtered == ["Люся: Я здесь."]


def test_direct_reply_is_exposed_as_named_ui_reaction():
    dm_result = {"npc_reactions": []}

    _append_direct_reply_reactions(
        dm_result,
        [
            {"speaker_id": _NPC_ID, "text": "Я тебя слушаю."},
            {"speaker_id": "maid_lusya", "text": "Не мне."},
        ],
        _NPC_ID,
        None,
        [{"npc_id": _NPC_ID, "name": "Торнин Серебряная Луна"}],
    )

    assert dm_result["npc_reactions"] == [
        "Торнин Серебряная Луна: Я тебя слушаю."
    ]


@pytest.mark.parametrize(
    "reply_text,expected_count",
    [
        ("Здравствуй, игрок.", 1),
        ("", 0),
        ("   \n\t", 0),
    ],
)
def test_player_reply_is_materialized_and_delivered_to_player(
    monkeypatch, reply_text, expected_count
):
    class EventBus:
        def __init__(self):
            self.events = []

        def publish(self, event):
            self.events.append(event)

    bus = EventBus()
    monkeypatch.setattr(
        "app.services.game_loop.task_scheduler.get_event_bus",
        lambda: bus,
    )
    router = MagicMock()
    router.request_for_agent.return_value = reply_text
    scheduler = TaskScheduler(
        router=router,
        context_provider=lambda campaign_id, npc_id: {"name": "Торнин"},
    )
    task = {
        "task_id": "player-reply-1",
        "tick": 3,
        "counter": 0,
        "kind": TaskKind.DIALOGUE.value,
        "priority": TaskPriority.NORMAL.value,
        "state": TaskState.PENDING.value,
        "creator_system": "DecisionHub",
        "owner_id": _NPC_ID,
        "target_ids": ["player"],
        "payload": {
            "topic": "Привет, Торнин!",
            "target_id": "player",
            "exposure_semantic": "normal",
            "intent_type": "player_reply",
            "emotional_state": "нейтрально",
            "npc_npc_context": "",
            "thread_id": "thread-player-reply",
            "prepared_prompt": "",
            "proposition": None,
        },
        "created_tick": 3,
    }
    scene = {
        "campaign_id": "test_campaign",
        "tick": 3,
        "game_time_seconds": 180.0,
        "pending_tasks": [task],
    }

    delivered = scheduler.execute_pending(scene, "test_campaign")

    assert len(delivered) == expected_count
    assert len(scene.get("recent_dialogues", [])) == expected_count
    assert len(bus.events) == expected_count
    if expected_count:
        assert delivered[0]["speaker_id"] == _NPC_ID
        assert delivered[0]["target_id"] == "player"
        assert delivered[0]["text"] == reply_text
        assert scene["recent_dialogues"][0]["speaker_id"] == _NPC_ID
        assert scene["recent_dialogues"][0]["target_id"] == "player"
        assert bus.events[0].type == "npc_spoke"
        assert bus.events[0].source == _NPC_ID
        assert bus.events[0].payload["target_id"] == "player"
    assert scene["pending_tasks"] == []

    scheduler._executor_pool.shutdown(wait=True)
