"""WORLD-MAP-PLACEMENT-INTEGRITY-1: 2D overlap diagnostics.

Detects territorial overlap between location rectangles.
Border touching (shared edge, area=0) is NOT an overlap.

Three distinct spatial relationships (per Master's architectural decision):
- Border touching -> adjacency (handled by spatial_registry_builder)
- 2D overlap -> warning (detected here, NOT adjacency)
- Disjoint -> allowed (no action)

This module does NOT create adjacency. Does NOT modify data.
Pure diagnostics only.
"""

from typing import Any


def rectangles_2d_overlap(
    a_origin: tuple[float, float],
    a_size: tuple[float, float],
    b_origin: tuple[float, float],
    b_size: tuple[float, float],
) -> tuple[float, float, float, float, float] | None:
    """Check if two rectangles have 2D area overlap.

    Returns (x, y, w, h, area) of overlap zone, or None.
    Border touching (w=0 or h=0) returns None — not an overlap.
    Full containment returns the inner rectangle.
    """
    ax1, ay1 = a_origin
    aw, ah = a_size
    ax2, ay2 = ax1 + aw, ay1 + ah

    bx1, by1 = b_origin
    bw, bh = b_size
    bx2, by2 = bx1 + bw, by1 + bh

    ox1 = max(ax1, bx1)
    oy1 = max(ay1, by1)
    ox2 = min(ax2, bx2)
    oy2 = min(ay2, by2)

    ow = ox2 - ox1
    oh = oy2 - oy1

    # Strictly positive — border touch (ow=0 or oh=0) is NOT overlap
    if ow > 0 and oh > 0:
        return (ox1, oy1, ow, oh, round(ow * oh, 2))
    return None


def detect_2d_overlaps(locations: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Detect all 2D area overlaps between locations.

    Args:
        locations: {filename: {origin: {x, y}, size: {w, h}, ...}}

    Returns:
        List of overlap records:
        {location_a, location_b, overlap_bounds: (x, y, w, h), overlap_area: float}
    """
    overlaps: list[dict[str, Any]] = []
    locs = list(locations.items())
    for i, (fname_a, data_a) in enumerate(locs):
        origin_a = data_a.get("origin", {"x": 0, "y": 0})
        size_a = data_a.get("size", {"w": 0, "h": 0})
        a_origin = (float(origin_a.get("x", 0)), float(origin_a.get("y", 0)))
        a_size = (float(size_a.get("w", 0)), float(size_a.get("h", 0)))

        for fname_b, data_b in locs[i + 1 :]:
            origin_b = data_b.get("origin", {"x": 0, "y": 0})
            size_b = data_b.get("size", {"w": 0, "h": 0})
            b_origin = (float(origin_b.get("x", 0)), float(origin_b.get("y", 0)))
            b_size = (float(size_b.get("w", 0)), float(size_b.get("h", 0)))

            result = rectangles_2d_overlap(a_origin, a_size, b_origin, b_size)
            if result:
                ox, oy, ow, oh, area = result
                overlaps.append(
                    {
                        "location_a": fname_a,
                        "location_b": fname_b,
                        "overlap_bounds": (ox, oy, ow, oh),
                        "overlap_area": area,
                    }
                )
    return overlaps


# Magnetic snapping threshold in world meters
SNAP_THRESHOLD = 1.0


def snap_location_position(
    new_origin: tuple[float, float],
    size: tuple[float, float],
    other_locations: dict[str, dict],
    threshold: float = SNAP_THRESHOLD,
    exclude: str | None = None,
) -> tuple[float, float]:
    """Snap location position to nearby edges of other locations.

    When dragging a location, if any edge comes within `threshold` meters
    of another location's edge (with perpendicular overlap), the position
    snaps to align the edges. Independent X and Y snapping.

    Inspired by window magnetic snapping (Windhawk Slick Window Arrangement).
    Threshold is in world meters, not screen pixels — snap zone scales
    with zoom, intuitive for map editing.

    Args:
        new_origin: proposed (x, y) origin in world meters
        size: (w, h) of the dragged location
        other_locations: {fname: {origin: {x, y}, size: {w, h}}}
        threshold: snap distance in meters (default 1.0)
        exclude: filename being moved (don't snap to self)

    Returns:
        Snapped (x, y) origin. Same as input if no snap within threshold.
    """
    wx, wy = new_origin
    w, h = size

    best_dx = 0.0
    best_dy = 0.0
    best_x_dist = threshold
    best_y_dist = threshold

    drag_left = wx
    drag_right = wx + w
    drag_top = wy
    drag_bottom = wy + h

    for fname, data in other_locations.items():
        if fname == exclude:
            continue
        origin = data.get("origin", {"x": 0, "y": 0})
        size_other = data.get("size", {"w": 0, "h": 0})
        ox = float(origin.get("x", 0))
        oy = float(origin.get("y", 0))
        ow = float(size_other.get("w", 0))
        oh = float(size_other.get("h", 0))

        other_left = ox
        other_right = ox + ow
        other_top = oy
        other_bottom = oy + oh

        # Perpendicular overlap checks
        y_overlap = drag_top < other_bottom and drag_bottom > other_top
        x_overlap = drag_left < other_right and drag_right > other_left

        # X-axis snapping: 4 edge pairs
        if y_overlap:
            for drag_edge, other_edge in [
                (drag_left, other_left),
                (drag_left, other_right),
                (drag_right, other_left),
                (drag_right, other_right),
            ]:
                dist = abs(drag_edge - other_edge)
                if dist < best_x_dist:
                    best_x_dist = dist
                    best_dx = other_edge - drag_edge

        # Y-axis snapping: 4 edge pairs
        if x_overlap:
            for drag_edge, other_edge in [
                (drag_top, other_top),
                (drag_top, other_bottom),
                (drag_bottom, other_top),
                (drag_bottom, other_bottom),
            ]:
                dist = abs(drag_edge - other_edge)
                if dist < best_y_dist:
                    best_y_dist = dist
                    best_dy = other_edge - drag_edge

    return (wx + best_dx, wy + best_dy)
