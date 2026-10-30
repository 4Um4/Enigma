"""Tests for map_editor.render.geometry_builder.

GAME-PREVIEW-IMPLEMENTATION-1: canonical conversion editor JSON -> (walls, obstacles).

Covers:
- split_wall_by_openings: pure geometry (no doors, zero-length, horizontal/vertical,
  off-wall doors skipped, overlapping gaps merged).
- build_geometry: empty input, walls-only, door carving (geometric/wall_id/rotation),
  center->top-left conversion, field completeness, blocks_los threshold,
  passability preservation, defaults for malformed objects.
"""

import pytest
from map_editor.render.geometry_builder import build_geometry, split_wall_by_openings

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
        {
            "id": "rug_1",
            "type": "decoration",
            "position": {"x": 10.0, "y": 7.0},
            "size": {"w": 3.0, "h": 2.0},
            "passability": {"walk": True},
            "cover": 0.0,
        },
    ],
}


class TestSplitWallByOpenings:
    def test_no_openings_returns_single_segment(self):
        wall = {"x1": 0.0, "y1": 0.0, "x2": 10.0, "y2": 0.0}
        result = split_wall_by_openings(wall, [])
        assert len(result) == 1
        assert result[0] == {"x1": 0.0, "y1": 0.0, "x2": 10.0, "y2": 0.0}

    def test_zero_length_wall(self):
        wall = {"x1": 5.0, "y1": 5.0, "x2": 5.0, "y2": 5.0}
        result = split_wall_by_openings(wall, [])
        assert len(result) == 1
        seg = result[0]
        assert seg["x1"] == seg["x2"] == 5.0
        assert seg["y1"] == seg["y2"] == 5.0

    def test_horizontal_wall_with_one_door(self):
        wall = {"x1": 0.0, "y1": 0.0, "x2": 20.0, "y2": 0.0}
        door = {"position": {"x": 10.0, "y": 0.0}, "size": {"w": 2.0, "h": 0.2}}
        result = split_wall_by_openings(wall, [door])
        assert len(result) == 2
        assert result[0]["x1"] == 0.0
        assert result[0]["x2"] == pytest.approx(9.0)
        assert result[1]["x1"] == pytest.approx(11.0)
        assert result[1]["x2"] == 20.0

    def test_opening_off_wall_skipped(self):
        wall = {"x1": 0.0, "y1": 0.0, "x2": 10.0, "y2": 0.0}
        door = {"position": {"x": 5.0, "y": 5.0}, "size": {"w": 2.0, "h": 0.2}}
        result = split_wall_by_openings(wall, [door])
        assert len(result) == 1
        assert result[0]["x2"] == 10.0

    def test_multiple_openings_merged(self):
        wall = {"x1": 0.0, "y1": 0.0, "x2": 20.0, "y2": 0.0}
        door1 = {"position": {"x": 5.0, "y": 0.0}, "size": {"w": 4.0, "h": 0.2}}
        door2 = {"position": {"x": 6.0, "y": 0.0}, "size": {"w": 4.0, "h": 0.2}}
        result = split_wall_by_openings(wall, [door1, door2])
        assert len(result) == 2
        assert result[0]["x1"] == 0.0
        assert result[0]["x2"] == pytest.approx(3.0)
        assert result[1]["x1"] == pytest.approx(8.0)
        assert result[1]["x2"] == 20.0

    def test_vertical_wall_uses_height_span(self):
        wall = {"x1": 0.0, "y1": 0.0, "x2": 0.0, "y2": 20.0}
        door = {"position": {"x": 0.0, "y": 10.0}, "size": {"w": 0.2, "h": 2.0}}
        result = split_wall_by_openings(wall, [door])
        assert len(result) == 2
        assert result[0]["y1"] == 0.0
        assert result[0]["y2"] == pytest.approx(9.0)
        assert result[1]["y1"] == pytest.approx(11.0)
        assert result[1]["y2"] == 20.0


