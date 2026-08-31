"""
path: backend/tests/test_affordance_shadow.py
Назначение: Тесты Gate-1 shadow (ADR-O-373): флаг-OFF no-op, вход =
    deepcopy-фото, ноль mutation scene/snapshot, ноль decision-input,
    метрики discovery ≠ execution, отказ наблюдателя не роняет вызов.
Зависимости: pytest, app.services.world.affordance_shadow

Запуск: cd backend; python -m pytest tests/test_affordance_shadow.py tests/test_world_object_spawner.py tests/test_object_fsms.py tests/test_world_object_topology.py tests/test_affordance_resolver.py -q; cd ..
"""
import copy

import pytest
from app.services.world.affordance_shadow import (
    ShadowMetrics,
    _shadow_enabled,
    run_affordance_shadow_guarded,
)


def _snap():
    """Мин. снапшот: 2 стула (FREE, AVAILABLE) + 1 дверь CLOSED."""
    _wo = {
        "wo_c1": {"object_id": "wo_c1", "archetype": "chair",
                  "location_id": "tavern", "position": [1.0, 1.0],
                  "state": "INTACT", "holder": None, "container_id": None,
                  "supported_by": None, "attachment": None,
                  "occupancy": None, "used_by": None, "ownership": None,
                  "damage": 0.0, "interaction_history_ref": None},
        "wo_c2": {"object_id": "wo_c2", "archetype": "chair",
                  "location_id": "tavern", "position": [12.0, 12.0],
                  "state": "INTACT", "holder": None, "container_id": None,
                  "supported_by": None, "attachment": None,
                  "occupancy": None, "used_by": None, "ownership": None,
                  "damage": 0.0, "interaction_history_ref": None},
        "wo_d1": {"object_id": "wo_d1", "archetype": "door",
                  "location_id": "tavern", "position": [8.0, 13.0],
                  "state": "CLOSED", "holder": None, "container_id": None,
                  "supported_by": None, "attachment": None,
                  "occupancy": None, "used_by": None, "ownership": None,
                  "damage": 0.0, "interaction_history_ref": None},
    }
    class _Snap:
        tick = 1
        world_objects = _wo
        npc_positions = {
            "npc_a": {"local_position": {"x": 1.2, "y": 1.0}},
            "npc_b": {"local_position": {"x": 50.0, "y": 50.0}},
        }
    return _Snap()


def _npcs():
    # §12.4 real-data-first: реальный здоровый body_state (прецедент
    # W2-тестов — _healthy), не самодельный «объект мечты».
    from app.models.npc_state import BODY_STATE_HEALTHY
    return [{
        "npc_id": "npc_a",
        "body_state": dict(BODY_STATE_HEALTHY),
    }, {
        "npc_id": "npc_b",
        "body_state": dict(BODY_STATE_HEALTHY),
    }]


def test_flag_off_full_noop(monkeypatch):
    monkeypatch.delenv("W3_SHADOW_ENABLED", raising=False)
    _snap_before = copy.deepcopy(_snap().world_objects)
    assert _shadow_enabled() is False
    count, metrics = run_affordance_shadow_guarded(1, _snap(), _npcs(), "tavern")
    assert count == 0
    assert metrics.resolve_calls == 0  # резолвер НЕ вызывался
    assert _snap().world_objects == _snap_before  # мир не тронут


def test_flag_off_no_resolver_call(monkeypatch):
    monkeypatch.delenv("W3_SHADOW_ENABLED", raising=False)
    # guarded OFF → run_affordance_shadow вообще не выполняется:
    # патчим имя в МОДУЛЕ (guarded вызывает через глобальное имя
    # этого же модуля — биндинг один, патч перехватывает вызов).
    monkeypatch.setattr(
        "app.services.world.affordance_shadow.run_affordance_shadow",
        lambda *a, **k: pytest.fail("resolver called under OFF flag"))
    run_affordance_shadow_guarded(1, _snap(), _npcs(), "tavern")


def test_flag_on_resolves_and_reports(monkeypatch):
    monkeypatch.setenv("W3_SHADOW_ENABLED", "1")
    _snapshot = _snap()
    _scene_frozen = copy.deepcopy(_snapshot.world_objects)
    count, metrics = run_affordance_shadow_guarded(
        1, _snapshot, _npcs(), "tavern")
    assert metrics.npcs_seen == 2
    assert metrics.objects_seen == 3
    # 2 NPC × 3 объекта
    assert metrics.resolve_calls == 6
    # npc_a рядом со стулом (1.2/1.0 vs 1.0/1.0): SIT/TAKE/MOVE/KICK
    # NPC_b (50/50) — вне adjacency: действий нет
    assert count > 0
    assert _snapshot.world_objects == _scene_frozen  # ноль mutation


def test_shadow_never_mutates_scene(monkeypatch):
    monkeypatch.setenv("W3_SHADOW_ENABLED", "1")
    _snapshot = _snap()
    _before = copy.deepcopy(_snapshot.world_objects)
    _before_npc_pos = copy.deepcopy(_snapshot.npc_positions)
    run_affordance_shadow_guarded(1, _snapshot, _npcs(), "tavern")
    assert _snapshot.world_objects == _before
    assert _snapshot.npc_positions == _before_npc_pos


def test_observer_failure_does_not_kill_call(monkeypatch):
    monkeypatch.setenv("W3_SHADOW_ENABLED", "1")
    _snapshot = _snap()
    # Сбой внутри резолвера: патчим метод ИСХОДНОГО класса
    # (имя в shadow-модуле — биндинг, AttributeError патчить нельзя).
    monkeypatch.setattr(
        "app.services.world.affordance_resolver.AffordanceResolver.resolve",
        staticmethod(lambda *a, **k: (_ for _ in ()).throw(
            RuntimeError("resolver crash")))
    )
    count, metrics = run_affordance_shadow_guarded(
        1, _snapshot, _npcs(), "tavern")
    assert count == 0  # отказ наблюдателя: ноль, но вызов не упал
    assert isinstance(metrics, ShadowMetrics)


def test_metrics_discovery_not_execution(monkeypatch):
    """Метрики тени — только discovery (available/blocked/failed):
    в G1 их нельзя смешивать с execution-причинами (stale/reject)."""
    monkeypatch.setenv("W3_SHADOW_ENABLED", "1")
    _count, _m = run_affordance_shadow_guarded(1, _snap(), _npcs(), "tavern")
    _fields = set(ShadowMetrics.__dataclass_fields__.keys())
    assert _fields == {
        "npcs_seen", "objects_seen", "resolve_calls",
        "available_actions", "blocked_actions", "failed_predicates"}


def test_npc_without_position_skipped(monkeypatch):
    monkeypatch.setenv("W3_SHADOW_ENABLED", "1")
    class _SnapNoPos:
        world_objects = _snap().world_objects
        npc_positions = {"npc_a": {"local_position": {"x": 1.2, "y": 1.0}}}
    _count, _m = run_affordance_shadow_guarded(
        1, _SnapNoPos(), _npcs(), "tavern")
    assert _m.npcs_seen == 1


def test_falsy_body_state_propagates_to_guarded(monkeypatch):
    """L2.2: falsy body_state → ValueError фабрики → guarded ловит,
    возвращает ноль/метрики; наблюдатель не роняет тик и не глотает."""
    monkeypatch.setenv("W3_SHADOW_ENABLED", "1")
    _npcs_bad = [{"npc_id": "npc_a", "body_state": None}]
    count, metrics = run_affordance_shadow_guarded(
        1, _snap(), _npcs_bad, "tavern")
    assert count == 0
    assert isinstance(metrics, ShadowMetrics)