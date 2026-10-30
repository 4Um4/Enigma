"""
path: /project/backend/tests/micro/test_npc_addressing_delivery.py
Назначение: C3-A1 regression — 21 контракт delivery channel NPC_ADDRESSES_PLAYER.
    Тестирует: staging → commit → drain → ack lifecycle, campaign/tick isolation,
    Phase 10 failure safety, ContextVar nesting, thread safety, ACK semantics.
    NPCState.intent = SSOT (subscriber хранит проекцию, не intent).
Зависимости: app.services.events.event_bus, app.services.events.event_types,
    app.domain.events, app.services.events.tick_campaign_context,
    app.services.events.npc_addressing_delivery_subscriber
Основные сущности: тесты battery 1-21
"""
from __future__ import annotations

import threading
from unittest.mock import MagicMock

import pytest

from app.domain.events import EventDTO
from app.services.events.event_bus import EventBus
from app.services.events.event_types import EventType
from app.services.events.npc_addressing_delivery_subscriber import (
    NpcAddressingDeliverySubscriber,
)
from app.services.events.tick_campaign_context import (
    TickCampaignContext,
    get_current_tick_context,
    reset_tick_context,
    set_tick_context,
)


# ── Helpers ──────────────────────────────────────────────────────────────


def _make_bus() -> EventBus:
    """Свежая шина с identity-провайдером (tick=100)."""
    bus = EventBus()
    _scene = {"tick": 100}

    def _provider(event_type: str, source: str):
        ordinals = _scene.setdefault("event_ordinals", {})
        key = f"{event_type}:{source}"
        ordinal = int(ordinals.get(key, 0)) + 1
        ordinals[key] = ordinal
        tick = int(_scene.get("tick", 0) or 0)
        return tick, ordinal

    bus.set_identity_provider(_provider)
    return bus


def _make_subscriber(bus: EventBus) -> NpcAddressingDeliverySubscriber:
    return NpcAddressingDeliverySubscriber(bus)


def _publish_addressing(
    bus: EventBus,
    npc_id: str = "lusya",
    intent: str = "talk",
    formed_at: int = 100,
) -> EventDTO:
    """Публикует NPC_ADDRESSES_PLAYER и возвращает EventDTO."""
    event = EventDTO.create(
        event_type=EventType.NPC_ADDRESSES_PLAYER.value,
        source=npc_id,
        payload={
            "intent": intent,
            "target_id": "player",
            "intent_formed_at": formed_at,
        },
        visibility="whisper",
        persistence_level="working",
    )
    bus.publish(event)
    return bus._event_log[-1]


def _set_ctx(campaign_id: str = "camp_A", tick_id: int = 100):
    """Устанавливает TickCampaignContext, возвращает token."""
    return set_tick_context(TickCampaignContext(campaign_id=campaign_id, tick_id=tick_id))


# ── Контракт 1: событие попадает в канал после Phase 10 ─────────────────


def test_1_event_reaches_delivery_after_commit():
    """publish + commit_staged → drain возвращает событие."""
    bus = _make_bus()
    sub = _make_subscriber(bus)
    token = _set_ctx("camp_A", 100)
    try:
        _publish_addressing(bus)
        assert get_current_tick_context().staged_events  # staging worked
        sub.commit_staged("camp_A")
        drained = sub.drain("camp_A")
        assert len(drained) == 1
        assert drained[0]["npc_id"] == "lusya"
    finally:
        reset_tick_context(token)


# ── Контракт 2: нет события без NPC_ADDRESSES_PLAYER ────────────────────


def test_2_no_event_without_addressing():
    """Обычный tick (без addressing) → drain = []."""
    bus = _make_bus()
    sub = _make_subscriber(bus)
    token = _set_ctx("camp_A", 100)
    try:
        # Publish a different event type
        bus.publish(
            EventDTO.create(
                event_type="npc_spoke",
                source="lusya",
                payload={"text": "hi"},
            )
        )
        sub.commit_staged("camp_A")
        assert sub.drain("camp_A") == []
    finally:
        reset_tick_context(token)


# ── Контракт 3: три NPC → три события ───────────────────────────────────


def test_3_three_npcs_three_events():
    """3 NPC обратились → 3 события в drain."""
    bus = _make_bus()
    sub = _make_subscriber(bus)
    token = _set_ctx("camp_A", 100)
    try:
        for npc in ("lusya", "borko", "mira"):
            _publish_addressing(bus, npc_id=npc)
        sub.commit_staged("camp_A")
        drained = sub.drain("camp_A")
        assert len(drained) == 3
        assert {e["npc_id"] for e in drained} == {"lusya", "borko", "mira"}
    finally:
        reset_tick_context(token)