class TestBuildGeometry:
    def test_empty_input(self):
        walls, obstacles = build_geometry({})
        assert walls == []
        assert obstacles == []

    def test_no_objects(self):
        loc = {"walls": [{"id": "w1", "x1": 0, "y1": 0, "x2": 10, "y2": 0}]}
        walls, obstacles = build_geometry(loc)
        assert len(walls) == 1
        assert obstacles == []

    def test_walls_split_by_doors(self):
        walls, obstacles = build_geometry(SAMPLE_LOCATION)
        assert len(walls) == 5  # 4 walls, wall_n split into 2
        north_segs = [w for w in walls if w["y1"] == 0.0 and w["y2"] == 0.0]
        assert len(north_segs) == 2

    def test_objects_center_to_top_left(self):
        walls, obstacles = build_geometry(SAMPLE_LOCATION)
        table = next(o for o in obstacles if o["id"] == "table_1")
        assert table["x"] == pytest.approx(4.0)
        assert table["y"] == pytest.approx(6.5)
        assert table["w"] == 2.0
        assert table["h"] == 1.0

    def test_obstacle_fields_present(self):
        walls, obstacles = build_geometry(SAMPLE_LOCATION)
        required = {"x", "y", "w", "h", "type", "id", "passability", "blocks_los"}
        for obs in obstacles:
            assert required.issubset(obs.keys()), f"missing fields in {obs['id']}"

    def test_blocks_los_threshold(self):
        walls, obstacles = build_geometry(SAMPLE_LOCATION)
        table = next(o for o in obstacles if o["id"] == "table_1")
        rug = next(o for o in obstacles if o["id"] == "rug_1")
        assert table["blocks_los"] is True
        assert rug["blocks_los"] is False

    def test_passability_preserved(self):
        walls, obstacles = build_geometry(SAMPLE_LOCATION)
        table = next(o for o in obstacles if o["id"] == "table_1")
        door = next(o for o in obstacles if o["id"] == "door_n")
        assert table["passability"] == {"walk": False}
        assert door["passability"] == {"walk": True}

    def test_door_wall_id_explicit(self):
        """Door ON wall with explicit wall_id -> wall split.

        wall_id reinforces geometric association. split_wall_by_openings
        still requires perp_dist <= 0.5 to carve.
        """
        loc = {
            "walls": [
                {"id": "wall_a", "x1": 0, "y1": 0, "x2": 10, "y2": 0},
                {"id": "wall_b", "x1": 0, "y1": 10, "x2": 10, "y2": 10},
            ],
            "objects": [
                {
                    "id": "d1",
                    "type": "door",
                    "position": {"x": 5, "y": 0},
                    "size": {"w": 2, "h": 0.2},
                    "passability": {"walk": True},
                    "wall_id": "wall_a",
                },
            ],
        }
        walls, obstacles = build_geometry(loc)
        segs_a = [w for w in walls if abs(w["y1"]) < 0.01 and abs(w["y2"]) < 0.01]
        segs_b = [w for w in walls if abs(w["y1"] - 10) < 0.01 and abs(w["y2"] - 10) < 0.01]
        assert len(segs_a) == 2  # split
        assert len(segs_b) == 1  # whole

    def test_door_wall_id_off_wall_not_carved(self):
        """Door OFF wall with wall_id -> wall NOT split (documents contract).

        wall_id associates door with wall in wall_openings, but
        split_wall_by_openings still requires geometric proximity
        (perp_dist <= 0.5) to carve. Original SpatialDataLoader behavior.
        """
        loc = {
            "walls": [{"id": "wall_a", "x1": 0, "y1": 0, "x2": 10, "y2": 0}],
            "objects": [
                {
                    "id": "d1",
                    "type": "door",
                    "position": {"x": 5, "y": 100},
                    "size": {"w": 2, "h": 0.2},
                    "passability": {"walk": True},
                    "wall_id": "wall_a",
                },
            ],
        }
        walls, obstacles = build_geometry(loc)
        assert len(walls) == 1  # not carved

    def test_door_rotation_prefix(self):
        """Door ON wall with rotation='wall_X' -> wall split."""
        loc = {
            "walls": [{"id": "wall_x", "x1": 0, "y1": 0, "x2": 10, "y2": 0}],
            "objects": [
                {
                    "id": "d1",
                    "type": "door",
                    "position": {"x": 5, "y": 0},
                    "size": {"w": 2, "h": 0.2},
                    "passability": {"walk": True},
                    "rotation": "wall_x",
                },
            ],
        }
        walls, obstacles = build_geometry(loc)
        assert len(walls) == 2  # carved

    def test_non_walkable_door_not_carved(self):
        loc = {
            "walls": [{"id": "w", "x1": 0, "y1": 0, "x2": 10, "y2": 0}],
            "objects": [
                {
                    "id": "d",
                    "type": "door",
                    "position": {"x": 5, "y": 0},
                    "size": {"w": 2, "h": 0.2},
                    "passability": {"walk": False},
                },
            ],
        }
        walls, obstacles = build_geometry(loc)
        assert len(walls) == 1

    def test_malformed_objects_use_defaults(self):
        loc = {
            "walls": [],
            "objects": [
                {"id": "o1", "type": "decoration"},
                {"id": "o2"},
            ],
        }
        walls, obstacles = build_geometry(loc)
        assert len(obstacles) == 2
        o1 = next(o for o in obstacles if o["id"] == "o1")
        assert o1["x"] == pytest.approx(-0.5)
        assert o1["y"] == pytest.approx(-0.5)
        assert o1["w"] == 1.0
        assert o1["h"] == 1.0

    def test_type_defaults_to_decoration(self):
        loc = {"objects": [{"id": "o", "position": {"x": 0, "y": 0}, "size": {"w": 1, "h": 1}}]}
        walls, obstacles = build_geometry(loc)
        assert obstacles[0]["type"] == "decoration"
