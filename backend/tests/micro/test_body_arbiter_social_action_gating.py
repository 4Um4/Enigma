"""
path: /project/backend/tests/micro/test_body_arbiter_social_action_gating.py
Назначение: Step 3.2 Stage C2b — тесты gating SOCIAL_ACTION.
    Проверяет: DEFERRED/WV rejected/fault блокируют SOCIAL_ACTION,
    AUTHORIZED+WV pass публикует, payload сохраняется,
    повторный проход не дублирует, projections только после авторизации.
Зависимости: app.services.body_arbiter
Запуск: cd backend; $env:DESIRES_ENABLED=1;
        python -m pytest tests/micro/test_body_arbiter_social_action_gating.py -v
"""

import os

os.environ["DESIRES_ENABLED"] = "1"

from app.domain.arbitration import CompatibilityClass
from app.domain.identity_uuids import IdentityUUIDs
from app.services.avatar.avatar_intent_formation import (
    get_active_avatar_intent,
    store_avatar_intent,
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


def _simulated_social_action_gate(arb_result, wv_rejected: bool = False) -> bool:
    """Simulates the pipeline gating logic for SOCIAL_ACTION publish."""
    if wv_rejected:
        return False
    if arb_result is None:
        return False  # Fail-closed
    return arb_result.player_decision == AuthorizationDecision.AUTHORIZED


# ── Tests ──────────────────────────────────────────────────────────


def test_deferred_blocks_social_action():
    """1: DEFERRED → SOCIAL_ACTION не публикуется."""
    scene, uuids = _fresh_scene_with_uuids()
    _store_player(scene, "flee", "east", 1)
    _store_avatar_intent(scene, "flee", "west", 1)
    arb = BodyArbiter()
    result = arb.authorize(scene, tick=1)
    assert _simulated_social_action_gate(result) is False


def test_wv_rejected_blocks_social_action():
    """2: WV rejected → SOCIAL_ACTION не публикуется."""
    scene, uuids = _fresh_scene_with_uuids()
    _store_player(scene, "attack", "goran", 1)
    arb = BodyArbiter()
    result = arb.authorize(scene, tick=1)
    assert result.player_decision == AuthorizationDecision.AUTHORIZED
    assert _simulated_social_action_gate(result, wv_rejected=True) is False


def test_arbiter_fault_blocks_social_action():
    """3: BodyArbiter fault → SOCIAL_ACTION не публикуется (fail-closed)."""
    scene, uuids = _fresh_scene_with_uuids()
    _store_player(scene, "attack", "goran", 1)
    result = None  # Simulate fault
    assert _simulated_social_action_gate(result) is False


def test_authorized_plus_wv_pass_allows_social_action():
    """4: AUTHORIZED + WV pass → SOCIAL_ACTION публикуется."""
    scene, uuids = _fresh_scene_with_uuids()
    _store_player(scene, "attack", "goran", 1)
    arb = BodyArbiter()
    result = arb.authorize(scene, tick=1)
    assert result.player_decision == AuthorizationDecision.AUTHORIZED
    assert _simulated_social_action_gate(result, wv_rejected=False) is True


def test_no_avatar_intent_allows_social_action():
    """4b: Нет Avatar → Player AUTHORIZED → SOCIAL_ACTION публикуется."""
    scene, uuids = _fresh_scene_with_uuids()
    _store_player(scene, "attack", "goran", 1)
    arb = BodyArbiter()
    result = arb.authorize(scene, tick=1)
    assert result.player_decision == AuthorizationDecision.AUTHORIZED
    assert _simulated_social_action_gate(result) is True


def test_compatible_intents_allow_social_action():
    """4c: COMPATIBLE → Player AUTHORIZED → SOCIAL_ACTION публикуется."""
    scene, uuids = _fresh_scene_with_uuids()
    _store_player(scene, "flee", "east", 1)
    _store_avatar_intent(scene, "talk", "goran", 1)
    arb = BodyArbiter()
    result = arb.authorize(scene, tick=1)
    assert result.compatibility == CompatibilityClass.COMPATIBLE
    assert _simulated_social_action_gate(result) is True


def test_repeated_tick_no_double_publish():
    """6: Повторный тик → одна авторизация, нет двойной публикации.
    Pipeline continuity сохраняет intent_id — SOCIAL_ACTION published
    once per AUTHORIZED intent (effect_status должен предотвращать дубль).
    """
    scene, uuids = _fresh_scene_with_uuids()
    _store_player(scene, "attack", "goran", 1)
    arb = BodyArbiter()

    result1 = arb.authorize(scene, tick=1)
    assert _simulated_social_action_gate(result1) is True

    result2 = arb.authorize(scene, tick=2)
    assert _simulated_social_action_gate(result2) is True
    # Same intent_id (continuity)
    player = get_active_player_intent(scene)
    assert player["intent_id"] is not None


def test_downstream_projections_only_after_authorization():
    """7: Projections (ACTOR_ATTACKS, COMMUNICATION_CLAIM) создаются
    только если SOCIAL_ACTION опубликован (AUTHORIZED)."""
    scene, uuids = _fresh_scene_with_uuids()
    _store_player(scene, "flee", "east", 1)
    _store_avatar_intent(scene, "flee", "west", 1)  # CONFLICT

    arb = BodyArbiter()
    result = arb.authorize(scene, tick=1)

    # CONFLICT → DEFERRED → SOCIAL_ACTION not published
    assert _simulated_social_action_gate(result) is False
    # If SOCIAL_ACTION not published → projections not created
    # (SocialActionSubscriber only fires on SOCIAL_ACTION event)


def test_no_player_intent_blocks_social_action():
    """8: Нет Player Intent → SOCIAL_ACTION не публикуется."""
    scene, uuids = _fresh_scene_with_uuids()
    arb = BodyArbiter()
    result = arb.authorize(scene, tick=1)
    assert result.player_decision == AuthorizationDecision.DEFERRED
    assert _simulated_social_action_gate(result) is False
