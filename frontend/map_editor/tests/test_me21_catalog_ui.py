"""ME-2.1 Step F: CatalogPanel integration tests."""

import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

frontend_root = Path(__file__).resolve().parents[2]
map_editor_root = frontend_root / "map_editor"
for p in [str(frontend_root), str(map_editor_root)]:
    if p not in sys.path:
        sys.path.insert(0, p)

import pygame

pygame.init()
_SCREEN = pygame.display.set_mode((100, 100))

from ui.catalog_panel import CatalogPanel

_ASSETS_DIR = map_editor_root / "assets"
_PIXELS_DIR = map_editor_root / "pixels"


def _make_panel():
    return CatalogPanel(0, 80, 250, 600, _ASSETS_DIR, _PIXELS_DIR)


class TestOpenClose:
    def test_open_loads_store_index_validator(self):
        panel = _make_panel()
        assert not panel.active
        panel.open()
        assert panel.active
        assert panel._store is not None
        assert panel._index is not None
        assert panel._validator is not None

    def test_open_loads_30_blueprints(self):
        panel = _make_panel()
        panel.open()
        assert panel._index.count == 30

    def test_close_deactivates(self):
        panel = _make_panel()
        panel.open()
        panel.close()
        assert not panel.active

    def test_open_activates_refresh(self):
        """Opening catalog activates AssetStore as source of truth."""
        from data_manager import _HARDCODED_OBJECT_PRESETS, OBJECT_PRESETS

        panel = _make_panel()
        panel.open()
        # After open, OBJECT_PRESETS should have 30 types from AssetStore
        assert len(OBJECT_PRESETS) == len(_HARDCODED_OBJECT_PRESETS)
        for t in _HARDCODED_OBJECT_PRESETS:
            assert t in OBJECT_PRESETS


class TestSearch:
    def test_search_filters_cards(self):
        panel = _make_panel()
        panel.open()
        panel._search_query = "table"
        panel._update_filtered()
        assert "table" in panel._filtered_ids
        assert len(panel._filtered_ids) < 30

    def test_search_russian(self):
        panel = _make_panel()
        panel.open()
        panel._search_query = "стол"
        panel._update_filtered()
        assert "table" in panel._filtered_ids

    def test_search_clear_shows_all(self):
        panel = _make_panel()
        panel.open()
        panel._search_query = "table"
        panel._update_filtered()
        panel._search_query = ""
        panel._update_filtered()
        assert len(panel._filtered_ids) == 30


class TestCategoryFilter:
    def test_filter_furniture(self):
        panel = _make_panel()
        panel.open()
        panel._selected_category = "furniture"
        panel._update_filtered()
        assert len(panel._filtered_ids) == 8

    def test_filter_clear(self):
        panel = _make_panel()
        panel.open()
        panel._selected_category = "furniture"
        panel._update_filtered()
        panel._selected_category = None
        panel._update_filtered()
        assert len(panel._filtered_ids) == 30

    def test_search_and_category_combined(self):
        panel = _make_panel()
        panel.open()
        panel._search_query = "ст"
        panel._selected_category = "furniture"
        panel._update_filtered()
        # "ст" matches "Стол", "Стул", "Стул" in furniture
        assert "table" in panel._filtered_ids


class TestSelection:
    def test_select_blueprint(self):
        panel = _make_panel()
        panel.open()
        panel._select_blueprint("table")
        assert panel._selected_bp_id == "table"
        assert panel._validation is not None

    def test_validation_can_place(self):
        panel = _make_panel()
        panel.open()
        panel._select_blueprint("table")
        assert panel._validation.can_place

    def test_select_calls_callback(self):
        panel = _make_panel()
        panel.open()
        called = []
        panel.on_select = lambda bp_id: called.append(bp_id)
        panel._select_blueprint("chair")
        assert called == ["chair"]


class TestPlaceCallback:
    def test_place_callback_called(self):
        panel = _make_panel()
        panel.open()
        panel._select_blueprint("table")
        placed = []
        panel.on_place = lambda bp_id: placed.append(bp_id)
        # Simulate place button click via direct call
        if panel._validation and panel._validation.can_place:
            panel.on_place(panel._selected_bp_id)
        assert placed == ["table"]

    def test_place_blocked_for_invalid(self):
        panel = _make_panel()
        panel.open()
        # Select a valid blueprint, then break its sprite
        panel._select_blueprint("table")
        bp = panel._store.get_blueprint("table").data
        bp["appearance"]["sprite"] = ["Nonexistent/sheet", 0, 0]
        panel._select_blueprint("table")  # re-validate
        assert not panel._validation.can_place


class TestEventHandling:
    def test_escape_closes(self):
        panel = _make_panel()
        panel.open()
        event = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE, unicode="")
        assert panel.handle_event(event)
        assert not panel.active

    def test_f3_closes(self):
        panel = _make_panel()
        panel.open()
        event = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F3, unicode="")
        assert panel.handle_event(event)
        assert not panel.active

    def test_inactive_returns_false(self):
        panel = _make_panel()
        event = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F3, unicode="")
        assert not panel.handle_event(event)


class TestEditorIntegration:
    """Verify editor_core has catalog panel integrated."""

    def test_editor_has_catalog_panel(self):
        ec_path = map_editor_root / "editor_core.py"
        text = ec_path.read_text(encoding="utf-8")
        assert "catalog_panel" in text
        assert "_catalog_place" in text

    def test_event_handler_has_f3(self):
        eh_path = map_editor_root / "core" / "event_handler.py"
        text = eh_path.read_text(encoding="utf-8")
        assert "pygame.K_F3" in text
        assert "catalog_panel" in text
