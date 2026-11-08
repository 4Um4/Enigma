"""
path: /project/backend/tests/micro/test_avatar_intent_formation.py
Назначение: Avatar agency — formation of Intent from Desire (Step 2).
    Avatar формирует Intent из Desire без Player command.
    Identity = AVATAR_INITIATIVE. desire_ref сохранён.
    Execution НЕ запускается (no CommunicationIntent, no MovementIntent).
    DESIRES_ENABLED=1 (test env).
Зависимости: app.services.avatar.avatar_intent_formation
Основные сущности: тесты battery
"""

import os
import copy

os.environ["DESIRES_ENABLED"] = "1"

from app.domain.avatar_intent_record import AvatarIntentRecord
from app.domain.control_source import ControlSource
from app.domain.intent_identity import IntentIdentity
from app.models.npc_state import Intent
from app.services.avatar.avatar_intent_formation import form_avatar_intent
from app.services.npc.desire_generator import _ensure_avatar_needs, update_npc_desires


def _avatar_with_hunger(nutrition: float = 30.0) -> dict:
    """Avatar NPC dict с body_state (hunger source) + desires formed."""
    npc = {
        "npc_id": "player",
        "id": "player",
        "name": "Странник",
        "body_state": {
            "nutrition": nutrition,
        },
    }
    _ensure_avatar_needs(npc)
    update_npc_desires(npc, tick=1)
    return npc


# ── Formation ─────────────────────────────────────────────────────


def test_avatar_forms_intent_from_hunger_desire():
    """Avatar с Desire(food) → AvatarIntentRecord formed."""
    npc = _avatar_with_hunger(nutrition=30.0)
    record = form_avatar_intent(npc, tick=1)
    assert record is not None
    assert record.intent == Intent.APPROACH


def test_avatar_intent_identity_is_avatar_initiative():
    """Intent identity: control_source = AVATAR_INITIATIVE."""
    npc = _avatar_with_hunger(nutrition=30.0)
    record = form_avatar_intent(npc, tick=1)
    assert record is not None
    assert record.identity.control_source == ControlSource.AVATAR_INITIATIVE
    assert record.identity.intent_owner == "player"
    assert record.identity.actor_id == "player"
    assert record.identity.body_id == "player"


def test_avatar_intent_desire_ref_preserved():
    """desire_ref сохранён — causal link к Desire."""
    npc = _avatar_with_hunger(nutrition=30.0)
    desires = npc.get("desires", [])
    food_desire_id = next(
        d["desire_id"] for d in desires if d.get("subject_class") == "food"
    )
    record = form_avatar_intent(npc, tick=1)
    assert record is not None
    assert record.desire_ref == food_desire_id


def test_avatar_intent_urgency_from_desire():
    """urgency в record = urgency из Desire."""
    npc = _avatar_with_hunger(nutrition=30.0)  # hunger = 0.7
    record = form_avatar_intent(npc, tick=1)
    assert record is not None
    assert record.urgency == 0.7


def test_avatar_intent_target_from_desire():
    """target в record = target_class из Desire."""
    npc = _avatar_with_hunger(nutrition=30.0)
    record = form_avatar_intent(npc, tick=1)
    assert record is not None
    # _NEED_TO_DESIRE: hunger → ("food", "food_portion")
    assert record.target == "food_portion"


def test_avatar_intent_formed_tick():
    """formed_tick = tick переданный в form_avatar_intent."""
    npc = _avatar_with_hunger(nutrition=30.0)
    record = form_avatar_intent(npc, tick=42)
    assert record is not None
    assert record.formed_tick == 42


# ── No Intent when no Desire ──────────────────────────────────────


def test_avatar_no_intent_when_no_desires():
    """Avatar без desires → None (no Intent formed)."""
    npc = {"npc_id": "player", "body_state": {"nutrition": 100.0}}
    _ensure_avatar_needs(npc)
    update_npc_desires(npc, tick=1)
    record = form_avatar_intent(npc, tick=1)
    # nutrition=100 → hunger=0.0 → desire exists with urgency=0.0
    # Intent still formed (no threshold), but urgency=0.0
    if record is not None:
        assert record.urgency == 0.0
    # OR: no desire at all if needs empty
    npc_empty = {"npc_id": "player"}
    record_empty = form_avatar_intent(npc_empty, tick=1)
    assert record_empty is None


