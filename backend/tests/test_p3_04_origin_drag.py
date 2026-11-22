"""P3-04: тесты Origin-драга (Uniform Shift)."""

import sys
import copy
import json
import pytest
from pathlib import Path

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"
MAP_EDITOR_DIR = FRONTEND_DIR / "map_editor"
for p in (str(FRONTEND_DIR), str(MAP_EDITOR_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from data_manager import DataManager


@pytest.fixture
def dm_with_tavern(tmp_path):
    """DataManager с реальной tavern.json (содержит H-16)."""
    dm = DataManager()
    tavern_src = Path("frontend/map_editor/campaigns/Open_road/locations/tavern.json")
    tavern_dst = tmp_path / "tavern.json"
    tavern_dst.write_text(tavern_src.read_text(encoding="utf-8"), encoding="utf-8")
    dm.set_base_dir(tmp_path)
    dm.load_all()
    return dm, "tavern.json"


@pytest.fixture
def dm_with_valid_loc(tmp_path):
    """DataManager с синтетической заведомо валидной локацией (без объектов, чтобы избежать проверки архетипов)."""
    dm = DataManager()
    valid_loc = {
        "location_id": "test",
        "label": "Test Loc",
        "origin": {"x": 10.0, "y": 10.0},
        "size": {"w": 20.0, "h": 15.0},
        "global_coords": True,
        "rooms": [{
            "id": "r1", "x": 12.0, "y": 12.0, "width": 10.0, "height": 10.0,
            "polygon": [[12.0, 12.0], [22.0, 12.0], [22.0, 22.0], [12.0, 22.0]],
            "name": "Room", "area_sqm": 100.0
        }],
        "walls": [{"id": "w1", "x1": 12.0, "y1": 12.0, "x2": 22.0, "y2": 12.0, "thickness": 0.5}],
        "nodes": {"n1": {"x": 15.0, "y": 15.0}},
        "objects": [],  # Пустой массив, чтобы не триггерить валидацию рантайм-архетипов
        "npcs": [{"ref_id": "npc1", "position": {"x": 17.0, "y": 17.0}, "room_id": "r1"}],
        "player_spawn": {"x": 15.0, "y": 15.0, "z": 0},
        "labels": [],
        "passages": []
    }
    loc_path = tmp_path / "valid.json"
    loc_path.write_text(json.dumps(valid_loc), encoding="utf-8")
    dm.set_base_dir(tmp_path)
    dm.load_all()
    return dm, "valid.json"


def get_all_coords(loc):
    """Извлекает все координатные поля. Возвращает (имя, значение, is_x)."""
    coords = []

    coords.append(("origin.x", loc["origin"]["x"], True))
    coords.append(("origin.y", loc["origin"]["y"], False))

    for i, room in enumerate(loc.get("rooms", [])):
        coords.append((f"rooms[{i}].x", room["x"], True))
        coords.append((f"rooms[{i}].y", room["y"], False))
        for j, point in enumerate(room.get("polygon", [])):
            coords.append((f"rooms[{i}].polygon[{j}][0]", point[0], True))
            coords.append((f"rooms[{i}].polygon[{j}][1]", point[1], False))

    for i, wall in enumerate(loc.get("walls", [])):
        coords.append((f"walls[{i}].x1", wall["x1"], True))
        coords.append((f"walls[{i}].y1", wall["y1"], False))
        coords.append((f"walls[{i}].x2", wall["x2"], True))
        coords.append((f"walls[{i}].y2", wall["y2"], False))

    for name, node in loc.get("nodes", {}).items():
        coords.append((f"nodes.{name}.x", node["x"], True))
        coords.append((f"nodes.{name}.y", node["y"], False))

    for i, obj in enumerate(loc.get("objects", [])):
        coords.append((f"objects[{i}].position.x", obj["position"]["x"], True))
        coords.append((f"objects[{i}].position.y", obj["position"]["y"], False))

    for i, passage in enumerate(loc.get("passages", [])):
        coords.append((f"passages[{i}].position.x", passage["position"]["x"], True))
        coords.append((f"passages[{i}].position.y", passage["position"]["y"], False))

    for i, npc in enumerate(loc.get("npcs", [])):
        coords.append((f"npcs[{i}].position.x", npc["position"]["x"], True))
        coords.append((f"npcs[{i}].position.y", npc["position"]["y"], False))

    spawn = loc.get("player_spawn")
    if spawn:
        coords.append(("player_spawn.x", spawn["x"], True))
        coords.append(("player_spawn.y", spawn["y"], False))

    for i, label in enumerate(loc.get("labels", [])):
        coords.append((f"labels[{i}].x", label["x"], True))
        coords.append((f"labels[{i}].y", label["y"], False))

    return coords


def test_t15_uniform_shift(dm_with_tavern):
    """T15: все координатные поля сдвигаются на (dx, dy)."""
    dm, filename = dm_with_tavern
    loc = dm.locations[filename]

    before = get_all_coords(loc)
    dx, dy = 10.5, -5.3

    result = dm.shift_all(filename, dx, dy)

    assert result["success"] is True
    assert result["error"] is None

    after = get_all_coords(loc)

    for (name_b, val_b, is_x), (name_a, val_a, _) in zip(before, after):
        assert name_b == name_a
        delta = dx if is_x else dy
        expected = round(val_b + delta, 2)
        assert abs(val_a - expected) < 0.01, f"{name_b}: expected {expected}, got {val_a}"


def test_t16_validation_after_shift(dm_with_valid_loc):
    """T16: после сдвига заведомо валидная локация остаётся валидной (проходит P3-02)."""
    dm, filename = dm_with_valid_loc

    result = dm.shift_all(filename, 100.0, 50.0)
    assert result["success"] is True

    save_result = dm.save(filename)
    assert save_result.ok is True, f"Validation failed after shift: {save_result.errors}"


def test_t17_rollback_on_error(dm_with_tavern):
    """T17: при ошибке сдвига состояние откатывается."""
    dm, filename = dm_with_tavern
    loc = dm.locations[filename]

    before = copy.deepcopy(loc)
    loc["origin"]["x"] = "not_a_number"

    result = dm.shift_all(filename, 10.0, 5.0)

    assert result["success"] is False
    assert result["error"] is not None

    loc["origin"]["x"] = before["origin"]["x"]
    assert loc["rooms"] == before["rooms"]
    assert loc["walls"] == before["walls"]


def test_t18_reverse_shift(dm_with_tavern):
    """T18: обратный сдвиг возвращает исходную геометрию с учётом погрешности float."""
    dm, filename = dm_with_tavern
    loc = dm.locations[filename]

    before = get_all_coords(loc)
    dx, dy = 15.7, -8.3

    dm.shift_all(filename, dx, dy)
    dm.shift_all(filename, -dx, -dy)

    after = get_all_coords(loc)

    for (name_b, val_b, _), (name_a, val_a, _) in zip(before, after):
        assert abs(val_a - val_b) < 0.01, f"{name_b}: expected {val_b}, got {val_a}"


def test_t19_geometry_invariance(dm_with_tavern):
    """T19: внутренние расстояния и относительное расположение сущностей не меняются."""
    dm, filename = dm_with_tavern
    loc = dm.locations[filename]

    rooms = loc.get("rooms", [])
    if len(rooms) >= 2:
        room0_before = (rooms[0]["x"], rooms[0]["y"])
        room1_before = (rooms[1]["x"], rooms[1]["y"])
        dist_before = ((room1_before[0] - room0_before[0])**2 + (room1_before[1] - room0_before[1])**2)**0.5

    dm.shift_all(filename, 50.0, 30.0)

    if len(rooms) >= 2:
        room0_after = (rooms[0]["x"], rooms[0]["y"])
        room1_after = (rooms[1]["x"], rooms[1]["y"])
        dist_after = ((room1_after[0] - room0_after[0])**2 + (room1_after[1] - room0_after[1])**2)**0.5

        assert abs(dist_after - dist_before) < 0.01, f"Distance changed: {dist_before} -> {dist_after}"
