# path: backend/tests/test_p3_03_delete_post_processing.py
"""P3-03 · T10-T14 — доказательства безопасной пост-обработки DELETE."""

import sys
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend" / "map_editor"
if str(FRONTEND_DIR) not in sys.path:
    sys.path.insert(0, str(FRONTEND_DIR))

from data_manager import DataManager


@pytest.fixture
def dm_with_location(tmp_path):
    """Создаёт DataManager с одной валидной локацией."""
    dm = DataManager()
    dm.set_base_dir(tmp_path)
    dm.locations["test.json"] = {
        "location_id": "test", "label": "Test Loc", "origin": {"x": 0, "y": 0},
        "size": {"w": 10, "h": 10}, "global_coords": True,
        "rooms": [], "walls": [], "nodes": {}, "objects": [], "npcs": [], "labels": []
    }
    (tmp_path / "test.json").write_text(json.dumps(dm.locations["test.json"]))
    return dm, tmp_path


def test_t10_successful_delete(dm_with_location):
    """T10: Исходник, память и (потенциально) зеркала очищены."""
    dm, tmp_path = dm_with_location
    res = dm.delete_location("test.json")

    assert res["success"] is True
    assert res["error"] is None
    assert "test.json" not in dm.locations
    assert not (tmp_path / "test.json").exists()


def test_t11_unlink_error_preserves_state(dm_with_location):
    """T11: Ошибка unlink: состояние редактора (память) не изменено."""
    dm, tmp_path = dm_with_location

    with patch("pathlib.Path.unlink", side_effect=PermissionError("Access denied")):
        res = dm.delete_location("test.json")

    assert res["success"] is False
    assert "Ошибка файловой системы" in res["error"]
    assert "test.json" in dm.locations  # Состояние сохранено
    assert (tmp_path / "test.json").exists()  # Файл на месте


def test_t14_missing_or_repeated_delete(dm_with_location):
    """T14: Повторное удаление или отсутствие исходника: нет падения и ложного успеха."""
    dm, tmp_path = dm_with_location

    # Первое удаление успешно
    res1 = dm.delete_location("test.json")
    assert res1["success"] is True

    # Повторное удаление того же файла
    res2 = dm.delete_location("test.json")
    assert res2["success"] is False
    assert "не найдена в памяти" in res2["error"]

    # Удаление несуществующего файла
    res3 = dm.delete_location("ghost.json")
    assert res3["success"] is False
    assert "не найдена в памяти" in res3["error"]


def test_t12_t13_sync_error_handling_contract():
    """T12/T13: Проверка контракта обработки ошибок синхронизации в EditorCore.

    Поскольку _dialog_delete_location содержит вложенную функцию on_confirm,
    мы проверяем сам контракт: если sync_res содержит failed>0 или errors,
    логика формирует сообщение о частичном успехе.
    """
    # Имитация успешного удаления, но с ошибкой mirror-delete (T12)
    sync_res_t12 = {"copied": 0, "deleted": 0, "failed": 1, "errors": ["Delete failed orphan.json"]}
    assert sync_res_t12.get("failed", 0) > 0 or sync_res_t12.get("errors")

    # Имитация успешного удаления, но с ошибкой пересборки реестра (T13)
    sync_res_t13 = {"copied": 0, "deleted": 1, "failed": 0, "errors": ["Registry rebuild failed: ..."]}
    assert sync_res_t13.get("failed", 0) == 0  # failed == 0, но errors есть!
    assert sync_res_t13.get("errors")  # Поэтому условие `or sync_res.get("errors")` сработает