def test_avatar_no_intent_when_not_avatar():
    """Non-Avatar NPC → None (adapter only for Avatar)."""
    npc = {"npc_id": "maid_lusya", "desires": [{"subject_class": "food", "urgency": 0.9}]}
    record = form_avatar_intent(npc, tick=1)
    assert record is None


def test_avatar_no_intent_when_subject_not_in_mapping():
    """Desire с subject_class не в mapping → None (honest UNKNOWN)."""
    npc = {
        "npc_id": "player",
        "desires": [
            {"desire_id": "d1", "subject_class": "unknown_thing", "urgency": 0.9, "target_class": "x"},
        ],
    }
    record = form_avatar_intent(npc, tick=1)
    assert record is None


# ── Most urgent Desire wins ───────────────────────────────────────


def test_avatar_picks_most_urgent_desire():
    """Несколько desires → наиболее срочный формирует Intent."""
    npc = {
        "npc_id": "player",
        "desires": [
            {"desire_id": "d_food", "subject_class": "food", "urgency": 0.5, "target_class": "food_portion"},
            {"desire_id": "d_ale", "subject_class": "ale", "urgency": 0.9, "target_class": "person"},
        ],
    }
    record = form_avatar_intent(npc, tick=1)
    assert record is not None
    assert record.desire_ref == "d_ale"  # more urgent
    assert record.intent == Intent.APPROACH


# ── Determinism ────────────────────────────────────────────────────


def test_avatar_intent_reproducible_same_state():
    """Одинаковое состояние → одинаковый Intent record."""
    npc_a = _avatar_with_hunger(nutrition=30.0)
    npc_b = _avatar_with_hunger(nutrition=30.0)
    record_a = form_avatar_intent(npc_a, tick=1)
    record_b = form_avatar_intent(npc_b, tick=1)
    assert record_a.intent == record_b.intent
    assert record_a.urgency == record_b.urgency
    assert record_a.desire_ref == record_b.desire_ref


# ── Round-trip ─────────────────────────────────────────────────────


def test_avatar_intent_record_round_trip():
    """AvatarIntentRecord → to_dict → from_dict → same record."""
    npc = _avatar_with_hunger(nutrition=30.0)
    record = form_avatar_intent(npc, tick=1)
    assert record is not None
    data = record.to_dict()
    loaded = AvatarIntentRecord.from_dict(data)
    assert loaded.intent == record.intent
    assert loaded.identity.control_source == record.identity.control_source
    assert loaded.desire_ref == record.desire_ref
    assert loaded.target == record.target
    assert loaded.formed_tick == record.formed_tick
    assert loaded.urgency == record.urgency


# ── No premature execution ────────────────────────────────────────


def test_avatar_intent_does_not_create_communication_intent():
    """Formation NOT execution: no CommunicationIntent created."""
    npc = _avatar_with_hunger(nutrition=30.0)
    record = form_avatar_intent(npc, tick=1)
    assert record is not None
    # AvatarIntentRecord is NOT CommunicationIntent — no speaker/audience/topic
    assert not hasattr(record, "speaker")
    assert not hasattr(record, "audience")
    assert not hasattr(record, "topic")


def test_avatar_intent_does_not_create_movement_intent():
    """Formation NOT execution: no MovementIntent created."""
    npc = _avatar_with_hunger(nutrition=30.0)
    record = form_avatar_intent(npc, tick=1)
    assert record is not None
    # AvatarIntentRecord is NOT MovementIntent — no domain/reason/node
    assert not hasattr(record, "domain")
    assert not hasattr(record, "reason")
    assert not hasattr(record, "node_id")


# ── Desire and Intent semantically separate ───────────────────────


