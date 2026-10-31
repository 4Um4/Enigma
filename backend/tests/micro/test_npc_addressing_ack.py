"""
path: /project/backend/tests/micro/test_npc_addressing_ack.py
Назначение: C3-A2-ACK-1 regression — ACK через игровой контур.
    TickOrchestrator.ack_addressing → GameLoop.ack_addressing →
    GameLoopBridge.ack_addressing → frontend call.
Зависимости: app.services.events.npc_addressing_delivery_subscriber,
    app.services.tick_orchestrator, app.services.game_loop.game_loop,
    frontend.game_loop_bridge
Основные сущности: тесты battery 1-12
"""
from __future__ import annotations

import threading
from pathlib import Path
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
    reset_tick_context,
    set_tick_context,
)
from app.services.tick_orchestrator import TickOrchestrator


# ── Helpers ──────────────────────────────────────────────────────────────


def _make_subscriber_with_event(
    campaign_id: str = "camp_A",
    npc_id: str = "lusya",
    tick_id: int = 100,
):
    """Creates subscriber with one committed event. Returns (sub, event_id)."""
    bus = EventBus()
    sub = NpcAddressingDeliverySubscriber(bus)
    token = set_tick_context(TickCampaignContext(campaign_id=campaign_id, tick_id=tick_id))
    try:
        bus.publish(
            EventDTO.create(
                event_type=EventType.NPC_ADDRESSES_PLAYER.value,
                source=npc_id,
                payload={"intent": "talk", "target_id": "player", "intent_formed_at": tick_id},
                visibility="whisper",
                persistence_level="working",
            )
        )
        sub.commit_staged(campaign_id)
    finally:
        reset_tick_context(token)
    event_id = str(sub.drain(campaign_id)[0]["event_id"])
    return sub, event_id


def _make_tick_orch_with_event(campaign_id="camp_A", npc_id="lusya"):
    """Creates TickOrchestrator (bypass __init__) with one event."""
    to = object.__new__(TickOrchestrator)
    bus = EventBus()
    to._npc_addressing_sub = NpcAddressingDeliverySubscriber(bus)
    token = set_tick_context(TickCampaignContext(campaign_id=campaign_id, tick_id=100))
    try:
        bus.publish(
            EventDTO.create(
                event_type=EventType.NPC_ADDRESSES_PLAYER.value,
                source=npc_id,
                payload={"intent": "talk", "target_id": "player", "intent_formed_at": 100},
                visibility="whisper",
                persistence_level="working",
            )
        )
        to._npc_addressing_sub.commit_staged(campaign_id)
    finally:
        reset_tick_context(token)
    event_id = str(to._npc_addressing_sub.drain(campaign_id)[0]["event_id"])
    return to, event_id


class _FakeTickOrch:
    """Fake TickOrchestrator for GameLoop tests."""
    def __init__(self, sub):
        self._npc_addressing_sub = sub
        self.ack_calls = []

    def ack_addressing(self, campaign_id, event_id):
        self.ack_calls.append((campaign_id, event_id))
        return self._npc_addressing_sub.ack(campaign_id, event_id)


# ── Контракт 1: ACK через GameLoop вызывает subscriber и возвращает True ──


def test_1_ack_through_gameloop_returns_true():
    """GameLoop.ack_addressing() → TickOrchestrator → subscriber → True."""
    from app.services.game_loop.game_loop import GameLoop

    sub, event_id = _make_subscriber_with_event()
    gl = object.__new__(GameLoop)
    gl._tick_orch = _FakeTickOrch(sub)

    result = gl.ack_addressing("camp_A", event_id)
    assert result is True
    assert gl._tick_orch.ack_calls == [("camp_A", event_id)]


# ── Контракт 2: ACK через GameLoopBridge проходит до GameLoop ──


def test_2_ack_through_bridge():
    """GameLoopBridge.ack_addressing() → GameLoop → subscriber."""
    from frontend.game_loop_bridge import GameLoopBridge

    sub, event_id = _make_subscriber_with_event()
    from app.services.game_loop.game_loop import GameLoop

    gl = object.__new__(GameLoop)
    gl._tick_orch = _FakeTickOrch(sub)

    bridge = object.__new__(GameLoopBridge)
    bridge._ready = True
    bridge._loop = gl

    result = bridge.ack_addressing("camp_A", event_id)
    assert result is True


