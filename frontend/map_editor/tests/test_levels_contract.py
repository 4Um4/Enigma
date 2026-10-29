"""path: /frontend/map_editor/tests/test_levels_contract.py

Назначение: ME-1.9 autotests — levels[] multi-level contract.
    levels[] — опциональный top-level field: массив {id, label, elevation?}.
    Сущности могут иметь поле 'level' (int, default 0).
    Если levels[] отсутствует — одноуровневая (backward compatible).
    SpatialDataLoader не меняется — editor-only до S-ME1.

Тесты:
    - test_no_levels_backward_compatible — нет levels[] → no new errors
    - test_empty_levels_valid — levels=[] → no new errors
    - test_valid_levels — valid levels with unique ids → no new errors
    - test_negative_id_valid — отрицательный id (подвал) → no new errors
    - test_duplicate_ids_error — duplicate ids → error
    - test_missing_id_error — level entry без id → error
    - test_missing_label_error — level entry без label → error
    - test_non_int_id_error — id не int → error
    - test_entity_level_not_in_levels — entity level не из levels[] → error
    - test_round_trip_preserves_levels — load->save->reload: levels[] preserved
    - test_round_trip_preserves_entity_level — level field preserved
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from data_manager import DataManager  # type: ignore[import-not-found]
from schema_validator import validate_location  # type: ignore[import-not-found]

_CAMPAIGN_DIR = (
    Path(__file__).resolve().parents[1] / "campaigns" / "Open_road" / "locations"
)


@pytest.fixture
def golden_location(tmp_path: Path) -> tuple[Path, dict, str]:
    fname = "tavern.json"
    src = _CAMPAIGN_DIR / fname
    dst = tmp_path / fname
    shutil.copy2(src, dst)
    data = json.loads(dst.read_text(encoding="utf-8-sig"))
    return dst, data, fname


def _levels_errors(data: dict) -> list[str]:
    """Return only levels-related validation errors."""
    return [e for e in validate_location(data, "test") if "level" in e.lower()]


def test_no_levels_backward_compatible(golden_location):
    """Нет levels[] → no levels-related errors (backward compatible)."""
    _, data, _ = golden_location
    assert not _levels_errors(data), f"unexpected levels errors: {_levels_errors(data)}"


def test_empty_levels_valid(golden_location):
    """levels=[] → no new levels errors."""
    _, data, _ = golden_location
    data["levels"] = []
    assert not _levels_errors(data), f"empty levels[] should be valid: {_levels_errors(data)}"


def test_valid_levels(golden_location):
    """Valid levels with unique ids + labels → no new errors."""
    _, data, _ = golden_location
    data["levels"] = [
        {"id": 0, "label": "первый этаж"},
        {"id": -1, "label": "подвал", "elevation": -3.0},
    ]
    assert not _levels_errors(data), f"valid levels should pass: {_levels_errors(data)}"


def test_negative_id_valid(golden_location):
    """Отрицательный id (подвал) → no new errors."""
    _, data, _ = golden_location
    data["levels"] = [{"id": -1, "label": "подвал"}]
    assert not _levels_errors(data), f"negative id should be valid: {_levels_errors(data)}"


def test_duplicate_ids_error(golden_location):
    """Duplicate level ids → error."""
    _, data, _ = golden_location
    data["levels"] = [{"id": 0, "label": "a"}, {"id": 0, "label": "b"}]
    errors = _levels_errors(data)
    assert any("дублирующийся" in e for e in errors), f"expected duplicate id error: {errors}"


def test_missing_id_error(golden_location):
    """Level entry без id → error."""
    _, data, _ = golden_location
    data["levels"] = [{"label": "без id"}]
    errors = _levels_errors(data)
    assert any("поле 'id'" in e for e in errors), f"expected missing id error: {errors}"


def test_missing_label_error(golden_location):
    """Level entry без label → error."""
    _, data, _ = golden_location
    data["levels"] = [{"id": 0}]
    errors = _levels_errors(data)
    assert any("поле 'label'" in e for e in errors), f"expected missing label error: {errors}"


def test_non_int_id_error(golden_location):
    """id не int → error."""
    _, data, _ = golden_location
    data["levels"] = [{"id": "ground", "label": "str id"}]
    errors = _levels_errors(data)
    assert any("поле 'id'" in e and "целое" in e for e in errors), f"expected non-int id error: {errors}"


def test_entity_level_not_in_levels(golden_location):
    """Entity level не из levels[] → error."""
    _, data, _ = golden_location
    data["levels"] = [{"id": 0, "label": "первый"}]
    if data.get("objects"):
        data["objects"][0]["level"] = 99
    errors = _levels_errors(data)
    assert any("level=99" in e and "не найден" in e for e in errors), f"expected invalid level error: {errors}"


def test_round_trip_preserves_levels(tmp_path: Path):
    """load->save->reload: levels[] preserved."""
    fname = "tavern.json"
    src = _CAMPAIGN_DIR / fname
    dst = tmp_path / fname
    shutil.copy2(src, dst)

    data = json.loads(dst.read_text(encoding="utf-8-sig"))
    data["levels"] = [
        {"id": 0, "label": "первый этаж"},
        {"id": -1, "label": "подвал", "elevation": -3.0},
    ]
    data["active_level"] = 0
    dst.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    dm = DataManager()
    dm.set_base_dir(tmp_path)
    assert dm.save(fname), "save failed"

    saved = json.loads(dst.read_text(encoding="utf-8-sig"))
    assert saved.get("levels") == data["levels"], "levels[] lost after round-trip"
    assert saved.get("active_level") == 0, "active_level lost after round-trip"


def test_round_trip_preserves_entity_level(tmp_path: Path):
    """load->save->reload: level field on entities preserved."""
    fname = "tavern.json"
    src = _CAMPAIGN_DIR / fname
    dst = tmp_path / fname
    shutil.copy2(src, dst)

    data = json.loads(dst.read_text(encoding="utf-8-sig"))
    data["levels"] = [{"id": 0, "label": "первый"}, {"id": -1, "label": "подвал"}]
    if data.get("objects"):
        data["objects"][0]["level"] = -1
    dst.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    dm = DataManager()
    dm.set_base_dir(tmp_path)
    assert dm.save(fname), "save failed"

    saved = json.loads(dst.read_text(encoding="utf-8-sig"))
    saved_objs = {o["id"]: o for o in saved.get("objects", []) if isinstance(o, dict) and "id" in o}
    first_id = data["objects"][0]["id"] if data.get("objects") else None
    if first_id and first_id in saved_objs:
        assert saved_objs[first_id].get("level") == -1, "level field lost after round-trip"