def test_desire_and_intent_not_mixed():
    """Desire (subject=food, urgency) ≠ Intent (APPROACH, target).
    Intent = РЕШЕНИЕ действовать, не повтор Desire."""
    npc = _avatar_with_hunger(nutrition=30.0)
    record = form_avatar_intent(npc, tick=1)
    assert record is not None
    # Desire says WHAT (food). Intent says HOW (approach).
    # They are different fields, not merged.
    assert record.intent.value == "approach"  # HOW
    assert record.target == "food_portion"     # WHAT (from desire)
    assert record.desire_ref != ""             # link to desire, not copy


# ── Change in Desire handled ──────────────────────────────────────


def test_intent_changes_when_desire_changes():
    """Desire urgency changes → Intent urgency changes."""
    npc_low = _avatar_with_hunger(nutrition=80.0)   # hunger = 0.2
    npc_high = _avatar_with_hunger(nutrition=10.0)   # hunger = 0.9
    record_low = form_avatar_intent(npc_low, tick=1)
    record_high = form_avatar_intent(npc_high, tick=1)
    assert record_low.urgency < record_high.urgency


# ── Step 2.1: storage in intent_lifecycle (no double storage) ────


def test_avatar_intent_stored_in_intent_lifecycle_not_separate_key():
    """B1: AvatarIntentRecord stored in intent_lifecycle (canonical store),
    NOT in separate avatar_pending_intent key (no double storage)."""
    from app.services.avatar.avatar_intent_formation import store_avatar_intent

    scene_state = {"tick": 1, "intent_ordinals": {}, "intent_lifecycle": {}}
    record = form_avatar_intent(_avatar_with_hunger(30.0), tick=1)
    store_avatar_intent(scene_state, record, 1)

    assert "avatar_pending_intent" not in scene_state  # NO separate key
    assert scene_state["intent_lifecycle"]  # HAS records
    assert len(scene_state["intent_lifecycle"]) == 1


def test_only_one_active_avatar_intent_at_a_time():
    """B2: Forming new intent (different desire_ref) SUPERSEDEs previous ACTIVE.

    Step 2.1.1: same desire_ref + same intent → UPDATE (continuity).
    This test verifies SUPERSEDE — needs different desire_ref (different
    subject_class), not just different urgency.
    """
    from app.services.avatar.avatar_intent_formation import store_avatar_intent

    scene_state = {"tick": 1, "intent_ordinals": {}, "intent_lifecycle": {}}

    # Tick 1: hunger → Desire(food), Intent.APPROACH
    record1 = form_avatar_intent(_avatar_with_hunger(nutrition=30.0), tick=1)
    store_avatar_intent(scene_state, record1, 1)

    # Tick 2: thirst becomes most urgent → Desire(ale), Intent.APPROACH
    # Different subject_class → different desire_ref → SUPERSEDE
    npc_thirst = _avatar_with_hunger(nutrition=80.0)  # hunger=0.2 (low)
    npc_thirst["body_state"]["hydration"] = 10.0       # thirst=0.9 (high)
    _ensure_avatar_needs(npc_thirst)
    update_npc_desires(npc_thirst, tick=2)
    record2 = form_avatar_intent(npc_thirst, tick=2)
    store_avatar_intent(scene_state, record2, 2)

    active = [
        e for e in scene_state["intent_lifecycle"].values()
        if isinstance(e, dict)
        and e.get("control_source") == "avatar_initiative"
        and e.get("lifecycle_state") == "ACTIVE"
    ]
    superseded = [
        e for e in scene_state["intent_lifecycle"].values()
        if isinstance(e, dict)
        and e.get("control_source") == "avatar_initiative"
        and e.get("lifecycle_state") == "SUPERSEDED"
    ]
    assert len(active) == 1
    assert len(superseded) == 1
    # Verify different desire_refs (food vs ale)
    assert active[0]["desire_ref"] != superseded[0]["desire_ref"]


