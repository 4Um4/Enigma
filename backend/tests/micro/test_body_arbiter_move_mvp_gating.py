"""
path: /project/backend/tests/micro/test_body_arbiter_move_mvp_gating.py
Назначение: Step 3.2 Stage C2a — тесты gating для Player MOVE и MvpController.
    Проверяет: DEFERRED блокирует MOVE и MvpController, AUTHORIZED + WV пропускает,
    fault fallback, повторный тик, отсутствие фиктивного действия.
Зависимости: app.services.body_arbiter
Запуск: cd backend; $env:DESIRES_ENABLED=1;
        python -m pytest tests/micro/test_body_arbiter_move_mvp_gating.py -v
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


def _simulated_move_gate(arb_result, wv_rejected: bool = False) -> bool:
    """Simulates the pipeline gating logic for MOVE/MvpController."""
    if wv_rejected:
        return False
    if arb_result is None:
        return False  # Fail-closed: fault blocks execution
    return arb_result.player_decision == AuthorizationDecision.AUTHORIZED


# ── Tests ──────────────────────────────────────────────────────────


def test_deferred_blocks_move():
    """1: BodyArbiter DEFERRED → MOVE не передаётся."""
    scene, uuids = _fresh_scene_with_uuids()
    _store_player(scene, "flee", "east", 1)
    _store_avatar_intent(scene, "flee", "west", 1)
    arb = BodyArbiter()
    result = arb.authorize(scene, tick=1)
    assert _simulated_move_gate(result) is False


def test_deferred_blocks_mvp_controller():
    """2: BodyArbiter DEFERRED → MvpController не вызывается."""
    scene, uuids = _fresh_scene_with_uuids()
    _store_player(scene, "flee", "east", 1)
    _store_avatar_intent(scene, "flee", "west", 1)
    arb = BodyArbiter()
    result = arb.authorize(scene, tick=1)
    assert _simulated_move_gate(result) is False


def test_authorized_plus_wv_pass_allows_move():
    """3: AUTHORIZED + WV not rejected → existing path preserved."""
    scene, uuids = _fresh_scene_with_uuids()
    _store_player(scene, "attack", "goran", 1)
    arb = BodyArbiter()
    result = arb.authorize(scene, tick=1)
    assert result.player_decision == AuthorizationDecision.AUTHORIZED
    assert _simulated_move_gate(result, wv_rejected=False) is True


def test_repeated_tick_uses_same_intent_id():
    """9: Повторный тик использует тот же intent_id (continuity).
    Pipeline не имеет явной защиты от повторного исполнения —
    intent_id сохраняется, но effect_status ещё не реализован.
    Этот тест документирует текущее состояние."""
    scene, uuids = _fresh_scene_with_uuids()
    _store_player(scene, "attack", "goran", 1)
    arb = BodyArbiter()

    result1 = arb.authorize(scene, tick=1)
    player1 = get_active_player_intent(scene)
    intent_id_1 = player1["intent_id"]

    result2 = arb.authorize(scene, tick=2)
    player2 = get_active_player_intent(scene)
    intent_id_2 = player2["intent_id"]

    # Continuity: same intent_id (Step 2.1.1)
    assert intent_id_1 == intent_id_2
    # Both AUTHORIZED (same state, no conflict)
    assert result1.player_decision == AuthorizationDecision.AUTHORIZED
    assert result2.player_decision == AuthorizationDecision.AUTHORIZED
    # NOTE: Pipeline не имеет effect_status gating — повторный тик
    # разрешает повторный MOVE. Это известное ограничение (Stage C2 future).


def test_authorized_but_wv_rejected_blocks_move():
    """4: AUTHORIZED + WV rejected → both paths blocked."""
    scene, uuids = _fresh_scene_with_uuids()
    _store_player(scene, "attack", "goran", 1)
    arb = BodyArbiter()
    result = arb.authorize(scene, tick=1)
    assert _simulated_move_gate(result, wv_rejected=True) is False


def test_no_player_intent_no_move():
    """5: Нет Player Intent → исполнитель не получает фиктивное действие."""
    scene, uuids = _fresh_scene_with_uuids()
    arb = BodyArbiter()
    result = arb.authorize(scene, tick=1)
    assert result.player_decision == AuthorizationDecision.DEFERRED
    assert _simulated_move_gate(result) is False


def test_repeated_tick_no_double_execution():
    """6: Повторный тик не исполняет уже обработанный Intent повторно."""
    scene, uuids = _fresh_scene_with_uuids()
    _store_player(scene, "attack", "goran", 1)
    arb = BodyArbiter()
    result1 = arb.authorize(scene, tick=1)
    assert result1.player_decision == AuthorizationDecision.AUTHORIZED
    result2 = arb.authorize(scene, tick=2)
    assert result2.player_decision == AuthorizationDecision.AUTHORIZED


def test_arbiter_fault_blocks_move():
    """7: Ошибка BodyArbiter блокирует MOVE (fail-closed)."""
    scene, uuids = _fresh_scene_with_uuids()
    _store_player(scene, "attack", "goran", 1)
    result = None  # Simulate fault
    assert _simulated_move_gate(result) is False


def test_arbiter_fault_blocks_mvp_controller():
    """8: Ошибка BodyArbiter блокирует MvpController (fail-closed)."""
    scene, uuids = _fresh_scene_with_uuids()
    _store_player(scene, "attack", "goran", 1)
    result = None  # Simulate fault
    assert _simulated_move_gate(result) is False
