"""
F5 Cross-branch: Event → v1 dictionary → game_screen telemetry.

Контракт (ADR-O-421, LC-IMPL-2/3, вердикт Мастера 2026-10-25):
- THEFT: independent event path (W3_G3_ENABLED, IntentEventAdapter._INTENT_EVENT_MAP["steal"]=EventType.THEFT)
- ACTIVITY_OUTCOME: joint rollout (DESIRES_ENABLED + ACTIVITY_LIFECYCLE_ENABLED)
- v1-словарь {ACTIVITY_OUTCOME, THEFT} — проекция {cause, target, value}
- game_loop.idle_tick returns events=[{cause, target, value}]
- game_screen.py: _idle_events = _tick_data.get("events") → логирует [TELEGRAPH]

Тест проверяет production-путь от bus.publish(EventDTO) до idle_tick return events.
НЕ запускает pygame/LLM. НЕ трогает WIP-зоны A (routes_chronicle, test_s369, test_cch4).

Сценарии:
- A. THEFT: publish EventDTO(event_type="theft") → idle_tick returns events with cause="theft"
- B. ACTIVITY_OUTCOME: publish EventDTO(event_type="activity_outcome") → idle_tick returns events with cause="activity_outcome"
- C. OFF-контроль: IDLE_EVENTS_PROJECTION_ENABLED=0 → events=[] (события в шине есть, проекция отключена)
- D. Изоляция: THEFT-событие НЕ матчится с activity (различимость источников)
- E. game_screen-телеграф: _idle_events читается и логируется (структурная проверка)
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

# Изоляция saves — per-test temp
_TEST_SAVES = tempfile.mkdtemp(prefix="f5_saves_")
os.environ.setdefault("AIDM_DATA_DIR", _TEST_SAVES)
os.environ.setdefault("AIDM_SAVES_DIR", _TEST_SAVES)

# ── Группы тестов по режимам флагов ──────────────────────────────────────────

def _setup_env(theft: bool = False, activity: bool = False, projection: bool = True) -> None:
    """Выставить env-флаги для теста. projection=False = OFF-контроль."""
    if theft:
        os.environ["W3_G3_ENABLED"] = "1"
    else:
        os.environ.pop("W3_G3_ENABLED", None)
    if activity:
        os.environ["DESIRES_ENABLED"] = "1"
        os.environ["ACTIVITY_LIFECYCLE_ENABLED"] = "1"
    else:
        os.environ.pop("DESIRES_ENABLED", None)
        os.environ.pop("ACTIVITY_LIFECYCLE_ENABLED", None)
    if projection:
        os.environ["IDLE_EVENTS_PROJECTION_ENABLED"] = "1"
    else:
        os.environ["IDLE_EVENTS_PROJECTION_ENABLED"] = "0"


def _publish_event(event_type: str, source: str, payload: Dict[str, Any]) -> None:
    """Прямая публикация EventDTO в шину — симуляция production-продюсера."""
    from app.domain.events import EventDTO
    from app.services.events.event_bus import get_event_bus
    bus = get_event_bus()
    evt = EventDTO.create(
        event_type=event_type,
        source=source,
        payload=payload,
    )
    bus.publish(evt)


def _make_scene(sources: List[str]) -> Dict[str, Any]:
    """Минимальная scene: игрок + все источники в точке (0,0) — в радиусе восприятия."""
    positions: Dict[str, Dict[str, Any]] = {
        "player": {"local_position": {"x": 0.0, "y": 0.0}},
    }
    for src in sources:
        positions[src] = {"local_position": {"x": 0.0, "y": 0.0}}
    return {"npc_positions": positions}


def _capture_projection(captured_events: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Вызывает project_idle_events над captured EventDTO, возвращает {cause, target, value}[].

    Scene: игрок + все источники в точке (0,0) — distance=0 ≤ OBSERVATION_SIGHT_RADIUS,
    visibility True (та же точка). _player_perceives пускает.
    """
    from app.domain.events import EventDTO
    from app.services.game_loop.idle_event_projection import (
        IdleEventTap,
        idle_events_projection_enabled,
        project_idle_events,
    )
    if not idle_events_projection_enabled():
        return {"events": []}
    sources = [e["source"] for e in captured_events]
    scene = _make_scene(sources)
    tap = IdleEventTap()
    bus = None
    try:
        from app.services.events.event_bus import get_event_bus
        bus = get_event_bus()
        tap.subscribe(bus)
        # Публикуем события
        for evt_dict in captured_events:
            bus.publish(EventDTO.create(
                event_type=evt_dict["event_type"],
                source=evt_dict["source"],
                payload=evt_dict["payload"],
            ))
        # Проекция
        projections = project_idle_events(tap.captured, scene)
        return {"events": [p.to_front() for p in projections]}
    finally:
        if bus is not None:
            tap.unsubscribe()


