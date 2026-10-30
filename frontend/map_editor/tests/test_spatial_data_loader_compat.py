"""path: /frontend/map_editor/tests/test_spatial_data_loader_compat.py

Назначение: ME-1.8(a) / S-ME1 compatibility gate — SpatialDataLoader
    корректно загружает локации с новыми optional-полями (levels[],
    spatial_ref, world_boundary, grid_cell_size) без изменения контракта.

    Legacy (без новых полей) и Extended (с новыми полями) — оба загружаются
    через настоящий SpatialDataLoader._build_spatial_data.

    Ограничение: levels[] не участвует в фильтрации сущностей.
    Игра загружает все entities без active_level filtering.
    Это явно обозначенная граница интеграции (ME-1.8(a)), не баг.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
import world_context

_CAMPAIGN_DIR = (
    Path(__file__).resolve().parents[1] / "campaigns" / "Open_road" / "locations"
)


def _load_location(name: str) -> dict:
    return json.loads((_CAMPAIGN_DIR / name).read_text(encoding="utf-8-sig"))


def _build_spatial(data: dict, name: str = "test"):
    """Call real SpatialDataLoader._build_spatial_data."""
    return world_context.SpatialDataLoader._build_spatial_data(
        data.get("location_id", name), data
    )


@pytest.fixture
def legacy_location() -> dict:
    """Golden location WITHOUT new optional fields (legacy format)."""
    return _load_location("tavern.json")


@pytest.fixture
def extended_location(legacy_location) -> dict:
    """Same location WITH new optional fields (extended format)."""
    data = copy.deepcopy(legacy_location)
    data["levels"] = [
        {"id": 0, "label": "первый этаж"},
        {"id": -1, "label": "подвал", "elevation": -3.0},
    ]
    data["active_level"] = 0
    data["world_boundary"] = {"mode": "open"}
    data["grid_cell_size"] = 1.0
    if data.get("objects"):
        data["objects"][0]["spatial_ref"] = "tavern_main_hall"
        data["objects"][0]["level"] = 0
    return data


# === 1. Both load without exceptions ===

def test_legacy_loads_without_exception(legacy_location):
    """SpatialDataLoader loads legacy location without exceptions."""
    result = _build_spatial(legacy_location)
    assert result is not None


def test_extended_loads_without_exception(extended_location):
    """SpatialDataLoader loads extended location (with new fields) without exceptions."""
    result = _build_spatial(extended_location)
    assert result is not None


# === 2. Object/wall count preserved ===

def test_obstacle_count_unchanged(legacy_location, extended_location):
    """Obstacle count is the same for legacy and extended."""
    legacy_result = _build_spatial(legacy_location)
    extended_result = _build_spatial(extended_location)
    assert len(legacy_result.obstacles) == len(extended_result.obstacles)


def test_wall_count_unchanged(legacy_location, extended_location):
    """Wall count is the same for legacy and extended."""
    legacy_result = _build_spatial(legacy_location)
    extended_result = _build_spatial(extended_location)
    assert len(legacy_result.walls) == len(extended_result.walls)


# === 3. origin/size semantics preserved ===

def test_floor_rect_unchanged(legacy_location, extended_location):
    """Floor rect (origin/size) is the same for legacy and extended."""
    legacy_result = _build_spatial(legacy_location)
    extended_result = _build_spatial(extended_location)
    assert legacy_result.floor_rect == extended_result.floor_rect


# === 4. New fields don't break old field reading ===

def test_obstacle_ids_match(legacy_location, extended_location):
    """Obstacle IDs are preserved (new fields don't break object reading)."""
    legacy_result = _build_spatial(legacy_location)
    extended_result = _build_spatial(extended_location)
    legacy_ids = {ob["id"] for ob in legacy_result.obstacles}
    extended_ids = {ob["id"] for ob in extended_result.obstacles}
    assert legacy_ids == extended_ids


def test_obstacle_sizes_match(legacy_location, extended_location):
    """Obstacle sizes are preserved."""
    legacy_result = _build_spatial(legacy_location)
    extended_result = _build_spatial(extended_location)
    legacy_sizes = {ob["id"]: (ob["w"], ob["h"]) for ob in legacy_result.obstacles}
    extended_sizes = {ob["id"]: (ob["w"], ob["h"]) for ob in extended_result.obstacles}
    for oid in legacy_sizes:
        assert legacy_sizes[oid] == extended_sizes[oid]


# === 5. Loading doesn't modify source JSON ===

def test_legacy_source_not_modified(legacy_location):
    """Loading via SpatialDataLoader doesn't modify the source dict."""
    original = copy.deepcopy(legacy_location)
    _build_spatial(legacy_location)
    assert legacy_location == original


def test_extended_source_not_modified(extended_location):
    """Loading extended location doesn't modify source dict (new fields preserved)."""
    original = copy.deepcopy(extended_location)
    _build_spatial(extended_location)
    assert extended_location == original


# === 6. Legacy behavior unchanged vs control ===

def test_legacy_floor_rect_matches_file(legacy_location):
    """Legacy floor_rect matches origin+size from file (control)."""
    result = _build_spatial(legacy_location, "tavern")
    assert result.floor_rect == (
        float(legacy_location["origin"]["x"]),
        float(legacy_location["origin"]["y"]),
        float(legacy_location["size"]["w"]),
        float(legacy_location["size"]["h"]),
    )


def test_legacy_obstacle_count_matches_file(legacy_location):
    """Legacy obstacle count matches objects count from file."""
    result = _build_spatial(legacy_location, "tavern")
    assert len(result.obstacles) == len(legacy_location["objects"])


# === 7. Documented limitation — levels[] not filtered ===

def test_levels_not_filtered_in_game(extended_location):
    """ME-1.8(a) limitation: levels[] doesn't participate in entity filtering.

    Game loads ALL entities regardless of level field.
    This is an explicitly documented boundary, not a bug.
    Full S-ME1 (with active_level filtering) is a separate future change.
    """
    result = _build_spatial(extended_location)
    assert len(result.obstacles) == len(extended_location["objects"]), (
        "SpatialDataLoader should load ALL objects regardless of level field. "
        "If this fails, game contract was changed (violates ME-1.8(a))."
    )
