# path: /project/backend/tests/gameplay/test_2bii_causal_addressee.py
# Назначение: 2b-ii (санкция Мастера, ревью SOCIAL): причинный адресат
#     в целеполагании _resolve_target — ступень 1.5 между явной целью
#     и резолвером близости. Контракт порядка: event.target_id >
#     causal_addressee > SocialTargetResolver > fallback. Лечит
#     intent-without-target системно (находка R7, Stage-1-валидатор).
# Зависимости: app.services.npc.decision_hub.DecisionHub
# Основные сущности: test_causal_addressee_beats_proximity_fallback,
#     test_explicit_target_beats_causal, test_self_addressee_ignored
# Запуск: cd backend; python -m pytest tests/gameplay/test_2bii_causal_addressee.py -v -s

from unittest.mock import MagicMock

from app.services.npc.decision_hub import DecisionHub


def _hub(addressee):
    hub = DecisionHub(rng=MagicMock())
    hub._rel_store = None
    hub._campaign_id = "t"
    hub._causal_addressee = addressee
    return hub


def _state(npc_id="hungry_npc"):
    s = MagicMock()
    s.npc_id = npc_id
    return s


def _event(target_id=None, event_type="WORLD_TICK", actor="somebody"):
    e = MagicMock()
    e.target_id = target_id
    e.event_type = event_type
    e.actor_id = actor
    return e


def _resolve(hub, intent="trade", event=None):
    return hub._resolve_target(
        intent=intent,
        event=event or _event(),
        state=_state(),
        spatial_query=None,
        all_npc_ids=[],
        pending_response_target=None,
        epistemic_context=None,
    )


def test_causal_addressee_beats_proximity_fallback():
    """Причина знает цель: голодный trade → tavern_keeper_tornin,
    даже когда резолверу некого найти (изоляция — кейс p7_e1)."""
    assert _resolve(_hub("tavern_keeper_tornin")) == "tavern_keeper_tornin"


def test_explicit_target_beats_causal():
    """Реактивность выше причины: явная цель события побеждает."""
    res = _resolve(
        _hub("tavern_keeper_tornin"),
        event=_event(target_id="player", event_type="PLAYER_ATTACKED"),
    )
    assert res == "player"


def test_self_addressee_ignored():
    """Адресат == сам агент (защита от самотаргетинга)."""
    res = _resolve(_hub("hungry_npc"))
    assert res != "hungry_npc"