def test_no_record_marks_previous_superseded():
    """B3: store_avatar_intent(None) → previous SUPERSEDED, no new ACTIVE."""
    from app.services.avatar.avatar_intent_formation import store_avatar_intent

    scene_state = {"tick": 1, "intent_ordinals": {}, "intent_lifecycle": {}}
    record1 = form_avatar_intent(_avatar_with_hunger(30.0), tick=1)
    store_avatar_intent(scene_state, record1, 1)
    store_avatar_intent(scene_state, None, 2)  # No new record

    active = [
        e for e in scene_state["intent_lifecycle"].values()
        if e.get("lifecycle_state") == "ACTIVE"
    ]
    superseded = [
        e for e in scene_state["intent_lifecycle"].values()
        if e.get("lifecycle_state") == "SUPERSEDED"
    ]
    assert len(active) == 0
    assert len(superseded) == 1


# ── Step 2.1: stale intent cleanup on exception ─────────────────


def test_formation_exception_voids_active_avatar_intent():
    """C1: On formation error, active avatar intent VOIDED (stale cleanup)."""
    from app.services.avatar.avatar_intent_formation import (
        store_avatar_intent,
        voided_avatar_intents,
    )

    scene_state = {"tick": 1, "intent_ordinals": {}, "intent_lifecycle": {}}
    record1 = form_avatar_intent(_avatar_with_hunger(30.0), tick=1)
    store_avatar_intent(scene_state, record1, 1)

    # Simulate formation error: voided_avatar_intents called
    voided_avatar_intents(scene_state, tick=2)

    active = [
        e for e in scene_state["intent_lifecycle"].values()
        if e.get("lifecycle_state") == "ACTIVE"
    ]
    voided = [
        e for e in scene_state["intent_lifecycle"].values()
        if e.get("lifecycle_state") == "VOIDED"
    ]
    assert len(active) == 0
    assert len(voided) == 1


# ── Step 2.1: causal link resilience ──────────────────────────────


def test_desire_ref_stable_across_ticks_same_state():
    """D1: Same Avatar state across ticks → same desire_ref."""
    npc_a = _avatar_with_hunger(30.0)
    record_a = form_avatar_intent(npc_a, tick=1)

    npc_b = _avatar_with_hunger(30.0)  # Same state, "next tick"
    record_b = form_avatar_intent(npc_b, tick=2)

    assert record_a.desire_ref == record_b.desire_ref  # Stable


def test_desire_ref_changes_when_different_desire_becomes_urgent():
    """D2: When different desire becomes most urgent, desire_ref changes."""
    # Avatar with high thirst, low hunger → thirst desire wins
    npc_thirst = _avatar_with_hunger(nutrition=80.0)  # hunger=0.2
    npc_thirst["body_state"]["hydration"] = 10.0  # thirst=0.9
    _ensure_avatar_needs(npc_thirst)
    update_npc_desires(npc_thirst, tick=1)
    record_thirst = form_avatar_intent(npc_thirst, tick=1)

    # Avatar with high hunger, low thirst → hunger desire wins
    npc_hunger = _avatar_with_hunger(nutrition=10.0)  # hunger=0.9
    npc_hunger["body_state"]["hydration"] = 80.0  # thirst=0.2
    _ensure_avatar_needs(npc_hunger)
    update_npc_desires(npc_hunger, tick=1)
    record_hunger = form_avatar_intent(npc_hunger, tick=1)

    # Different desires win → different desire_refs
    assert record_thirst.desire_ref != record_hunger.desire_ref


def test_no_intent_when_desires_disappear():
    """D3: When desires list is empty, no intent formed."""
    npc = {"npc_id": "player", "desires": []}
    record = form_avatar_intent(npc, tick=1)
    assert record is None


# ── Step 2.1.1: Intent continuity ──────────────────────────────────


