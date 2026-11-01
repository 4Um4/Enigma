"""ME-2.1-G-8: New-from clone tests."""

from __future__ import annotations

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

from assets.asset_store import AssetStore, AssetStoreError  # noqa: E402
from assets.blueprint_editor import BlueprintEditor, SessionState  # noqa: E402
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
    return {"store": store, "validator": validator, "assets_dir": assets_dir, "bp_path": bp_dir / "door.json"}


@pytest.fixture
def editor(isolated_assets):
    return BlueprintEditor(asset_store=isolated_assets["store"], validator=isolated_assets["validator"])


def _deep_copy(data):
    return json.loads(json.dumps(data))


class TestNewFromCreation:
    def test_new_from_creates_session(self, isolated_assets, editor):
        session = editor.new_from("door", "door_red")
        assert session is not None
        assert session.blueprint_id == "door_red"
        assert session.is_new is True
        assert session.state == SessionState.NEW

    def test_source_and_copy_independent(self, isolated_assets, editor):
        session = editor.new_from("door", "door_red")
        session.set_field("metadata.label", "Red Door")
        original = editor.open("door")
        assert original.get_field("metadata.label") == "Дверь"

    def test_id_replaced(self, isolated_assets, editor):
        session = editor.new_from("door", "door_red")
        assert session.get_field("blueprint_id") == "door_red"

    def test_version_is_1(self, isolated_assets, editor):
        session = editor.new_from("door", "door_red")
        assert session.get_field("version") == 1

    def test_compat_is_1(self, isolated_assets, editor):
        session = editor.new_from("door", "door_red")
        assert session.get_field("compat") == 1


class TestUnknownFieldsPreserved:
    def test_unknown_fields_preserved_in_clone(self, isolated_assets, editor):
        original = editor.open("door")
        original.set_field("metadata._custom", "test_value")
        original.save()
        session = editor.new_from("door", "door_clone")
        assert session.get_field("metadata._custom") == "test_value"


class TestUniqueness:
    def test_duplicate_id_rejected(self, isolated_assets, editor):
        with pytest.raises(AssetStoreError, match="уже существует"):
            editor.new_from("door", "door")


class TestNoOverwrite:
    def test_save_does_not_overwrite_existing(self, isolated_assets, editor):
        session = editor.new_from("door", "door_new")
        session.set_field("metadata.label", "New Door")
        result = session.save()
        assert result.ok

        # Второй клон с тем же ID — new_from падает (ID уже существует)
        with pytest.raises(AssetStoreError, match="уже существует"):
            editor.new_from("door", "door_new")


class TestPathTraversal:
    def test_path_traversal_rejected(self, isolated_assets, editor):
        with pytest.raises(AssetStoreError, match="недопустим"):
            editor.new_from("door", "../evil")

    def test_slash_in_id_rejected(self, isolated_assets, editor):
        with pytest.raises(AssetStoreError, match="недопустим"):
            editor.new_from("door", "a/b")


class TestTwoDraftsSameId:
    def test_two_drafts_same_id_only_one_saves(self, isolated_assets, editor):
        session1 = editor.new_from("door", "door_dup")
        session2 = editor.new_from("door", "door_dup")
        session1.set_field("metadata.label", "First")
        result1 = session1.save()
        assert result1.ok
        session2.set_field("metadata.label", "Second")
        with pytest.raises(AssetStoreError, match="уже существует|race"):
            session2.save()


class TestCancelNoRegistration:
    def test_cancel_does_not_register(self, isolated_assets, editor):
        store = isolated_assets["store"]
        count_before = len(store.list_blueprints())
        session = editor.new_from("door", "door_cancelled")
        session.cancel()
        assert len(store.list_blueprints()) == count_before
        assert "door_cancelled" not in store.list_blueprints()


class TestSaveThroughAssetStore:
    def test_save_through_asset_store(self, isolated_assets, editor, monkeypatch):
        store = isolated_assets["store"]
        session = editor.new_from("door", "door_saved")
        session.set_field("metadata.label", "Saved Door")
        calls = []
        original = store.save_new_blueprint_atomic

        def spy(*args, **kwargs):
            calls.append(True)
            return original(*args, **kwargs)

        monkeypatch.setattr(store, "save_new_blueprint_atomic", spy)
        result = session.save()
        assert len(calls) == 1
        assert result.ok


class TestSaveFailurePreservesDraft:
    def test_save_failure_preserves_draft(self, isolated_assets, editor):
        bp_path = isolated_assets["bp_path"]
        new_path = bp_path.parent / "door_new.json"
        new_path.write_text("{}", encoding="utf-8")
        session = editor.new_from("door", "door_new")
        session.set_field("metadata.label", "Race Door")
        with pytest.raises(AssetStoreError, match="race|существует"):
            session.save()
        assert session.state in (SessionState.NEW, SessionState.OPEN)
        assert session.get_field("metadata.label") == "Race Door"


class TestReopenCreatedBlueprint:
    def test_reopen_created_blueprint(self, isolated_assets, editor):
        session = editor.new_from("door", "door_persistent")
        session.set_field("metadata.label", "Persistent Door")
        result = session.save()
        assert result.ok
        reopened = editor.open("door_persistent")
        assert reopened.get_field("metadata.label") == "Persistent Door"
        assert reopened.is_new is False
        assert reopened.state == SessionState.OPEN


class TestNoRegression:
    def test_existing_save_still_works(self, isolated_assets, editor):
        session = editor.open("door")
        session.set_field("metadata.label", "Regression Test")
        result = session.save()
        assert result.ok
        assert result.blueprint_id == "door"
        reopened = editor.open("door")
        assert reopened.get_field("metadata.label") == "Regression Test"


class TestSourceNotModified:
    def test_source_not_modified_after_clone(self, isolated_assets, editor):
        store = isolated_assets["store"]
        original_data = _deep_copy(store.get_blueprint("door").data)
        session = editor.new_from("door", "door_clone")
        session.set_field("metadata.label", "Clone Label")
        session.save()
        store.load()
        door_data = store.get_blueprint("door").data
        assert door_data["metadata"]["label"] == original_data["metadata"]["label"]
