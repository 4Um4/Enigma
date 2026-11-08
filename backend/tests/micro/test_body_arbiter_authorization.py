"""
path: /project/backend/tests/micro/test_body_arbiter_authorization.py
Назначение: Step 3.2 Stage B — тесты BodyArbiter authorization.
Зависимости: app.services.body_arbiter
Запуск: cd backend; $env:DESIRES_ENABLED=1;
        python -m pytest tests/micro/test_body_arbiter_authorization.py -v
"""

import os

os.environ["DESIRES_ENABLED"] = "1"

from app.domain.arbitration import ArbitrationVerdict, CompatibilityClass
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
    """Store Avatar Intent using a valid Intent enum member."""
    record = AvatarIntentRecord(
        intent=Intent[action.upper()],
        identity=IntentIdentity.for_avatar_initiative("player"),
        desire_ref="desire:test:1",
        target=target,
        formed_tick=tick,
        urgency=0.7,
    )
    store_avatar_intent(scene, record, tick)


def _store_raw_avatar_intent(scene: dict, action: str, target: str = "x", tick: int = 1) -> None:
    """Store Avatar Intent directly in lifecycle (for unknown/invalid actions)."""
    from app.services.events.event_identity import intent_id_str, next_intent_identity
    lifecycle = scene.setdefault("intent_lifecycle", {})
    uuids_data = scene.get("identity_uuids", {})
    from app.domain.identity_uuids import IdentityUUIDs as IU
    uuids = IU.from_dict(uuids_data) if uuids_data else None
    owner = uuids.avatar_consciousness if uuids else "player"
    body = uuids.body if uuids else "player"
    _tick_id, _ordinal = next_intent_identity(scene, owner, action)
    _intent_id = intent_id_str(_tick_id, owner, action, _ordinal)
    lifecycle[_intent_id] = {
        "intent_id": _intent_id,
        "owner": owner,
        "body_id": body,
        "control_source": "avatar_initiative",
        "action": action,
        "target": target,
        "desire_ref": "desire:test:1",
        "urgency": 0.5,
        "lifecycle_state": "ACTIVE",
        "arbitration_result": "PENDING",
        "execution_status": "NOT_EXECUTED",
        "created_tick": tick,
        "transitioned_tick": tick,
    }


# ── No intent scenarios ────────────────────────────────────────────


def test_no_player_intent_avatar_authorized():
    scene, uuids = _fresh_scene_with_uuids()
    _store_avatar_intent(scene, "approach", "food", 1)
    arb = BodyArbiter()
    result = arb.authorize(scene, tick=1)
    assert result.player_decision == AuthorizationDecision.DEFERRED
    assert result.avatar_decision == AuthorizationDecision.AUTHORIZED


def test_no_avatar_intent_player_authorized():
    scene, uuids = _fresh_scene_with_uuids()
    _store_player(scene, "attack", "goran", 1)
    arb = BodyArbiter()
    result = arb.authorize(scene, tick=1)
    assert result.player_decision == AuthorizationDecision.AUTHORIZED
    assert result.avatar_decision == AuthorizationDecision.DEFERRED


def test_no_intents_both_deferred():
    scene, uuids = _fresh_scene_with_uuids()
    arb = BodyArbiter()
    result = arb.authorize(scene, tick=1)
    assert result.player_decision == AuthorizationDecision.DEFERRED
    assert result.avatar_decision == AuthorizationDecision.DEFERRED


# ── Compatible intents ─────────────────────────────────────────────


def test_compatible_intents_both_authorized():
    scene, uuids = _fresh_scene_with_uuids()
    _store_player(scene, "flee", "east", 1)
    _store_avatar_intent(scene, "talk", "goran", 1)
    arb = BodyArbiter()
    result = arb.authorize(scene, tick=1)
    assert result.compatibility == CompatibilityClass.COMPATIBLE
    assert result.player_decision == AuthorizationDecision.AUTHORIZED
    assert result.avatar_decision == AuthorizationDecision.AUTHORIZED


# ── Conflict (DEFERRED, no winner) ────────────────────────────────


def test_conflict_both_deferred_no_winner():
    scene, uuids = _fresh_scene_with_uuids()
    _store_player(scene, "flee", "east", 1)
    _store_avatar_intent(scene, "flee", "west", 1)
    arb = BodyArbiter()
    result = arb.authorize(scene, tick=1)
    assert result.compatibility == CompatibilityClass.CONFLICT
    assert result.player_decision == AuthorizationDecision.DEFERRED
    assert result.avatar_decision == AuthorizationDecision.DEFERRED
    assert result.conflict_type == "B"


# ── UNKNOWN (DEFERRED) ─────────────────────────────────────────────


def test_unknown_compatibility_both_deferred():
    scene, uuids = _fresh_scene_with_uuids()
    _store_player(scene, "unknown_action", "x", 1)
    _store_raw_avatar_intent(scene, "another_unknown", "y", 1)
    arb = BodyArbiter()
    result = arb.authorize(scene, tick=1)
    assert result.compatibility == CompatibilityClass.UNKNOWN
    assert result.player_decision == AuthorizationDecision.DEFERRED
    assert result.avatar_decision == AuthorizationDecision.DEFERRED


def test_unknown_does_not_fail_both():
    """UNKNOWN не приводит к FAIL_BOTH — неизвестность не запрет."""
    scene, uuids = _fresh_scene_with_uuids()
    _store_player(scene, "unknown_action", "x", 1)
    _store_raw_avatar_intent(scene, "another_unknown", "y", 1)

    arb = BodyArbiter()
    result = arb.authorize(scene, tick=1)

    assert result.compatibility == CompatibilityClass.UNKNOWN
    assert result.verdict != ArbitrationVerdict.FAIL_BOTH
    assert result.verdict == ArbitrationVerdict.DEFER_BOTH
    assert result.player_decision == AuthorizationDecision.DEFERRED
    assert result.avatar_decision == AuthorizationDecision.DEFERRED

