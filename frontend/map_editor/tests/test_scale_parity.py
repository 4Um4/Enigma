"""path: /frontend/map_editor/tests/test_scale_parity.py

Назначение: Обязательный автотест соответствия линейных масштабов
    редактор↔игра (вердикт Мастера 2026-10-12; ME-1.4). Игра читает
    editor-JSON напрямую (world_context.SpatialDataLoader) — тест
    доказывает на каждой живой локации, что линейные величины файла
    переходят в игровую геометрию один-в-один, без скрытых умножений.
    Экранные пиксельные масштабы (SCALE 40/20) здесь ни при чём:
    это экран, а не данные (ME-D2 — отдельный SCALE-аудит, в.22).
Проверки: (1) global_coords=True на диске — игра доверяет флагу и
    пересчётом не занимается; (2) площадь пола — точное равенство с
    origin+size файла; (3) каждому игровому препятствию — объект файла
    с ТОЧНО теми же размерами и позицией по единственной разрешённой
    формуле «центр → левый верх». Стены (игра режет их проёмами, но не
    растягивает) — v1.1, после чтения _split_wall_by_openings.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import world_context

_CAMPAIGN = "Open_road"
_LOC_DIR = Path(__file__).resolve().parents[1] / "campaigns" / _CAMPAIGN / "locations"


def _locations() -> list[tuple[str, dict]]:
    files = sorted(_LOC_DIR.glob("*.json"))
    assert files, f"живые локации не найдены: {_LOC_DIR}"
    return [
        (path.name, json.loads(path.read_text(encoding="utf-8-sig")))
        for path in files
    ]


_LOCATIONS = _locations()
_IDS = [name for name, _ in _LOCATIONS]


def _build(name: str, data: dict):
    return world_context.SpatialDataLoader._build_spatial_data(
        data.get("location_id", name), data
    )


@pytest.mark.parametrize("name,data", _LOCATIONS, ids=_IDS)
def test_global_coords_on_disk(name: str, data: dict) -> None:
    """Флаг миграции обязан стоять: игра пересчётом не занимается."""
    assert data.get("global_coords") is True, (
        f"{name}: global_coords не True — игра прочтёт координаты как "
        f"мировые без пересчёта (ME-D10)"
    )


@pytest.mark.parametrize("name,data", _LOCATIONS, ids=_IDS)
def test_floor_rect_exact(name: str, data: dict) -> None:
    """Пол: игровая площадь == origin + size из файла, точное равенство."""
    spatial = _build(name, data)
    expected = (
        float(data["origin"]["x"]),
        float(data["origin"]["y"]),
        float(data["size"]["w"]),
        float(data["size"]["h"]),
    )
    assert spatial.floor_rect == expected


@pytest.mark.parametrize("name,data", _LOCATIONS, ids=_IDS)
def test_obstacles_exact_sizes(name: str, data: dict) -> None:
    """Препятствия: каждому — объект файла; размеры и позиция точные.

    Позиция: центр → левый верх (x − w/2) — единственное разрешённое
    преобразование; скрытое масштабирование размеров поймано точным
    сравнением.
    """
    spatial = _build(name, data)
    by_id = {
        obj["id"]: obj
        for obj in data["objects"]
        if isinstance(obj, dict) and "id" in obj
    }
    assert len(spatial.obstacles) == len(data["objects"])
    for ob in spatial.obstacles:
        src = by_id[ob["id"]]
        w = float(src["size"]["w"])
        h = float(src["size"]["h"])
        assert ob["w"] == w, f"{name}/{ob['id']}: w {ob['w']} != файл {w}"
        assert ob["h"] == h, f"{name}/{ob['id']}: h {ob['h']} != файл {h}"
        assert ob["x"] == float(src["position"]["x"]) - w / 2
        assert ob["y"] == float(src["position"]["y"]) - h / 2
