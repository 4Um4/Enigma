"""path: /frontend/map_editor/tests/test_overrides_initial_state.py

Назначение: ME-1.10 autotests — typed overrides + initial_state validation.
    _resolve_one (data_manager.py:1117) already validates:
    - overrides: rejects unknown keys (AR-ME-2, _INSTANCE_OVERRIDE_KEYS)
    - initial_state: rejects unknown keys (computed from blueprint components)
ME-1.11 verified: destructible reserve in _initial_state_keys (->damage).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from data_manager import (  # type: ignore[import-not-found]
    _INSTANCE_OVERRIDE_KEYS,
    DataManager,
)

_CAMPAIGN_DIR = (
    Path(__file__).resolve().parents[1] / "campaigns" / "Open_road" / "locations"
)

_TEST_BLUEPRINT = {
    "blueprint_id": "test_chest",
    "version": 1,
    "compat": 1,
    "type": "decoration",
    "geometry": {"source": "primitive", "size": {"w": 2, "h": 1, "d": 1}},
    "physics": {
        "passability": {
            "walk": False,
            "jump_over": False,
            "crawl_under": False,
            "climb_on": False,
            "walk_around": True,
        },
    },
    "function": {
        "components": [
            {"type": "storage", "capacity": 10},
            {"type": "lockable", "key_ref": "key1"},
            {"type": "opener", "mechanism": "hinge", "states": ["closed", "open"]},
            {"type": "destructible", "durability": 20},
        ]
    },
}


@pytest.fixture
def dm_with_blueprint(tmp_path: Path) -> DataManager:
    """DataManager with a test blueprint in its asset store."""
    from assets.asset_store import AssetStore  # type: ignore[import-not-found]

    assets_dir = tmp_path / "assets"
    bp_dir = assets_dir / "catalogs" / "test" / "blueprints"
    bp_dir.mkdir(parents=True)
    (bp_dir / "test_chest.json").write_text(
        json.dumps(_TEST_BLUEPRINT, ensure_ascii=False), encoding="utf-8"
    )

    dm = DataManager()
    dm.set_base_dir(tmp_path)

    store = AssetStore(assets_dir, campaign_id=None)
    store.load()
    dm.set_asset_store(store)
    return dm


def test_override_keys_match_spec():
    """_INSTANCE_OVERRIDE_KEYS matches BLUEPRINT_FORMAT_SPEC 5.1."""
    expected = {
        "variant",
        "color",
        "name",
        "semantics.owner",
        "semantics.origin",
        "semantics.history",
    }
    assert _INSTANCE_OVERRIDE_KEYS == expected


def test_initial_state_keys_from_components():
    """_initial_state_keys returns correct keys from all 4 component types."""
    bp = {
        "function": {
            "components": [
                {"type": "storage"},
                {"type": "lockable"},
                {"type": "opener"},
                {"type": "destructible"},
            ]
        },
        "physics": {},
    }
    keys = DataManager._initial_state_keys(bp)
    assert keys == {"durability", "contents", "locked", "open", "damage"}


def test_initial_state_keys_empty():
    """_initial_state_keys returns only durability for empty components."""
    bp = {"function": {"components": []}, "physics": {}}
    keys = DataManager._initial_state_keys(bp)
    assert keys == {"durability"}


def test_destructible_initial_state_key():
    """ME-1.11 reserve: destructible component -> damage state key."""
    bp = {
        "function": {"components": [{"type": "destructible", "durability": 20}]},
        "physics": {},
    }
    keys = DataManager._initial_state_keys(bp)
    assert "damage" in keys


def test_valid_overrides_pass(dm_with_blueprint):
    """Valid override keys pass validation (AR-ME-2 positive)."""
    dm = dm_with_blueprint
    ref = {
        "id": "inst_0",
        "blueprint_id": "test_chest",
        "position": {"x": 5, "y": 5},
        "rotation": 0,
        "overrides": {"color": "#ff0000", "name": "Red chest"},
    }
    errors: list = []
    result = dm._resolve_one(ref, errors)
    assert result is not None, f"valid overrides should pass: {errors}"
    assert not errors


def test_unknown_override_key_rejected(dm_with_blueprint):
    """Unknown override key is rejected (AR-ME-2 negative)."""
    dm = dm_with_blueprint
    ref = {
        "id": "inst_1",
        "blueprint_id": "test_chest",
        "position": {"x": 5, "y": 5},
        "rotation": 0,
        "overrides": {"unknown_key": "value"},
    }
    errors: list = []
    result = dm._resolve_one(ref, errors)
    assert result is None, "unknown override key should be rejected"
    assert any("neizvestnyj" in e or "неизвестный" in e for e in errors)


def test_valid_initial_state_pass(dm_with_blueprint):
    """Valid initial_state keys (from blueprint components) pass."""
    dm = dm_with_blueprint
    ref = {
        "id": "inst_2",
        "blueprint_id": "test_chest",
        "position": {"x": 5, "y": 5},
        "rotation": 0,
        "initial_state": {
            "open": True,
            "locked": False,
            "contents": [],
            "durability": 10,
            "damage": 0,
        },
    }
    errors: list = []
    result = dm._resolve_one(ref, errors)
    assert result is not None, f"valid initial_state should pass: {errors}"
    assert not errors


def test_unknown_initial_state_key_rejected(dm_with_blueprint):
    """Unknown initial_state key is rejected."""
    dm = dm_with_blueprint
    ref = {
        "id": "inst_3",
        "blueprint_id": "test_chest",
        "position": {"x": 5, "y": 5},
        "rotation": 0,
        "initial_state": {"unknown_state": True},
    }
    errors: list = []
    result = dm._resolve_one(ref, errors)
    assert result is None, "unknown initial_state key should be rejected"
    assert any("ne ob" in e or "не объявлен" in e for e in errors)


def test_non_dict_overrides_rejected(dm_with_blueprint):
    """Non-dict overrides is rejected."""
    dm = dm_with_blueprint
    ref = {
        "id": "inst_4",
        "blueprint_id": "test_chest",
        "position": {"x": 5, "y": 5},
        "rotation": 0,
        "overrides": "not a dict",
    }
    errors: list = []
    result = dm._resolve_one(ref, errors)
    assert result is None
    assert any("JSON-ob" in e or "JSON-объектом" in e for e in errors)
