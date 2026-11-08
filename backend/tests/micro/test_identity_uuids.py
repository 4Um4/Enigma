"""
path: /project/backend/tests/micro/test_identity_uuids.py
Назначение: Step 3.1-Identity Fix — три устойчивых UUID (UUID-P, UUID-A, UUID-B).
    Инварианты: player != avatar, player != body, avatar != body.
    Save/load: UUIDs восстанавливаются без регенерации.
    Old save: получает UUIDs при первом запуске.
    Independent ordinal counters: Player и Avatar — разные счётчики.
Зависимости: app.domain.identity_uuids, app.services.avatar.player_intent_formation,
             app.services.avatar.avatar_intent_formation
Запуск: cd backend; $env:DESIRES_ENABLED=1;
        python -m pytest tests/micro/test_identity_uuids.py -v
"""

import copy
import json
import tempfile
from pathlib import Path

from app.domain.avatar_intent_record import AvatarIntentRecord
from app.domain.identity_uuids import IdentityUUIDs
from app.domain.intent_identity import IntentIdentity
from app.models.npc_state import Intent
from app.services.avatar.avatar_intent_formation import (
    get_active_avatar_intent,
    store_avatar_intent,
)
from app.services.avatar.player_intent_formation import (
    get_active_player_intent,
    store_player_intent,
)
from app.services.player_avatar_service import PlayerAvatarService


def _fresh_scene_with_uuids(tick: int = 1) -> tuple[dict, IdentityUUIDs]:
    """scene_state with identity_uuids loaded (production mode)."""
    uuids = IdentityUUIDs.generate_new()
    scene = {
        "tick": tick,
        "intent_ordinals": {},
        "intent_lifecycle": {},
        "identity_uuids": uuids.to_dict(),
    }
    return scene, uuids


def _avatar_record(tick: int = 1) -> AvatarIntentRecord:
    """Build a test AvatarIntentRecord."""
    return AvatarIntentRecord(
        intent=Intent.APPROACH,
        identity=IntentIdentity.for_avatar_initiative("player"),
        desire_ref="desire:food:1",
        target="food_portion",
        formed_tick=tick,
        urgency=0.7,
    )


# ── IdentityUUIDs invariants ───────────────────────────────────────


def test_player_and_avatar_have_different_owner_uuid():
    """1: Player UUID != Avatar UUID."""
    scene, uuids = _fresh_scene_with_uuids()
    assert uuids.player_consciousness != uuids.avatar_consciousness


def test_both_have_same_body_uuid():
    """2: Player body_id == Avatar body_id (общее тело)."""
    scene, uuids = _fresh_scene_with_uuids()
    store_player_intent(scene, "alice", "attack", "goran", 1)
    store_avatar_intent(scene, _avatar_record(), 1)

    player = get_active_player_intent(scene)
    avatar = get_active_avatar_intent(scene)
    assert player is not None
    assert avatar is not None
    assert player["body_id"] == avatar["body_id"]


def test_no_owner_equals_body():
    """3: Ни один owner UUID не совпадает с body UUID."""
    scene, uuids = _fresh_scene_with_uuids()
    store_player_intent(scene, "alice", "attack", "goran", 1)
    store_avatar_intent(scene, _avatar_record(), 1)

    player = get_active_player_intent(scene)
    avatar = get_active_avatar_intent(scene)
    assert player is not None
    assert avatar is not None
    assert player["owner"] != player["body_id"]
    assert avatar["owner"] != avatar["body_id"]


def test_player_and_avatar_owners_differ():
    """4: Player owner UUID != Avatar owner UUID (разные сознания)."""
    scene, uuids = _fresh_scene_with_uuids()
    store_player_intent(scene, "alice", "attack", "goran", 1)
    store_avatar_intent(scene, _avatar_record(), 1)

    player = get_active_player_intent(scene)
    avatar = get_active_avatar_intent(scene)
    assert player is not None
    assert avatar is not None
    assert player["owner"] != avatar["owner"]


def test_player_and_avatar_have_independent_ordinal_counters():
    """5: Player и Avatar — независимые ordinal counters (через UUID owner)."""
    scene, uuids = _fresh_scene_with_uuids()

    store_player_intent(scene, "alice", "attack", "goran", 1)
    store_avatar_intent(scene, _avatar_record(), 1)

    # Separate counters: player=1, avatar=1 (not shared sequential)
    assert scene["intent_ordinals"][uuids.player_consciousness] == 1
    assert scene["intent_ordinals"][uuids.avatar_consciousness] == 1


