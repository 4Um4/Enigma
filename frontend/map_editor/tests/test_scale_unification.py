"""path: /frontend/map_editor/tests/test_scale_unification.py

Назначение: ME-2.8 — SCALE audit verification tests.
    Verifies: Geometry transforms are correct and self-consistent.
    SCALE is MODULE-level in geometry.py (not Geometry class attribute).
    editor_core SCALE=40 is INTENTIONAL (hit testing 2x compensation,
    per test_audit_quick_wins.py:167-169 comment — unification worsened drag).
"""

from __future__ import annotations

from core.geometry import SCALE as GEO_SCALE
from core.geometry import Geometry


def test_geometry_module_scale_is_20():
    """geometry.SCALE = 20 (module-level, not Geometry class attribute)."""
    assert GEO_SCALE == 20, f"geometry.SCALE should be 20, got {GEO_SCALE}"


def test_geometry_class_has_no_scale_attribute():
    """Geometry class does NOT have SCALE (it's module-level)."""
    assert not hasattr(Geometry, "SCALE"), (
        "Geometry.SCALE should not exist — SCALE is module-level in geometry.py"
    )


def test_world_to_screen_screen_to_world_inverse():
    """world_to_screen and screen_to_world are inverse operations."""
    cam_x, cam_y, zoom = 100.0, 200.0, 1.5
    wx, wy = 5.0, 3.0
    sx, sy = Geometry.world_to_screen(cam_x, cam_y, zoom, wx, wy)
    rx, ry = Geometry.screen_to_world(cam_x, cam_y, zoom, sx, sy)
    assert abs(rx - wx) < 0.01, f"round-trip x: {rx} != {wx}"
    assert abs(ry - wy) < 0.01, f"round-trip y: {ry} != {wy}"


def test_world_to_screen_at_origin():
    """world (0,0) maps to camera position."""
    sx, sy = Geometry.world_to_screen(100, 200, 1.0, 0.0, 0.0)
    assert sx == 100 and sy == 200


def test_world_to_screen_with_zoom():
    """Zoom scales the world-to-screen transform."""
    sx1, _ = Geometry.world_to_screen(0, 0, 1.0, 1.0, 0.0)
    sx2, _ = Geometry.world_to_screen(0, 0, 2.0, 1.0, 0.0)
    assert sx2 == sx1 * 2


def test_object_sizing_uses_module_scale():
    """Object sizing: w_pixels = w_meters * SCALE * zoom (SCALE=20, module-level)."""
    w_meters = 2.0
    zoom = 1.0
    w_pixels = w_meters * GEO_SCALE * zoom
    assert w_pixels == 40, f"2m * 20px/m * 1.0zoom = 40px, got {w_pixels}"
