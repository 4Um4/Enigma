"""
path: /project/backend/tests/micro/test_body_arbiter_pipeline_integration.py
Назначение: Step 3.2 Stage C — интеграция BodyArbiter с Player pipeline.
    Проверяет gating publish_classified_player_event.
Зависимости: app.services.body_arbiter
Запуск: cd backend; $env:DESIRES_ENABLED=1;
        python -m pytest tests/micro/test_body_arbiter_pipeline_integration.py -v
"""

import os

os.environ["DESIRES_ENABLED"] = "1"

from app.domain.arbitration import CompatibilityClass
from app.domain.identity_uuids import IdentityUUIDs
from app.services.avatar.avatar_intent_formation import (
    get_active_avatar_intent,
    store_avatar_intent,
    voided_avatar_intents,
)
from app.domain.avatar_intent_record import AvatarIntentRecord
from app.domain.intent_identity import IntentIdentity
from app.models.npc_state import Intent
from app.services.avatar.player_intent_formation import (
    get_active_player_intent,
    store_player_intent,
)
from app.services.body_arbiter import AuthorizationDecision, BodyArbiter


def _fresh_scene_with_uuids(tick: int = 1) -> tuple[dict, IdentityUUIDs]:
    uuids = IdentityUUIDs.generate_new()
    scene = {
        "tick": tick,
        "intent_ordinals": {},
        "intent_lifecycle": {},
        "identity_uuids": uuids.to_dict(),
    }
    return scene, uuids


def _store_player(scene: dict, action: str = "attack", target: str = "goran", tick: int = 1) -> str:
    return store_player_intent(scene, "alice", action, target, tick)


def _store_avatar_intent(scene: dict, action: str = "approach", target: str = "food", tick: int = 1) -> None:
    record = AvatarIntentRecord(
        intent=Intent[action.upper()],
        identity=IntentIdentity.for_avatar_initiative("player"),
        desire_ref="desire:test:1",
        target=target,
        formed_tick=tick,
        urgency=0.7,
    )
    store_avatar_intent(scene, record, tick)


# ── Pipeline gating logic (simulated) ──────────────────────────────


def _is_publish_authorized(scene: dict, arb_result) -> bool:
    """Simulates the pipeline gating logic from turn_pipeline.py:838."""
    if arb_result is None:
        return True  # Fallback: BodyArbiter not run, use existing gate

    return arb_result.player_decision == AuthorizationDecision.AUTHORIZED


# ── Tests ──────────────────────────────────────────────────────────


def test_no_avatar_intent_player_authorized_for_publish():
    """Нет Avatar → Player AUTHORIZED → publish allowed."""
    scene, uuids = _fresh_scene_with_uuids()
    _store_player(scene, "attack", "goran", 1)

    arb = BodyArbiter()
    result = arb.authorize(scene, tick=1)

    assert _is_publish_authorized(scene, result) is True


def test_compatible_intents_player_authorized_for_publish():
    """COMPATIBLE → Player AUTHORIZED → publish allowed."""
    scene, uuids = _fresh_scene_with_uuids()
    _store_player(scene, "flee", "east", 1)
    _store_avatar_intent(scene, "talk", "goran", 1)

    arb = BodyArbiter()
    result = arb.authorize(scene, tick=1)

    assert _is_publish_authorized(scene, result) is True


def test_conflict_player_deferred_publish_blocked():
    """CONFLICT → Player DEFERRED → publish blocked."""
    scene, uuids = _fresh_scene_with_uuids()
    _store_player(scene, "flee", "east", 1)
    _store_avatar_intent(scene, "flee", "west", 1)

    arb = BodyArbiter()
    result = arb.authorize(scene, tick=1)

    assert _is_publish_authorized(scene, result) is False


def test_unknown_player_deferred_publish_blocked():
    """UNKNOWN → Player DEFERRED → publish blocked."""
    scene, uuids = _fresh_scene_with_uuids()
    # Store raw player intent with unknown action
    from app.services.events.event_identity import intent_id_str, next_intent_identity
    lifecycle = scene.setdefault("intent_lifecycle", {})
    owner = uuids.player_consciousness
    body = uuids.body
    _t, _o = next_intent_identity(scene, owner, "unknown_action")
    _id = intent_id_str(_t, owner, "unknown_action", _o)
    lifecycle[_id] = {
        "intent_id": _id, "owner": owner, "body_id": body,
        "control_source": "player_input", "action": "unknown_action",
        "target": "x", "desire_ref": None, "urgency": None,
        "lifecycle_state": "ACTIVE", "arbitration_result": "PENDING",
        "execution_status": "NOT_EXECUTED", "created_tick": 1, "transitioned_tick": 1,
    }
    _store_avatar_intent(scene, "observe", "y", 1)

    arb = BodyArbiter()
    result = arb.authorize(scene, tick=1)

    assert result.compatibility == CompatibilityClass.UNKNOWN
    assert _is_publish_authorized(scene, result) is False


def test_arbiter_fault_fallback_allows_publish():
    """BodyArbiter fault → fallback → publish allowed (existing gate)."""
    scene, uuids = _fresh_scene_with_uuids()
    _store_player(scene, "attack", "goran", 1)

    # Simulate fault: arb_result is None
    result = None

    assert _is_publish_authorized(scene, result) is True


def test_authorized_written_before_publish():
    """AUTHORIZED записывается в lifecycle до publish."""
    scene, uuids = _fresh_scene_with_uuids()
    _store_player(scene, "attack", "goran", 1)

    arb = BodyArbiter()
    arb.authorize(scene, tick=1)

    player = get_active_player_intent(scene)
    assert player["arbitration_result"] == "AUTHORIZED"


def test_deferred_written_when_blocked():
    """DEFERRED записывается в lifecycle when blocked."""
    scene, uuids = _fresh_scene_with_uuids()
    _store_player(scene, "flee", "east", 1)
    _store_avatar_intent(scene, "flee", "west", 1)

    arb = BodyArbiter()
    arb.authorize(scene, tick=1)

    player = get_active_player_intent(scene)
    assert player["arbitration_result"] == "DEFERRED"