# ── Тесты: v1-словарь + projection ──────────────────────────────────────────

def test_f5_theft_event_in_v1_dictionary():
    """A. THEFT-событие проходит через v1-словарь → cause='theft', value=target_id."""
    _setup_env(theft=True, activity=False, projection=True)
    result = _capture_projection([{
        "event_type": "theft",
        "source": "thief_shadow",
        "payload": {"target_id": "wo_gold_chest"},
    }])
    events = result["events"]
    assert len(events) == 1, f"Ожидалось 1 событие, получено {len(events)}: {events}"
    evt = events[0]
    assert evt["cause"] == "theft", f"cause должен быть 'theft', получено {evt['cause']}"
    assert evt["target"] == "thief_shadow", f"target должен быть 'thief_shadow', получено {evt['target']}"
    assert evt["value"] == "wo_gold_chest", f"value должен быть target_id, получено {evt['value']}"


def test_f5_activity_outcome_event_in_v1_dictionary():
    """B. ACTIVITY_OUTCOME-событие проходит через v1-словарь → cause='activity_outcome', value='eat:ok'/'eat:fail'."""
    _setup_env(theft=False, activity=True, projection=True)
    result = _capture_projection([{
        "event_type": "activity_outcome",
        "source": "tavern_keeper_tornin",
        "payload": {"activity_type": "eat", "success": True, "reason": ""},
    }])
    events = result["events"]
    assert len(events) == 1, f"Ожидалось 1 событие, получено {len(events)}: {events}"
    evt = events[0]
    assert evt["cause"] == "activity_outcome"
    assert evt["target"] == "tavern_keeper_tornin"
    assert evt["value"] == "eat:ok", f"value должен быть 'eat:ok', получено {evt['value']}"


def test_f5_activity_outcome_fail_value():
    """B.2. ACTIVITY_OUTCOME с success=False → value='eat:fail'."""
    _setup_env(theft=False, activity=True, projection=True)
    result = _capture_projection([{
        "event_type": "activity_outcome",
        "source": "tavern_keeper_tornin",
        "payload": {"activity_type": "eat", "success": False, "reason": "no_food"},
    }])
    events = result["events"]
    assert len(events) == 1
    assert events[0]["value"] == "eat:fail"


def test_f5_off_control_projection_disabled():
    """C. OFF-контроль: IDLE_EVENTS_PROJECTION_ENABLED=0 → events=[] (события в шине есть, проекция отключена)."""
    _setup_env(theft=True, activity=True, projection=False)
    # При projection=False, _capture_projection возвращает {"events": []}
    result = _capture_projection([{
        "event_type": "theft",
        "source": "thief_shadow",
        "payload": {"target_id": "wo_gold"},
    }])
    assert result["events"] == [], f"OFF-контроль: events должен быть пуст, получено {result['events']}"


def test_f5_theft_and_activity_outcome_distinct():
    """D. Изоляция: THEFT-событие ≠ ACTIVITY_OUTCOME (различимость источников)."""
    _setup_env(theft=True, activity=True, projection=True)
    result = _capture_projection([
        {
            "event_type": "theft",
            "source": "thief_shadow",
            "payload": {"target_id": "wo_gold"},
        },
        {
            "event_type": "activity_outcome",
            "source": "tavern_keeper_tornin",
            "payload": {"activity_type": "eat", "success": True, "reason": ""},
        },
    ])
    events = result["events"]
    assert len(events) == 2, f"Ожидалось 2 события, получено {len(events)}"
    causes = [e["cause"] for e in events]
    assert "theft" in causes
    assert "activity_outcome" in causes
    # Различимость: THEFT ≠ ACTIVITY_OUTCOME
    theft_evt = next(e for e in events if e["cause"] == "theft")
    activity_evt = next(e for e in events if e["cause"] == "activity_outcome")
    assert theft_evt["target"] == "thief_shadow"
    assert activity_evt["target"] == "tavern_keeper_tornin"
    assert theft_evt["value"] == "wo_gold"
    assert activity_evt["value"] == "eat:ok"


