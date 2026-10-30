"""Tests for scene_bridge.build_perceived_scene — Game Preview parity.

GAME-PREVIEW-IMPLEMENTATION-1: Preview uses SAME geometry as SpatialDataLoader.

Mandatory tests covered:
- Objects conversion parity (vs SpatialDataLoader)
- Wall splitting parity (same segments + door openings)
- NPC rendering (no AttributeError, correct position)
- Camera (centered on player_spawn)
- Empty/malformed input (no crash)
"""

import sys
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

frontend_root = Path(__file__).resolve().parents[2]
map_editor_root = frontend_root / "map_editor"
for p in [str(frontend_root), str(map_editor_root)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from map_editor.render.scene_bridge import build_perceived_scene
from world_context import SpatialDataLoader

SAMPLE_LOCATION = {
    "id": "test_loc",
    "size": {"w": 20.0, "h": 15.0},
    "origin": {"x": 0.0, "y": 0.0},
    "walls": [
        {"id": "wall_n", "x1": 0.0, "y1": 0.0, "x2": 20.0, "y2": 0.0},
        {"id": "wall_s", "x1": 0.0, "y1": 15.0, "x2": 20.0, "y2": 15.0},
        {"id": "wall_w", "x1": 0.0, "y1": 0.0, "x2": 0.0, "y2": 15.0},
        {"id": "wall_e", "x1": 20.0, "y1": 0.0, "x2": 20.0, "y2": 15.0},
    ],
    "objects": [
        {
            "id": "door_n",
            "type": "door",
            "position": {"x": 10.0, "y": 0.0},
            "size": {"w": 2.0, "h": 0.2},
            "passability": {"walk": True},
            "cover": 0.0,
        },
        {
            "id": "table_1",
            "type": "table",
            "position": {"x": 5.0, "y": 7.0},
            "size": {"w": 2.0, "h": 1.0},
            "passability": {"walk": False},
            "cover": 0.9,
        },
    ],
    "rooms": [{"x": 0.0, "y": 0.0, "width": 20.0, "height": 15.0}],
    "npcs": [{"ref_id": "npc_test", "position": {"x": 8.0, "y": 8.0}}],
    "player_spawn": {"x": 10.0, "y": 7.5},
}


def _make_core(loc=None, current_file="test_loc"):
    core = SimpleNamespace()
    core.current_file = current_file
    core.dm = SimpleNamespace()
    core.dm.locations = {current_file: deepcopy(loc)} if loc else {}
    core._npc_list = [{"id": "npc_test", "name": "Test NPC"}]
    return core


class TestParityWithSpatialDataLoader:
    """Mandatory: 'Objects conversion — Полное совпадение с SpatialDataLoader'."""

    def test_obstacles_match_spatial_data_loader(self):
        core = _make_core(SAMPLE_LOCATION)
        result = build_perceived_scene(core)
        assert result is not None
        _scene, _walls, sb_obstacles, _floors, _sw, _sh, _pxy = result

        spatial = SpatialDataLoader._build_spatial_data("test_loc", deepcopy(SAMPLE_LOCATION))
        sdl_obstacles = list(spatial.obstacles)

        assert len(sb_obstacles) == len(sdl_obstacles)
        for sb_obs, sdl_obs in zip(sb_obstacles, sdl_obstacles):
            assert sb_obs == sdl_obs, f"obstacle mismatch: {sb_obs} vs {sdl_obs}"

    def test_walls_match_spatial_data_loader(self):
        """Mandatory: 'Wall splitting — Одинаковые сегменты и дверные проёмы'."""
        core = _make_core(SAMPLE_LOCATION)
        result = build_perceived_scene(core)
        _scene, sb_walls, _obst, _floors, _sw, _sh, _pxy = result

        spatial = SpatialDataLoader._build_spatial_data("test_loc", deepcopy(SAMPLE_LOCATION))
        sdl_walls = list(spatial.walls)

        assert len(sb_walls) == len(sdl_walls)
        for sb_w, sdl_w in zip(sb_walls, sdl_walls):
            assert sb_w == sdl_w, f"wall mismatch: {sb_w} vs {sdl_w}"

    def test_walls_are_split_not_raw(self):
        """Critical: walls from scene_bridge are SPLIT (door carved), not raw."""
        core = _make_core(SAMPLE_LOCATION)
        result = build_perceived_scene(core)
        _scene, walls, _obst, _floors, _sw, _sh, _pxy = result
        assert len(walls) == 5, f"expected 5 split segments, got {len(walls)}"
        raw_count = len(SAMPLE_LOCATION["walls"])
        assert len(walls) != raw_count, "walls NOT split — topology discrepancy!"

    def test_obstacles_use_top_left_coords(self):
        core = _make_core(SAMPLE_LOCATION)
        result = build_perceived_scene(core)
        _scene, _walls, obstacles, _floors, _sw, _sh, _pxy = result
        table = next(o for o in obstacles if o["id"] == "table_1")
        assert table["x"] == pytest.approx(4.0)
        assert table["y"] == pytest.approx(6.5)


class TestNpcRendering:
    """Mandatory: 'NPC rendering — Нет AttributeError, корректное положение'."""

    def test_npc_entity_creation_no_attribute_error(self):
        core = _make_core(SAMPLE_LOCATION)
        result = build_perceived_scene(core)
        scene = result[0]
        assert len(scene.entities) == 1
        npc = scene.entities[0]
        assert npc.entity_id == "npc_test"
        assert npc.entity_type == "npc"
        assert npc.x == 8.0
        assert npc.y == 8.0
        _ = npc.visible
        _ = npc.clarity
        _ = npc.display_name
        _ = npc.recognition_confidence

    def test_npc_position_correct(self):
        core = _make_core(SAMPLE_LOCATION)
        result = build_perceived_scene(core)
        scene = result[0]
        npc = scene.entities[0]
        assert npc.x == 8.0
        assert npc.y == 8.0

    def test_npc_display_name_from_npc_list(self):
        core = _make_core(SAMPLE_LOCATION)
        result = build_perceived_scene(core)
        scene = result[0]
        npc = scene.entities[0]
        assert npc.display_name == "Test NPC"


class TestCameraAndSpawn:
    """Mandatory: 'Camera — Центрирование по player_spawn'."""

    def test_player_xy_from_spawn(self):
        core = _make_core(SAMPLE_LOCATION)
        result = build_perceived_scene(core)
        _scene, _walls, _obst, _floors, _sw, _sh, player_xy = result
        assert player_xy == (10.0, 7.5)

    def test_player_xy_defaults_to_center_when_no_spawn(self):
        loc = deepcopy(SAMPLE_LOCATION)
        loc["player_spawn"] = None
        core = _make_core(loc)
        result = build_perceived_scene(core)
        _scene, _walls, _obst, _floors, scene_w, scene_h, player_xy = result
        assert player_xy == (scene_w / 2.0, scene_h / 2.0)


class TestEmptyAndMalformed:
    """Mandatory: 'Empty/malformed optional data — Без падения редактора'."""

    def test_no_location_open_returns_none(self):
        core = _make_core()
        core.current_file = None
        assert build_perceived_scene(core) is None

    def test_empty_location_no_crash(self):
        loc = {"size": {"w": 10, "h": 10}}
        core = _make_core(loc)
        result = build_perceived_scene(core)
        assert result is not None
        _scene, walls, obstacles, floors, _sw, _sh, _pxy = result
        assert walls == []
        assert obstacles == []
        assert len(floors) == 1

    def test_missing_objects_key(self):
        loc = {"size": {"w": 10, "h": 10}, "walls": [{"id": "w", "x1": 0, "y1": 0, "x2": 5, "y2": 0}]}
        core = _make_core(loc)
        result = build_perceived_scene(core)
        _scene, walls, obstacles, _f, _sw, _sh, _pxy = result
        assert len(walls) == 1
        assert obstacles == []

    def test_missing_walls_key(self):
        loc = {
            "size": {"w": 10, "h": 10},
            "objects": [{"id": "o", "type": "decoration", "position": {"x": 1, "y": 1}, "size": {"w": 1, "h": 1}}],
        }
        core = _make_core(loc)
        result = build_perceived_scene(core)
        _scene, walls, obstacles, _f, _sw, _sh, _pxy = result
        assert walls == []
        assert len(obstacles) == 1