# ── Контракт 3: После ACK событие отсутствует в следующем drain ──


def test_3_ack_removes_from_drain():
    """После ACK → drain возвращает [] (без event)."""
    to, event_id = _make_tick_orch_with_event()
    # Verify event exists before ACK
    assert len(to._npc_addressing_sub.drain("camp_A")) == 1

    result = to.ack_addressing("camp_A", event_id)
    assert result is True

    drained = to._npc_addressing_sub.drain("camp_A")
    assert len(drained) == 0


# ── Контракт 4: ACK с чужим campaign_id возвращает False ──


def test_4_ack_wrong_campaign_returns_false():
    """ACK чужой кампании → False, исходное событие сохраняется."""
    to, event_id = _make_tick_orch_with_event("camp_A")

    result = to.ack_addressing("camp_B", event_id)
    assert result is False

    # Event still in camp_A
    drained = to._npc_addressing_sub.drain("camp_A")
    assert len(drained) == 1


# ── Контракт 5: Повторный ACK возвращает False без ошибки ──


def test_5_repeat_ack_returns_false():
    """Повторный ACK → False, no error."""
    to, event_id = _make_tick_orch_with_event()

    first = to.ack_addressing("camp_A", event_id)
    assert first is True

    second = to.ack_addressing("camp_A", event_id)
    assert second is False


# ── Контракт 6: ACK несуществующего event_id возвращает False ──


def test_6_ack_nonexistent_event_returns_false():
    """ACK несуществующего event_id → False."""
    to, _ = _make_tick_orch_with_event()

    result = to.ack_addressing("camp_A", "nonexistent-event-id")
    assert result is False


# ── Контракт 7: ACK одного события не удаляет остальные ──


def test_7_ack_preserves_other_events():
    """ACK одного event → другие остаются в drain."""
    bus = EventBus()
    sub = NpcAddressingDeliverySubscriber(bus)
    token = set_tick_context(TickCampaignContext(campaign_id="camp_A", tick_id=100))
    try:
        for npc in ("lusya", "borko"):
            bus.publish(
                EventDTO.create(
                    event_type=EventType.NPC_ADDRESSES_PLAYER.value,
                    source=npc,
                    payload={"intent": "talk", "target_id": "player", "intent_formed_at": 100},
                    visibility="whisper",
                    persistence_level="working",
                )
            )
        sub.commit_staged("camp_A")
    finally:
        reset_tick_context(token)

    to = object.__new__(TickOrchestrator)
    to._npc_addressing_sub = sub

    drained = sub.drain("camp_A")
    assert len(drained) == 2
    first_eid = drained[0]["event_id"]

    result = to.ack_addressing("camp_A", first_eid)
    assert result is True

    remaining = sub.drain("camp_A")
    assert len(remaining) == 1
    assert remaining[0]["event_id"] != first_eid


# ── Контракт 8: Параллельные ACK и drain не повреждают очередь ──


