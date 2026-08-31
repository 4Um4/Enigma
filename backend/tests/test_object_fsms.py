"""
path: backend/tests/test_object_fsms.py
Назначение: Тесты W3 Object FSM. Гварды: ТЗ §22.1-точность
    (LOCKED/BROKEN без CLOSE), О1 NO_OP, О7 структурный вердикт
    (REJECT всегда с reason), О2 chair-политика над отношениями,
    авто-release-запрет, О6 damage-закон, терминальность DESTROYED.
Зависимости: pytest, app.domain.object_fsms, app.domain.world_object,
    app.domain.semantic_action, app.services.world.world_object_store
"""
import pytest
from app.domain.object_fsms import (
    TransitionVerdict,
    damage_object,
    transition_object,
)
from app.domain.semantic_action import WorldActionType
from app.domain.world_object import build_world_object
from app.services.world.world_object_store import WorldObjectStore


def _door(state: str):
    return build_world_object(
        "door_1", "door", "loc_1", (1.0, 1.0), state=state)


def _chair():
    return build_world_object(
        "chair_1", "chair", "loc_1", (1.0, 1.0), state="AVAILABLE")


def _container(state: str):
    return build_world_object(
        "box_1", "container", "loc_1", (1.0, 1.0), state=state)


# ── door ────────────────────────────────────────────────────────────

def test_door_open_closed():
    res = transition_object(_door("CLOSED"), WorldActionType.OPEN)
    assert res.verdict == TransitionVerdict.PASS
    assert res.new_obj.state == "OPEN"
    res2 = transition_object(res.new_obj, WorldActionType.CLOSE)
    assert res2.verdict == TransitionVerdict.PASS
    assert res2.new_obj.state == "CLOSED"


def test_door_no_op_open():
    res = transition_object(_door("OPEN"), WorldActionType.OPEN)
    assert res.verdict == TransitionVerdict.NO_OP
    assert res.new_obj is not None and res.new_obj.state == "OPEN"


def test_door_lock_unlock():
    res = transition_object(_door("CLOSED"), WorldActionType.LOCK)
    assert res.verdict == TransitionVerdict.PASS
    assert res.new_obj.state == "LOCKED"
    res2 = transition_object(res.new_obj, WorldActionType.UNLOCK)
    assert res2.verdict == TransitionVerdict.PASS
    assert res2.new_obj.state == "CLOSED"


def test_door_close_from_locked_rejected():
    """ТЗ §22.1: LOCKED→CLOSED только через UNLOCK."""
    res = transition_object(_door("LOCKED"), WorldActionType.CLOSE)
    assert res.verdict == TransitionVerdict.REJECT
    assert res.reason
    assert res.new_obj is None


def test_door_break_repair_resets_damage():
    res = transition_object(_door("CLOSED"), WorldActionType.BREAK)
    assert res.verdict == TransitionVerdict.PASS
    assert res.new_obj.state == "BROKEN"
    assert res.new_obj.damage == 1.0
    res2 = transition_object(res.new_obj, WorldActionType.REPAIR)
    assert res2.verdict == TransitionVerdict.PASS
    assert res2.new_obj.state == "CLOSED"
    assert res2.new_obj.damage == 0.0


def test_door_open_from_broken_keeps_damage():
    """ТЗ §22.1: BROKEN→OPEN легален; damage-track — физика (О6)."""
    broken = transition_object(
        _door("CLOSED"), WorldActionType.BREAK).new_obj
    res = transition_object(broken, WorldActionType.OPEN)
    assert res.verdict == TransitionVerdict.PASS
    assert res.new_obj.state == "OPEN"
    assert res.new_obj.damage == 1.0


# ── container ───────────────────────────────────────────────────────

def test_container_no_op_open():
    res = transition_object(_container("OPEN"), WorldActionType.OPEN)
    assert res.verdict == TransitionVerdict.NO_OP


def test_container_destroyed_terminal():
    res = transition_object(_container("DESTROYED"), WorldActionType.OPEN)
    assert res.verdict == TransitionVerdict.REJECT
    res2 = transition_object(
        _container("DESTROYED"), WorldActionType.REPAIR)
    assert res2.verdict == TransitionVerdict.REJECT


# ── chair (О2: политика над отношениями) ────────────────────────────