# ── CONDITIONAL / CONFLICT with different targets ─────────────────


def test_conditional_both_deferred():
    scene, uuids = _fresh_scene_with_uuids()
    _store_player(scene, "steal", "target_a", 1)
    _store_avatar_intent(scene, "steal", "target_b", 1)
    arb = BodyArbiter()
    result = arb.authorize(scene, tick=1)
    assert result.compatibility == CompatibilityClass.CONFLICT
    assert result.player_decision == AuthorizationDecision.DEFERRED


# ── Lifecycle write ────────────────────────────────────────────────


def test_authorized_written_to_lifecycle():
    scene, uuids = _fresh_scene_with_uuids()
    _store_player(scene, "attack", "goran", 1)
    arb = BodyArbiter()
    arb.authorize(scene, tick=1)
    player = get_active_player_intent(scene)
    assert player["arbitration_result"] == "AUTHORIZED"


def test_deferred_written_to_lifecycle():
    scene, uuids = _fresh_scene_with_uuids()
    _store_player(scene, "flee", "east", 1)
    _store_avatar_intent(scene, "flee", "west", 1)
    arb = BodyArbiter()
    arb.authorize(scene, tick=1)
    player = get_active_player_intent(scene)
    avatar = get_active_avatar_intent(scene)
    assert player["arbitration_result"] == "DEFERRED"
    assert avatar["arbitration_result"] == "DEFERRED"


def test_rejected_not_written_unless_fail_both():
    scene, uuids = _fresh_scene_with_uuids()
    _store_player(scene, "flee", "east", 1)
    _store_avatar_intent(scene, "flee", "west", 1)
    arb = BodyArbiter()
    result = arb.authorize(scene, tick=1)
    assert result.player_decision == AuthorizationDecision.DEFERRED
    assert result.avatar_decision == AuthorizationDecision.DEFERRED


# ── Repeated arbitration ───────────────────────────────────────────


def test_repeated_arbitration_overwrites_result():
    scene, uuids = _fresh_scene_with_uuids()
    _store_player(scene, "attack", "goran", 1)
    arb = BodyArbiter()
    result1 = arb.authorize(scene, tick=1)
    assert result1.player_decision == AuthorizationDecision.AUTHORIZED
    _store_avatar_intent(scene, "attack", "borko", 1)
    result2 = arb.authorize(scene, tick=2)
    assert result2.player_decision == AuthorizationDecision.DEFERRED
    player = get_active_player_intent(scene)
    assert player["arbitration_result"] == "DEFERRED"


def test_arbitration_reset_on_new_tick():
    scene, uuids = _fresh_scene_with_uuids()
    _store_player(scene, "attack", "goran", 1)
    _store_avatar_intent(scene, "observe", "food", 1)
    arb = BodyArbiter()
    result1 = arb.authorize(scene, tick=1)
    assert result1.player_decision == AuthorizationDecision.AUTHORIZED
    assert result1.avatar_decision == AuthorizationDecision.AUTHORIZED
    voided_avatar_intents(scene, tick=2)
    result2 = arb.authorize(scene, tick=2)
    assert result2.player_decision == AuthorizationDecision.AUTHORIZED
    assert result2.avatar_decision == AuthorizationDecision.DEFERRED


# ── No side effects ────────────────────────────────────────────────


def test_no_social_action_published():
    scene, uuids = _fresh_scene_with_uuids()
    _store_player(scene, "attack", "goran", 1)
    arb = BodyArbiter()
    arb.authorize(scene, tick=1)
    assert "events" not in scene or len(scene.get("events", [])) == 0


def test_no_stm_write():
    scene, uuids = _fresh_scene_with_uuids()
    _store_player(scene, "talk", "goran", 1)
    arb = BodyArbiter()
    arb.authorize(scene, tick=1)
    assert "stm" not in scene or len(scene.get("stm", [])) == 0


def test_no_physical_damage():
    scene, uuids = _fresh_scene_with_uuids()
    _store_player(scene, "attack", "goran", 1)
    arb = BodyArbiter()
    arb.authorize(scene, tick=1)
    assert "body_state_changes" not in scene


# ── UUID independence ───────────────────────────────────────────────


def test_player_and_avatar_owners_differ_same_body():
    scene, uuids = _fresh_scene_with_uuids()
    _store_player(scene, "attack", "goran", 1)
    _store_avatar_intent(scene, "approach", "food", 1)
    arb = BodyArbiter()
    arb.authorize(scene, tick=1)
    player = get_active_player_intent(scene)
    avatar = get_active_avatar_intent(scene)
    assert player["owner"] != avatar["owner"]
    assert player["body_id"] == avatar["body_id"]
    assert player["owner"] != player["body_id"]
    assert avatar["owner"] != avatar["body_id"]


# ── Effect status preserved ────────────────────────────────────────


def test_effect_status_not_reset_by_arbitration():
    scene, uuids = _fresh_scene_with_uuids()
    _store_player(scene, "attack", "goran", 1)
    arb = BodyArbiter()
    arb.authorize(scene, tick=1)
    player = get_active_player_intent(scene)
    player["effect_status"] = {"stm_write": "COMPLETED"}
    arb.authorize(scene, tick=2)
    player2 = get_active_player_intent(scene)
    assert player2["effect_status"]["stm_write"] == "COMPLETED"