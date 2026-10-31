"""ME-2.1 Step B: Derive OBJECT_PRESETS from AssetStore — equivalence tests.

Verifies that derivation from AssetStore produces identical values
to the hardcoded _HARDCODED_OBJECT_PRESETS. Tests round-trip:
hardcoded -> Blueprint JSON (Step A) -> derived presets (Step B).
"""

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
from data_manager import _HARDCODED_OBJECT_PRESETS, OBJECT_PRESETS, refresh_object_presets
from sprite_registry import ENTITY_SPRITE_MAP, refresh_entity_sprite_map

_ASSETS_DIR = map_editor_root / "assets"


def _load_store():
    """Load AssetStore with base catalog blueprints."""
    store = AssetStore(_ASSETS_DIR)
    store.load()
    return store


class TestDerivationEquivalence:
    """Derived OBJECT_PRESETS must match hardcoded values for all fields."""

    def test_all_types_derived(self):
        """All 30 types present after derivation from AssetStore."""
        store = _load_store()
        refresh_object_presets(store)
        for type_name in _HARDCODED_OBJECT_PRESETS:
            assert type_name in OBJECT_PRESETS, f"Missing after derivation: {type_name}"

    def test_count_matches(self):
        """Derived count == hardcoded count."""
        store = _load_store()
        refresh_object_presets(store)
        assert len(OBJECT_PRESETS) == len(_HARDCODED_OBJECT_PRESETS), (
            f"Count mismatch: {len(OBJECT_PRESETS)} != {len(_HARDCODED_OBJECT_PRESETS)}"
        )

    def test_label_equivalence(self):
        store = _load_store()
        refresh_object_presets(store)
        for t, hardcoded in _HARDCODED_OBJECT_PRESETS.items():
            assert OBJECT_PRESETS[t]["label"] == hardcoded["label"], f"{t}: label"

    def test_icon_equivalence(self):
        store = _load_store()
        refresh_object_presets(store)
        for t, hardcoded in _HARDCODED_OBJECT_PRESETS.items():
            assert OBJECT_PRESETS[t].get("icon", "") == hardcoded.get("icon", ""), f"{t}: icon"

    def test_passability_equivalence(self):
        store = _load_store()
        refresh_object_presets(store)
        for t, hardcoded in _HARDCODED_OBJECT_PRESETS.items():
            for key in ("walk", "jump_over", "crawl_under", "climb_on", "walk_around"):
                assert OBJECT_PRESETS[t]["passability"][key] == hardcoded["passability"][key], f"{t}: passability.{key}"

    def test_cover_equivalence(self):
        store = _load_store()
        refresh_object_presets(store)
        for t, hardcoded in _HARDCODED_OBJECT_PRESETS.items():
            assert OBJECT_PRESETS[t]["cover"] == hardcoded["cover"], f"{t}: cover"

    def test_height_equivalence(self):
        store = _load_store()
        refresh_object_presets(store)
        for t, hardcoded in _HARDCODED_OBJECT_PRESETS.items():
            assert OBJECT_PRESETS[t]["height"] == hardcoded["height"], f"{t}: height"

    def test_color_equivalence(self):
        store = _load_store()
        refresh_object_presets(store)
        for t, hardcoded in _HARDCODED_OBJECT_PRESETS.items():
            assert OBJECT_PRESETS[t]["color"] == hardcoded["color"], f"{t}: color"

    def test_default_size_equivalence(self):
        store = _load_store()
        refresh_object_presets(store)
        for t, hardcoded in _HARDCODED_OBJECT_PRESETS.items():
            assert OBJECT_PRESETS[t].get("default_size", {}) == hardcoded.get("default_size", {}), f"{t}: default_size"

    def test_sprite_equivalence(self):
        store = _load_store()
        refresh_object_presets(store)
        for t, hardcoded in _HARDCODED_OBJECT_PRESETS.items():
            orig = hardcoded.get("sprite")
            derived = OBJECT_PRESETS[t].get("sprite")
            if orig is None:
                assert derived is None, f"{t}: sprite should be None"
            else:
                assert derived == tuple(orig), f"{t}: sprite {derived} != {tuple(orig)}"

    def test_default_properties_equivalence(self):
        store = _load_store()
        refresh_object_presets(store)
        for t, hardcoded in _HARDCODED_OBJECT_PRESETS.items():
            orig = hardcoded.get("default_properties", {})
            derived = OBJECT_PRESETS[t].get("default_properties", {})
            assert derived == orig, f"{t}: default_properties {derived} != {orig}"

    def test_rotation_mode_equivalence(self):
        store = _load_store()
        refresh_object_presets(store)
        for t, hardcoded in _HARDCODED_OBJECT_PRESETS.items():
            assert OBJECT_PRESETS[t].get("rotation_mode", "free") == hardcoded.get("rotation_mode", "free"), (
                f"{t}: rotation_mode"
            )

    def test_requires_wall_equivalence(self):
        store = _load_store()
        refresh_object_presets(store)
        for t, hardcoded in _HARDCODED_OBJECT_PRESETS.items():
            assert OBJECT_PRESETS[t].get("requires_wall", False) == hardcoded.get("requires_wall", False), (
                f"{t}: requires_wall"
            )


