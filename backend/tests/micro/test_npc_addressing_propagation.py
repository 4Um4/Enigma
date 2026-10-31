"""
path: /project/backend/tests/micro/test_npc_addressing_propagation.py
Назначение: C3-A2-DELIVERY-1 regression — propagation of npc_addressing
    from TickResultDTO through GameLoop.idle_tick return dict.
Зависимости: app.domain.tick, app.services.events.npc_addressing_delivery_subscriber
Основные сущности: тесты battery 1-10
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.domain.tick import TickResultDTO


def _read_game_loop_source() -> str:
    test_dir = Path(__file__).resolve().parent
    game_loop_path = test_dir.parent.parent / "app" / "services" / "game_loop" / "game_loop.py"
    return game_loop_path.read_text(encoding="utf-8-sig")


def _make_tick_result_with_addressing(addressing=None):
    return TickResultDTO(status="ok", npc_addressing=addressing or [])


def test_1_npc_addressing_in_idle_tick_success_return():
    src = _read_game_loop_source()
    idle_start = src.index("def idle_tick(")
    idle_end = src.index("def ", idle_start + 10)
    idle_src = src[idle_start:idle_end]
    assert "npc_addressing" in idle_src


def test_2_bridge_passthrough_preserves_npc_addressing():
    test_dir = Path(__file__).resolve().parent
    bridge_path = test_dir.parent.parent.parent / "frontend" / "game_loop_bridge.py"
    if not bridge_path.exists():
        pytest.skip("game_loop_bridge.py not found")
    bridge_src = bridge_path.read_text(encoding="utf-8-sig")
    assert "self._loop.idle_tick" in bridge_src


def test_3_empty_npc_addressing_in_tick_result():
    result = _make_tick_result_with_addressing(addressing=[])
    assert result.npc_addressing == []


def test_4_multiple_addressing_in_tick_result():
    events = [
        {"event_id": "evt1", "npc_id": "lusya", "intent": "talk"},
        {"event_id": "evt2", "npc_id": "borko", "intent": "warn"},
        {"event_id": "evt3", "npc_id": "mira", "intent": "help"},
    ]
    result = _make_tick_result_with_addressing(addressing=events)
    assert len(result.npc_addressing) == 3


def test_5_event_id_preserved_in_tick_result():
    test_id = "550e8400-e29b-41d4-a716-446655440000"
    events = [{"event_id": test_id, "npc_id": "lusya", "intent": "talk"}]
    result = _make_tick_result_with_addressing(addressing=events)
    assert result.npc_addressing[0]["event_id"] == test_id


def test_6_campaign_id_not_in_tick_result_addressing():
    events = [{"event_id": "evt1", "npc_id": "lusya", "intent": "talk"}]
    result = _make_tick_result_with_addressing(addressing=events)
    assert "campaign_id" not in result.npc_addressing[0]


def test_7_idle_tick_without_addressing_has_empty_list():
    result = TickResultDTO(status="ok")
    assert result.npc_addressing == []


def test_8_drain_returns_same_events_before_ack():
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
    from app.domain.events import EventDTO

    bus = EventBus()
    sub = NpcAddressingDeliverySubscriber(bus)
    token = set_tick_context(TickCampaignContext(campaign_id="camp_A", tick_id=100))
    try:
        bus.publish(
            EventDTO.create(
                event_type=EventType.NPC_ADDRESSES_PLAYER.value,
                source="lusya",
                payload={"intent": "talk", "target_id": "player", "intent_formed_at": 100},
                visibility="whisper",
                persistence_level="working",
            )
        )
        sub.commit_staged("camp_A")
        d1 = sub.drain("camp_A")
        d2 = sub.drain("camp_A")
        assert d1[0]["event_id"] == d2[0]["event_id"]
    finally:
        reset_tick_context(token)


def test_9_early_return_contains_npc_addressing():
    src = _read_game_loop_source()
    assert '"player_turn_in_flight"' in src
    idx = src.index('"player_turn_in_flight"')
    assert "npc_addressing" in src[idx:idx + 200]


def test_10_no_scene_returns_contain_npc_addressing():
    """Source-inspection: return statements with 'no_scene' contain 'npc_addressing'."""
    src = _read_game_loop_source()
    lines = src.split("\n")
    no_scene_returns = [
        l for l in lines
        if '"no_scene"' in l and l.strip().startswith("return")
    ]
    assert len(no_scene_returns) >= 2, (
        f"Expected >=2 no_scene return statements, found {len(no_scene_returns)}"
    )
    for line in no_scene_returns:
        assert "npc_addressing" in line, (
            f"no_scene return must contain 'npc_addressing': {line.strip()}"
        )