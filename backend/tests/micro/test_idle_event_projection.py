"""
path: /project/backend/tests/micro/test_idle_event_projection.py
Назначение: микро-замки ADR-O-420 (LC-IMPL-1): полнота словаря проекции
    (enum == словарь ∪ EXCLUDED — молчаливых дыр нет), полярность флага,
    value-экстракторы (fail-loud), read-only чистота, гейт восприятия
    (private/whisper-адресат/мембрана близко-далеко-LOS/Vacuum),
    деградация наблюдателя (не крах тика), детерминизм, tap-окно.
Зависимости: pytest, app.domain.events, app.domain.idle_projection,
    app.services.game_loop.idle_event_projection,
    app.services.spatial.spatial_query_service
Основные сущности: test_* (18 замков)
"""
from __future__ import annotations

import copy
from typing import Any, Dict, List

import pytest

from app.domain.events import EventDTO
from app.domain.idle_projection import IdleEventProjection
from app.services.events.event_types import EventType
from app.services.game_loop import idle_event_projection as iep
from app.services.spatial.spatial_query_service import SpatialQueryService


# ── Фабрики (объект реальности: EventDTO.create, §13.4) ─────────────────


def _evt(
    event_type: str,
    source: str = "npc_a",
    payload: Dict[str, Any] | None = None,
    visibility: str = "public",
) -> EventDTO:
    return EventDTO.create(
        event_type=event_type,
        source=source,
        payload=payload or {},
        visibility=visibility,  # type: ignore[arg-type]
    )


def _scene(positions: Dict[str, Any]) -> Dict[str, Any]:
    """Минимальная сцена: проекция читает из неё только npc_positions."""
    return {"npc_positions": positions}


def _pos(x: float, y: float) -> Dict[str, Any]:
    return {"local_position": {"x": x, "y": y}}


_EAT_OK: Dict[str, Any] = {"activity_type": "eat", "success": True}


# ── 1. Полнота словаря ──────────────────────────────────────────────────


def test_dictionary_completeness_no_silent_holes() -> None:
    covered = set(iep.PROJECTION_EVENT_TYPES) | set(iep.EXCLUDED_EVENT_TYPES)
    enum_members = set(EventType)
    assert covered == enum_members, (
        "ADR-O-420: EventType без вердикта проекции: "
        f"{sorted(e.value for e in enum_members - covered)}; "
        f"лишние в реестрах: {sorted(e.value for e in covered - enum_members)}"
    )


def test_dictionary_is_exactly_v1_scope() -> None:
    """v1-словарь (вердикт Мастера В2): ровно ACTIVITY_OUTCOME + THEFT."""
    assert set(iep.PROJECTION_EVENT_TYPES) == {
        EventType.ACTIVITY_OUTCOME,
        EventType.THEFT,
    }
    assert EventType.NPC_MOVED in iep.EXCLUDED_EVENT_TYPES


# ── 2. Флаг (default OFF фиксирует commit A; флип ON — commit D
#        обновляет первое утверждение этим же коммитом) ──────────────────


