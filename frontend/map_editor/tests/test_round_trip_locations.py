"""path: /frontend/map_editor/tests/test_round_trip_locations.py

Назначение: ME-1.7 golden round-trip тесты — load->save->reload не теряет данные.
    Для каждой локации кампании Open_road: копия в tmp_path -> DataManager.load_all()
    -> DataManager.save() -> сравнение с оригиналом. Все объекты (по ID + содержимое),
    стены, комнаты, NPC, узлы сохраняются. modified_at обновляется save() — ожидаемо.
Зависимости: pytest, data_manager.DataManager, real campaign locations (read-only).
Основные сущности:
    - test_round_trip_preserves_objects — objects: все ID + содержимое сохранены
    - test_round_trip_preserves_walls — walls: массив сохранён целиком
    - test_round_trip_preserves_rooms — rooms: массив сохранён целиком
    - test_round_trip_preserves_npcs — npcs: массив сохранён целиком
    - test_round_trip_preserves_nodes — nodes: dict сохранён целиком
    - test_round_trip_preserves_top_level — top-level fields (except modified_at)
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from data_manager import DataManager  # type: ignore[import-not-found]

_CAMPAIGN = "Open_road"
_CAMPAIGN_DIR = (
    Path(__file__).resolve().parents[1] / "campaigns" / _CAMPAIGN / "locations"
)


def _location_files() -> list[Path]:
    files = sorted(_CAMPAIGN_DIR.glob("*.json"))
    assert files, f"golden locations not found: {_CAMPAIGN_DIR}"
    return files


_LOC_FILES = _location_files()
_LOC_NAMES = [f.name for f in _LOC_FILES]


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


@pytest.fixture
def round_trip_copy(tmp_path: Path, request) -> tuple[Path, dict, dict]:
    """Copy golden location to tmp_path, save via DataManager, return (saved_path, original, saved)."""
    fname = request.param
    src = _CAMPAIGN_DIR / fname
    dst = tmp_path / fname
    shutil.copy2(src, dst)

    dm = DataManager()
    dm.set_base_dir(tmp_path)
    assert dm.save(fname), f"save failed for {fname}"

    original = _load_json(src)
    saved = _load_json(dst)
    return dst, original, saved


@pytest.mark.parametrize("round_trip_copy", _LOC_NAMES, indirect=True)
def test_round_trip_preserves_objects(round_trip_copy):
    """objects: все ID + содержимое сохранены после round-trip."""
    _, original, saved = round_trip_copy
    orig_objs = {
        o["id"]: o
        for o in original.get("objects", [])
        if isinstance(o, dict) and "id" in o
    }
    saved_objs = {
        o["id"]: o
        for o in saved.get("objects", [])
        if isinstance(o, dict) and "id" in o
    }
    assert set(orig_objs.keys()) == set(saved_objs.keys()), (
        f"object IDs changed: only-original={set(orig_objs) - set(saved_objs)}, "
        f"only-saved={set(saved_objs) - set(orig_objs)}"
    )
    for oid in orig_objs:
        assert orig_objs[oid] == saved_objs[oid], (
            f"object {oid} content changed after round-trip"
        )


@pytest.mark.parametrize("round_trip_copy", _LOC_NAMES, indirect=True)
def test_round_trip_preserves_walls(round_trip_copy):
    """walls: массив сохранён целиком."""
    _, original, saved = round_trip_copy
    assert original.get("walls", []) == saved.get("walls", []), "walls changed"


@pytest.mark.parametrize("round_trip_copy", _LOC_NAMES, indirect=True)
def test_round_trip_preserves_rooms(round_trip_copy):
    """rooms: массив сохранён целиком."""
    _, original, saved = round_trip_copy
    assert original.get("rooms", []) == saved.get("rooms", []), "rooms changed"


@pytest.mark.parametrize("round_trip_copy", _LOC_NAMES, indirect=True)
def test_round_trip_preserves_npcs(round_trip_copy):
    """npcs: массив сохранён целиком."""
    _, original, saved = round_trip_copy
    assert original.get("npcs", []) == saved.get("npcs", []), "npcs changed"


@pytest.mark.parametrize("round_trip_copy", _LOC_NAMES, indirect=True)
def test_round_trip_preserves_nodes(round_trip_copy):
    """nodes: dict сохранён целиком."""
    _, original, saved = round_trip_copy
    assert original.get("nodes", {}) == saved.get("nodes", {}), "nodes changed"


@pytest.mark.parametrize("round_trip_copy", _LOC_NAMES, indirect=True)
def test_round_trip_preserves_top_level(round_trip_copy):
    """top-level fields preserved (except modified_at — save updates it)."""
    _, original, saved = round_trip_copy
    for key in original:
        if key == "modified_at":
            continue
        assert key in saved, f"top-level field {key!r} lost after round-trip"
        assert original[key] == saved[key], (
            f"top-level field {key!r} changed: "
            f"original={original[key]!r} saved={saved[key]!r}"
        )
