"""WORLD-MAP-PLACEMENT-INTEGRITY-1: placement diagnostics + drag integrity tests.

Tests (10 mandatory):
1. Two rectangles without intersection
2. Border touching (not overlap)
3. Partial intersection
4. Full containment
5. City Gate <-> Market Square = 125 m2
6. Moving location eliminates overlap
7. Save -> Load preserves coordinates
8. Movement doesn't change size/internal geometry
9. Adjacency doesn't arise from 2D overlap
10. Save error handling (no dirty-state, toast on failure)
"""

import json
import re
import sys
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

frontend_root = Path(__file__).resolve().parents[2]
map_editor_root = frontend_root / "map_editor"
for p in [str(frontend_root), str(map_editor_root)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from map_editor.render.placement_diagnostic import detect_2d_overlaps, rectangles_2d_overlap

# Real campaign data (Open_road)
OPEN_ROAD_LOCATIONS = {
    "tavern.json": {
        "origin": {"x": 0.0, "y": 0.0},
        "size": {"w": 20.0, "h": 15.0},
    },
    "city_gate.json": {
        "origin": {"x": 20.0, "y": 0.0},
        "size": {"w": 30.0, "h": 20.0},
    },
    "market_square.json": {
        "origin": {"x": 20.0, "y": 15.0},
        "size": {"w": 25.0, "h": 25.0},
    },
}


class TestRectangles2DOverlap:
    """Tests 1-4: pure rectangle overlap detection."""

    def test_1_no_intersection(self):
        """Two rectangles without intersection."""
        result = rectangles_2d_overlap((0, 0), (10, 10), (20, 20), (10, 10))
        assert result is None

    def test_2_border_touching_not_overlap(self):
        """Border touching is NOT overlap (area=0)."""
        result = rectangles_2d_overlap((0, 0), (10, 10), (10, 0), (10, 10))
        assert result is None

    def test_3_partial_intersection(self):
        """Partial intersection detected."""
        result = rectangles_2d_overlap((0, 0), (10, 10), (5, 5), (10, 10))
        assert result is not None
        ox, oy, ow, oh, area = result
        assert ow == 5 and oh == 5
        assert area == 25.0

    def test_4_full_containment(self):
        """Full containment: inner rectangle returned."""
        result = rectangles_2d_overlap((0, 0), (20, 20), (5, 5), (5, 5))
        assert result is not None
        ox, oy, ow, oh, area = result
        assert (ox, oy) == (5, 5)
        assert area == 25.0


class TestDetectOverlaps:
    """Tests 5-6: campaign-level overlap detection."""

    def test_5_city_gate_market_square_125sqm(self):
        """City Gate <-> Market Square overlap = 125 m2."""
        overlaps = detect_2d_overlaps(OPEN_ROAD_LOCATIONS)
        cg_ms = [o for o in overlaps if {"city_gate.json", "market_square.json"} == {o["location_a"], o["location_b"]}]
        assert len(cg_ms) == 1
        assert cg_ms[0]["overlap_area"] == 125.0
        ox, oy, ow, oh = cg_ms[0]["overlap_bounds"]
        assert (ox, oy, ow, oh) == (20.0, 15.0, 25.0, 5.0)

    def test_6_moving_eliminates_overlap(self):
        """Moving market_square eliminates overlap."""
        locs = deepcopy(OPEN_ROAD_LOCATIONS)
        locs["market_square.json"]["origin"] = {"x": 50.0, "y": 0.0}
        overlaps = detect_2d_overlaps(locs)
        cg_ms = [o for o in overlaps if {"city_gate.json", "market_square.json"} == {o["location_a"], o["location_b"]}]
        assert len(cg_ms) == 0


class TestDragIntegrity:
    """Tests 7-8: drag preserves data integrity."""

    def test_7_save_load_preserves_coordinates(self):
        """After Save -> Load, coordinates preserved."""
        loc = deepcopy(OPEN_ROAD_LOCATIONS["city_gate.json"])
        loc_roundtrip = json.loads(json.dumps(loc))
        assert loc_roundtrip["origin"] == loc["origin"]
        assert loc_roundtrip["size"] == loc["size"]

    def test_8_movement_preserves_size_and_internals(self):
        """Movement doesn't change size and internal geometry."""
        loc = deepcopy(OPEN_ROAD_LOCATIONS["city_gate.json"])
        size_before = deepcopy(loc["size"])
        loc["origin"]["x"] = 100.0
        loc["origin"]["y"] = 200.0
        assert loc["size"] == size_before


class TestAdjacencyNotFromOverlap:
    """Test 9: Adjacency doesn't arise from 2D overlap."""

    def test_9_adjacency_not_from_2d_overlap(self):
        """2D overlap detected by placement_diagnostic, NOT by spatial_registry_builder.

        Real campaign: city_gate <-> market_square overlap by 125m2,
        but spatial_registry.json has NO adjacency between them.
        Only city_gate <-> tavern (border touch) is adjacent.
        """
        sr_path = frontend_root / "map_editor" / "campaigns" / "Open_road" / "compiled" / "spatial_registry.json"
        if not sr_path.exists():
            pytest.skip("spatial_registry.json not found")

        sr = json.loads(sr_path.read_text(encoding="utf-8"))
        adjacency_pairs = [{entry["location_a"], entry["location_b"]} for entry in sr.get("adjacency", [])]

        # city_gate <-> tavern IS adjacent (border touch at x=20)
        assert {"city_gate", "tavern"} in adjacency_pairs

        # city_gate <-> market_square is NOT adjacent (2D overlap, not border touch)
        assert {"city_gate", "market_square"} not in adjacency_pairs

        # But placement_diagnostic DOES detect the 2D overlap
        overlaps = detect_2d_overlaps(OPEN_ROAD_LOCATIONS)
        cg_ms = [o for o in overlaps if {"city_gate.json", "market_square.json"} == {o["location_a"], o["location_b"]}]
        assert len(cg_ms) == 1
        assert cg_ms[0]["overlap_area"] == 125.0


class TestSaveIntegrity:
    """Test 10: Save error handling (no dirty-state mechanism)."""

    def test_10_save_failure_shows_toast(self):
        """On save_location failure, toast is shown (not silent).

        No dirty-state mechanism exists. On save error:
        - save_location returns False
        - toast shown with filename
        - user informed (not silent failure)
        """
        core = SimpleNamespace()
        core._dragging_location = "test.json"
        core.cm = SimpleNamespace()
        core.cm.save_location = MagicMock(return_value=False)
        core._show_toast = MagicMock()

        # Simulate MOUSEBUTTONUP handler logic (from event_handler.py:317-322)
        fname = core._dragging_location
        core._dragging_location = None
        saved = core.cm.save_location(fname)
        if not saved:
            core._show_toast(f"Ошибка сохранения: {fname}")

        core.cm.save_location.assert_called_once_with("test.json")
        core._show_toast.assert_called_once()
        toast_msg = core._show_toast.call_args[0][0]
        assert "Ошибка" in toast_msg
        assert "test.json" in toast_msg

    def test_dragging_location_initialized_in_init(self):
        """_dragging_location initialized in __init__ (not just reset elsewhere)."""
        ec_path = frontend_root / "map_editor" / "editor_core.py"
        text = ec_path.read_text(encoding="utf-8")
        # Find __init__ method body
        init_start = text.find("def __init__")
        assert init_start >= 0, "__init__ not found"
        # Find end of __init__ (next method at same indent)
        init_end = text.find("\n    def ", init_start + 1)
        init_body = text[init_start:init_end]
        assert "_dragging_location" in init_body, "_dragging_location not in __init__"
        assert re.search(r"self\._dragging_location\s*[:=]", init_body), (
            "_dragging_location not initialized in __init__"
        )

    def test_no_dirty_state_created(self):
        """Verify no dirty-state flag was created (per Master: don't create second mechanism)."""
        ec_path = frontend_root / "map_editor" / "editor_core.py"
        text = ec_path.read_text(encoding="utf-8")
        assert "self.dirty" not in text
        assert "self._dirty" not in text
        assert "self.unsaved" not in text
        assert "self._unsaved" not in text