def test_same_desire_same_state_preserves_intent_id():
    """2.1.1-1: При неизменных Desire, target, urgency и состоянии Avatar
    два последовательных тика сохраняют один и тот же активный intent_id."""
    from app.services.avatar.avatar_intent_formation import (
        get_active_avatar_intent,
        store_avatar_intent,
    )

    scene_state = {"tick": 1, "intent_ordinals": {}, "intent_lifecycle": {}}

    # Tick 1: Avatar голоден, nutrition=30 → hunger=0.7
    npc_t1 = _avatar_with_hunger(nutrition=30.0)
    record_t1 = form_avatar_intent(npc_t1, tick=1)
    store_avatar_intent(scene_state, record_t1, 1)
    active_t1 = get_active_avatar_intent(scene_state)
    assert active_t1 is not None
    intent_id_t1 = active_t1["intent_id"]

    # Tick 2: Same state, same desire_ref → same intent_id
    npc_t2 = _avatar_with_hunger(nutrition=30.0)
    record_t2 = form_avatar_intent(npc_t2, tick=2)
    store_avatar_intent(scene_state, record_t2, 2)
    active_t2 = get_active_avatar_intent(scene_state)
    assert active_t2 is not None
    intent_id_t2 = active_t2["intent_id"]

    assert intent_id_t1 == intent_id_t2, (
        f"Same desire should preserve intent_id: {intent_id_t1} != {intent_id_t2}"
    )

    # Lifecycle должен иметь ОДНУ запись (не накапливать)
    all_avatar_entries = [
        e for e in scene_state["intent_lifecycle"].values()
        if isinstance(e, dict)
        and e.get("control_source") == "avatar_initiative"
    ]
    assert len(all_avatar_entries) == 1, (
        f"Should not accumulate: {len(all_avatar_entries)} entries"
    )


def test_changed_desire_supersedes_previous_intent():
    """2.1.1-2: При изменении исходного Desire старый Intent → SUPERSEDED,
    формируется новый."""
    from app.services.avatar.avatar_intent_formation import (
        get_active_avatar_intent,
        store_avatar_intent,
    )

    scene_state = {"tick": 1, "intent_ordinals": {}, "intent_lifecycle": {}}

    # Tick 1: Avatar голоден (nutrition=30 → hunger=0.7)
    npc_hunger = _avatar_with_hunger(nutrition=30.0)
    record_hunger = form_avatar_intent(npc_hunger, tick=1)
    store_avatar_intent(scene_state, record_hunger, 1)
    active_t1 = get_active_avatar_intent(scene_state)
    assert active_t1 is not None
    assert active_t1["desire_ref"] == record_hunger.desire_ref
    intent_id_t1 = active_t1["intent_id"]

    # Tick 2: Avatar теперь жаждет больше (hydration=10 → thirst=0.9,
    # nutrition остаётся 30 → hunger=0.7, но thirst доминирует)
    npc_thirst = _avatar_with_hunger(nutrition=80.0)  # hunger=0.2
    npc_thirst["body_state"]["hydration"] = 10.0       # thirst=0.9
    _ensure_avatar_needs(npc_thirst)
    update_npc_desires(npc_thirst, tick=2)
    record_thirst = form_avatar_intent(npc_thirst, tick=2)
    store_avatar_intent(scene_state, record_thirst, 2)

    # Проверяем: предыдущий → SUPERSEDED
    superseded = [
        e for e in scene_state["intent_lifecycle"].values()
        if isinstance(e, dict)
        and e.get("control_source") == "avatar_initiative"
        and e.get("lifecycle_state") == "SUPERSEDED"
    ]
    assert len(superseded) == 1
    assert superseded[0]["intent_id"] == intent_id_t1

    # Проверяем: новый ACTIVE с другим desire_ref
    active_t2 = get_active_avatar_intent(scene_state)
    assert active_t2 is not None
    assert active_t2["desire_ref"] != record_hunger.desire_ref
    assert active_t2["desire_ref"] == record_thirst.desire_ref
    assert active_t2["intent_id"] != intent_id_t1