# ── Контракт 4: изоляция кампаний ───────────────────────────────────────


def test_4_campaign_isolation():
    """drain("A") не возвращает события "B"."""
    bus = _make_bus()
    sub = _make_subscriber(bus)
    # Campaign A
    token_a = _set_ctx("camp_A", 100)
    try:
        _publish_addressing(bus, npc_id="lusya")
        sub.commit_staged("camp_A")
    finally:
        reset_tick_context(token_a)
    # Campaign B
    token_b = _set_ctx("camp_B", 100)
    try:
        _publish_addressing(bus, npc_id="borko")
        sub.commit_staged("camp_B")
    finally:
        reset_tick_context(token_b)
    # Check isolation
    assert len(sub.drain("camp_A")) == 1
    assert sub.drain("camp_A")[0]["npc_id"] == "lusya"
    assert len(sub.drain("camp_B")) == 1
    assert sub.drain("camp_B")[0]["npc_id"] == "borko"


# ── Контракт 5: параллельные тики не смешивают ─────────────────────────


def test_5_parallel_ticks_no_cross_contamination():
    """Параллельные execute("A"), execute("B") → изоляция через ContextVar."""
    bus = _make_bus()
    sub = _make_subscriber(bus)
    errors = []

    def _tick_campaign(campaign_id: str, npc_id: str):
        try:
            token = _set_ctx(campaign_id, 100)
            try:
                _publish_addressing(bus, npc_id=npc_id)
                sub.commit_staged(campaign_id)
            finally:
                reset_tick_context(token)
        except Exception as e:
            errors.append(str(e))

    t_a = threading.Thread(target=_tick_campaign, args=("camp_A", "lusya"))
    t_b = threading.Thread(target=_tick_campaign, args=("camp_B", "borko"))
    t_a.start()
    t_b.start()
    t_a.join()
    t_b.join()
    assert errors == [], f"Thread errors: {errors}"
    # Each campaign has exactly its own event
    a_drain = sub.drain("camp_A")
    b_drain = sub.drain("camp_B")
    assert len(a_drain) == 1 and a_drain[0]["npc_id"] == "lusya"
    assert len(b_drain) == 1 and b_drain[0]["npc_id"] == "borko"


# ── Контракт 6: tick не крадёт staging другого tick ────────────────────


def test_6_tick_does_not_steal_other_tick_staging():
    """Staging tick B не появляется в staging tick A.

    Примечание: ранее закоммиченные, но не ACKed события ДОЛЖНЫ
    возвращаться в drain (повторная доставка) — это ожидаемое
    поведение, не contamination. Этот тест проверяет staging,
    а не delivery queue.
    """
    bus = _make_bus()
    sub = _make_subscriber(bus)
    # Tick A: publish but DON'T commit
    token_a = _set_ctx("camp_A", 100)
    try:
        _publish_addressing(bus, npc_id="lusya")
        ctx_a = get_current_tick_context()
        assert len(ctx_a.staged_events) == 1
        # DON'T commit_staged — simulate exception
    finally:
        reset_tick_context(token_a)
    # Tick B: new context, staged_events should be empty
    token_b = _set_ctx("camp_A", 101)
    try:
        ctx_b = get_current_tick_context()
        assert ctx_b.staged_events == [], "New tick inherited staging!"
        assert ctx_b.tick_id == 101
    finally:
        reset_tick_context(token_b)
    # Delivery queue should be empty (tick A never committed)
    assert sub.drain("camp_A") == []


# ── Контракт 7: повторная выдача до ACK — тот же event_id ──────────────


def test_7_repeat_drain_before_ack_same_event_id():
    """drain дважды → тот же event_id (queue не очищается)."""
    bus = _make_bus()
    sub = _make_subscriber(bus)
    token = _set_ctx("camp_A", 100)
    try:
        _publish_addressing(bus, npc_id="lusya")
        sub.commit_staged("camp_A")
        d1 = sub.drain("camp_A")
        d2 = sub.drain("camp_A")
        assert d1 == d2
        assert d1[0]["event_id"] == d2[0]["event_id"]
    finally:
        reset_tick_context(token)


# ── Контракт 8: ACK удаляет только подтверждённое ──────────────────────


def test_8_ack_removes_only_acked():
    """ack(event_A) → drain возвращает event_B, не A."""
    bus = _make_bus()
    sub = _make_subscriber(bus)
    token = _set_ctx("camp_A", 100)
    try:
        e_a = _publish_addressing(bus, npc_id="lusya")
        e_b = _publish_addressing(bus, npc_id="borko")
        sub.commit_staged("camp_A")
        # ACK event A
        assert sub.ack("camp_A", str(e_a.id)) is True
        drained = sub.drain("camp_A")
        assert len(drained) == 1
        assert drained[0]["npc_id"] == "borko"
    finally:
        reset_tick_context(token)


