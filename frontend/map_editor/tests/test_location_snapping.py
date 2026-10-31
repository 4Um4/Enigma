"""WORLD-MAP-SNAP: magnetic location snapping tests.

Tests:
1. No snap when far away
2. Snap left edge to other's right edge (adjacency)
3. Snap right edge to other's left edge
4. Snap top edge to other's bottom edge
5. Snap bottom edge to other's top edge
6. Snap to same edge (alignment)
7. Independent X and Y snapping
8. Don't snap to self
9. Threshold boundary
10. Multiple locations: snap to closest
"""

import sys
from pathlib import Path

frontend_root = Path(__file__).resolve().parents[2]
map_editor_root = frontend_root / "map_editor"
for p in [str(frontend_root), str(map_editor_root)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from map_editor.render.placement_diagnostic import snap_location_position


def _loc(origin, size):
    """Helper: create a location dict."""
    return {"origin": {"x": origin[0], "y": origin[1]}, "size": {"w": size[0], "h": size[1]}}


class TestNoSnap:
    def test_1_no_snap_when_far(self):
        """Locations far apart: no snapping."""
        others = {"b.json": _loc((100, 0), (10, 10))}
        result = snap_location_position((0, 0), (10, 10), others, exclude="a.json")
        assert result == (0, 0)

    def test_8_dont_snap_to_self(self):
        """Don't snap to self (exclude parameter)."""
        others = {"a.json": _loc((0, 0), (10, 10))}
        # Moving a.json near itself — should not snap
        result = snap_location_position((0.5, 0), (10, 10), others, exclude="a.json")
        assert result == (0.5, 0)


class TestEdgeSnap:
    def test_2_snap_left_to_other_right(self):
        """Drag left edge snaps to other's right edge (adjacency)."""
        # Other at (20, 0) size 10x10 → right edge at x=30
        # Drag at (28.5, 0) size 10x10 → left edge at 28.5
        # Within threshold 1.0 → snap left to 30
        others = {"b.json": _loc((20, 0), (10, 10))}
        result = snap_location_position((29.5, 0), (10, 10), others, exclude="a.json")
        assert result[0] == 30.0  # snapped: left edge aligned to other's right

    def test_3_snap_right_to_other_left(self):
        """Drag right edge snaps to other's left edge."""
        # Other at (20, 0) size 10x10 → left edge at x=20
        # Drag at (5, 0) size 10x10 → right edge at 15
        # Distance 5 — too far. Let's put drag at (18.5, 0) → right edge at 28.5
        # Wait, need right edge near other's left (20). Drag at (10.5, 0) → right=20.5, dist=0.5
        others = {"b.json": _loc((20, 0), (10, 10))}
        result = snap_location_position((10.5, 0), (10, 10), others, exclude="a.json")
        # right edge (20.5) snaps to other_left (20) → dx = -0.5 → origin = 10.0
        assert result[0] == 10.0

    def test_4_snap_top_to_other_bottom(self):
        """Drag top edge snaps to other's bottom edge."""
        # Other at (0, 20) size 10x10 → bottom edge at y=30
        # Drag at (0, 28.5) size 10x10 → top edge at 28.5
        # Within threshold → snap top to 30
        others = {"b.json": _loc((0, 20), (10, 10))}
        result = snap_location_position((0, 29.5), (10, 10), others, exclude="a.json")
        assert result[1] == 30.0

    def test_5_snap_bottom_to_other_top(self):
        """Drag bottom edge snaps to other's top edge."""
        # Other at (0, 20) size 10x10 → top edge at y=20
        # Drag at (0, 10.5) size 10x10 → bottom edge at 20.5
        # Distance 0.5 → snap bottom to 20 → origin = 10.0
        others = {"b.json": _loc((0, 20), (10, 10))}
        result = snap_location_position((0, 10.5), (10, 10), others, exclude="a.json")
        assert result[1] == 10.0


class TestAlignmentSnap:
    def test_6_snap_same_edge_alignment(self):
        """Snap left edge to other's left edge (alignment)."""
        # Other at (20, 0) size 10x10 → left at x=20
        # Drag at (19.5, 0) size 10x10 → left at 19.5, dist=0.5
        # Y overlap: both [0, 10] → overlap
        others = {"b.json": _loc((20, 0), (10, 10))}
        result = snap_location_position((19.5, 0), (10, 10), others, exclude="a.json")
        assert result[0] == 20.0  # left edge aligned


class TestIndependentAxes:
    def test_7_independent_xy_snapping(self):
        """Both X and Y can snap simultaneously."""
        # Other at (20, 20) size 10x10
        # Drag at (28.5, 28.5) size 10x10
        # X: drag_left(28.5) near other_right(30) → snap to 30
        # Y: drag_top(28.5) near other_bottom(30) → snap to 30
        others = {"b.json": _loc((20, 20), (10, 10))}
        result = snap_location_position((29.5, 29.5), (10, 10), others, exclude="a.json")
        assert result == (30.0, 30.0)


class TestThreshold:
    def test_9_threshold_boundary(self):
        """At exactly threshold distance: no snap (strict less-than)."""
        others = {"b.json": _loc((20, 0), (10, 10))}
        # Other right at 30. Drag left at 29.0 → distance = 1.0 = threshold
        # Strict < → no snap
        result = snap_location_position((29.0, 0), (10, 10), others, exclude="a.json")
        assert result[0] == 29.0  # no snap at exactly threshold

    def test_9b_within_threshold_snaps(self):
        """Just within threshold: snaps."""
        others = {"b.json": _loc((20, 0), (10, 10))}
        # Distance 0.99 < 1.0 → snap
        result = snap_location_position((29.01, 0), (10, 10), others, exclude="a.json")
        assert result[0] == 30.0


class TestMultipleLocations:
    def test_10_snap_to_closest(self):
        """When multiple locations nearby, snap to closest edge."""
        others = {
            "b.json": _loc(
                (20, 0),
                (10, 10),
            ),  # right at 30
            "c.json": _loc(
                (35, 0),
                (10, 10),
            ),  # left at 35
        }
        # Drag at (28.5, 0) size 10x10
        # b: drag_left(28.5) to b_right(30) → dist 1.5... wait threshold is 1.0
        # Let's use drag at (29.5, 0) → left=29.5
        # b_right=30, dist=0.5 → snap to 30
        # c_left=35, drag_right=39.5, dist=4.5 → too far
        result = snap_location_position((29.5, 0), (10, 10), others, exclude="a.json")
        assert result[0] == 30.0  # snapped to b's right edge


class TestRealCampaign:
    def test_snap_tavern_to_city_gate(self):
        """Tavern (0,0,20x15) near City Gate (20,0,30x20): snap left to right."""
        # If tavern is at (19.5, 0), its right edge (39.5) is near city_gate left (20)?
        # No: drag_right = 19.5+20 = 39.5, city_gate_left = 20 → dist = 19.5, too far
        # Let's move tavern near city_gate: drag at (19.0, 0) → right=39, left=19
        # city_gate_left=20, drag_right=39 → no
        # Actually: drag_left=19 near city_gate_left=20 → dist=1.0 = threshold → no snap
        # drag at (19.01, 0) → left=19.01, dist=0.99 < 1.0 → snap to 20
        others = {
            "city_gate.json": _loc((20, 0), (30, 20)),
            "market_square.json": _loc((20, 15), (25, 25)),
        }
        result = snap_location_position((19.01, 0), (20, 15), others, exclude="tavern.json")
        # drag_left(19.01) snaps to city_gate_left(20) → origin = 20.0
        # But wait: city_gate_left=20, drag_left=19.01 → dx=0.99 → origin=20.0
        assert result[0] == 20.0
