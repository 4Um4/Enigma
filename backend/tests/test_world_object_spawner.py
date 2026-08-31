"""
path: backend/tests/test_world_object_spawner.py
Назначение: Тесты W3 production-spawner (ADR-O-373). Гварды:
    SpawnMapping-фильтр, identity-детерминизм (вердикт Мастера),
    state-проекция В-2, W0-фильтр presentation-полей, fault isolation,
    fallback editor-id, запись через стор.
Зависимости: pytest, app.services.world.world_object_spawner,
    app.services.world.world_object_store, app.domain.world_object

    Запуск: cd backend; python -m pytest tests/test_world_object_spawner.py tests/test_object_fsms.py tests/test_world_object_topology.py tests/test_affordance_resolver.py -q; cd ..
"""
import pytest
from app.services.world.world_object_spawner import (
    SpawnReport,
    WorldObjectSpawner,
    _deterministic_object_id,
    _project_initial_state,
)
from app.services.world.world_object_store import WorldObjectStore


def _scene() -> dict:
    return {"world_objects": {}}


def _editor_obj(etype: str, **overrides) -> dict:
    """Структура по print-археологии tavern.json (real-data-first)."""
    base = {
        "type": etype,
        "position": {"x": 10.5, "y": 3.0},
        "size": {"w": 1.5, "h": 1.5, "d": 0.8},
        "rotation": 0,
        "passability": {"walk": False, "jump_over": True},
        "cover": 0.5,
        "color": "#8B7355",
        "id": f"obj_{etype}",
        "name": f"Объект {etype}",
        "show_name": True,
        "sprite": ["текстуры/Утварь трактира", 805, 177, 253, 150],
        "properties": {"open": True, "locked": False, "durability": 20},
    }
    base.update(overrides)
    return base


def test_spawn_mapping_filters_unmapped():
    editor = {"objects": [
        _editor_obj("table"), _editor_obj("wall"),
        _editor_obj("decoration"), _editor_obj("bar"),
    ]}
    report = WorldObjectSpawner.spawn_from_editor(
        _scene(), "Open_road", "tavern", editor)
    assert report.spawned == 0
    assert len(report.skipped_unmapped) == 4
    assert report.faults == ()


def test_door_and_door_transition_map_to_door():
    editor = {"objects": [_editor_obj("door"), _editor_obj("door_transition")]}
    scene = _scene()
    report = WorldObjectSpawner.spawn_from_editor(
        scene, "Open_road", "tavern", editor)
    assert report.spawned == 2
    for _oid in report.spawned_ids:
        assert WorldObjectStore.get(scene, _oid).archetype == "door"


def test_door_initial_state_projection():
    # В-2: locked → LOCKED (приоритет); open → OPEN; default → CLOSED
    assert _project_initial_state("door", {"locked": True, "open": True}) == "LOCKED"
    assert _project_initial_state("door", {"locked": False, "open": True}) == "OPEN"
    assert _project_initial_state("door", {"locked": False, "open": False}) == "CLOSED"


def test_chair_spawns_intact_with_position():
    editor = {"objects": [_editor_obj("chair", position={"x": 4.25, "y": 7.0})]}
    scene = _scene()
    report = WorldObjectSpawner.spawn_from_editor(
        scene, "Open_road", "tavern", editor)
    obj = WorldObjectStore.get(scene, report.spawned_ids[0])
    assert obj.archetype == "chair"
    assert obj.state == "INTACT"  # damage-track; AVAILABLE — деривация W1
    assert obj.position == (4.25, 7.0)
    assert obj.location_id == "tavern"


def test_object_id_deterministic_and_stable():
    a = _deterministic_object_id("Open_road", "tavern", "obj_7")
    b = _deterministic_object_id("Open_road", "tavern", "obj_7")
    c = _deterministic_object_id("Open_road", "city_gate", "obj_7")
    d = _deterministic_object_id("Open_road", "tavern", "obj_8")
    assert a == b            # детерминизм (replay)
    assert len({a, c, d}) == 3  # provenance различает локацию/editor_id
    assert a.startswith("wo_") and len(a) == 3 + 16
    import re
    assert re.fullmatch(r"wo_[0-9a-f]{16}", a)


def test_presentation_fields_not_projected():
    editor = {"objects": [_editor_obj("door")]}
    scene = _scene()
    report = WorldObjectSpawner.spawn_from_editor(
        scene, "Open_road", "tavern", editor)
    raw = scene["world_objects"][report.spawned_ids[0]]
    # W0-инвариант: ни одного ключа из presentation/spatial editor-полей
    for _forbidden in ("sprite", "color", "name", "show_name",
                       "size", "passability", "cover", "rotation",
                       "properties", "durability", "wall_id"):
        assert _forbidden not in raw, f"W0-утечка: {_forbidden}"


def test_fault_isolation_duplicate_editor_id():
    editor = {"objects": [
        _editor_obj("chair", id="dupe_1"),
        _editor_obj("chair", id="dupe_1"),  # дубль → STRICT стора
        _editor_obj("chair", id="ok_2"),
    ]}
    scene = _scene()
    report = WorldObjectSpawner.spawn_from_editor(
        scene, "Open_road", "tavern", editor)
    assert report.spawned == 2          # первый + третий живут
    assert len(report.faults) == 1      # дубль — fault с причиной
    assert "dupe_1" in report.faults[0]


def test_missing_editor_id_fallback_index():
    editor = {"objects": [_editor_obj("door", id=None)]}
    scene = _scene()
    report = WorldObjectSpawner.spawn_from_editor(
        scene, "Open_road", "tavern", editor)
    assert report.spawned == 1
    assert report.faults == ()


def test_none_editor_data_empty_report():
    report = WorldObjectSpawner.spawn_from_editor(
        _scene(), "Open_road", "tavern", None)
    assert isinstance(report, SpawnReport)
    assert report.spawned == 0


def test_real_tavern_json_spawn():
    """Интеграция: реальный editor-JSON (real-data-first, §12.4).
    tavern.json objects: 16 chair + 1 door + 1 door_transition
    (portals не входят в objects — вне реестра by design)."""
    import json
    from pathlib import Path
    _p = Path(__file__).resolve().parents[2].parent / (
        "frontend/map_editor/campaigns/Open_road/locations/tavern.json")
    if not _p.exists():
        pytest.skip("campaign JSON недоступен в этом окружении")
    editor = json.loads(_p.read_text(encoding="utf-8-sig"))
    scene = _scene()
    report = WorldObjectSpawner.spawn_from_editor(
        scene, "Open_road", "tavern", editor)
    doors = sum(
        1 for oid in report.spawned_ids
        if WorldObjectStore.get(scene, oid).archetype == "door")
    chairs = report.spawned - doors
    assert doors >= 2 and chairs >= 16
    assert report.faults == ()