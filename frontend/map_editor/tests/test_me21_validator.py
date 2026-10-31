"""ME-2.1 Step D: ResourceValidator tests."""

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
from assets.resource_validator import ResourceValidator, ValidationResult

_PIXELS_DIR = map_editor_root / "pixels"
_ASSETS_DIR = map_editor_root / "assets"


def _make_validator():
    return ResourceValidator(_PIXELS_DIR)


def _load_table_bp():
    store = AssetStore(_ASSETS_DIR)
    store.load()
    return store.get_blueprint("table").data


class TestStructuralValidation:
    def test_valid_blueprint_no_structural_errors(self):
        v = _make_validator()
        result = v.validate_blueprint(_load_table_bp())
        structural_errors = [i for i in result.errors if i.category == "structural"]
        assert structural_errors == []

    def test_missing_required_field(self):
        v = _make_validator()
        bp = {"blueprint_id": "test", "version": 1}  # missing compat
        result = v.validate_blueprint(bp)
        assert not result.can_place
        assert any(i.field == "compat" for i in result.errors)

    def test_missing_layer(self):
        v = _make_validator()
        bp = {"blueprint_id": "test", "version": 1, "compat": 1}
        result = v.validate_blueprint(bp)
        assert any("Missing layer: geometry" in i.message for i in result.errors)

    def test_invalid_geometry_size(self):
        v = _make_validator()
        bp = {
            "blueprint_id": "test",
            "version": 1,
            "compat": 1,
            "geometry": {"size": {"w": 0, "h": -1, "d": 0}},
            "appearance": {},
            "physics": {"passability": {}},
        }
        result = v.validate_blueprint(bp)
        assert any("geometry.size.w" in str(i.field) for i in result.errors)

    def test_missing_passability_keys(self):
        v = _make_validator()
        bp = {
            "blueprint_id": "test",
            "version": 1,
            "compat": 1,
            "geometry": {"size": {"w": 1, "h": 1, "d": 1}},
            "appearance": {},
            "physics": {"passability": {}},
        }
        result = v.validate_blueprint(bp)
        assert any("passability.walk" in str(i.field) for i in result.errors)


class TestResourceValidation:
    def test_valid_sprite_no_error(self):
        v = _make_validator()
        result = v.validate_blueprint(_load_table_bp())
        resource_errors = [i for i in result.errors if i.category == "resource"]
        assert resource_errors == []

    def test_missing_sprite_file(self):
        v = _make_validator()
        bp = _load_table_bp()
        bp["appearance"]["sprite"] = ["Nonexistent/sheet", 0, 0]
        result = v.validate_blueprint(bp)
        assert not result.can_place
        assert any("Sprite file not found" in i.message for i in result.errors)

    def test_null_sprite_warning(self):
        v = _make_validator()
        bp = _load_table_bp()
        bp["appearance"]["sprite"] = None
        result = v.validate_blueprint(bp)
        assert result.can_place  # warning, not error
        assert any("uses fallback" in i.message for i in result.warnings)

    def test_invalid_sprite_format(self):
        v = _make_validator()
        bp = _load_table_bp()
        bp["appearance"]["sprite"] = [1, 2]  # wrong length
        result = v.validate_blueprint(bp)
        assert not result.can_place
        assert any("Invalid sprite format" in i.message for i in result.errors)


class TestEditorCompat:
    def test_known_type_no_warning(self):
        v = _make_validator()
        result = v.validate_blueprint(_load_table_bp())
        editor_warnings = [i for i in result.warnings if i.category == "editor"]
        assert editor_warnings == []

    def test_unknown_type_warning(self):
        v = _make_validator()
        bp = _load_table_bp()
        bp["type"] = "custom_new_type"
        result = v.validate_blueprint(bp)
        assert any("Unknown type" in i.message for i in result.warnings)


class TestRuntimeCompat:
    def test_known_archetype_no_info(self):
        v = _make_validator()
        bp = _load_table_bp()
        bp["type"] = "door"  # known archetype
        result = v.validate_blueprint(bp)
        runtime_infos = [i for i in result.infos if i.category == "runtime"]
        assert runtime_infos == []

    def test_unknown_archetype_info(self):
        v = _make_validator()
        bp = _load_table_bp()
        bp["type"] = "table"  # not in _KNOWN_ARCHETYPES
        result = v.validate_blueprint(bp)
        assert any("decorative only" in i.message for i in result.infos)


class TestValidateAll:
    def test_validate_all_30(self):
        v = _make_validator()
        store = AssetStore(_ASSETS_DIR)
        store.load()
        results = v.validate_all(store)
        assert len(results) == 30

    def test_all_can_place(self):
        v = _make_validator()
        store = AssetStore(_ASSETS_DIR)
        store.load()
        results = v.validate_all(store)
        for bp_id, result in results.items():
            assert result.can_place, f"{bp_id}: cannot place — {[e.message for e in result.errors]}"

    def test_result_is_structured_not_boolean(self):
        v = _make_validator()
        result = v.validate_blueprint(_load_table_bp())
        assert isinstance(result, ValidationResult)
        assert hasattr(result, "issues")
        assert hasattr(result, "can_place")
        assert hasattr(result, "errors")
        assert hasattr(result, "warnings")
        assert hasattr(result, "infos")