def test_flag_default_on_and_overridable(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default ON с коммита D (вердикт В4): delenv = включён; OFF — только
    явным env. Вечный мёртвый выключатель не оставляется."""
    monkeypatch.delenv("IDLE_EVENTS_PROJECTION_ENABLED", raising=False)
    assert iep.idle_events_projection_enabled() is True
    monkeypatch.setenv("IDLE_EVENTS_PROJECTION_ENABLED", "0")
    assert iep.idle_events_projection_enabled() is False
    monkeypatch.setenv("IDLE_EVENTS_PROJECTION_ENABLED", "1")
    assert iep.idle_events_projection_enabled() is True


# ── 3. value-экстракторы: контракты продюсеров ──────────────────────────


def test_extractor_activity_outcome_ok_fail() -> None:
    assert iep._value_activity_outcome(_EAT_OK) == "eat:ok"
    assert (
        iep._value_activity_outcome({"activity_type": "eat", "success": False})
        == "eat:fail"
    )


def test_extractor_activity_outcome_fail_loud() -> None:
    with pytest.raises(ValueError):
        iep._value_activity_outcome({"success": True})
    with pytest.raises(ValueError):
        iep._value_activity_outcome({"activity_type": "eat", "success": "yes"})


def test_extractor_theft_target() -> None:
    assert iep._value_theft({"target_id": "obj_42"}) == "obj_42"
    with pytest.raises(ValueError):
        iep._value_theft({})
    with pytest.raises(ValueError):
        iep._value_theft({"target_id": 42})


# ── 4. Гейт восприятия (мембрана: visibility стабится — формат стен
#        сцены в микро-тесте не угадывается, §13.1; интеграция — SUPERBOX) ─


def test_membrane_near_far(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(SpatialQueryService, "visibility", lambda s, a, b: True)
    near = iep.project_idle_events(
        [_evt("activity_outcome", payload=_EAT_OK)],
        _scene({"player": _pos(0.0, 0.0), "npc_a": _pos(3.0, 0.0)}),
    )
    assert [p.to_front() for p in near] == [
        {"cause": "activity_outcome", "target": "npc_a", "value": "eat:ok"}
    ]
    far = iep.project_idle_events(
        [_evt("activity_outcome", payload=_EAT_OK)],
        _scene({"player": _pos(0.0, 0.0), "npc_a": _pos(50.0, 0.0)}),
    )
    assert far == []


def test_membrane_los_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(SpatialQueryService, "visibility", lambda s, a, b: False)
    out = iep.project_idle_events(
        [_evt("activity_outcome", payload=_EAT_OK)],
        _scene({"player": _pos(0.0, 0.0), "npc_a": _pos(3.0, 0.0)}),
    )
    assert out == []


def test_whisper_addressee_player_perceives(monkeypatch: pytest.MonkeyPatch) -> None:
    """Кража у игрока: whisper-адресат видит даже без позиций/LOS."""
    monkeypatch.setattr(SpatialQueryService, "visibility", lambda s, a, b: False)
    evt = _evt(
        "theft",
        payload={"target_id": "player"},
        visibility="whisper",
    )
    out = iep.project_idle_events([evt], _scene({"npc_a": _pos(0.0, 0.0)}))
    assert [p.to_front() for p in out] == [
        {"cause": "theft", "target": "npc_a", "value": "player"}
    ]


def test_whisper_other_addressee_not_player(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(SpatialQueryService, "visibility", lambda s, a, b: True)
    evt = _evt(
        "theft",
        payload={"target_id": "npc_b"},
        visibility="whisper",
    )
    out = iep.project_idle_events(
        [evt],
        _scene({"player": _pos(0.0, 0.0), "npc_a": _pos(50.0, 0.0)}),
    )
    assert out == []


def test_private_event_never_projected(monkeypatch: pytest.MonkeyPatch) -> None:
    """§17.3: private видит только источник; вплотную — всё равно нет."""
    monkeypatch.setattr(SpatialQueryService, "visibility", lambda s, a, b: True)
    evt = _evt("activity_outcome", payload=_EAT_OK, visibility="private")
    out = iep.project_idle_events(
        [evt], _scene({"player": _pos(0.0, 0.0), "npc_a": _pos(1.0, 0.0)})
    )
    assert out == []


def test_vacuum_player_absent_silence() -> None:
    """Игрока нет в сцене → дистанция 999 (Vacuum ≠ Neutral) → тишина."""
    out = iep.project_idle_events(
        [_evt("activity_outcome", payload=_EAT_OK)],
        _scene({"npc_a": _pos(0.0, 0.0)}),
    )
    assert out == []


# ── 5. Чистота и детерминизм ────────────────────────────────────────────


def test_projection_readonly_scene_and_captured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(SpatialQueryService, "visibility", lambda s, a, b: True)
    scene = _scene({"player": _pos(0.0, 0.0), "npc_a": _pos(2.0, 0.0)})
    scene_before = copy.deepcopy(scene)
    events = [
        _evt("activity_outcome", payload=_EAT_OK),
        _evt("theft", payload={"target_id": "obj_42"}),
    ]
    iep.project_idle_events(events, scene)
    assert scene == scene_before  # §15.4-8: мир не изменён
    assert [e.type for e in events] == ["activity_outcome", "theft"]  # вход цел


def test_projection_deterministic(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(SpatialQueryService, "visibility", lambda s, a, b: True)
    scene = _scene({"player": _pos(0.0, 0.0), "npc_a": _pos(2.0, 0.0)})
    events = [_evt("activity_outcome", payload=_EAT_OK)]
    first = iep.project_idle_events(events, copy.deepcopy(scene))
    second = iep.project_idle_events(events, copy.deepcopy(scene))
    assert first == second


def test_projection_shape_exactly_three_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Формат вербатим LC-01: ровно {cause, target, value} — ничего сверх."""
    monkeypatch.setattr(SpatialQueryService, "visibility", lambda s, a, b: True)
    out = iep.project_idle_events(
        [_evt("activity_outcome", payload=_EAT_OK)],
        _scene({"player": _pos(0.0, 0.0), "npc_a": _pos(2.0, 0.0)}),
    )
    assert isinstance(out[0], IdleEventProjection)
    assert set(out[0].to_front()) == {"cause", "target", "value"}


# ── 6. Деградация наблюдателя (§11.2: не крах тика) ─────────────────────


def test_extractor_degradation_skips_bad_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(SpatialQueryService, "visibility", lambda s, a, b: True)
    scene = _scene({"player": _pos(0.0, 0.0), "npc_a": _pos(2.0, 0.0)})
    events = [
        _evt("activity_outcome", payload={"activity_type": "eat"}),  # контракт бит
        _evt("activity_outcome", payload=_EAT_OK),
    ]
    out = iep.project_idle_events(events, scene)
    assert [p.value for p in out] == ["eat:ok"]


def test_observer_degradation_no_crash(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(self: Any, a: str, b: str) -> bool:
        raise RuntimeError("observer failure")

    monkeypatch.setattr(SpatialQueryService, "visibility", _boom)
    out = iep.project_idle_events(
        [_evt("activity_outcome", payload=_EAT_OK)],
        _scene({"player": _pos(0.0, 0.0), "npc_a": _pos(2.0, 0.0)}),
    )
    assert out == []  # ошибка наблюдателя = пропуск, не исключение


# ── 7. Tap-окно: подписка ровно на словарь, захват, чистый демонтаж ─────


class _StubBus:
    """Duck-стаб шины: tap использует только subscribe/unsubscribe."""

    def __init__(self) -> None:
        self.handlers: Dict[str, List[Any]] = {}

    def subscribe(self, event_type: Any, handler: Any) -> None:
        self.handlers.setdefault(event_type.value, []).append(handler)

    def unsubscribe(self, event_type: Any, handler: Any) -> None:
        handlers = self.handlers.get(event_type.value, [])
        if handler in handlers:
            handlers.remove(handler)


def test_tap_window_capture_and_cleanup() -> None:
    bus = _StubBus()
    tap = iep.IdleEventTap()
    tap.subscribe(bus)
    assert set(bus.handlers) == {et.value for et in iep.PROJECTION_EVENT_TYPES}
    assert all(len(v) == 1 for v in bus.handlers.values())
    # захват: шина зовёт handler синхронно — дергаем напрямую
    bus.handlers["activity_outcome"][0](_evt("activity_outcome", payload=_EAT_OK))
    bus.handlers["theft"][0](_evt("theft", payload={"target_id": "obj_42"}))
    assert [e.type for e in tap.captured] == ["activity_outcome", "theft"]
    tap.unsubscribe()
    assert all(not v for v in bus.handlers.values())  # окно не течёт