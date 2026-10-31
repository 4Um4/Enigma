"""ME-2.1 Step E: Category hierarchy + multiple membership tests."""

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

from assets.asset_store import AssetStore
from assets.catalog_index import CatalogIndex

_ASSETS_DIR = map_editor_root / "assets"


def _make_index():
    store = AssetStore(_ASSETS_DIR)
    store.load()
    return CatalogIndex(store)


class TestHierarchicalCategories:
    def test_parent_furniture_matches_indoor(self):
        """filter('furniture') matches 'furniture/indoor'."""
        idx = _make_index()
        results = idx.filter(category="furniture")
        assert "table" in results
        assert "chair" in results
        assert "tent" in results  # furniture/outdoor
        assert len(results) == 8

    def test_child_furniture_indoor_only(self):
        """filter('furniture/indoor') matches only indoor."""
        idx = _make_index()
        results = idx.filter(category="furniture/indoor")
        assert "table" in results
        assert "tent" not in results  # outdoor
        assert len(results) == 7

    def test_parent_nature_matches_plant_and_mineral(self):
        idx = _make_index()
        results = idx.filter(category="nature")
        assert "spruce" in results
        assert "rocks" in results
        assert len(results) == 6

    def test_child_nature_plant_only(self):
        idx = _make_index()
        results = idx.filter(category="nature/plant")
        assert "spruce" in results
        assert "rocks" not in results
        assert len(results) == 5

    def test_parent_transition_matches_vertical_and_portal(self):
        idx = _make_index()
        results = idx.filter(category="transition")
        assert "stairs_up" in results
        assert "portal_magic" in results
        assert "hatch" in results

    def test_list_category_tree(self):
        idx = _make_index()
        tree = idx.list_category_tree()
        assert "furniture" in tree
        assert "indoor" in tree["furniture"]
        assert "outdoor" in tree["furniture"]
        assert "nature" in tree
        assert "plant" in tree["nature"]


class TestMultipleMembership:
    def test_door_in_multiple_categories(self):
        """door is in wall_object/opening AND transition/portal."""
        idx = _make_index()
        # door should appear in both parent categories
        wall_results = idx.filter(category="wall_object")
        transition_results = idx.filter(category="transition")
        assert "door" in wall_results
        assert "door" in transition_results

    def test_door_transition_in_both(self):
        """door_transition is in wall_object AND transition."""
        idx = _make_index()
        assert "door_transition" in idx.filter(category="wall_object")
        assert "door_transition" in idx.filter(category="transition")

    def test_hatch_in_vertical_and_portal(self):
        """hatch is in transition/portal AND transition/vertical."""
        idx = _make_index()
        assert "hatch" in idx.filter(category="transition/portal")
        assert "hatch" in idx.filter(category="transition/vertical")


class TestBackwardCompat:
    def test_category_field_still_exists(self):
        """Old 'category' field still works."""
        idx = _make_index()
        cats = idx.list_categories()
        assert "furniture" in cats

    def test_categories_field_in_preview(self):
        """Preview includes 'categories' list."""
        idx = _make_index()
        preview = idx.get_preview("table")
        assert preview is not None
        assert "categories" in preview
        assert "furniture/indoor" in preview["categories"]