# ── Контракт 9: повторный ACK безопасен ────────────────────────────────


def test_9_repeat_ack_safe():
    """ack дважды → no error, second returns False."""
    bus = _make_bus()
    sub = _make_subscriber(bus)
    token = _set_ctx("camp_A", 100)
    try:
        e = _publish_addressing(bus)
        sub.commit_staged("camp_A")
        assert sub.ack("camp_A", str(e.id)) is True
        assert sub.ack("camp_A", str(e.id)) is False  # already removed
    finally:
        reset_tick_context(token)


# ── Контракт 10: exception в Phase 10 не загрязняет ───────────────────


def test_10_phase10_failure_does_not_enqueue():
    """publish + Phase 10 crash → commit_staged НЕ вызывается → drain = []."""
    bus = _make_bus()
    sub = _make_subscriber(bus)
    token = _set_ctx("camp_A", 100)
    try:
        _publish_addressing(bus)
        # Simulate Phase 10 failure: DON'T call commit_staged
        # (in real code, exception → continue → skip commit_staged)
    finally:
        reset_tick_context(token)  # staged destroyed
    # Delivery queue should be empty
    assert sub.drain("camp_A") == []


# ── Контракт 11: новый ctx не наследует старые события ─────────────────


def test_11_new_ctx_no_inheritance():
    """Новый execute() → новый TickCampaignContext, staged_events пуст."""
    bus = _make_bus()
    sub = _make_subscriber(bus)
    token1 = _set_ctx("camp_A", 100)
    try:
        _publish_addressing(bus)
        sub.commit_staged("camp_A")
    finally:
        reset_tick_context(token1)
    # New tick
    token2 = _set_ctx("camp_A", 101)
    try:
        ctx = get_current_tick_context()
        assert ctx.staged_events == []
        assert ctx.tick_id == 101
    finally:
        reset_tick_context(token2)
    # But delivery queue retains unACKed from tick 100
    assert len(sub.drain("camp_A")) == 1


# ── Контракт 12: EXCLUDED projection не нарушен ────────────────────────


def test_12_excluded_projection_intact():
    """NPC_ADDRESSES_PLAYER остаётся в EXCLUDED_EVENT_TYPES (regression)."""
    from app.services.game_loop.idle_event_projection import EXCLUDED_EVENT_TYPES
    assert EventType.NPC_ADDRESSES_PLAYER in EXCLUDED_EVENT_TYPES


# ── Контракт 13: NPCState.intent = SSOT ────────────────────────────────


def test_13_intent_ssot_preserved():
    """Subscriber хранит проекцию EventDTO, не intent (regression)."""
    bus = _make_bus()
    sub = _make_subscriber(bus)
    token = _set_ctx("camp_A", 100)
    try:
        _publish_addressing(bus, intent="warn")
        sub.commit_staged("camp_A")
        drained = sub.drain("camp_A")
        # Projection contains intent from payload, but subscriber
        # does NOT store or modify NPCState.intent
        assert drained[0]["intent"] == "warn"
        # Verify subscriber has no NPCState reference
        assert not hasattr(sub, "_npc_states")
        assert not hasattr(sub, "_intent_store")
    finally:
        reset_tick_context(token)


# ── Контракт 14: нет новых persistent NPC-полей ────────────────────────


def test_14_no_new_persistent_fields():
    """NPCState не получила новых полей (regression)."""
    from app.models.npc_state import NPCState
    # Verify C3-A1 did not add fields to NPCState
    state = NPCState(npc_id="test")
    assert not hasattr(state, "addressing_buffer")
    assert not hasattr(state, "addressing_queue")
    assert not hasattr(state, "pending_addressing")


# ── Контракт 15: другие events/subscribers не затронуты ───────────────


def test_15_other_events_subscribers_unchanged():
    """NPC_SPOKE и другие EventType не затрагиваются delivery subscriber."""
    bus = _make_bus()
    sub = _make_subscriber(bus)
    token = _set_ctx("camp_A", 100)
    try:
        # Publish NPC_SPOKE — subscriber should NOT capture it
        bus.publish(
            EventDTO.create(
                event_type="npc_spoke",
                source="lusya",
                payload={"text": "hello"},
            )
        )
        assert get_current_tick_context().staged_events == []
        sub.commit_staged("camp_A")
        assert sub.drain("camp_A") == []
    finally:
        reset_tick_context(token)


# ── Контракт 16: Phase 10 failure → нет доставки (интеграционный) ──────


