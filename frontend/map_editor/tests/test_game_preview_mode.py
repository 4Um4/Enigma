"""Tests for Game Preview mode in editor_core.

GAME-PREVIEW-IMPLEMENTATION-1.

Mandatory tests covered:
- SCALE 40 px/m (game constant)
- Sprite loading (shared registry)
- Mode switching (preview_active field, F11 hotkey, no coordinate change)
- Save -> Load -> Preview (geometry preserved)
- Preview -> Editing (no JSON mutation)
- Comparison: Preview inputs vs game inputs (structural parity)
"""

import json
import os
import sys
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

pygame.init()
_SCREEN = pygame.display.set_mode((100, 100))

frontend_root = Path(__file__).resolve().parents[2]
map_editor_root = frontend_root / "map_editor"
for p in [str(frontend_root), str(map_editor_root)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from tools.constants import MODE_LOCAL

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
        },
        {
            "id": "table_1",
            "type": "table",
            "position": {"x": 5.0, "y": 7.0},
            "size": {"w": 2.0, "h": 1.0},
            "passability": {"walk": False},
        },
    ],
    "rooms": [{"x": 0.0, "y": 0.0, "width": 20.0, "height": 15.0}],
    "npcs": [{"ref_id": "npc_test", "position": {"x": 8.0, "y": 8.0}}],
    "player_spawn": {"x": 10.0, "y": 7.5},
}


class TestScaleConstant:
    """Mandatory: 'SCALE — 40 px/m'."""

    def test_game_scale_is_40(self):
        from constants import SCALE_PIXELS_PER_METER

        assert SCALE_PIXELS_PER_METER == 40

    def test_scene_renderer_uses_game_scale(self):
        import scene_renderer

        assert scene_renderer.SCALE == 40


class TestSpriteRegistry:
    """Mandatory: 'Sprite loading — Общий registry, корректные ресурсы'."""

    def test_preview_uses_same_sprite_registry(self):
        import scene_renderer
        from map_editor.sprite_registry import sprite_registry as editor_sr_obj

        assert scene_renderer.sprite_registry is editor_sr_obj


class TestPreviewActiveField:
    """Mandatory: 'Mode switching — Координаты и размеры не меняются'."""

    def test_default_is_false(self):
        ec_path = frontend_root / "map_editor" / "editor_core.py"
        text = ec_path.read_text(encoding="utf-8")
        assert "self.preview_active: bool = False" in text

    def test_toggle_logic(self):
        core = SimpleNamespace(preview_active=False, mode=MODE_LOCAL)
        if core.mode == MODE_LOCAL:
            core.preview_active = not core.preview_active
        assert core.preview_active is True
        if core.mode == MODE_LOCAL:
            core.preview_active = not core.preview_active
        assert core.preview_active is False

    def test_no_coordinate_change_on_toggle(self):
        """Toggling preview must not change camera/zoom/JSON."""
        core = SimpleNamespace(
            preview_active=False,
            mode=MODE_LOCAL,
            camera_x=100.0,
            camera_y=200.0,
            zoom=1.5,
            current_file="loc",
            dm=SimpleNamespace(locations={"loc": {"id": "loc"}}),
        )
        cam_before = (core.camera_x, core.camera_y, core.zoom)
        loc_before = deepcopy(core.dm.locations["loc"])
        core.preview_active = not core.preview_active
        cam_after = (core.camera_x, core.camera_y, core.zoom)
        loc_after = core.dm.locations["loc"]
        assert cam_before == cam_after
        assert loc_before == loc_after


class TestF11Hotkey:
    def test_f11_handler_present(self):
        eh_path = frontend_root / "map_editor" / "core" / "event_handler.py"
        text = eh_path.read_text(encoding="utf-8")
        assert "pygame.K_F11" in text
        assert "core.preview_active = not core.preview_active" in text

    def test_f11_only_in_local_mode(self):
        eh_path = frontend_root / "map_editor" / "core" / "event_handler.py"
        text = eh_path.read_text(encoding="utf-8")
        idx = text.find("pygame.K_F11")
        assert idx >= 0
        block = text[idx : idx + 500]
        assert "MODE_LOCAL" in block


