"""ME-2.1 Step C: CatalogIndex tests."""

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


class TestIndexBuilding:
    def test_all_30_indexed(self):
        idx = _make_index()
        assert idx.count == 30

    def test_list_all_sorted(self):
        idx = _make_index()
        all_ids = idx.list_all()
        assert len(all_ids) == 30
        assert all_ids == sorted(all_ids)


class TestSearch:
    def test_search_by_id(self):
        idx = _make_index()
        results = idx.search("table")
        assert "table" in results

    def test_search_by_label_russian(self):
        idx = _make_index()
        results = idx.search("стол")
        assert "table" in results

    def test_search_by_tag(self):
        idx = _make_index()
        results = idx.search("furniture")
        assert "table" in results
        assert "chair" in results

    def test_search_case_insensitive(self):
        idx = _make_index()
        assert "table" in idx.search("TABLE")
        assert "table" in idx.search("Table")

    def test_search_no_match(self):
        idx = _make_index()
        results = idx.search("nonexistent_xyz")
        assert results == []


class TestFilter:
    def test_filter_by_category_furniture(self):
        idx = _make_index()
        results = idx.filter(category="furniture")
        assert len(results) == 8
        assert "table" in results
        assert "chair" in results

    def test_filter_by_category_nature(self):
        idx = _make_index()
        results = idx.filter(category="nature")
        assert len(results) == 6
        assert "spruce" in results
        assert "tree" in results

    def test_filter_by_tag_requires_wall(self):
        idx = _make_index()
        results = idx.filter(tags=["requires_wall"])
        assert "door" in results
        assert "window" in results
        assert "table" not in results

    def test_filter_by_tag_walkable(self):
        idx = _make_index()
        results = idx.filter(tags=["walkable"])
        assert "door" in results
        assert "grass" in results
        assert "table" not in results

    def test_filter_by_category_and_tag(self):
        idx = _make_index()
        results = idx.filter(category="wall_object", tags=["requires_wall"])
        assert len(results) == 4
        assert "door" in results
        assert "window" in results

    def test_filter_multiple_tags_all_required(self):
        idx = _make_index()
        results = idx.filter(tags=["walkable", "blocks_los"])
        # walkable AND blocks_los — should be empty (walkable=walk=True, blocks_los=cover>=0.7)
        assert results == []

    def test_filter_no_args_returns_all(self):
        idx = _make_index()
        results = idx.filter()
        assert len(results) == 30


class TestPreview:
    def test_get_preview_table(self):
        idx = _make_index()
        preview = idx.get_preview("table")
        assert preview is not None
        assert preview["label"] == "Стол"
        assert preview["category"] == "furniture"
        assert "furniture" in preview["tags"]
        assert preview["sprite"] == ["Deadbeat/deadbeat_b", 5, 11]

    def test_get_preview_nonexistent(self):
        idx = _make_index()
        assert idx.get_preview("nonexistent") is None

    def test_preview_returns_copy(self):
        idx = _make_index()
        p1 = idx.get_preview("table")
        p2 = idx.get_preview("table")
        assert p1 == p2
        p1["label"] = "modified"
        assert p2["label"] == "Стол"  # original unchanged


class TestCategoriesAndTags:
    def test_list_categories(self):
        idx = _make_index()
        cats = idx.list_categories()
        assert "furniture" in cats
        assert "nature" in cats
        assert "wall_object" in cats
        assert "transition" in cats
        assert "interactive" in cats
        assert "decoration" in cats

    def test_category_count(self):
        idx = _make_index()
        assert idx.get_category_count("furniture") == 8
        assert idx.get_category_count("nature") == 6

    def test_list_tags(self):
        idx = _make_index()
        tags = idx.list_tags()
        assert "requires_wall" in tags
        assert "walkable" in tags
        assert "blocks_los" in tags
        assert "tall" in tags

    def test_tag_count(self):
        idx = _make_index()
        assert idx.get_tag_count("requires_wall") == 4  # door, window, gap, door_transition
        assert idx.get_tag_count("furniture") == 8  # category tag


class TestRefresh:
    def test_refresh_clears_and_rebuilds(self):
        idx = _make_index()
        assert idx.count == 30
        idx.refresh()
        assert idx.count == 30  # same after refresh

    def test_empty_store(self):
        store = AssetStore(Path("/nonexistent"))
        store.load()
        idx = CatalogIndex(store)
        assert idx.count == 0
        assert idx.list_all() == []
        assert idx.list_categories() == []
