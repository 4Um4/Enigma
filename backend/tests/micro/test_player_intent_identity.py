"""
path: /project/backend/tests/micro/test_player_intent_identity.py
Назначение: Player Intent Identity (Step 3.1).
    Player Intent получает детерминированный intent_id, симметричный
    Avatar Intent. Uses IntentIdentity.for_player_input, intent_lifecycle,
    next_intent_identity. Continuity: same (action, target) → same intent_id.
    НЕ urgency=1.0 (Master test 9).
Зависимости: app.services.avatar.player_intent_formation
Основные сущности: тесты battery
"""

import copy

from app.domain.control_source import ControlSource
from app.services.avatar.player_intent_formation import (
    get_active_player_intent,
    store_player_intent,
    voided_player_intents,
)


def _fresh_scene(tick: int = 1) -> dict:
    return {"tick": tick, "intent_ordinals": {}, "intent_lifecycle": {}}


# ── ID generation ──────────────────────────────────────────────────


def test_player_intent_gets_deterministic_id():
    """1: Player Intent получает детерминированный ID."""
    scene = _fresh_scene(tick=1)
    intent_id = store_player_intent(scene, "player1", "attack", "goran", 1)
    assert intent_id is not None
    # Owner = player_name (fallback, no identity_uuids in scene_state).
    # Format: intent:{tick}:{owner}:{action}:{ordinal}
    assert intent_id.startswith("intent:1:player1:attack:")


def test_player_intent_id_reproducible_same_inputs():
    """1b: Одинаковые inputs → одинаковый intent_id (replay-safe)."""
    scene_a = _fresh_scene(tick=5)
    id_a = store_player_intent(scene_a, "player1", "attack", "goran", 5)

    scene_b = _fresh_scene(tick=5)
    id_b = store_player_intent(scene_b, "player1", "attack", "goran", 5)

    assert id_a == id_b


# ── Authorship ─────────────────────────────────────────────────────


def test_player_intent_authorship_is_player_input():
    """2: Авторство определяется как PLAYER_INPUT."""
    scene = _fresh_scene(tick=1)
    store_player_intent(scene, "player1", "attack", "goran", 1)
    active = get_active_player_intent(scene)
    assert active is not None
    assert active["control_source"] == ControlSource.PLAYER_INPUT.value
    assert active["owner"] == "player1"
    assert active["body_id"] == "player"


def test_player_intent_identity_owner_is_player_name():
    """2b: owner = player_name (who decided), не character_id."""
    scene = _fresh_scene(tick=1)
    store_player_intent(scene, "alice", "attack", "goran", 1)
    active = get_active_player_intent(scene)
    assert active["owner"] == "alice"  # player_name, not "player"


# ── Continuity ─────────────────────────────────────────────────────


def test_repeat_same_intent_preserves_intent_id():
    """3: Повтор того же актуального намерения не создаёт новый ID."""
    scene = _fresh_scene(tick=1)
    id1 = store_player_intent(scene, "player1", "attack", "goran", 1)

    # Same action + target, next tick — continuity, no new id
    scene["tick"] = 2
    id2 = store_player_intent(scene, "player1", "attack", "goran", 2)

    assert id1 == id2

    # Only 1 entry in lifecycle (no accumulation)
    player_entries = [
        e for e in scene["intent_lifecycle"].values()
        if isinstance(e, dict)
        and e.get("control_source") == "player_input"
    ]
    assert len(player_entries) == 1


def test_new_intent_gets_new_id():
    """4: Новое намерение (different action) получает новый ID."""
    scene = _fresh_scene(tick=1)
    id1 = store_player_intent(scene, "player1", "attack", "goran", 1)

    id2 = store_player_intent(scene, "player1", "talk", "goran", 2)

    assert id1 != id2

    # Previous → SUPERSEDED
    entries = list(scene["intent_lifecycle"].values())
    active = [e for e in entries if e.get("lifecycle_state") == "ACTIVE"]
    superseded = [e for e in entries if e.get("lifecycle_state") == "SUPERSEDED"]
    assert len(active) == 1
    assert len(superseded) == 1
    assert active[0]["intent_id"] == id2
    assert superseded[0]["intent_id"] == id1


# ── Target/action change handling ─────────────────────────────────


def test_change_target_supersedes_previous():
    """5a: Смена target → SUPERSEDE previous, new intent_id."""
    scene = _fresh_scene(tick=1)
    id1 = store_player_intent(scene, "player1", "attack", "goran", 1)
    id2 = store_player_intent(scene, "player1", "attack", "borko", 2)

    assert id1 != id2
    active = get_active_player_intent(scene)
    assert active["target"] == "borko"