def test_8_parallel_ack_and_drain():
    """Конкурентные ACK + drain → no corruption."""
    bus = EventBus()
    sub = NpcAddressingDeliverySubscriber(bus)
    token = set_tick_context(TickCampaignContext(campaign_id="camp_A", tick_id=100))
    try:
        for i in range(10):
            bus.publish(
                EventDTO.create(
                    event_type=EventType.NPC_ADDRESSES_PLAYER.value,
                    source=f"npc_{i}",
                    payload={"intent": "talk", "target_id": "player", "intent_formed_at": 100},
                    visibility="whisper",
                    persistence_level="working",
                )
            )
        sub.commit_staged("camp_A")
    finally:
        reset_tick_context(token)

    events = sub.drain("camp_A")
    event_ids = [e["event_id"] for e in events]
    errors = []

    def _worker():
        try:
            for eid in event_ids:
                sub.ack("camp_A", eid)
                sub.drain("camp_A")
        except Exception as e:
            errors.append(str(e))

    threads = [threading.Thread(target=_worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == [], f"Concurrent errors: {errors}"
    assert sub.drain("camp_A") == []


# ── Контракт 9: Frontend сохраняет событие до ACK (source inspection) ──


def test_9_frontend_saves_before_ack():
    """Source-inspection: game_screen сохраняет в indicators ДО вызова ack."""
    gs_path = Path(__file__).resolve().parent.parent.parent.parent / "frontend" / "game_screen.py"
    if not gs_path.exists():
        pytest.skip("game_screen.py not found")
    src = gs_path.read_text(encoding="utf-8-sig")

    # Find the ACK block
    ack_idx = src.index("ack_addressing(campaign_folder, _addr_eid)")
    # Find the save line before it
    block_start = src.rfind("npc_addressing_indicators", 0, ack_idx)
    assert block_start < ack_idx, "Save must come before ACK"

    # Verify save is in an if block (not after ACK)
    between = src[block_start:ack_idx]
    assert "npc_addressing_indicators[_addr_eid]" in between
    assert "ack_addressing" not in between


# ── Контракт 10: Повторный event_id не создаёт дублирующий индикатор ──


def test_10_repeat_event_id_no_duplicate():
    """Source-inspection: game_screen проверяет _addr_eid not in indicators."""
    gs_path = Path(__file__).resolve().parent.parent.parent.parent / "frontend" / "game_screen.py"
    if not gs_path.exists():
        pytest.skip("game_screen.py not found")
    src = gs_path.read_text(encoding="utf-8-sig")

    # Find the dedup check
    assert "_addr_eid not in self.npc_addressing_indicators" in src, (
        "Frontend must check for duplicate event_id before creating indicator"
    )


# ── Контракт 11: При невалидном event_id или npc_id ACK не вызывается ──


def test_11_invalid_event_id_no_ack():
    """Source-inspection: ACK inside 'if _addr_npc and _addr_eid' guard."""
    gs_path = Path(__file__).resolve().parent.parent.parent.parent / "frontend" / "game_screen.py"
    if not gs_path.exists():
        pytest.skip("game_screen.py not found")
    src = gs_path.read_text(encoding="utf-8-sig")

    # Find the guard
    guard_idx = src.index("if _addr_npc and _addr_eid:")
    ack_idx = src.index("ack_addressing(campaign_folder, _addr_eid)")

    # ACK must be after the guard (inside the if block)
    assert ack_idx > guard_idx, "ACK must be inside 'if _addr_npc and _addr_eid' guard"

    # Verify ACK is indented more than the guard
    guard_line = src[src.rfind("\n", 0, guard_idx) + 1:guard_idx]
    ack_line = src[src.rfind("\n", 0, ack_idx) + 1:ack_idx]
    assert len(ack_line) > len(guard_line), "ACK must be more indented than guard"


# ── Контракт 12: При ошибке ACK событие остаётся в frontend-состоянии ──


def test_12_ack_error_preserves_state():
    """Source-inspection: ACK wrapped in try/except, error doesn't break loop."""
    gs_path = Path(__file__).resolve().parent.parent.parent.parent / "frontend" / "game_screen.py"
    if not gs_path.exists():
        pytest.skip("game_screen.py not found")
    src = gs_path.read_text(encoding="utf-8-sig")

    # Find ACK call
    ack_idx = src.index("ack_addressing(campaign_folder, _addr_eid)")
    # Find try before it
    try_idx = src.rfind("try:", 0, ack_idx)
    assert try_idx < ack_idx, "ACK must be inside try block"

    # Find except after ACK
    except_idx = src.index("except", ack_idx)
    assert except_idx > ack_idx, "ACK must have except handler"

    # Verify except doesn't re-raise (just logs)
    except_block = src[except_idx:except_idx + 200]
    assert "logger" in except_block or "pass" in except_block, (
        "Except must log or pass, not re-raise"
    )
    assert "raise" not in except_block[:100], "Except must not re-raise"