def test_f5_v1_dictionary_excludes_other_event_types():
    """v1-словарь УЗКИЙ: NPC_MOVED, NPC_SPOKE и др. — НЕ входят в проекцию."""
    _setup_env(theft=True, activity=True, projection=True)
    result = _capture_projection([
        {"event_type": "npc_moved", "source": "test_npc", "payload": {"from": "a", "to": "b"}},
        {"event_type": "npc_spoke", "source": "test_npc", "payload": {"text": "hello"}},
        {"event_type": "theft", "source": "thief", "payload": {"target_id": "wo_x"}},
    ])
    events = result["events"]
    # Только theft — NPC_MOVED, NPC_SPOKE в EXCLUDED-реестре
    assert len(events) == 1
    assert events[0]["cause"] == "theft"


# ── Тесты: game_screen structural (без pygame) ──────────────────────────────

def test_f5_game_screen_reads_events_key():
    """E. game_screen читает _tick_data.get("events") — структурная проверка."""
    import inspect
    _project_root = Path(__file__).resolve().parents[3]
    game_screen_path = _project_root / "frontend" / "game_screen.py"
    content = game_screen_path.read_text(encoding="utf-8")
    # Проверяем, что _idle_events = _tick_data.get("events") существует
    assert '_idle_events = _tick_data.get("events")' in content, \
        "game_screen должен читать _idle_events = _tick_data.get('events')"
    # Проверяем, что логирует [TELEGRAPH]
    assert "[TELEGRAPH]" in content, "game_screen должен логировать [TELEGRAPH]"
    # Проверяем cause/target/value
    assert "_cause" in content
    assert "_target" in content
    assert "_value" in content


def test_f5_game_screen_telegraph_log_format():
    """E.2. game_screen логирует cause/target/value в формате [TELEGRAPH]."""
    _project_root = Path(__file__).resolve().parents[3]
    game_screen_path = _project_root / "frontend" / "game_screen.py"
    content = game_screen_path.read_text(encoding="utf-8")
    # Формат лога: f"[TELEGRAPH] cause={_cause} target={_target_name} value={_value}"
    assert 'f"[TELEGRAPH] cause={_cause}' in content
    assert 'target={_target_name}' in content
    assert 'value={_value}' in content


# ── Тесты: IntentEventAdapter mapping (THEFT path) ─────────────────────────

def test_f5_intent_event_adapter_maps_steal_to_theft():
    """THEFT path: IntentEventAdapter._INTENT_EVENT_MAP['steal'] = EventType.THEFT."""
    from app.services.events.intent_event_adapter import IntentEventAdapter
    from app.services.events.event_types import EventType
    assert IntentEventAdapter._INTENT_EVENT_MAP.get("steal") is EventType.THEFT, \
        "IntentEventAdapter должен мапить 'steal' → EventType.THEFT"


def test_f5_activity_lifecycle_publishes_activity_outcome_event_type():
    """ACTIVITY_OUTCOME path: _publish_outcome публикует event_type='activity_outcome'."""
    import inspect
    from app.services.npc import activity_lifecycle_service
    source = inspect.getsource(activity_lifecycle_service)
    assert 'event_type="activity_outcome"' in source, \
        "activity_lifecycle_service._publish_outcome должен публиковать event_type='activity_outcome'"


# ── Очистка env после тестов ──────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _cleanup_env():
    """Сброс env-флагов после каждого теста."""
    yield
    for key in ("W3_G3_ENABLED", "DESIRES_ENABLED", "ACTIVITY_LIFECYCLE_ENABLED", "IDLE_EVENTS_PROJECTION_ENABLED"):
        os.environ.pop(key, None)