def test_changing_player_name_does_not_change_identity():
    """6: Изменение player_name не меняет UUID-P (identity stable)."""
    scene, uuids = _fresh_scene_with_uuids()
    store_player_intent(scene, "alice", "attack", "goran", 1)
    active1 = get_active_player_intent(scene)

    # Same action+target → continuity (same intent_id, same owner)
    store_player_intent(scene, "bob", "attack", "goran", 2)
    active2 = get_active_player_intent(scene)

    assert active1["owner"] == active2["owner"]
    assert active2["owner"] == uuids.player_consciousness


def test_intent_continuity_preserved_with_uuids():
    """7: Intent continuity сохраняется с UUID owner."""
    scene, uuids = _fresh_scene_with_uuids()
    id1 = store_player_intent(scene, "alice", "attack", "goran", 1)
    scene["tick"] = 2
    id2 = store_player_intent(scene, "alice", "attack", "goran", 2)
    assert id1 == id2


def test_avatar_continuity_preserved_with_uuids():
    """7b: Avatar Intent continuity сохраняется с UUID owner."""
    scene, uuids = _fresh_scene_with_uuids()
    store_avatar_intent(scene, _avatar_record(tick=1), 1)
    scene["tick"] = 2
    store_avatar_intent(scene, _avatar_record(tick=2), 2)

    entries = [
        e for e in scene["intent_lifecycle"].values()
        if isinstance(e, dict)
        and e.get("control_source") == "avatar_initiative"
    ]
    assert len(entries) == 1


def test_npc_path_not_affected_by_uuids():
    """8: NPC execution path не затронут (only player_input + avatar_initiative)."""
    scene, uuids = _fresh_scene_with_uuids()
    store_player_intent(scene, "alice", "attack", "goran", 1)
    store_avatar_intent(scene, _avatar_record(), 1)

    for entry in scene["intent_lifecycle"].values():
        assert entry["control_source"] in ("player_input", "avatar_initiative")


# ── IdentityUUIDs persistence ──────────────────────────────────────


def test_identity_uuids_survive_save_load():
    """9: Повторная загрузка не меняет UUID."""
    with tempfile.TemporaryDirectory() as tmp:
        svc = PlayerAvatarService(Path(tmp))
        uuids1 = svc.ensure_identity_uuids("camp1", "alice")

        svc2 = PlayerAvatarService(Path(tmp))
        uuids2 = svc2.ensure_identity_uuids("camp1", "alice")

        assert uuids1.player_consciousness == uuids2.player_consciousness
        assert uuids1.avatar_consciousness == uuids2.avatar_consciousness
        assert uuids1.body == uuids2.body


def test_old_save_without_uuids_gets_them_on_first_load():
    """10: Старое сохранение без identity_uuids получает их при первой загрузке."""
    with tempfile.TemporaryDirectory() as tmp:
        camp_dir = Path(tmp) / "camp1"
        camp_dir.mkdir()
        old_data = {
            "sheet": {"name": "alice"},
            "profile": {"character_id": "alice"},
            "state": {"npc_id": "alice"},
        }
        (camp_dir / "player_avatar.json").write_text(
            json.dumps(old_data, ensure_ascii=False), encoding="utf-8"
        )

        svc = PlayerAvatarService(Path(tmp))
        uuids = svc.ensure_identity_uuids("camp1", "alice")

        assert uuids is not None
        assert uuids.player_consciousness != uuids.avatar_consciousness
        assert uuids.player_consciousness != uuids.body

        loaded = json.loads(
            (camp_dir / "player_avatar.json").read_text(encoding="utf-8-sig")
        )
        assert "identity_uuids" in loaded


# ── IdentityUUIDs dataclass validation ─────────────────────────────


def test_identity_uuids_rejects_equal_player_and_avatar():
    """11: IdentityUUIDs rejects player == avatar."""
    import pytest

    with pytest.raises(ValueError):
        IdentityUUIDs("same", "same", "other")


def test_identity_uuids_rejects_player_equals_body():
    """11b: IdentityUUIDs rejects player == body."""
    import pytest

    with pytest.raises(ValueError):
        IdentityUUIDs("p", "a", "p")


def test_identity_uuids_rejects_avatar_equals_body():
    """11c: IdentityUUIDs rejects avatar == body."""
    import pytest

    with pytest.raises(ValueError):
        IdentityUUIDs("p", "b", "b")
        