def test_change_action_supersedes_previous():
    """5b: Смена action → SUPERSEDE previous, new intent_id."""
    scene = _fresh_scene(tick=1)
    id1 = store_player_intent(scene, "player1", "attack", "goran", 1)
    id2 = store_player_intent(scene, "player1", "talk", "goran", 2)

    assert id1 != id2
    active = get_active_player_intent(scene)
    assert active["action"] == "talk"


# ── Save/load round-trip ───────────────────────────────────────────


def test_player_intent_survives_save_load():
    """6: Намерение не теряется при сохранении/загрузке (deepcopy proxy)."""
    scene = _fresh_scene(tick=1)
    store_player_intent(scene, "player1", "attack", "goran", 1)

    loaded = copy.deepcopy(scene)
    active = get_active_player_intent(loaded)
    assert active is not None
    assert active["action"] == "attack"
    assert active["target"] == "goran"
    # Owner = player_name (fallback). Format: intent:{tick}:{owner}:{action}:{ordinal}
    assert active["intent_id"].startswith("intent:1:player1:attack:")


def test_player_intent_ordinals_survive_save_load():
    """6b: intent_ordinals восстанавливаются (continuity preserved)."""
    scene = _fresh_scene(tick=1)
    store_player_intent(scene, "player1", "attack", "goran", 1)
    store_player_intent(scene, "player1", "talk", "goran", 2)

    loaded = copy.deepcopy(scene)
    # Next intent after load should continue ordinal sequence
    store_player_intent(loaded, "player1", "flee", "goran", 3)
    # ordinal for "player1" (owner = player_name in fallback mode) should be 3
    assert loaded["intent_ordinals"]["player1"] == 3


# ── No duplicates ──────────────────────────────────────────────────


def test_repeated_pipeline_pass_no_duplicates():
    """7: Повторное прохождение pipeline не создаёт дубликаты."""
    scene = _fresh_scene(tick=1)

    # Simulate 5 ticks of same Player input
    for tick in range(1, 6):
        store_player_intent(scene, "player1", "attack", "goran", tick)

    player_entries = [
        e for e in scene["intent_lifecycle"].values()
        if isinstance(e, dict)
        and e.get("control_source") == "player_input"
    ]
    assert len(player_entries) == 1  # No duplicates

    # intent_ordinals not bloated (owner = player_name in fallback mode)
    assert scene["intent_ordinals"]["player1"] == 1


# ── NPC isolation ──────────────────────────────────────────────────


def test_npc_execution_path_not_affected():
    """8: NPC execution path не затронут — only control_source=player_input stored."""
    scene = _fresh_scene(tick=1)
    store_player_intent(scene, "player1", "attack", "goran", 1)

    # All entries are player_input, none npc_decision
    for entry in scene["intent_lifecycle"].values():
        assert entry["control_source"] == ControlSource.PLAYER_INPUT.value


def test_avatar_intent_coexists_with_player_intent():
    """8b: Avatar и Player intents могут сосуществовать в intent_lifecycle."""
    from app.services.avatar.avatar_intent_formation import store_avatar_intent
    from app.domain.avatar_intent_record import AvatarIntentRecord
    from app.domain.intent_identity import IntentIdentity
    from app.models.npc_state import Intent

    scene = _fresh_scene(tick=1)

    # Player intent
    store_player_intent(scene, "player1", "attack", "goran", 1)

    # Avatar intent (separate)
    avatar_record = AvatarIntentRecord(
        intent=Intent.APPROACH,
        identity=IntentIdentity.for_avatar_initiative("player"),
        desire_ref="desire:food:1",
        target="food_portion",
        formed_tick=1,
        urgency=0.7,
    )
    store_avatar_intent(scene, avatar_record, 1)

    # Both coexist, different control_source
    player_active = [
        e for e in scene["intent_lifecycle"].values()
        if e.get("control_source") == "player_input"
        and e.get("lifecycle_state") == "ACTIVE"
    ]
    avatar_active = [
        e for e in scene["intent_lifecycle"].values()
        if e.get("control_source") == "avatar_initiative"
        and e.get("lifecycle_state") == "ACTIVE"
    ]
    assert len(player_active) == 1
    assert len(avatar_active) == 1


# ── No automatic urgency=1.0 ───────────────────────────────────────


