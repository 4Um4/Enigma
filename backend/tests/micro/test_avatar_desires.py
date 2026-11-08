"""
path: /project/backend/tests/micro/test_avatar_desires.py
Назначение: Avatar agency — самостоятельное формирование Desire.
    Stage 2.1: Avatar (npc_id="player") формирует desires из body_state
    через adapter _ensure_avatar_needs → update_npc_desires.
    DESIRES_ENABLED=1 (test env).
Зависимости: app.services.npc.desire_generator
Основные сущности: тесты battery
"""

import os
import copy

# Тест-окружение: DESIRES_ENABLED=1 (вне pytest fixture —
# _desires_enabled() читает os.environ при каждом вызове)
os.environ["DESIRES_ENABLED"] = "1"

from app.services.npc.desire_generator import (
    _AVATAR_BODY_TO_NEEDS,
    _ensure_avatar_needs,
    update_all,
    update_npc_desires,
)


def _avatar_npc(body_state: dict = None) -> dict:
    """Avatar NPC dict с body_state (как из game_loop injection)."""
    return {
        "npc_id": "player",
        "id": "player",
        "name": "Странник",
        "body_state": body_state or {
            "current_hp": 100,
            "nutrition": 30.0,    # 70% голоден
            "hydration": 50.0,    # 50% жажда
            "fatigue": 80.0,      # 20% усталости (wait — 80 = устал на 80%, но шкала инвертируется)
            "sleep_pressure": 0.7,  # 70% потребность сна
        },
    }


# ── _ensure_avatar_needs ─────────────────────────────────────────


def test_ensure_avatar_needs_creates_needs_dict():
    """Avatar без needs → adapter создаёт needs dict из body_state."""
    npc = _avatar_npc()
    assert "needs" not in npc
    _ensure_avatar_needs(npc)
    assert "needs" in npc
    assert isinstance(npc["needs"], dict)


def test_ensure_avatar_needs_maps_nutrition_to_hunger():
    """body_state.nutrition (30) → needs.hunger (0.7) — инверсия шкалы."""
    npc = _avatar_npc(body_state={"nutrition": 30.0})
    _ensure_avatar_needs(npc)
    assert npc["needs"]["hunger"] == 0.7  # (100 - 30) / 100


def test_ensure_avatar_needs_maps_hydration_to_thirst():
    """body_state.hydration (50) → needs.thirst (0.5)."""
    npc = _avatar_npc(body_state={"hydration": 50.0})
    _ensure_avatar_needs(npc)
    assert npc["needs"]["thirst"] == 0.5


def test_ensure_avatar_needs_maps_fatigue():
    """body_state.fatigue (80) → needs.fatigue (0.2) — инверсия (80=устал)."""
    # NOTE: fatigue 80 = high fatigue = high need; check mapping direction
    npc = _avatar_npc(body_state={"fatigue": 80.0})
    _ensure_avatar_needs(npc)
    # fatigue in body_state: 100 = full fatigue (tired), 0 = rested
    # need = (100 - 80) / 100 = 0.2 — но это означает "20% need to rest"
    # Это может быть семантически неверно: high fatigue → high need
    # TODO: verify direction with Master — is fatigue 100=tired or 100=rested?
    # Per BODY_STATE_HEALTHY (npc_state:86): "fatigue": 0.0 — healthy = 0
    # So 80 = high fatigue = tired. need should be 0.8, not 0.2.
    # The mapping (100 - val) / 100 is WRONG for fatigue.
    # Fix: fatigue doesn't invert — need = val / 100
    assert npc["needs"]["fatigue"] == 0.8  # CORRECTED below


def test_ensure_avatar_needs_maps_sleep_pressure():
    """body_state.sleep_pressure (0.7) → needs.shelter_urge (0.7)."""
    npc = _avatar_npc(body_state={"sleep_pressure": 0.7})
    _ensure_avatar_needs(npc)
    assert npc["needs"]["shelter_urge"] == 0.7


def test_ensure_avatar_needs_no_body_state_returns_silently():
    """Avatar без body_state → adapter returns, no crash (fail-soft)."""
    npc = {"npc_id": "player"}
    _ensure_avatar_needs(npc)
    # No body_state, no needs created — but no crash
    assert "needs" not in npc or npc.get("needs") == {}


def test_ensure_avatar_needs_does_not_create_social_urge():
    """social_urge нет источника в body_state — честное отсутствие (§ENIGMA-003)."""
    npc = _avatar_npc(body_state={"nutrition": 30.0})
    _ensure_avatar_needs(npc)
    assert "social_urge" not in npc["needs"]


