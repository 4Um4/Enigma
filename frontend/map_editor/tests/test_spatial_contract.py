"""path: /frontend/map_editor/tests/test_spatial_contract.py

Назначение: ME-1.12 autotests — глобальный пространственный контракт v1.2/v1.3.
    Инварианты: grid_cell_size > 0, spatial_ref (optional string),
    world_boundary (optional, mode in {open, hard, transition}).
    SCALE = rendering concern (canonical=20 per audit, fix in ME-2.8).
    SpatialDataLoader unchanged (game-side, S-ME1).
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from data_manager import DataManager  # type: ignore[import-not-found]
from schema_validator import validate_location  # type: ignore[import-not-found]

_CAMPAIGN_DIR = (
    Path(__file__).resolve().parents[1] / "campaigns" / "Open_road" / "locations"
)


@pytest.fixture
def golden_location(tmp_path: Path) -> tuple[Path, dict, str]:
    fname = "tavern.json"
    src = _CAMPAIGN_DIR / fname
    dst = tmp_path / fname
    shutil.copy2(src, dst)
    data = json.loads(dst.read_text(encoding="utf-8-sig"))
    return dst, data, fname


def _spatial_errors(data: dict) -> list[str]:
    keywords = ("grid_cell_size", "world_boundary", "spatial_ref")
    return [e for e in validate_location(data, "test") if any(k in e for k in keywords)]


def test_grid_cell_size_valid(golden_location):
    _, data, _ = golden_location
    data["grid_cell_size"] = 1.0
    assert not _spatial_errors(data)


def test_grid_cell_size_zero_error(golden_location):
    _, data, _ = golden_location
    data["grid_cell_size"] = 0
    assert any("grid_cell_size" in e for e in _spatial_errors(data))


def test_grid_cell_size_negative_error(golden_location):
    _, data, _ = golden_location
    data["grid_cell_size"] = -1
    assert any("grid_cell_size" in e for e in _spatial_errors(data))


def test_grid_cell_size_absent(golden_location):
    _, data, _ = golden_location
    data.pop("grid_cell_size", None)
    assert not _spatial_errors(data)


def test_world_boundary_open(golden_location):
    _, data, _ = golden_location
    data["world_boundary"] = {"mode": "open"}
    assert not _spatial_errors(data)


def test_world_boundary_hard(golden_location):
    _, data, _ = golden_location
    data["world_boundary"] = {"mode": "hard"}
    assert not _spatial_errors(data)


def test_world_boundary_transition(golden_location):
    _, data, _ = golden_location
    data["world_boundary"] = {"mode": "transition"}
    assert not _spatial_errors(data)


def test_world_boundary_invalid_mode(golden_location):
    _, data, _ = golden_location
    data["world_boundary"] = {"mode": "invalid"}
    assert any("world_boundary.mode" in e for e in _spatial_errors(data))


def test_world_boundary_absent(golden_location):
    _, data, _ = golden_location
    data.pop("world_boundary", None)
    assert not _spatial_errors(data)


def test_spatial_ref_valid(golden_location):
    _, data, _ = golden_location
    if data.get("objects"):
        data["objects"][0]["spatial_ref"] = "tavern_main_hall"
    assert not _spatial_errors(data)


def test_spatial_ref_invalid(golden_location):
    _, data, _ = golden_location
    if data.get("objects"):
        data["objects"][0]["spatial_ref"] = 42
    assert any("spatial_ref" in e for e in _spatial_errors(data))


def test_spatial_ref_absent(golden_location):
    _, data, _ = golden_location
    if data.get("objects"):
        data["objects"][0].pop("spatial_ref", None)
    assert not _spatial_errors(data)


def test_round_trip_preserves_spatial_fields(tmp_path: Path):
    fname = "tavern.json"
    src = _CAMPAIGN_DIR / fname
    dst = tmp_path / fname
    shutil.copy2(src, dst)
    data = json.loads(dst.read_text(encoding="utf-8-sig"))
    data["grid_cell_size"] = 2.0
    data["world_boundary"] = {"mode": "open"}
    if data.get("objects"):
        data["objects"][0]["spatial_ref"] = "main_hall"
    dst.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    dm = DataManager()
    dm.set_base_dir(tmp_path)
    assert dm.save(fname), "save failed"
    saved = json.loads(dst.read_text(encoding="utf-8-sig"))
    assert saved.get("grid_cell_size") == 2.0
    assert saved.get("world_boundary") == {"mode": "open"}
    saved_objs = {o["id"]: o for o in saved.get("objects", []) if isinstance(o, dict) and "id" in o}
    first_id = data["objects"][0]["id"] if data.get("objects") else None
    if first_id and first_id in saved_objs:
        assert saved_objs[first_id].get("spatial_ref") == "main_hall"
