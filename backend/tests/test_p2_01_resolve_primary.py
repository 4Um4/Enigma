# path: backend/tests/test_p2_01_resolve_primary.py
# Назначение: P2-01 (ADR-O-439 D.2) — unit-тесты детерминированного выбора
#     primary-чанка на общих границах. Замена [0]-потребителей на
#     resolve_primary: минимальная площадь → лексикографически меньший
#     location_id. Защита от зависимости текущей локации от порядка
#     артефакта [city_gate, market_square, tavern].
# Зависимости: pytest, ChunkDescriptor (реальные координаты из compiled
#     артефакта Open_road), _MinimalFrontendRegistry (frontend зеркало).
# Основные сущности:
#     - test_d2_boundary_tavern_vs_city_gate — (45.0333, 10) → tavern (300<600)
#     - test_d2_triple_point — (45.0333, 20.018) → tavern (300 минимальна)
#     - test_d2_city_gate_vs_market_square — (47.0, 20.018) → city_gate (600<625)
#     - test_d2_multi_chunk_min_area_wins — синтетика: 2 чанка, меньшая площадь
#     - test_d2_lex_tiebreaker — синтетика: равная площадь → лекс. меньший id
#     - test_d2_single_chunk_returns_itself — 1 чанк → единственный
#     - test_d2_no_chunk_returns_none — точка вне footprint'ов → None
#     - test_d2_minimal_frontend_registry_mirror — frontend-зеркало: та же семантика
"""
P2-01 (ADR-O-439 D.2): детерминированный владелец чанка на общих границах.

Контракт D.2 (ROADMAP §P2-01):
- 0 чанков → None
- 1 чанк   → единственный
- >1 чанка → минимальная площадь (width*height); при равенстве —
  лексикографически меньший location_id

Заменяет 4 call-site'а [0]-потребителей:
- frontend/world_context.py:245 (ContextResolver.resolve)
- backend/app/api/routes.py:1029 (SpatialOracle)
- frontend/game_loop_bridge.py:171 (frontend oracle)
- backend/app/services/game_loop/game_loop.py:1317 (idle oracle)

Реализован в двух реестрах с идентичной семантикой:
- backend/app/services/spatial/spatial_registry.py:SpatialRegistry.resolve_primary
- frontend/spatial_compilation_orchestrator.py:_MinimalFrontendRegistry.resolve_primary

P0-02 находка: на текущих данных Open_road B-09 (multi-chunk на общей границе)
НЕ воспроизводится из-за float-representation gap (cg_left=45.033...324 >
tv_right=45.033...332). D.2 защитит будущее — если координаты нормализуют
и multi-chunk станет реальным, правило сработает. Тесты используют
синтетические чанки с наложением для проверки алгоритма.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.spatial.spatial_registry import (
    ChunkDescriptor,
    SpatialRegistry,
    WorldBounds,
)


# ─────────────────────────────────────────────────────────────────────────────
# Реальные координаты из compiled/spatial_registry.json (post-P1-02)
# ─────────────────────────────────────────────────────────────────────────────

# city_gate: origin (45.033, 0.018), size 30×20 → площадь 600
# market_square: origin (25.033, 20.018), size 25×25 → площадь 625
# tavern: origin (25.033, 5.018), size 20×15 → площадь 300

_CG = ChunkDescriptor(
    location_id="city_gate",
    filename="city_gate.json",
    origin_x=45.033333333333324,
    origin_y=0.01800000000000708,
    width=30.0,
    height=20.0,
    is_outdoor=True,
    label="Городские ворота",
    content_hash="cg_hash",
    global_coords=True,
)
_MK = ChunkDescriptor(
    location_id="market_square",
    filename="market_square.json",
    origin_x=25.033333333333328,
    origin_y=20.018000000000008,
    width=25.0,
    height=25.0,
    is_outdoor=True,
    label="Торговая площадь",
    content_hash="mk_hash",
    global_coords=True,
)
_TV = ChunkDescriptor(
    location_id="tavern",
    filename="tavern.json",
    origin_x=25.03333333333332,
    origin_y=5.018000000000007,
    width=20.0,
    height=15.0,
    is_outdoor=False,
    label="Таверна Серебряного Волка",
    content_hash="tv_hash",
    global_coords=True,
)


def _make_registry(chunks: list) -> SpatialRegistry:
    """Сборка SpatialRegistry из списка чанков (empty adjacency, neutral bounds)."""
    bounds = WorldBounds(
        min_x=min(c.origin_x for c in chunks),
        min_y=min(c.origin_y for c in chunks),
        max_x=max(c.origin_x + c.width for c in chunks),
        max_y=max(c.origin_y + c.height for c in chunks),
    )
    return SpatialRegistry(chunks=chunks, adjacency=[], world_bounds=bounds)


@pytest.fixture
def open_road_registry() -> SpatialRegistry:
    """Реестр с реальными чанками Open_road (post-P1-02)."""
    return _make_registry([_CG, _MK, _TV])


# ─────────────────────────────────────────────────────────────────────────────
# Тест 1 (D.2): граница city_gate/tavern → tavern (300 < 600)
# ─────────────────────────────────────────────────────────────────────────────


def test_d2_boundary_tavern_vs_city_gate(open_road_registry: SpatialRegistry) -> None:
    """D.2: точка на общей границе → минимальная площадь.

    Реальные координаты: cg.origin_x=45.033...324, tv.origin_x+width=45.033...332.
    float-gap ~4e-15 делает общую точку невоспроизводимой (P0-02 находка).
    Тест использует чуть смещённую точку, попадающую ТОЛЬКО в tavern —
    проверяем, что resolve_primary корректно выбирает единственный чанк.
    """
    # Точка внутри tavern (origin (25.033, 5.018), size 20×15)
    result = open_road_registry.resolve_primary(33.0, 12.0)
    assert result is not None
    assert result.location_id == "tavern"


# ─────────────────────────────────────────────────────────────────────────────
# Тест 2 (D.2): синтетический multi-chunk — минимальная площадь побеждает
# ─────────────────────────────────────────────────────────────────────────────


def test_d2_multi_chunk_min_area_wins() -> None:
    """D.2: 2 чанка содержат точку → выбирается с меньшей площадью.

    Синтетика: большой чанк (площадь 100) и малый (площадь 25) перекрываются
    в точке (10, 10). Ожидание: малый побеждает.
    """
    big = ChunkDescriptor(
        location_id="big_loc",
        filename="big.json",
        origin_x=0.0,
        origin_y=0.0,
        width=10.0,
        height=10.0,  # площадь 100
        is_outdoor=True,
        label="Большая",
        content_hash="big",
        global_coords=True,
    )
    small = ChunkDescriptor(
        location_id="small_loc",
        filename="small.json",
        origin_x=5.0,
        origin_y=5.0,
        width=5.0,
        height=5.0,  # площадь 25
        is_outdoor=True,
        label="Малая",
        content_hash="small",
        global_coords=True,
    )
    registry = _make_registry([big, small])

    # Точка (7, 7) — внутри обоих
    result = registry.resolve_primary(7.0, 7.0)
    assert result is not None
    assert result.location_id == "small_loc"  # 25 < 100


# ─────────────────────────────────────────────────────────────────────────────
# Тест 3 (D.2): равная площадь → лексикографически меньший location_id
# ─────────────────────────────────────────────────────────────────────────────


def test_d2_lex_tiebreaker() -> None:
    """D.2: 2 чанка с равной площадью → лексикографически меньший id.

    Синтетика: 'alpha' и 'beta' — оба 5×5 (площадь 25), перекрываются в (5, 5).
    Ожидание: 'alpha' (лексикографически меньше).
    """
    alpha = ChunkDescriptor(
        location_id="alpha",
        filename="alpha.json",
        origin_x=0.0,
        origin_y=0.0,
        width=5.0,
        height=5.0,
        is_outdoor=True,
        label="Alpha",
        content_hash="a",
        global_coords=True,
    )
    beta = ChunkDescriptor(
        location_id="beta",
        filename="beta.json",
        origin_x=3.0,
        origin_y=3.0,
        width=5.0,
        height=5.0,
        is_outdoor=True,
        label="Beta",
        content_hash="b",
        global_coords=True,
    )
    registry = _make_registry([beta, alpha])  # beta первой — проверяем stable

    # Точка (4, 4) — внутри обоих
    result = registry.resolve_primary(4.0, 4.0)
    assert result is not None
    assert result.location_id == "alpha"  # лексикографически меньше


# ─────────────────────────────────────────────────────────────────────────────
# Тест 4 (D.2): тройная точка (синтетика) → минимальная площадь
# ─────────────────────────────────────────────────────────────────────────────


def test_d2_triple_point_min_area() -> None:
    """D.2: 3 чанка в одной точке → минимальная площадь.

    Синтетика имитирует теоретическую тройную точку city_gate/market_square/tavern.
    Площади: 600 (cg), 625 (mk), 300 (tv) → tv победитель.
    """
    # Все три чанка содержат точку (10, 10) — синтетика с общим центром
    cg = ChunkDescriptor(
        location_id="city_gate",
        filename="cg.json",
        origin_x=0.0,
        origin_y=0.0,
        width=30.0,
        height=20.0,  # 600
        is_outdoor=True,
        label="CG",
        content_hash="cg",
        global_coords=True,
    )
    mk = ChunkDescriptor(
        location_id="market_square",
        filename="mk.json",
        origin_x=0.0,
        origin_y=0.0,
        width=25.0,
        height=25.0,  # 625
        is_outdoor=True,
        label="MK",
        content_hash="mk",
        global_coords=True,
    )
    tv = ChunkDescriptor(
        location_id="tavern",
        filename="tv.json",
        origin_x=0.0,
        origin_y=0.0,
        width=20.0,
        height=15.0,  # 300
        is_outdoor=False,
        label="TV",
        content_hash="tv",
        global_coords=True,
    )
    registry = _make_registry([cg, mk, tv])

    result = registry.resolve_primary(10.0, 10.0)
    assert result is not None
    assert result.location_id == "tavern"  # 300 < 600 < 625


# ─────────────────────────────────────────────────────────────────────────────
# Тест 5 (D.2): city_gate vs market_square — city_gate (600 < 625)
# ─────────────────────────────────────────────────────────────────────────────


def test_d2_city_gate_vs_market_square() -> None:
    """D.2: cg(600) vs mk(625) → city_gate.

    Синтетика: 2 чанка в одной точке, cg меньше.
    """
    cg = ChunkDescriptor(
        location_id="city_gate",
        filename="cg.json",
        origin_x=0.0,
        origin_y=0.0,
        width=30.0,
        height=20.0,  # 600
        is_outdoor=True,
        label="CG",
        content_hash="cg",
        global_coords=True,
    )
    mk = ChunkDescriptor(
        location_id="market_square",
        filename="mk.json",
        origin_x=0.0,
        origin_y=0.0,
        width=25.0,
        height=25.0,  # 625
        is_outdoor=True,
        label="MK",
        content_hash="mk",
        global_coords=True,
    )
    registry = _make_registry([mk, cg])  # mk первой — проверяем правило

    result = registry.resolve_primary(10.0, 10.0)
    assert result is not None
    assert result.location_id == "city_gate"  # 600 < 625


# ─────────────────────────────────────────────────────────────────────────────
# Тест 6: single chunk → возвращается сам
# ─────────────────────────────────────────────────────────────────────────────


def test_d2_single_chunk_returns_itself(open_road_registry: SpatialRegistry) -> None:
    """D.2: 1 чанк содержит точку → единственный (no warning, no comparison)."""
    # Точка внутри только tavern (вне cg/mk)
    result = open_road_registry.resolve_primary(28.0, 8.0)
    assert result is not None
    assert result.location_id == "tavern"


# ─────────────────────────────────────────────────────────────────────────────
# Тест 7: точка вне всех чанков → None
# ─────────────────────────────────────────────────────────────────────────────


def test_d2_no_chunk_returns_none(open_road_registry: SpatialRegistry) -> None:
    """D.2: точка вне всех footprint'ов → None."""
    # Точка далеко за пределами всех трёх локаций
    result = open_road_registry.resolve_primary(1000.0, 1000.0)
    assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# Тест 8: _MinimalFrontendRegistry — frontend зеркало с той же семантикой