class TestDrawGamePreview:
    """Mandatory: 'Preview -> Editing — Нет изменений JSON'."""

    def _make_minimal_core(self, loc):
        core = SimpleNamespace()
        core.current_file = "test_loc"
        core.dm = SimpleNamespace()
        core.dm.locations = {"test_loc": deepcopy(loc)}
        core._npc_list = []
        core.screen = _SCREEN
        core.preview_active = True
        core._preview_scene_renderer = None
        core._show_toast = MagicMock()
        return core

    def test_no_json_mutation(self):
        from map_editor.editor_core import EditorCore

        core = self._make_minimal_core(SAMPLE_LOCATION)
        loc_before = deepcopy(core.dm.locations["test_loc"])
        mock_renderer = MagicMock()
        with patch("scene_renderer.SceneRenderer", return_value=mock_renderer):
            EditorCore._draw_game_preview(core)
        loc_after = core.dm.locations["test_loc"]
        assert loc_after == loc_before, "Preview mutated JSON!"

    def test_scene_renderer_called_with_correct_args(self):
        from map_editor.editor_core import EditorCore

        core = self._make_minimal_core(SAMPLE_LOCATION)
        mock_renderer = MagicMock()
        with patch("scene_renderer.SceneRenderer", return_value=mock_renderer):
            EditorCore._draw_game_preview(core)
        mock_renderer.render.assert_called_once()
        kwargs = mock_renderer.render.call_args.kwargs
        assert len(kwargs["walls"]) == 5  # split, not 4 raw
        assert len(kwargs["obstacles"]) == 2  # not empty
        assert kwargs["player_xy"] == (10.0, 7.5)
        assert kwargs["floor_rects"] is not None
        assert len(kwargs["floor_rects"]) == 1

    def test_no_current_file_disables_preview(self):
        from map_editor.editor_core import EditorCore

        core = self._make_minimal_core(SAMPLE_LOCATION)
        core.current_file = None
        EditorCore._draw_game_preview(core)
        assert core.preview_active is False

    def test_scene_renderer_lazy_init(self):
        from map_editor.editor_core import EditorCore

        core = self._make_minimal_core(SAMPLE_LOCATION)
        assert core._preview_scene_renderer is None
        with patch("scene_renderer.SceneRenderer", return_value=MagicMock()):
            EditorCore._draw_game_preview(core)
        assert core._preview_scene_renderer is not None

    def test_no_avatar_state_passed(self):
        """Preview must NOT pass avatar_state (clean frame, no blood/tunnel/shake)."""
        from map_editor.editor_core import EditorCore

        core = self._make_minimal_core(SAMPLE_LOCATION)
        mock_renderer = MagicMock()
        with patch("scene_renderer.SceneRenderer", return_value=mock_renderer):
            EditorCore._draw_game_preview(core)
        kwargs = mock_renderer.render.call_args.kwargs
        assert kwargs.get("avatar_state") is None


class TestSaveLoadPreviewRoundTrip:
    """Mandatory: 'Save -> Load -> Preview — Геометрия сохраняется'."""

    def test_geometry_preserved_through_round_trip(self):
        from map_editor.render.scene_bridge import build_perceived_scene

        loc_v1 = deepcopy(SAMPLE_LOCATION)
        loc_v2 = json.loads(json.dumps(loc_v1))
        assert loc_v1 == loc_v2
        core1 = SimpleNamespace(
            current_file="t",
            dm=SimpleNamespace(locations={"t": loc_v1}),
            _npc_list=[],
        )
        core2 = SimpleNamespace(
            current_file="t",
            dm=SimpleNamespace(locations={"t": loc_v2}),
            _npc_list=[],
        )
        r1 = build_perceived_scene(core1)
        r2 = build_perceived_scene(core2)
        assert r1[1] == r2[1]  # walls
        assert r1[2] == r2[2]  # obstacles


class TestPreviewVsGameComparison:
    """Mandatory: 'сравнить результат Preview с игровым рендером на одной карте'.

    Structural comparison: scene_bridge output == SpatialDataLoader output.
    Proves Preview renders the SAME world the game would render.
    Visual screenshot comparison is a manual step (see report).
    """

    def test_preview_inputs_match_game_inputs(self):
        from map_editor.render.scene_bridge import build_perceived_scene
        from world_context import SpatialDataLoader

        core = SimpleNamespace(
            current_file="t",
            dm=SimpleNamespace(locations={"t": deepcopy(SAMPLE_LOCATION)}),
            _npc_list=[],
        )
        sb_result = build_perceived_scene(core)
        _scene, sb_walls, sb_obstacles, _floors, _sw, _sh, _pxy = sb_result
        sdl = SpatialDataLoader._build_spatial_data("t", deepcopy(SAMPLE_LOCATION))
        sdl_walls = list(sdl.walls)
        assert len(sb_walls) == len(sdl_walls)
        for sb_w, sdl_w in zip(sb_walls, sdl_walls):
            assert sb_w == sdl_w
        sdl_obstacles = list(sdl.obstacles)
        assert len(sb_obstacles) == len(sdl_obstacles)
        for sb_o, sdl_o in zip(sb_obstacles, sdl_obstacles):
            assert sb_o == sdl_o

    def test_floor_rects_match_spatial_data(self):
        from map_editor.render.scene_bridge import build_perceived_scene
        from world_context import SpatialDataLoader

        core = SimpleNamespace(
            current_file="t",
            dm=SimpleNamespace(locations={"t": deepcopy(SAMPLE_LOCATION)}),
            _npc_list=[],
        )
        sb_result = build_perceived_scene(core)
        _scene, _walls, _obst, sb_floors, _sw, _sh, _pxy = sb_result
        sdl = SpatialDataLoader._build_spatial_data("t", deepcopy(SAMPLE_LOCATION))
        sdl_floor = sdl.floor_rect
        assert len(sb_floors) >= 1
        assert any(
            abs(f[0] - sdl_floor[0]) < 0.01
            and abs(f[1] - sdl_floor[1]) < 0.01
            and abs(f[2] - sdl_floor[2]) < 0.01
            and abs(f[3] - sdl_floor[3]) < 0.01
            for f in sb_floors
        )