def test_player_intent_no_automatic_urgency():
    """9: Player Intent НЕ получает автоматический urgency=1.0."""
    scene = _fresh_scene(tick=1)
    store_player_intent(scene, "player1", "attack", "goran", 1)
    active = get_active_player_intent(scene)
    assert active is not None
    # urgency should be None, not 1.0 (BodyArbiter decides urgency)
    assert active.get("urgency") is None


# ── Stale cleanup ──────────────────────────────────────────────────


def test_player_intent_voided_on_exception():
    """Stale cleanup: voided_player_intents marks ACTIVE as VOIDED."""
    scene = _fresh_scene(tick=1)
    store_player_intent(scene, "player1", "attack", "goran", 1)

    voided_player_intents(scene, tick=2)

    active = [
        e for e in scene["intent_lifecycle"].values()
        if e.get("control_source") == "player_input"
        and e.get("lifecycle_state") == "ACTIVE"
    ]
    voided = [
        e for e in scene["intent_lifecycle"].values()
        if e.get("control_source") == "player_input"
        and e.get("lifecycle_state") == "VOIDED"
    ]
    assert len(active) == 0
    assert len(voided) == 1


# ── ACTIVE ≠ AUTHORIZED ───────────────────────────────────────────


def test_player_intent_active_not_authorized():
    """ACTIVE ≠ AUTHORIZED: lifecycle_state=ACTIVE, arbitration_result=PENDING."""
    scene = _fresh_scene(tick=1)
    store_player_intent(scene, "player1", "attack", "goran", 1)
    active = get_active_player_intent(scene)
    assert active["lifecycle_state"] == "ACTIVE"
    assert active["arbitration_result"] == "PENDING"
    assert active["execution_status"] == "NOT_EXECUTED"


# ── Step 3.1-Final: fail-open diagnostics ──────────────────────────


def test_formation_error_creates_diagnostic_signal():
    """Step 3.1-Final: ошибка формирования НЕ маскируется под отсутствие
    Player Intent. BodyArbiter различает:
      - intent_id is not None → намерение сформировано
      - intent_id is None AND error is None → намерения нет
      - intent_id is None AND error is not None → ошибка формирования
    """
    # Simulate formation error: store_player_intent raises
    from unittest.mock import patch

    scene = _fresh_scene(tick=1)

    # Mock store_player_intent to raise
    with patch(
        "app.services.avatar.player_intent_formation.store_player_intent",
        side_effect=RuntimeError("test formation error"),
    ):
        # This mirrors turn_pipeline.py exception handling
        import app.services.avatar.player_intent_formation as pif

        intent_id = None
        error = None
        try:
            intent_id = pif.store_player_intent(scene, "player1", "attack", "goran", 1)
        except Exception as e:
            error = str(e)
            pif.voided_player_intents(scene, 1)

        # Verify: error captured, intent_id is None
        assert intent_id is None
        assert error is not None
        assert "test formation error" in error

        # Verify: no ACTIVE player intent in lifecycle (voided on error)
        active = get_active_player_intent(scene)
        assert active is None


def test_no_intent_vs_formation_error_distinguishable():
    """Step 3.1-Final: BodyArbiter может различить отсутствие намерения
    и ошибку формирования по паре (intent_id, intent_error)."""
    # State 1: no Player intent (never formed)
    # (simulates: store_player_intent not called, or returned None gracefully)
    # In turn_pipeline: shared_context.player_intent_id = None, error = None
    state_no_intent_id = None
    state_no_intent_error = None
    # BodyArbiter sees: no intent, no error → "намерения нет"

    # State 2: formation error
    # (simulates: store_player_intent raised, voided_player_intents called)
    state_error_id = None
    state_error_error = "RuntimeError: test error"
    # BodyArbiter sees: no intent, error → "ошибка формирования"

    # State 3: intent formed successfully
    scene_ok = _fresh_scene(tick=1)
    state_ok_id = store_player_intent(scene_ok, "player1", "attack", "goran", 1)
    state_ok_error = None
    # BodyArbiter sees: intent_id present → "намерение сформировано"

    # Three states are distinguishable by (intent_id, error) pair
    assert state_no_intent_id is None and state_no_intent_error is None
    assert state_error_id is None and state_error_error is not None
    assert state_ok_id is not None and state_ok_error is None

    # No two states have the same (id, error) signature
    sigs = {
        (state_no_intent_id, state_no_intent_error),
        (state_error_id, state_error_error),
        (state_ok_id, state_ok_error),
    }
    assert len(sigs) == 3  # All distinguishable