def test_chair_sit_stand_up():
    res = transition_object(_chair(), WorldActionType.SIT, actor_id="npc_1")
    assert res.verdict == TransitionVerdict.PASS
    assert res.new_obj.occupancy == "npc_1"
    res2 = transition_object(res.new_obj, WorldActionType.STAND_UP)
    assert res2.verdict == TransitionVerdict.PASS
    assert res2.new_obj.occupancy is None


def test_chair_sit_occupied_rejected():
    sat = transition_object(
        _chair(), WorldActionType.SIT, actor_id="npc_1").new_obj
    res = transition_object(sat, WorldActionType.SIT, actor_id="npc_2")
    assert res.verdict == TransitionVerdict.REJECT
    assert "OCCUPIED" in res.reason


def test_chair_take_occupied_rejected():
    """ТЗ §22.1: OCCUPIED→{AVAILABLE} — взять занятое нельзя."""
    sat = transition_object(
        _chair(), WorldActionType.SIT, actor_id="npc_1").new_obj
    res = transition_object(sat, WorldActionType.TAKE, actor_id="npc_2")
    assert res.verdict == TransitionVerdict.REJECT


def test_chair_break_occupied_rejected():
    sat = transition_object(
        _chair(), WorldActionType.SIT, actor_id="npc_1").new_obj
    res = transition_object(sat, WorldActionType.BREAK)
    assert res.verdict == TransitionVerdict.REJECT
    assert "OCCUPIED" in res.reason


def test_chair_take_drop():
    res = transition_object(_chair(), WorldActionType.TAKE, actor_id="npc_1")
    assert res.verdict == TransitionVerdict.PASS
    assert res.new_obj.holder == "npc_1"
    res2 = transition_object(res.new_obj, WorldActionType.DROP)
    assert res2.verdict == TransitionVerdict.PASS
    assert res2.new_obj.holder is None


def test_chair_drop_not_held_rejected():
    res = transition_object(_chair(), WorldActionType.DROP)
    assert res.verdict == TransitionVerdict.REJECT
    assert "NOT_HELD" in res.reason


def test_chair_stand_up_not_occupied_rejected():
    res = transition_object(_chair(), WorldActionType.STAND_UP)
    assert res.verdict == TransitionVerdict.REJECT
    assert "NOT_OCCUPIED" in res.reason


def test_chair_break_then_repair_preserves_relations():
    """Auto-release запрещён (ADR-O-371): held-сломанный-починенный
    проецируется как HELD — модель W1 богаче ТЗ (О2)."""
    held = transition_object(
        _chair(), WorldActionType.TAKE, actor_id="npc_1").new_obj
    broken = transition_object(held, WorldActionType.BREAK)
    assert broken.verdict == TransitionVerdict.PASS
    assert broken.new_obj.state == "BROKEN"
    assert broken.new_obj.damage == 1.0
    assert broken.new_obj.holder == "npc_1"
    repaired = transition_object(broken.new_obj, WorldActionType.REPAIR)
    assert repaired.verdict == TransitionVerdict.PASS
    assert repaired.new_obj.state == "AVAILABLE"
    assert repaired.new_obj.holder == "npc_1"


def test_chair_move_is_spatial_rejected():
    """О3: MOVED — legacy; перемещение = relocate, не FSM."""
    res = transition_object(_chair(), WorldActionType.MOVE)
    assert res.verdict == TransitionVerdict.REJECT
    assert res.reason == "SPATIAL_OPERATION"


def test_unknown_archetype_rejected():
    """О4: bed — до W4 честный отказ."""
    bed = build_world_object("bed_1", "bed", "loc_1", (1.0, 1.0))
    res = transition_object(bed, WorldActionType.OPEN)
    assert res.verdict == TransitionVerdict.REJECT
    assert "UNKNOWN_ARCHETYPE" in res.reason


# ── damage (О6) ─────────────────────────────────────────────────────

def test_damage_object_to_broken():
    new_door = damage_object(_door("CLOSED"), 1.0)
    assert new_door.state == "BROKEN"
    assert new_door.damage == 1.0


def test_damage_accumulates():
    mid = damage_object(_door("CLOSED"), 0.4)
    assert mid.state == "CLOSED"
    assert abs(mid.damage - 0.4) < 1e-9
    full = damage_object(mid, 0.7)
    assert full.damage == 1.0
    assert full.state == "BROKEN"


