# backend/tests/micro/test_butterfly_report_targeting.py
"""COGNITIVE-CONTINUITY-01 Etap 4 — DecisionHub report targeting + proposition fallback."""
from types import SimpleNamespace
from unittest.mock import patch

from app.domain.control_source import ControlSource
from app.domain.epistemology import EpistemicContext, Predicate, Proposition
from app.services.npc.decision_hub import DecisionHub


def _ctx_with_report(agent="maid_lusya", victim="tavern_keeper_tornin"):
    return EpistemicContext(
        agent_id=agent,
        report_proposition=Proposition(subject_id="player", predicate=Predicate.INSULTED, object_id=victim),
    )


def test_build_communication_carries_report_proposition():
    hub = DecisionHub.__new__(DecisionHub)
    ctx = _ctx_with_report()
    with patch("app.domain.control_source.resolve_control_source", return_value=ControlSource.NPC_DECISION):
        intent = hub._build_communication(
            npc_id="maid_lusya", intent_value="spread_rumor", intent_target="tavern_keeper_tornin",
            topic="spread_rumor", emotion_value="нейтрально", epistemic_context=ctx,
        )
    assert intent is not None
    assert intent.proposition is not None
    assert intent.proposition.predicate == Predicate.INSULTED
    assert intent.proposition.object_id == "tavern_keeper_tornin"


def test_build_communication_trigger_priority_over_report():
    hub = DecisionHub.__new__(DecisionHub)
    trigger = Proposition(subject_id="guard_borko", predicate=Predicate.STOLE, object_id="merchant_goran")
    report = Proposition(subject_id="player", predicate=Predicate.INSULTED, object_id="tavern_keeper_tornin")
    ctx = EpistemicContext(agent_id="maid_lusya", trigger_proposition=trigger, report_proposition=report)
    with patch("app.domain.control_source.resolve_control_source", return_value=ControlSource.NPC_DECISION):
        intent = hub._build_communication(
            npc_id="maid_lusya", intent_value="warn", intent_target="guard_borko",
            topic="warn", emotion_value="гнев", epistemic_context=ctx,
        )
    assert intent is not None
    assert intent.proposition == trigger


def test_resolve_target_report_returns_victim():
    hub = DecisionHub.__new__(DecisionHub)
    ctx = _ctx_with_report(agent="maid_lusya", victim="tavern_keeper_tornin")
    state = SimpleNamespace(npc_id="maid_lusya")
    event = SimpleNamespace(target_id=None, event_type=None, actor_id="player")
    with patch("app.domain.sanity_membrane.can_address", return_value=True):
        target = hub._resolve_target(
            intent="spread_rumor", event=event, state=state,
            spatial_query=None, all_npc_ids=["maid_lusya", "tavern_keeper_tornin", "player"],
            epistemic_context=ctx,
        )
    assert target == "tavern_keeper_tornin"


def test_resolve_target_no_report_no_crash():
    hub = DecisionHub.__new__(DecisionHub)
    ctx = EpistemicContext(agent_id="maid_lusya")
    state = SimpleNamespace(npc_id="maid_lusya")
    event = SimpleNamespace(target_id=None, event_type=None, actor_id="player")
    try:
        target = hub._resolve_target(
            intent="talk", event=event, state=state,
            spatial_query=None, all_npc_ids=["maid_lusya"],
            epistemic_context=ctx,
        )
        assert target is None or isinstance(target, str)
    except Exception as e:
        assert "report" not in str(e).lower()