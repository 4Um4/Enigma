"""path: /frontend/map_editor/tests/test_me15_normalization.py

Назначение: Обязательные автотесты ME-1.5 — единая форма хранения wall_id
    (root, без дубликата в properties.wall_id и без rotation-хака S129) и
    полное отсутствие легаси-ключа `portals` после save. Игра читает
    editor-JSON напрямую (world_context.SpatialDataLoader), поэтому любая
    миграция данных обязана доказать round-trip: load→save→load не теряет
    wall_id и не воскрешает `portals`.
Зависимости: pytest, data_manager.DataManager, _PASSAGE_TYPES (модульная
    константа), реальные файлы кампании Open_road (фикстура campaigns/).
Основные сущности:
    - test_add_passage_writes_wall_id_root_only — passage: wall_id в root,
      дубликат в properties отсутствует, rotation != wall_id (S129 снят).
    - test_add_object_with_wall_id_writes_root_only — add_object(c wall_id):
      wall_id только в root.
    - test_save_drops_portals_key — save(...) не пишет `portals` в файл.
    - test_round_trip_preserves_wall_id_root — load→save→load: wall_id
      выживает в одной форме (root).
    - test_migrated_campaign_locations_have_no_portals — все живые локации
      Open_road после ME-1.5 не содержат ключ `portals`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Tuple

import pytest
from data_manager import DataManager  # type: ignore[import-not-found]

_CAMPAIGN = "Open_road"
_CAMPAIGN_DIR = (
    Path(__file__).resolve().parents[1] / "campaigns" / _CAMPAIGN / "locations"
)


@pytest.fixture
def isolated_dm(tmp_path: Path) -> Tuple[DataManager, str]:
    """Изолированный DataManager на tmp_path + имя тестовой локации.

    set_base_dir переключает склад и рабочую директорию; load_all() на пустой
    папке даёт чистый словарь locations — тест не зависит от глобальных
    шаблонов и не пишет в них.
    """
    dm = DataManager()
    dm.set_base_dir(tmp_path)
    fname = "me15_test.json"
    ok, err = dm.create_location(fname, width=20, height=15)
    assert ok, f"create_location упал: {err}"
    return dm, fname


def _passage_objects(loc: dict) -> list[dict]:
    """Только passage-объекты (двери/окна/переходы) — те, что несут wall_id."""
    from data_manager import _PASSAGE_TYPES  # type: ignore[import-not-found]

    return [o for o in loc["objects"] if o.get("type") in _PASSAGE_TYPES]


def test_add_passage_writes_wall_id_root_only(isolated_dm):
    """add_passage: wall_id в root, без дубликата в properties, без S129-хака."""
    dm, fname = isolated_dm
    wall_id = dm.add_wall(fname, 0.0, 0.0, 5.0, 0.0)
    pos = {"x": 2.5, "y": 0.0}
    dm.add_passage(fname, wall_id=wall_id, passage_type="door", position=pos)

    passages = _passage_objects(dm.locations[fname])
    assert passages, "passage должен попасть в objects"
    obj = passages[-1]

    # ME-1.5 контракт: wall_id в root
    assert obj.get("wall_id") == wall_id, (
        f"wall_id должен быть в root, а не {obj.get('wall_id')!r}"
    )
    # ME-1.5 контракт: дубликат в properties отсутствует
    props = obj.get("properties") or {}
    assert "wall_id" not in props, (
        f"properties.wall_id должен быть удалён, а не {props.get('wall_id')!r}"
    )
    # ME-1.5 контракт: rotation больше не несёт wall_id (S129 снят)
    assert obj.get("rotation") != wall_id, (
        f"rotation не должен дублировать wall_id (S129 снят), "
        f"получено rotation={obj.get('rotation')!r}"
    )


def test_add_object_with_wall_id_writes_root_only(isolated_dm):
    """add_object(c wall_id): wall_id в root, без дубликата в properties."""
    dm, fname = isolated_dm
    wall_id = dm.add_wall(fname, 0.0, 0.0, 5.0, 0.0)
    dm.add_object(fname, "door", 2.5, 0.0, wall_id=wall_id)

    passages = _passage_objects(dm.locations[fname])
    assert passages, "door-объект должен попасть в objects"
    obj = passages[-1]

    assert obj.get("wall_id") == wall_id, "wall_id должен быть в root"
    props = obj.get("properties") or {}
    assert "wall_id" not in props, (
        f"properties.wall_id не должен дублироваться, получено {props.get('wall_id')!r}"
    )


def test_save_drops_portals_key(isolated_dm, tmp_path):
    """save(...) не пишет легаси-ключ `portals` в файл."""
    dm, fname = isolated_dm
    wall_id = dm.add_wall(fname, 0.0, 0.0, 5.0, 0.0)
    dm.add_passage(
        fname, wall_id=wall_id, passage_type="door", position={"x": 2.5, "y": 0.0}
    )

    ok = dm.save(fname)
    assert ok, "save должен вернуть True"

    saved_path = tmp_path / fname
    assert saved_path.exists(), f"файл {saved_path} должен существовать после save"
    saved = json.loads(saved_path.read_text(encoding="utf-8"))

    assert "portals" not in saved, (
        "ME-1.5: ключ `portals` не должен присутствовать в сохранённом файле"
    )


def test_round_trip_preserves_wall_id_root(isolated_dm, tmp_path):
    """load→save→load: wall_id выживает в одной форме (root)."""
    dm, fname = isolated_dm
    wall_id = dm.add_wall(fname, 0.0, 0.0, 5.0, 0.0)
    dm.add_passage(
        fname, wall_id=wall_id, passage_type="door", position={"x": 2.5, "y": 0.0}
    )
    assert dm.save(fname), "save должен вернуть True"

    # Новый менеджер на ту же папку — симулирует холодный старт редактора
    dm2 = DataManager()
    dm2.set_base_dir(tmp_path)
    loc2 = dm2.locations[fname]
    passages = _passage_objects(loc2)
    assert passages, "после round-trip passage должен присутствовать"

    obj = passages[-1]
    assert obj.get("wall_id") == wall_id, (
        f"wall_id потерян после round-trip: {obj.get('wall_id')!r} != {wall_id!r}"
    )
    props = obj.get("properties") or {}
    assert "wall_id" not in props, (
        "после round-trip properties.wall_id не должен воскрешаться"
    )
    assert "portals" not in loc2, "после round-trip ключ `portals` не должен появляться"


def test_migrated_campaign_locations_have_no_portals():
    """Все живые локации Open_road после ME-1.5 не содержат `portals`."""
    assert _CAMPAIGN_DIR.exists(), f"каталог кампании не найден: {_CAMPAIGN_DIR}"
    files = sorted(_CAMPAIGN_DIR.glob("*.json"))
    assert files, f"локации кампании не найдены: {_CAMPAIGN_DIR}"

    offenders: list[str] = []
    for path in files:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        if "portals" in data:
            offenders.append(path.name)
    assert not offenders, (
        f"ME-1.5: локации всё ещё содержат легаси `portals`: {offenders}"
    )