def test_damage_negative_raises():
    with pytest.raises(ValueError):
        damage_object(_door("CLOSED"), -0.5)


# ── О6 (вердикт Мастера): archetype-specific damage policy ──────────

def test_damage_container_to_destroyed():
    """ТЗ §22.1: терминальное состояние container — DESTROYED, не BROKEN."""
    new_box = damage_object(_container("CLOSED"), 1.0)
    assert new_box.state == "DESTROYED"
    assert new_box.damage == 1.0


def test_damage_door_still_broken():
    new_door = damage_object(_door("CLOSED"), 1.0)
    assert new_door.state == "BROKEN"


# ── О8 (вердикт Мастера): факт перехода + topology-контракт ────────

def test_transition_result_carries_old_state():
    res = transition_object(_door("CLOSED"), WorldActionType.OPEN)
    assert res.old_state == "CLOSED"
    assert res.new_obj.state == "OPEN"


def test_topology_effect_door_pass_only():
    door_res = transition_object(_door("CLOSED"), WorldActionType.OPEN)
    assert door_res.topology_effect is True
    chair_res = transition_object(
        _chair(), WorldActionType.SIT, actor_id="npc_1")
    assert chair_res.topology_effect is False
    reject_res = transition_object(_door("LOCKED"), WorldActionType.CLOSE)
    assert reject_res.topology_effect is False
    noop_res = transition_object(_door("OPEN"), WorldActionType.OPEN)
    assert noop_res.topology_effect is False
    assert noop_res.old_state == "OPEN"



# ── О7/L4: структурный вердикт ──────────────────────────────────────

def test_reject_always_carries_reason():
    rejects = [
        transition_object(_door("LOCKED"), WorldActionType.CLOSE),
        transition_object(_chair(), WorldActionType.DROP),
        transition_object(_container("DESTROYED"), WorldActionType.OPEN),
        transition_object(
            build_world_object("bed_1", "bed", "loc_1", (1.0, 1.0)),
            WorldActionType.SIT),
    ]
    for res in rejects:
        assert res.verdict == TransitionVerdict.REJECT
        assert res.reason, f"REJECT без причины = тихий отказ (L4): {res}"
        assert res.new_obj is None


# ── store (apply: домен → scene_state) ─────────────────────────────

def test_store_apply_transition():
    scene_state: dict = {"world_objects": {}}
    WorldObjectStore.spawn(
        scene_state, "door_1", "door", "loc_1", (1.0, 1.0),
        state="CLOSED")
    res = WorldObjectStore.apply_transition(
        scene_state, "door_1", WorldActionType.OPEN)
    assert res.verdict == TransitionVerdict.PASS
    assert WorldObjectStore.get(scene_state, "door_1").state == "OPEN"


def test_store_apply_transition_reject_does_not_mutate():
    scene_state: dict = {"world_objects": {}}
    WorldObjectStore.spawn(
        scene_state, "door_1", "door", "loc_1", (1.0, 1.0),
        state="CLOSED")
    res = WorldObjectStore.apply_transition(
        scene_state, "door_1", WorldActionType.CLOSE)
    assert res.verdict == TransitionVerdict.REJECT
    assert WorldObjectStore.get(scene_state, "door_1").state == "CLOSED"


def test_store_apply_damage():
    scene_state: dict = {"world_objects": {}}
    WorldObjectStore.spawn(
        scene_state, "door_1", "door", "loc_1", (1.0, 1.0),
        state="CLOSED")
    WorldObjectStore.apply_damage(scene_state, "door_1", 1.0)
    assert WorldObjectStore.get(scene_state, "door_1").state == "BROKEN"


def test_store_chair_relation_transition():
    """О2-интеграция: chair-переход через relations в scene_state."""
    scene_state: dict = {"world_objects": {}}
    WorldObjectStore.spawn(
        scene_state, "chair_1", "chair", "loc_1", (1.0, 1.0),
        state="AVAILABLE")
    res = WorldObjectStore.apply_transition(
        scene_state, "chair_1", WorldActionType.SIT, actor_id="npc_1")
    assert res.verdict == TransitionVerdict.PASS
    assert WorldObjectStore.get(scene_state, "chair_1").occupancy == "npc_1"