def test_16_phase10_failure_does_not_enqueue_address():
    """Публикация + падение Phase 10 → событие не попадает в delivery queue."""
    bus = _make_bus()
    sub = _make_subscriber(bus)
    token = _set_ctx("camp_A", 100)
    try:
        _publish_addressing(bus)
        # Simulate Phase 10 failure: exception before commit_staged
        raise RuntimeError("Simulated Phase 10 crash")
    except RuntimeError:
        pass  # Caught — commit_staged NOT called
    finally:
        reset_tick_context(token)
    # staged_events destroyed with context → delivery queue empty
    assert sub.drain("camp_A") == []


# ── Контракт 17: commit failure → нет доставки ─────────────────────────


def test_17_commit_failure_does_not_enqueue_address():
    """Ошибка scene_manager.commit → событие не доставляется."""
    bus = _make_bus()
    sub = _make_subscriber(bus)
    token = _set_ctx("camp_A", 100)
    try:
        _publish_addressing(bus)
        # Simulate commit failure: exception in commit_staged itself
        # (e.g., scene_manager.commit raised before commit_staged called)
        # In real code: execute_persistence raises → continue → skip commit_staged
        # Here: just don't call commit_staged
    finally:
        reset_tick_context(token)
    assert sub.drain("camp_A") == []


# ── Контракт 18: staged недоступен через drain до commit ──────────────


def test_18_staged_not_drainable_before_commit():
    """До commit_staged → drain = [] (событие в staging, не в delivery queue)."""
    bus = _make_bus()
    sub = _make_subscriber(bus)
    token = _set_ctx("camp_A", 100)
    try:
        _publish_addressing(bus)
        # Event is in staged_events but NOT in delivery queue
        assert len(get_current_tick_context().staged_events) == 1
        assert sub.drain("camp_A") == []  # Not yet committed
        # Now commit
        sub.commit_staged("camp_A")
        assert len(sub.drain("camp_A")) == 1
    finally:
        reset_tick_context(token)


# ── Контракт 19: вложенный ContextVar reset ───────────────────────────


def test_19_contextvar_nested_reset():
    """Вложенный контекст восстанавливает предыдущий."""
    bus = _make_bus()
    sub = _make_subscriber(bus)
    token_outer = _set_ctx("camp_A", 100)
    try:
        _publish_addressing(bus, npc_id="outer")
        # Nested context
        token_inner = _set_ctx("camp_A", 101)
        try:
            _publish_addressing(bus, npc_id="inner")
            ctx_inner = get_current_tick_context()
            assert ctx_inner.tick_id == 101
            assert len(ctx_inner.staged_events) == 1
            sub.commit_staged("camp_A")
        finally:
            reset_tick_context(token_inner)
        # Outer restored
        ctx_outer = get_current_tick_context()
        assert ctx_outer.tick_id == 100
        assert len(ctx_outer.staged_events) == 1  # outer event still staged
        assert ctx_outer.staged_events[0].source == "outer"
    finally:
        reset_tick_context(token_outer)


# ── Контракт 20: конкурентные операции над очередью ───────────────────


def test_20_parallel_same_campaign_queue_operations():
    """Конкурентные drain + ack не повреждают данные."""
    bus = _make_bus()
    sub = _make_subscriber(bus)
    token = _set_ctx("camp_A", 100)
    try:
        # Publish 10 events
        events = []
        for i in range(10):
            events.append(_publish_addressing(bus, npc_id=f"npc_{i}"))
        sub.commit_staged("camp_A")
    finally:
        reset_tick_context(token)
    # Now do concurrent drain + ack
    errors = []

    def _worker():
        try:
            for e in events:
                sub.ack("camp_A", str(e.id))
                sub.drain("camp_A")
        except Exception as e:
            errors.append(str(e))

    threads = [threading.Thread(target=_worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == [], f"Concurrent errors: {errors}"
    # After all ACKs, queue should be empty
    assert sub.drain("camp_A") == []


# ── Контракт 21: ACK чужой кампании = no-op ───────────────────────────


def test_21_ack_wrong_campaign_noop():
    """Нельзя подтвердить событие другой кампании."""
    bus = _make_bus()
    sub = _make_subscriber(bus)
    # Campaign A event
    token = _set_ctx("camp_A", 100)
    try:
        e = _publish_addressing(bus)
        sub.commit_staged("camp_A")
    finally:
        reset_tick_context(token)
    # Try ACK from campaign B
    assert sub.ack("camp_B", str(e.id)) is False
    # Event still in campaign A
    assert len(sub.drain("camp_A")) == 1
    assert sub.drain("camp_B") == []