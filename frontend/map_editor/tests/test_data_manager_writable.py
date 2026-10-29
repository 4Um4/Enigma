"""path: /frontend/map_editor/tests/test_data_manager_writable.py

Назначение: ME-1.7 autotests — DataManager._writable flag invariants.
    ME-1.6 сделал location_templates/ read-only starter library: save,
    save_all, delete_location, create_location fail-loud when _writable=False.
    Тесты доказывают: (1) default (templates) read-only; (2) campaign writable;
    (3) tmp_path writable (tests can write); (4) save/delete/create blocked on
    templates; (5) save/create work on tmp_path.
Зависимости: pytest, data_manager.DataManager, tmp_path fixture.
Основные сущности:
    - test_default_writable_false — DataManager() default: _writable=False
    - test_set_base_dir_campaign_writable_true — campaigns/<id>/locations: True
    - test_set_base_dir_templates_writable_false — TEMPLATE_DIR: False
    - test_set_base_dir_tmp_path_writable_true — tmp_path: True (tests can write)
    - test_save_blocked_on_templates — save() returns False on templates
    - test_save_all_blocked_on_templates — save_all() doesn't modify template files
    - test_delete_location_blocked_on_templates — delete_location() returns False
    - test_create_location_blocked_on_templates — create_location() returns (False, msg)
    - test_save_works_on_tmp_path — save() returns True on tmp_path
    - test_create_location_works_on_tmp_path — create_location() works on tmp_path
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from data_manager import DataManager  # type: ignore[import-not-found]

_TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "location_templates"
_CAMPAIGN_DIR = (
    Path(__file__).resolve().parents[1] / "campaigns" / "Open_road" / "locations"
)


def test_default_writable_false():
    """DataManager() default: base_dir=TEMPLATE_DIR, _writable=False."""
    dm = DataManager()
    assert dm._writable is False, "default (templates) should be read-only"


def test_set_base_dir_campaign_writable_true():
    """set_base_dir(campaigns/<id>/locations): _writable=True."""
    dm = DataManager()
    dm.set_base_dir(_CAMPAIGN_DIR)
    assert dm._writable is True, "campaign should be writable"


def test_set_base_dir_templates_writable_false():
    """set_base_dir(TEMPLATE_DIR): _writable=False (read-only)."""
    dm = DataManager()
    dm.set_base_dir(_CAMPAIGN_DIR)
    dm.set_base_dir(_TEMPLATES_DIR)
    assert dm._writable is False, "templates should be read-only after switch-back"


def test_set_base_dir_tmp_path_writable_true(tmp_path: Path):
    """set_base_dir(tmp_path): _writable=True (tests can write to temp dirs)."""
    dm = DataManager()
    dm.set_base_dir(tmp_path)
    assert dm._writable is True, "tmp_path should be writable (not templates)"


def test_save_blocked_on_templates():
    """save() on templates returns False (read-only)."""
    dm = DataManager()
    result = dm.save("tavern.json")
    assert result is False, "save should be blocked on templates"


def test_save_all_blocked_on_templates():
    """save_all() on templates returns early — no template files modified."""
    dm = DataManager()
    before = {
        f.name: hashlib.md5(f.read_bytes()).hexdigest()
        for f in _TEMPLATES_DIR.glob("*.json")
    }
    dm.save_all()
    after = {
        f.name: hashlib.md5(f.read_bytes()).hexdigest()
        for f in _TEMPLATES_DIR.glob("*.json")
    }
    assert before == after, "save_all modified template files (should be blocked)"


def test_delete_location_blocked_on_templates():
    """delete_location() on templates returns False (read-only)."""
    dm = DataManager()
    result = dm.delete_location("tavern.json")
    assert result is False, "delete should be blocked on templates"


def test_create_location_blocked_on_templates():
    """create_location() on templates returns (False, error_msg)."""
    dm = DataManager()
    ok, err = dm.create_location("test_me16.json", width=10, height=10)
    assert ok is False, "create_location should be blocked on templates"
    assert "read-only" in err.lower() or "starter templates" in err.lower(), (
        f"error should mention read-only/starter templates, got: {err}"
    )


def test_save_works_on_tmp_path(tmp_path: Path):
    """save() on tmp_path returns True (writable)."""
    dm = DataManager()
    dm.set_base_dir(tmp_path)
    ok, err = dm.create_location("test.json", width=10, height=10)
    assert ok, f"create_location failed: {err}"
    result = dm.save("test.json")
    assert result is True, "save should succeed on tmp_path"
    assert (tmp_path / "test.json").exists(), "file should exist after save"


def test_create_location_works_on_tmp_path(tmp_path: Path):
    """create_location() on tmp_path succeeds (writable)."""
    dm = DataManager()
    dm.set_base_dir(tmp_path)
    ok, err = dm.create_location("new_loc.json", width=20, height=15)
    assert ok, f"create_location should succeed on tmp_path: {err}"
    assert "new_loc.json" in dm.locations