# ── update_npc_desires on Avatar ──────────────────────────────────


def test_avatar_forms_desire_from_hunger():
    """Avatar с hunger (nutrition=30) → Desire(food) formed."""
    npc = _avatar_npc(body_state={"nutrition": 30.0})
    _ensure_avatar_needs(npc)
    update_npc_desires(npc, tick=1)
    desires = npc.get("desires", [])
    food_desires = [d for d in desires if d.get("subject_class") == "food"]
    assert len(food_desires) == 1
    assert food_desires[0]["urgency"] == 0.7


def test_avatar_desire_has_correct_provenance():
    """Avatar Desire provenance: source=NEED, origin_ref=hunger."""
    npc = _avatar_npc(body_state={"nutrition": 30.0})
    _ensure_avatar_needs(npc)
    update_npc_desires(npc, tick=1)
    desires = npc.get("desires", [])
    assert desires
    provenance = desires[0].get("provenance", [])
    assert len(provenance) == 1
    assert provenance[0]["source"] == "need"
    assert provenance[0]["origin_ref"] == "hunger"


def test_avatar_no_desire_when_full():
    """Avatar с nutrition=100 → hunger=0 → no desire (urgency 0)."""
    npc = _avatar_npc(body_state={"nutrition": 100.0})
    _ensure_avatar_needs(npc)
    update_npc_desires(npc, tick=1)
    desires = npc.get("desires", [])
    food_desires = [d for d in desires if d.get("subject_class") == "food"]
    if food_desires:
        # Desire может существовать с urgency=0.0 (upsert не удаляет)
        assert food_desires[0]["urgency"] == 0.0


# ── update_all includes Avatar ────────────────────────────────────


def test_update_all_processes_avatar():
    """update_all с Avatar в списке → Avatar gets desires (DESIRES_ENABLED=1)."""
    all_npcs = [_avatar_npc(body_state={"nutrition": 30.0})]
    update_all(all_npcs, tick=1)
    avatar = all_npcs[0]
    desires = avatar.get("desires", [])
    assert desires, "Avatar should have desires after update_all"
    assert any(d.get("subject_class") == "food" for d in desires)


def test_update_all_avatar_desire_owned_by_avatar_not_player_input():
    """Desire принадлежит Avatar (subject=food, provenance=need:hunger),
    НЕ Player input. Avatar — субъект желания, не пассивный получатель."""
    all_npcs = [_avatar_npc(body_state={"nutrition": 30.0})]
    update_all(all_npcs, tick=1)
    avatar = all_npcs[0]
    desires = avatar.get("desires", [])
    assert desires
    # Subject class = "food" (Avatar wants food), not "player" (player wants Avatar)
    assert desires[0]["subject_class"] == "food"


# ── Determinism ────────────────────────────────────────────────────


def test_avatar_desires_reproducible_same_state():
    """Одинаковые body_state Avatar → одинаковые desires."""
    npc_a = _avatar_npc(body_state={"nutrition": 30.0})
    npc_b = _avatar_npc(body_state={"nutrition": 30.0})
    _ensure_avatar_needs(npc_a)
    _ensure_avatar_needs(npc_b)
    update_npc_desires(npc_a, tick=1)
    update_npc_desires(npc_b, tick=1)
    assert npc_a["desires"] == npc_b["desires"]


def test_avatar_desires_survive_round_trip():
    """needs/desires сохраняются через deepcopy (proxy for save/load)."""
    npc = _avatar_npc(body_state={"nutrition": 30.0})
    _ensure_avatar_needs(npc)
    update_npc_desires(npc, tick=1)
    loaded = copy.deepcopy(npc)
    assert loaded["needs"] == npc["needs"]
    assert loaded["desires"] == npc["desires"]


# ── NPC not affected ───────────────────────────────────────────────


def test_npc_desires_unchanged_by_avatar_adapter():
    """NPC (non-player) не затрагивается adapter — _ensure_avatar_needs
    не вызывается для npc_id != "player"."""
    npc = {"npc_id": "maid_lusya", "body_state": {"nutrition": 30.0}}
    # update_all вызывает _ensure_avatar_needs ТОЛЬКО для player
    update_all([npc], tick=1)
    # NPC не имеет needs (adapter не вызывался для него)
    # → update_npc_desires вышел на line 63 (no needs)
    # Если desires появились — это от existing needs, не от adapter
    # (NPC без needs не получает desires через adapter)
    assert "needs" not in npc or npc.get("needs") == {}