def test_repeated_tick_does_not_accumulate_active_intents():
    """2.1.1-3: Повторное формирование не создаёт бесконечную
    последовательность новых Intent при неизменном состоянии."""
    from app.services.avatar.avatar_intent_formation import (
        get_active_avatar_intent,
        store_avatar_intent,
    )

    scene_state = {"tick": 0, "intent_ordinals": {}, "intent_lifecycle": {}}

    # 5 тиков с одинаковым состоянием Avatar
    for tick in range(1, 6):
        npc = _avatar_with_hunger(nutrition=30.0)
        record = form_avatar_intent(npc, tick=tick)
        store_avatar_intent(scene_state, record, tick)

    # Должна быть ТОЛЬКО ОДНА ACTIVE запись
    active = [
        e for e in scene_state["intent_lifecycle"].values()
        if isinstance(e, dict)
        and e.get("control_source") == "avatar_initiative"
        and e.get("lifecycle_state") == "ACTIVE"
    ]
    assert len(active) == 1, (
        f"Only 1 ACTIVE intent expected, got {len(active)}"
    )

    # Всего в lifecycle должна быть 1 запись (не 5)
    all_avatar_entries = [
        e for e in scene_state["intent_lifecycle"].values()
        if isinstance(e, dict)
        and e.get("control_source") == "avatar_initiative"
    ]
    assert len(all_avatar_entries) == 1, (
        f"Should not accumulate: {len(all_avatar_entries)} entries after 5 ticks"
    )

    # intent_ordinals должен быть 1 (не создавались новые intent_id)
    assert scene_state["intent_ordinals"].get("player") == 1, (
        f"intent_ordinals[player] should be 1, got "
        f"{scene_state['intent_ordinals'].get('player')}"
    )


def test_disappeared_desire_supersedes_previous_intent():
    """2.1.1-3b: При исчезновении Desire предыдущий Intent → SUPERSEDED,
    новый не создаётся."""
    from app.services.avatar.avatar_intent_formation import (
        get_active_avatar_intent,
        store_avatar_intent,
    )

    scene_state = {"tick": 1, "intent_ordinals": {}, "intent_lifecycle": {}}

    # Tick 1: Avatar голоден
    npc_hungry = _avatar_with_hunger(nutrition=30.0)
    record = form_avatar_intent(npc_hungry, tick=1)
    store_avatar_intent(scene_state, record, 1)
    assert get_active_avatar_intent(scene_state) is not None

    # Tick 2: Avatar поел, desires исчезли (record=None)
    store_avatar_intent(scene_state, None, 2)

    # No ACTIVE avatar intent
    assert get_active_avatar_intent(scene_state) is None

    # Previous → SUPERSEDED
    superseded = [
        e for e in scene_state["intent_lifecycle"].values()
        if isinstance(e, dict)
        and e.get("control_source") == "avatar_initiative"
        and e.get("lifecycle_state") == "SUPERSEDED"
    ]
    assert len(superseded) == 1


def test_urgency_update_preserves_intent_id():
    """2.1.1-4: При эскалации urgency того же desire — intent_id сохраняется,
    urgency обновляется."""
    from app.services.avatar.avatar_intent_formation import (
        get_active_avatar_intent,
        store_avatar_intent,
    )

    scene_state = {"tick": 1, "intent_ordinals": {}, "intent_lifecycle": {}}

    # Tick 1: hunger=0.7 (nutrition=30)
    npc_t1 = _avatar_with_hunger(nutrition=30.0)
    record_t1 = form_avatar_intent(npc_t1, tick=1)
    store_avatar_intent(scene_state, record_t1, 1)
    active_t1 = get_active_avatar_intent(scene_state)
    intent_id_t1 = active_t1["intent_id"]
    assert active_t1["urgency"] == 0.7

    # Tick 2: hunger=0.9 (nutrition=10) — same desire, higher urgency
    npc_t2 = _avatar_with_hunger(nutrition=10.0)
    record_t2 = form_avatar_intent(npc_t2, tick=2)
    store_avatar_intent(scene_state, record_t2, 2)
    active_t2 = get_active_avatar_intent(scene_state)

    # Same intent_id (continuity), updated urgency
    assert active_t2["intent_id"] == intent_id_t1, (
        "Same desire_ref should preserve intent_id even with urgency change"
    )
    assert active_t2["urgency"] == 0.9, (
        f"Urgency should update to 0.9, got {active_t2['urgency']}"
    )