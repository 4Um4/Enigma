"""
path: /project/backend/tests/micro/test_npc_addresses_player.py
Назначение: 8 контрактов ADR-O-436 NPC_ADDRESSES_PLAYER producer (LC-IMPL-3 Ступень A).
    Интеграционный тест: вызывает реальный execute_persistence с минимальным ctx,
    перехватывая события через monkeypatch get_event_bus (singleton bypass).
    Идемпотентность producer'а опирается на tick-lifecycle контракт
    (один execute_persistence на тик) — не на внутренние флаги/реестры.
Зависимости: app.services.phases.commit_phase, app.services.events.event_bus,
    app.services.events.event_identity, app.domain.events
Основные сущности: тесты battery A-H
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.domain.events import EventDTO  # noqa: F401 — sanity import
from app.services.events.event_bus import EventBus
from app.services.events.event_identity import next_event_identity
from app.services.events.event_types import EventType
from app.services.phases.commit_phase import execute_persistence


# ── Helpers ──────────────────────────────────────────────────────────────


def _make_bus(scene: dict) -> EventBus:
    """Свежая шина с identity-провайдером (по образцу test_event_identity.py)."""
    bus = EventBus()
    bus.set_identity_provider(lambda t, s: next_event_identity(scene, t, s))
    return bus


def _npc(
    npc_id: str = "lusya",
    intent: str | None = "talk",
    target: str | None = "player",
    formed_at: int | None = 100,
) -> dict:
    """Канонический NPC dict в форме to_persistence_dict (npc_state.py:1010-1030)."""
    return {
        "npc_id": npc_id,
        "id": npc_id,
        "intent": intent,
        "intent_target": target,
        "intent_formed_at": formed_at,
        "intent_duration": 5,
        "intent_progress_ticks": 0,
        "last_intent_change": 100,
    }


def _build_ctx(
    tick: int = 100,
    npcs: list | None = None,
    scene_state: dict | None = None,
) -> SimpleNamespace:
    """Минимальный ctx для execute_persistence (idle-path).

    Поля подобраны так, чтобы:
      - DRF drain (L29) — no-op (drain возвращает [])
      - None-gate (L42-45) — проходит (orchestrator._scene_manager not None)
      - interpretation_snapshot=None (L48) — skip
      - delta_buffer=[] (L53) — skip flush path
      - producer (L82-135) — выполняется с all_npcs_raw и tick_number
      - SIL (L138) — skip (semantic_buffer=None)
      - idle-else (L174-200):
          - L177-178: engine.update_cache — OK (mock orchestrator)
          - L181: ctx.tick_events = ctx.decision_events ([])
          - L184: scene_changes=[] → skip apply_changes
          - L190-195: _scene_manager.commit — OK (mock, returns 1)
          - L194: significant_events or [] — []
    """
    drf = MagicMock()
    drf.drain.return_value = []  # L29-32: итерация по [] — нет TypeError
    return SimpleNamespace(
        tick_number=tick,
        all_npcs_raw=list(npcs) if npcs is not None else [],
        delta_buffer=[],
        interpretation_snapshot=None,
        semantic_buffer=None,
        drf_bus=drf,
        scene_state=scene_state or {"tick": tick},
        campaign_id="test_campaign",
        shared_context=None,
        dirty_npcs=set(),
        prop_dirty=False,
        scene_changes=[],
        decision_events=[],      # L181: ctx.tick_events = ctx.decision_events
        significant_events=[],   # L194: significant_events=ctx.significant_events or []
        tick_events=[],          # L181 write target (pre-set для safety)
    )


def _build_orchestrator() -> SimpleNamespace:
    """Минимальный orchestrator для execute_persistence idle-path.

    Idle-path (L174-200) требования:
      - _scene_manager.commit(...) — всегда вызывается (returns 1 = saved>0)
      - _scene_manager.apply_changes(...) — только если scene_changes непуст (у нас [])
      - _get_life_engine() — возвращает mock с update_cache (L177-178)
      - _state_applicator — None (L65, L76: apply_batch skip)
    """
    orch = SimpleNamespace()
    orch._scene_manager = MagicMock()
    orch._scene_manager.commit.return_value = 1  # L197: saved > 0 → debug log
    orch._state_applicator = None  # L65, L76: None-gate → apply_batch skip
    _engine_mock = MagicMock()
    orch._get_life_engine = lambda: _engine_mock  # L177: engine.update_cache(...)
    return orch


@pytest.fixture
def bus(monkeypatch):
    """Свежая шина (tick=100) + monkeypatch get_event_bus.

    Producer-block делает `from app.services.events.event_bus import get_event_bus`
    ВНУТРИ функции — resolves at call time. Патчим модуль-источник.
    Синглтон _bus не затрагивается — изоляция теста.
    """
    scene = {"tick": 100}
    fresh = _make_bus(scene)
    monkeypatch.setattr(
        "app.services.events.event_bus.get_event_bus", lambda: fresh
    )
    return fresh


def _run(ctx, orch) -> None:
    """Вызывает execute_persistence (idle path)."""
    execute_persistence(ctx, orch, is_player_turn=False)


def _addr_events(bus: EventBus) -> list:
    """Только NPC_ADDRESSES_PLAYER из _event_log."""
    return [
        e for e in bus._event_log
        if e.type == EventType.NPC_ADDRESSES_PLAYER.value
    ]


# ── Контракт A: Accept (валидное обращение публикует событие) ────────────


def test_A1_valid_npc_publishes_one_event(bus):
    ctx = _build_ctx(tick=100, npcs=[_npc(intent="talk", formed_at=100)])
    _run(ctx, _build_orchestrator())
    evts = _addr_events(bus)
    assert len(evts) == 1


def test_A2_event_fields_canonical(bus):
    ctx = _build_ctx(
        tick=100, npcs=[_npc(npc_id="lusya", intent="talk", formed_at=100)]
    )
    _run(ctx, _build_orchestrator())
    e = _addr_events(bus)[0]
    assert e.type == "npc_addresses_player"
    assert e.source == "lusya"
    assert e.visibility == "whisper"
    assert e.persistence_level == "working"
    assert e.payload == {
        "intent": "talk",
        "target_id": "player",
        "intent_formed_at": 100,
    }


@pytest.mark.parametrize(
    "intent_key",
    [
        "talk", "warn", "trade", "offer_job",
        "request_service", "help", "report", "intimidate",
    ],
)
def test_A3_all_8_intents_accepted(bus, intent_key):
    ctx = _build_ctx(
        tick=100, npcs=[_npc(intent=intent_key, formed_at=100)]
    )
    _run(ctx, _build_orchestrator())
    evts = _addr_events(bus)
    assert len(evts) == 1
    assert evts[0].payload["intent"] == intent_key


# ── Контракт B: No false positives ──────────────────────────────────────


def test_B1_missing_intent_skipped(bus):
    npc = _npc()
    npc.pop("intent")
    _run(_build_ctx(npcs=[npc]), _build_orchestrator())
    assert _addr_events(bus) == []


def test_B2_missing_target_skipped(bus):
    npc = _npc()
    npc.pop("intent_target")
    _run(_build_ctx(npcs=[npc]), _build_orchestrator())
    assert _addr_events(bus) == []


def test_B3_missing_formed_at_skipped(bus):
    npc = _npc()
    npc.pop("intent_formed_at")
    _run(_build_ctx(npcs=[npc]), _build_orchestrator())
    assert _addr_events(bus) == []


def test_B4_intent_none_skipped(bus):
    _run(_build_ctx(npcs=[_npc(intent=None)]), _build_orchestrator())
    assert _addr_events(bus) == []


def test_B5_target_not_player_skipped(bus):
    _run(_build_ctx(npcs=[_npc(target="borko")]), _build_orchestrator())
    assert _addr_events(bus) == []


def test_B6_formed_at_wrong_tick_skipped(bus):
    """intent_formed_at != tick_now — событие уже публиковалось в прошлом тике."""
    _run(
        _build_ctx(tick=100, npcs=[_npc(formed_at=99)]),
        _build_orchestrator(),
    )
    assert _addr_events(bus) == []


def test_B7_unknown_intent_skipped(bus):
    _run(_build_ctx(npcs=[_npc(intent="dance")]), _build_orchestrator())
    assert _addr_events(bus) == []


def test_B8_tick_zero_skipped(bus):
    """_tick_now > 0 гейт — тик 0 не публикует (защита от инициализации)."""
    _run(
        _build_ctx(tick=0, npcs=[_npc(formed_at=0)]),
        _build_orchestrator(),
    )
    assert _addr_events(bus) == []


def test_B9_empty_npcs_skipped(bus):
    _run(_build_ctx(npcs=[]), _build_orchestrator())
    assert _addr_events(bus) == []


def test_B10_npc_id_player_skipped(bus):
    """NPC с id=player в all_npcs_raw пропускается (defensive)."""
    _run(
        _build_ctx(npcs=[_npc(npc_id="player")]),
        _build_orchestrator(),
    )
    assert _addr_events(bus) == []


def test_B11_formed_at_non_numeric_skipped(bus):
    """Non-int formed_at — TypeError/ValueError, продолжаем без публикации."""
    npc = _npc()
    npc["intent_formed_at"] = "abc"
    _run(_build_ctx(npcs=[npc]), _build_orchestrator())
    assert _addr_events(bus) == []


# ── Контракт C: Cross-tick idempotency ──────────────────────────────────


def test_C1_same_intent_next_tick_no_republish(bus):
    """intent_formed_at=100, tick_now=101 — intent не сменился, formed_at не обновился.

    Гейт `formed_at == tick_now` ложен — событие не публикуется.
    Это естественная кросс-tick идемпотентность без флагов/реестров.
    """
    _run(
        _build_ctx(tick=101, npcs=[_npc(formed_at=100)]),
        _build_orchestrator(),
    )
    assert _addr_events(bus) == []


def test_C2_double_call_same_tick_documents_lifecycle_contract(bus):
    """Документация контракта: producer-блок НЕ подавляет повторную публикацию
    в том же тике — идемпотентность гарантируется tick-lifecycle (один
    execute_persistence на тик), а не producer-логикой.

    Гейт `formed_at == tick_now` ничего не знает о прошлом. Если caller нарушит
    контракт одного вызова, второй вызов опубликует снова, но с новым ordinal
    (Single Writer) → другой event_id.
    """
    ctx = _build_ctx(tick=100, npcs=[_npc(formed_at=100)])
    orch = _build_orchestrator()
    _run(ctx, orch)
    _run(ctx, orch)
    evts = _addr_events(bus)
    assert len(evts) == 2  # обе публикации прошли гейт
    assert evts[0].id != evts[1].id  # разные ordinal → разные id


# ── Контракт D: Whisper privacy ─────────────────────────────────────────


def test_D1_visibility_whisper(bus):
    _run(_build_ctx(npcs=[_npc()]), _build_orchestrator())
    assert _addr_events(bus)[0].visibility == "whisper"


def test_D2_persistence_working(bus):
    _run(_build_ctx(npcs=[_npc()]), _build_orchestrator())
    assert _addr_events(bus)[0].persistence_level == "working"


# ── Контракт E: Read-only (all_npcs_raw не мутируется) ──────────────────


def test_E1_all_npcs_raw_keys_unchanged(bus):
    npc = _npc(npc_id="lusya", intent="warn", formed_at=100)
    keys_before = set(npc.keys())
    _run(_build_ctx(npcs=[npc]), _build_orchestrator())
    assert set(npc.keys()) == keys_before, (
        f"добавлены ключи: {set(npc.keys()) - keys_before}"
    )


def test_E2_all_npcs_raw_values_unchanged(bus):
    npc = _npc(npc_id="lusya", intent="warn", formed_at=100)
    snapshot = dict(npc)
    _run(_build_ctx(npcs=[npc]), _build_orchestrator())
    for k, v in snapshot.items():
        assert npc[k] == v, f"поле {k} изменено: {v!r} → {npc[k]!r}"


def test_E3_tick_number_unchanged(bus):
    ctx = _build_ctx(tick=100, npcs=[_npc()])
    _run(ctx, _build_orchestrator())
    assert ctx.tick_number == 100


# ── Контракт F: Replay determinism (Single Writer) ──────────────────────


def test_F1_replay_same_sequence_same_ids(monkeypatch):
    """Один и тот же поток → те же event_id (Single Writer next_event_identity).

    Ordinal-счётчик хранится в scene_state["event_ordinals"] и инкрементируется
    единым писателем (event_identity.py:13). Повтор того же потока в свежей
    scene → тот же ordinal → тот же event_id (MD5(type:source:tick:ordinal)).
    """
    scene1 = {"tick": 100}
    bus1 = _make_bus(scene1)
    monkeypatch.setattr(
        "app.services.events.event_bus.get_event_bus", lambda: bus1
    )
    _run(
        _build_ctx(
            tick=100,
            npcs=[_npc(npc_id="lusya", intent="talk", formed_at=100)],
        ),
        _build_orchestrator(),
    )
    id1 = _addr_events(bus1)[0].id

    scene2 = {"tick": 100}
    bus2 = _make_bus(scene2)
    monkeypatch.setattr(
        "app.services.events.event_bus.get_event_bus", lambda: bus2
    )
    _run(
        _build_ctx(
            tick=100,
            npcs=[_npc(npc_id="lusya", intent="talk", formed_at=100)],
        ),
        _build_orchestrator(),
    )
    id2 = _addr_events(bus2)[0].id

    assert id1 == id2, f"replay нарушил детерминизм: {id1} vs {id2}"


# ── Контракт G: Single producer per NPC ─────────────────────────────────


def test_G1_multiple_addressing_npcs_each_one_event(bus):
    npcs = [
        _npc(npc_id="lusya", intent="talk", formed_at=100),
        _npc(npc_id="borko", intent="warn", formed_at=100),
        _npc(npc_id="mira", intent="help", formed_at=100),
    ]
    _run(_build_ctx(tick=100, npcs=npcs), _build_orchestrator())
    evts = _addr_events(bus)
    assert len(evts) == 3
    assert {e.source for e in evts} == {"lusya", "borko", "mira"}


def test_G2_mixed_addressing_and_non_addressing(bus):
    npcs = [
        _npc(npc_id="lusya", intent="talk", formed_at=100),
        _npc(npc_id="borko", intent="idle", formed_at=100),  # не в множестве
        _npc(
            npc_id="mira", intent="help", target="kira", formed_at=100
        ),  # target != player
        _npc(npc_id="kira", intent="warn", formed_at=100),
    ]
    _run(_build_ctx(tick=100, npcs=npcs), _build_orchestrator())
    evts = _addr_events(bus)
    assert {e.source for e in evts} == {"lusya", "kira"}


# ── Контракт H: APPROACH exclusion ──────────────────────────────────────


def test_H1_approach_excluded(bus):
    """APPROACH — движение (motion_core.py:18, action_intent_bridge.py:27),
    не обращение. audit Г: APPROACH исключён из _addr_intents."""
    _run(
        _build_ctx(npcs=[_npc(intent="approach", formed_at=100)]),
        _build_orchestrator(),
    )
    assert _addr_events(bus) == []


def test_H2_approach_uppercase_excluded(bus):
    """Регистронезависимая проверка: 'APPROACH'.lower() тоже не в множестве."""
    _run(
        _build_ctx(npcs=[_npc(intent="APPROACH", formed_at=100)]),
        _build_orchestrator(),
    )
    assert _addr_events(bus) == []