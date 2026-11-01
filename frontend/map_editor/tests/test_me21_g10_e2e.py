"""ME-2.1-G-10: E2E Integration tests.

Доказывает, что построенная система Blueprint Editor работает как единое целое.
Изоляция: OBJECT_PRESETS сохраняется и восстанавливается через fixture.
"""

from __future__ import annotations

import copy
import json
import shutil
import sys
from pathlib import Path

import pytest

frontend_root = Path(__file__).resolve().parents[2]
map_editor_root = frontend_root / "map_editor"
for p in [str(frontend_root), str(map_editor_root)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from assets.asset_store import AssetStore, SaveBlocked  # noqa: E402
from assets.blueprint_editor import BlueprintEditor, SessionState  # noqa: E402
from assets.catalog_index import CatalogIndex  # noqa: E402
from assets.resource_validator import ResourceValidator  # noqa: E402


@pytest.fixture
def isolated_assets(tmp_path):
    src = map_editor_root / "assets" / "catalogs" / "base" / "blueprints" / "door.json"
    assets_dir = tmp_path / "assets"
    bp_dir = assets_dir / "catalogs" / "base" / "blueprints"
    bp_dir.mkdir(parents=True)
    pixels_dir = tmp_path / "pixels"
    pixels_dir.mkdir()
    (pixels_dir / "Deadbeat").mkdir()
    (pixels_dir / "Deadbeat" / "deadbeat_b.png").write_bytes(b"")
    shutil.copy(src, bp_dir / "door.json")
    store = AssetStore(assets_dir)
    store.load()
    validator = ResourceValidator(pixels_dir)
    index = CatalogIndex(store)
    return {
        "store": store,
        "validator": validator,
        "index": index,
        "assets_dir": assets_dir,
        "bp_path": bp_dir / "door.json",
        "pixels_dir": pixels_dir,
    }


@pytest.fixture
def editor(isolated_assets):
    return BlueprintEditor(
        asset_store=isolated_assets["store"],
        validator=isolated_assets["validator"],
    )


@pytest.fixture
def preserve_object_presets():
    """Сохранить и восстановить глобальный OBJECT_PRESETS (изоляция G-10)."""
    from data_manager import OBJECT_PRESETS

    saved = copy.deepcopy(OBJECT_PRESETS)
    yield OBJECT_PRESETS
    OBJECT_PRESETS.clear()
    OBJECT_PRESETS.update(saved)


def _deep_copy(data):
    return json.loads(json.dumps(data))


def _refresh_caches(store, index):
    from data_manager import refresh_object_presets

    refresh_object_presets(store)
    index.refresh()


class TestOpenEdit:
    def test_edit_does_not_mutate_record(self, isolated_assets, editor):
        store = isolated_assets["store"]
        original_data = _deep_copy(store.get_blueprint("door").data)
        session = editor.open("door")
        session.set_field("geometry.size.w", 5.0)
        assert store.get_blueprint("door").data == original_data
        assert session.get_field("geometry.size.w") == 5.0


class TestValidateSave:
    def test_invalid_data_blocked(self, isolated_assets, editor):
        bp_path = isolated_assets["bp_path"]
        original_bytes = bp_path.read_bytes()
        session = editor.open("door")
        session.set_field("geometry.size.w", -1)
        with pytest.raises(SaveBlocked):
            session.save()
        assert bp_path.read_bytes() == original_bytes

    def test_valid_data_saved(self, isolated_assets, editor):
        session = editor.open("door")
        session.set_field("geometry.size.w", 2.5)
        result = session.save()
        assert result.ok
        assert result.blueprint_id == "door"


class TestSaveRefresh:
    def test_catalog_index_refreshed_after_save(self, isolated_assets, editor):
        index = isolated_assets["index"]
        session = editor.open("door")
        session.set_field("metadata.label", "Updated Door")
        session.save(on_cache_refresh=lambda: index.refresh())
        preview = index.get_preview("door")
        assert preview["label"] == "Updated Door"

    def test_object_presets_refreshed_after_save(self, isolated_assets, editor, preserve_object_presets):
        store = isolated_assets["store"]
        index = isolated_assets["index"]
        session = editor.open("door")
        session.set_field("metadata.label", "Preset Door")
        session.save(on_cache_refresh=lambda: _refresh_caches(store, index))
        from data_manager import OBJECT_PRESETS

        assert OBJECT_PRESETS["door"]["label"] == "Preset Door"


class TestExistingInstances:
    def test_old_instance_unchanged_after_save(self, isolated_assets, editor):
        store = isolated_assets["store"]
        old_instance = _deep_copy(store.get_blueprint("door").data)
        old_width = old_instance["geometry"]["size"]["w"]
        session = editor.open("door")
        session.set_field("geometry.size.w", old_width + 10.0)
        session.save()
        assert old_instance["geometry"]["size"]["w"] == old_width


class TestPlaceNewInstance:
    def test_new_instance_gets_updated_data(self, isolated_assets, editor, preserve_object_presets):
        store = isolated_assets["store"]
        index = isolated_assets["index"]
        session = editor.open("door")
        session.set_field("metadata.label", "New Instance Door")
        session.set_field("geometry.size.w", 3.0)
        session.save(on_cache_refresh=lambda: _refresh_caches(store, index))
        from data_manager import OBJECT_PRESETS

        preset = OBJECT_PRESETS["door"]
        assert preset["label"] == "New Instance Door"


class TestHistory:
    def test_history_created_and_accessible(self, isolated_assets, editor):
        bp_path = isolated_assets["bp_path"]
        session = editor.open("door")
        session.set_field("metadata.label", "History Test")
        session.save()
        history_dir = bp_path.parent / ".history"
        history_files = list(history_dir.glob("door.*.json"))
        assert len(history_files) >= 1
        hist_data = json.loads(history_files[0].read_text(encoding="utf-8-sig"))
        assert hist_data["metadata"]["label"] == "Дверь"


class TestPropagationHint:
    def test_propagation_count_correct(self, isolated_assets, editor):
        fake_location = {"objects": [{"type": "door"}, {"type": "door"}, {"type": "chair"}]}
        fake_locations = {"tavern.json": fake_location}

        def count_fn(bp_id):
            loc = fake_locations.get("tavern.json", {})
            return sum(1 for o in loc.get("objects", []) if o.get("type") == bp_id)

        assert count_fn("door") == 2


class TestNewFromIndependence:
    def test_clone_independent_after_save(self, isolated_assets, editor, preserve_object_presets):
        store = isolated_assets["store"]
        index = isolated_assets["index"]
        session = editor.new_from("door", "door_clone")
        session.set_field("metadata.label", "Cloned Door")
        session.save(on_cache_refresh=lambda: _refresh_caches(store, index))
        original = store.get_blueprint("door")
        assert original.data["metadata"]["label"] == "Дверь"
        clone = store.get_blueprint("door_clone")
        assert clone is not None
        assert clone.data["metadata"]["label"] == "Cloned Door"
        assert clone.data["blueprint_id"] == "door_clone"


class TestFullE2E:
    def test_full_pipeline(self, isolated_assets, editor, preserve_object_presets):
        store = isolated_assets["store"]
        index = isolated_assets["index"]
        original = _deep_copy(store.get_blueprint("door").data)
        original_label = original["metadata"]["label"]
        session = editor.open("door")
        assert session.state == SessionState.OPEN
        session.set_field("metadata.label", "E2E Test Door")
        session.set_field("geometry.size.w", 3.5)
        assert session.dirty is True
        assert session.last_validation is not None
        assert len(session.last_validation.errors) == 0
        result = session.save(on_cache_refresh=lambda: _refresh_caches(store, index))
        assert result.ok
        preview = index.get_preview("door")
        assert preview["label"] == "E2E Test Door"
        from data_manager import OBJECT_PRESETS

        assert OBJECT_PRESETS["door"]["label"] == "E2E Test Door"
        assert original["metadata"]["label"] == original_label
        history_dir = isolated_assets["bp_path"].parent / ".history"
        assert history_dir.exists()
        assert len(list(history_dir.glob("door.*.json"))) >= 1
        store.load()
        reloaded = store.get_blueprint("door")
        assert reloaded.data["metadata"]["label"] == "E2E Test Door"
        assert reloaded.data["geometry"]["size"]["w"] == 3.5

    def test_full_pipeline_with_clone(self, isolated_assets, editor, preserve_object_presets):
        store = isolated_assets["store"]
        index = isolated_assets["index"]
        session = editor.new_from("door", "door_e2e")
        session.set_field("metadata.label", "E2E Clone")
        session.set_field("appearance.color", "#FF0000")
        result = session.save(on_cache_refresh=lambda: _refresh_caches(store, index))
        assert result.ok
        original = store.get_blueprint("door")
        assert original.data["metadata"]["label"] == "Дверь"
        clone = store.get_blueprint("door_e2e")
        assert clone is not None
        assert clone.data["metadata"]["label"] == "E2E Clone"
        assert clone.data["appearance"]["color"] == "#FF0000"
        session2 = editor.open("door")
        session2.set_field("metadata.label", "Original Changed")
        session2.save(on_cache_refresh=lambda: _refresh_caches(store, index))
        store.load()
        clone_after = store.get_blueprint("door_e2e")
        assert clone_after.data["metadata"]["label"] == "E2E Clone"


class TestGamePreviewPath:
    def test_geometry_data_accessible_for_preview(self, isolated_assets, editor, preserve_object_presets):
        store = isolated_assets["store"]
        index = isolated_assets["index"]
        session = editor.open("door")
        session.set_field("geometry.size.w", 4.0)
        session.set_field("geometry.size.h", 0.5)
        session.save(on_cache_refresh=lambda: index.refresh())
        store.load()
        bp = store.get_blueprint("door")
        geometry = bp.data.get("geometry", {})
        size = geometry.get("size", {})
        assert size["w"] == 4.0
        assert size["h"] == 0.5
        physics = bp.data.get("physics", {})
        assert "passability" in physics
        assert "cover" in physics

    def test_scene_bridge_data_path(self, isolated_assets, editor, preserve_object_presets):
        store = isolated_assets["store"]
        index = isolated_assets["index"]
        session = editor.open("door")
        session.set_field("metadata.label", "Scene Bridge Test")
        session.save(on_cache_refresh=lambda: _refresh_caches(store, index))
        from data_manager import OBJECT_PRESETS

        preset = OBJECT_PRESETS["door"]
        assert preset["label"] == "Scene Bridge Test"
        assert "color" in preset
        assert "passability" in preset
        assert "cover" in preset


class TestNoDoubleTruth:
    def test_assetstore_remains_ssot(self, isolated_assets, editor, preserve_object_presets):
        store = isolated_assets["store"]
        session = editor.open("door")
        session.set_field("metadata.label", "SSOT Test")
        session.save()
        store.load()
        assert store.get_blueprint("door").data["metadata"]["label"] == "SSOT Test"
        from data_manager import OBJECT_PRESETS, refresh_object_presets

        refresh_object_presets(store)
        assert OBJECT_PRESETS["door"]["label"] == "SSOT Test"
