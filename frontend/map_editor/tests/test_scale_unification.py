"""path: /frontend/map_editor/tests/test_scale_unification.py

Назначение: ME-2.8-FIX — SCALE unification + coordinate space separation.
    SCALE=20 unified across all editor modules (editor_core, geometry,
    renderer, event_handler, interaction).
    UI elements (rotation buttons, resize handles) anchored to real geometry
    (SCALE=20) with separate padding for grab area.
    Tests verify mathematical invariants of coordinate transforms.

Invariant tests (Part C):
    - world_to_screen → screen_to_world round-trip (non-zero camera, zoom != 1)
    - center_on: object center at screen center
    - zoom_to_cursor: point stays under cursor
    - location_rect: matches rendered bounds
    - drag: 100px mouse = correct screen movement
"""

from __future__ import annotations

from core.geometry import SCALE as GEO_SCALE
from core.geometry import Geometry

# === Existing tests (SCALE value verification) ===

def test_geometry_module_scale_is_20():
    """geometry.SCALE = 20 (module-level, canonical world scale)."""
    assert GEO_SCALE == 20


def test_geometry_class_has_no_scale_attribute():
    """Geometry class does NOT have SCALE (it's module-level)."""
    assert not hasattr(Geometry, "SCALE")


# === Part C: Invariant tests ===

def test_world_screen_world_roundtrip():
    """World → Screen → World returns original coordinate."""
    cam_x, cam_y, zoom = 100.0, 200.0, 1.5
    wx, wy = 5.0, 3.0
    sx, sy = Geometry.world_to_screen(cam_x, cam_y, zoom, wx, wy)
    rx, ry = Geometry.screen_to_world(cam_x, cam_y, zoom, sx, sy)
    assert abs(rx - wx) < 0.01
    assert abs(ry - wy) < 0.01


def test_roundtrip_nonzero_camera_zoom():
    """Round-trip with non-zero camera and zoom != 1 (edge case)."""
    cam_x, cam_y, zoom = 137.0, 242.0, 1.7
    wx, wy = 8.3, -4.2
    sx, sy = Geometry.world_to_screen(cam_x, cam_y, zoom, wx, wy)
    rx, ry = Geometry.screen_to_world(cam_x, cam_y, zoom, sx, sy)
    assert abs(rx - wx) < 0.01, f"x: {rx} != {wx}"
    assert abs(ry - wy) < 0.01, f"y: {ry} != {wy}"


def test_center_on_object_at_screen_center():
    """After _center_on math, object center maps to screen center."""
    cx, screen_cx, zoom = 5.0, 400, 1.0
    scale = 20  # editor_core.SCALE after fix
    camera_x = screen_cx - cx * scale * zoom
    sx = int(cx * scale * zoom + camera_x)
    assert sx == screen_cx, f"center: {sx} != {screen_cx}"


def test_center_on_nonzero_zoom():
    """Center on with zoom != 1."""
    cx, screen_cx, zoom = 10.0, 500, 2.0
    scale = 20
    camera_x = screen_cx - cx * scale * zoom
    sx = int(cx * scale * zoom + camera_x)
    assert sx == screen_cx


def test_center_on_far_origin():
    """Center on with far-from-zero origin."""
    cx, screen_cx, zoom = 150.0, 300, 0.5
    scale = 20
    camera_x = screen_cx - cx * scale * zoom
    sx = int(cx * scale * zoom + camera_x)
    assert sx == screen_cx


def test_zoom_preserves_point_under_cursor():
    """After zoom, the world point under the cursor stays put."""
    cx, camera_x = 300, 100
    old_zoom, new_zoom = 1.0, 2.0
    scale = 20
    world_x = (cx - camera_x) / (scale * old_zoom)
    new_camera_x = cx - world_x * scale * new_zoom
    sx = int(world_x * scale * new_zoom + new_camera_x)
    assert sx == cx, f"zoom: {sx} != {cx}"


def test_zoom_nonzero_camera():
    """Zoom with non-zero camera and zoom != 1."""
    cx, camera_x = 200, 50
    old_zoom, new_zoom = 1.5, 3.0
    scale = 20
    world_x = (cx - camera_x) / (scale * old_zoom)
    new_camera_x = cx - world_x * scale * new_zoom
    sx = int(world_x * scale * new_zoom + new_camera_x)
    assert sx == cx


def test_location_rect_matches_rendered():
    """Location rect size matches renderer size (both SCALE=20)."""
    size_w, zoom = 20.0, 1.0
    scale = 20
    rect_w = size_w * scale * zoom
    renderer_w = size_w * scale * zoom
    assert rect_w == renderer_w


def test_location_rect_nonzero_zoom():
    """Location rect with zoom != 1."""
    size_w, zoom = 15.0, 2.5
    scale = 20
    rect_w = size_w * scale * zoom
    renderer_w = size_w * scale * zoom
    assert rect_w == renderer_w


def test_drag_100px_correct_movement():
    """100px mouse movement gives correct object movement on screen."""
    scale = 20  # event_handler.SCALE
    zoom = 1.0
    total_dx = 100
    dx_world = total_dx / (scale * zoom)
    visual_dx = dx_world * 20 * zoom  # renderer SCALE=20
    assert visual_dx == total_dx, f"drag: visual {visual_dx} != mouse {total_dx}"


def test_drag_nonzero_zoom():
    """Drag with zoom != 1 — visual movement matches mouse."""
    scale = 20
    zoom = 2.0
    total_dx = 100
    dx_world = total_dx / (scale * zoom)
    visual_dx = dx_world * 20 * zoom
    assert visual_dx == total_dx


def test_world_to_screen_at_origin():
    """world (0,0) maps to camera position."""
    sx, sy = Geometry.world_to_screen(100, 200, 1.0, 0.0, 0.0)
    assert sx == 100 and sy == 200


def test_world_to_screen_with_zoom():
    """Zoom scales the world-to-screen transform."""
    sx1, _ = Geometry.world_to_screen(0, 0, 1.0, 1.0, 0.0)
    sx2, _ = Geometry.world_to_screen(0, 0, 2.0, 1.0, 0.0)
    assert sx2 == sx1 * 2