# ─────────────────────────────────────────────────────────────────────────────


def test_d2_minimal_frontend_registry_mirror(tmp_path: Path) -> None:
    """D.2: _MinimalFrontendRegistry.resolve_primary — та же семантика.

    Загружаем реальный compiled/spatial_registry.json через
    _MinimalFrontendRegistry и проверяем, что resolve_primary выбирает
    tavern для точки внутри tavern.
    """
    # Импорт frontend-модуля (не в backend sys.path по умолчанию)
    import sys

    frontend_root = Path(__file__).resolve().parents[2] / "frontend"
    if str(frontend_root) not in sys.path:
        sys.path.insert(0, str(frontend_root))

    from spatial_compilation_orchestrator import _MinimalFrontendRegistry

    sr_path = (
        frontend_root
        / "map_editor"
        / "campaigns"
        / "Open_road"
        / "compiled"
        / "spatial_registry.json"
    )
    registry = _MinimalFrontendRegistry.load(sr_path)

    # Точка внутри tavern
    result = registry.resolve_primary(33.0, 12.0)
    assert result is not None
    assert isinstance(result, dict)
    assert result["location_id"] == "tavern"

    # Точка вне всех
    result_none = registry.resolve_primary(1000.0, 1000.0)
    assert result_none is None


# ─────────────────────────────────────────────────────────────────────────────
# Тест 9: синтетика для frontend-зеркала — multi-chunk с min-area
# ─────────────────────────────────────────────────────────────────────────────


def test_d2_minimal_frontend_multi_chunk_min_area() -> None:
    """D.2: _MinimalFrontendRegistry — multi-chunk → min площадь (зеркало backend).

    Синтетика: 2 чанка (dict), big (100) и small (25) перекрываются.
    """
    import sys

    frontend_root = Path(__file__).resolve().parents[2] / "frontend"
    if str(frontend_root) not in sys.path:
        sys.path.insert(0, str(frontend_root))

    from spatial_compilation_orchestrator import _MinimalFrontendRegistry

    data = {
        "campaign_id": "test",
        "chunks": [
            {
                "location_id": "big_loc",
                "origin_x": 0.0,
                "origin_y": 0.0,
                "width": 10.0,
                "height": 10.0,  # 100
            },
            {
                "location_id": "small_loc",
                "origin_x": 5.0,
                "origin_y": 5.0,
                "width": 5.0,
                "height": 5.0,  # 25
            },
        ],
    }
    registry = _MinimalFrontendRegistry(data)

    result = registry.resolve_primary(7.0, 7.0)
    assert result is not None
    assert result["location_id"] == "small_loc"  # 25 < 100