class TestFallbackBehavior:
    """refresh_object_presets(None) must restore hardcoded values."""

    def test_fallback_restores_hardcoded(self):
        refresh_object_presets(None)
        for t, hardcoded in _HARDCODED_OBJECT_PRESETS.items():
            assert OBJECT_PRESETS[t] == hardcoded, f"{t}: fallback value mismatch"

    def test_empty_store_falls_back(self):
        """Empty AssetStore triggers fallback."""
        store = AssetStore(Path("/nonexistent/path"))
        store.load()  # no dir → empty store
        result = refresh_object_presets(store)
        assert result is False, "Empty store should return False (fallback)"
        for t in _HARDCODED_OBJECT_PRESETS:
            assert t in OBJECT_PRESETS, f"{t}: missing after empty fallback"


class TestEntitySpriteMapRefresh:
    """refresh_entity_sprite_map() must rebuild after OBJECT_PRESETS changes."""

    def test_refresh_updates_sprite_map(self):
        """After refresh, ENTITY_SPRITE_MAP has all types."""
        store = _load_store()
        refresh_object_presets(store)
        refresh_entity_sprite_map()
        for t in OBJECT_PRESETS:
            preset = OBJECT_PRESETS[t]
            if "sprite" in preset:
                assert t in ENTITY_SPRITE_MAP, f"{t}: missing from ENTITY_SPRITE_MAP after refresh"

    def test_sprite_map_values_match(self):
        """ENTITY_SPRITE_MAP values match OBJECT_PRESETS sprites."""
        store = _load_store()
        refresh_object_presets(store)
        refresh_entity_sprite_map()
        for t, preset in OBJECT_PRESETS.items():
            sprite = preset.get("sprite")
            if sprite:
                assert ENTITY_SPRITE_MAP.get(t) == tuple(sprite), f"{t}: ENTITY_SPRITE_MAP mismatch"


class TestNoCircularImports:
    """Verify no circular import chains."""

    def test_asset_store_no_data_manager_import(self):
        """AssetStore must NOT import from data_manager."""
        import ast

        as_path = map_editor_root / "assets" / "asset_store.py"
        tree = ast.parse(as_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                if isinstance(node, ast.ImportFrom) and node.module:
                    assert "data_manager" not in node.module, f"asset_store imports data_manager: {node.module}"
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        assert "data_manager" not in alias.name, f"asset_store imports data_manager: {alias.name}"

    def test_no_circular_import_chain(self):
        """data_manager may import asset_store at module level — this is safe.

        Circular import = asset_store ALSO imports data_manager.
        asset_store imports only stdlib (json, logging, pathlib, etc.).
        So data_manager -> asset_store is a one-way dependency, NOT circular.
        """
        import ast

        # Verify asset_store does NOT import data_manager (one-way dependency)
        as_path = map_editor_root / "assets" / "asset_store.py"
        as_tree = ast.parse(as_path.read_text(encoding="utf-8"))
        for node in ast.walk(as_tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert "data_manager" not in node.module, f"asset_store imports data_manager (circular): {node.module}"
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert "data_manager" not in alias.name, (
                        f"asset_store imports data_manager (circular): {alias.name}"
                    )

        # Verify sprite_registry does NOT create a cycle with data_manager
        # sprite_registry imports OBJECT_PRESETS from data_manager — one-way
        # Verify data_manager does NOT import sprite_registry (would be circular)
        dm_path = map_editor_root / "data_manager.py"
        dm_tree = ast.parse(dm_path.read_text(encoding="utf-8"))
        for node in ast.walk(dm_tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert "sprite_registry" not in node.module, (
                    f"data_manager imports sprite_registry (circular): {node.module}"
                )
