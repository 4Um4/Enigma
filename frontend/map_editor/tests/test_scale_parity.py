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
    растягивает) — включено: test_walls_split_not_stretched (сегменты лежат
    на линиях исходных стен, суммарная длина не растёт).
"""

from __future__ import annotations

import json
import math
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


def _on_segment(
    px: float,
    py: float,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    eps: float = 1e-6,
) -> bool:
    """Точка лежит на отрезке (коллинеарна и внутри), допуск на арифметику."""
    dx, dy = x2 - x1, y2 - y1
    length = math.hypot(dx, dy)
    if length < eps:
        return math.hypot(px - x1, py - y1) <= eps
    cross = abs((px - x1) * dy - (py - y1) * dx) / length
    if cross > eps:
        return False
    t = ((px - x1) * dx + (py - y1) * dy) / (length * length)
    return -eps <= t <= 1.0 + eps


@pytest.mark.parametrize("name,data", _LOCATIONS, ids=_IDS)
def test_walls_split_not_stretched(name: str, data: dict) -> None:
    """Стены: игра режет проёмы, но не растягивает и не сдвигает.

    Каждый игровой сегмент обязан лежать на линии какой-то исходной стены
    файла; суммарная длина сегментов не превышает суммарную длину стен
    файла. Скрытый множитель длины ломает оба условия с адресом.
    """
    spatial = _build(name, data)
    file_walls = [
        (
            float(w["x1"]),
            float(w["y1"]),
            float(w["x2"]),
            float(w["y2"]),
        )
        for w in data["walls"]
    ]
    if not file_walls:
        assert not spatial.walls
        return
    total_file = sum(
        math.hypot(x2 - x1, y2 - y1) for x1, y1, x2, y2 in file_walls
    )
    total_game = sum(
        math.hypot(s["x2"] - s["x1"], s["y2"] - s["y1"]) for s in spatial.walls
    )
    assert total_game <= total_file + 1e-6, (
        f"{name}: суммарная длина стен в игре ({total_game:.3f}) больше "
        f"файла ({total_file:.3f}) — скрытое растяжение"
    )
    for seg in spatial.walls:
        ok = any(
            _on_segment(seg["x1"], seg["y1"], *w)
            and _on_segment(seg["x2"], seg["y2"], *w)
            for w in file_walls
        )
        assert ok, f"{name}: сегмент {seg} не лежит ни на одной стене файла"
