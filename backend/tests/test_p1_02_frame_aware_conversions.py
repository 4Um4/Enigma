"""P1-02 (ADR-O-439 W3): фрейм-осознанные конверсии ContextResolver.

Тестирует:
- global_coords=true  → identity (local_to_world == input)
- global_coords=false → +origin (легаси)
- chunk=None          → identity (fallback)

ROADMAP: P1-02, §D.1.2 W3.
"""
import sys
from pathlib import Path
from dataclasses import dataclass

_ROOT = Path(__file__).resolve().parents[2]
_BACKEND = _ROOT / "backend"
_FRONTEND = _ROOT / "frontend"
for _p in (str(_ROOT), str(_BACKEND), str(_FRONTEND)):
    if _p not in sys.path:
        sys.path.insert(0, _p)


@dataclass(frozen=True)
class _MockChunk:
    """Mock ChunkDescriptor для тестов (с global_coords)."""
    location_id: str
    origin_x: float
    origin_y: float
    global_coords: bool = True


class _MockRegistry:
    """Минимальный registry: get_chunk возвращает mock или None."""
    def __init__(self, chunks_dict):
        self._chunks = chunks_dict

    def get_chunk(self, location_id):
        return self._chunks.get(location_id)


def _make_resolver(chunks_dict):
    """Создать ContextResolver с mock registry (loader не нужен для конверсий)."""
    from world_context import ContextResolver
    return ContextResolver(_MockRegistry(chunks_dict), data_loader=None)


def test_global_coords_true_identity():
    """W3: при global_coords=true local_to_world = identity."""
    chunks = {"tavern": _MockChunk("tavern", 25.03, 5.02, global_coords=True)}
    r = _make_resolver(chunks)

    # Локальные координаты (8.18, 10.70) — при identity возвращаются как есть
    wx, wy = r.local_to_world(8.18, 10.70, "tavern")
    assert (wx, wy) == (8.18, 10.70), f"Expected identity, got ({wx}, {wy})"

    # world_to_local — симметрично
    lx, ly = r.world_to_local(8.18, 10.70, "tavern")
    assert (lx, ly) == (8.18, 10.70), f"Expected identity, got ({lx}, {ly})"


def test_global_coords_false_legacy_shift():
    """W3: при global_coords=false — легаси сдвиг +origin."""
    chunks = {"legacy_loc": _MockChunk("legacy_loc", 25.03, 5.02, global_coords=False)}
    r = _make_resolver(chunks)

    # Локальные (8.18, 10.70) + origin (25.03, 5.02) = мировые (33.21, 15.72)
    wx, wy = r.local_to_world(8.18, 10.70, "legacy_loc")
    assert abs(wx - 33.21) < 0.01, f"Expected ~33.21, got {wx}"
    assert abs(wy - 15.72) < 0.01, f"Expected ~15.72, got {wy}"

    # world_to_local — симметрично: мировые - origin = локальные
    lx, ly = r.world_to_local(33.21, 15.72, "legacy_loc")
    assert abs(lx - 8.18) < 0.01, f"Expected ~8.18, got {lx}"
    assert abs(ly - 10.70) < 0.01, f"Expected ~10.70, got {ly}"


def test_chunk_none_identity_fallback():
    """W3: chunk=None → identity (fallback)."""
    r = _make_resolver({})  # пустой registry

    wx, wy = r.local_to_world(5.0, 7.0, "nonexistent")
    assert (wx, wy) == (5.0, 7.0), f"Expected identity fallback, got ({wx}, {wy})"

    lx, ly = r.world_to_local(5.0, 7.0, "nonexistent")
    assert (lx, ly) == (5.0, 7.0), f"Expected identity fallback, got ({lx}, {ly})"


def test_real_tavern_global_coords_true():
    """Интеграция: реальный compiled артефакт Open_road — все чанки global_coords=true."""
    from app.services.spatial.spatial_registry import SpatialRegistry

    sr_path = _FRONTEND / "map_editor" / "campaigns" / "Open_road" / "compiled" / "spatial_registry.json"
    import json
    data = json.loads(sr_path.read_text(encoding="utf-8"))

    for chunk_dict in data["chunks"]:
        assert chunk_dict.get("global_coords") is True, (
            f"Chunk {chunk_dict['location_id']} should have global_coords=true, "
            f"got {chunk_dict.get('global_coords')}"
        )


def test_real_tavern_local_to_world_identity():
    """Интеграция: ContextResolver с реальным registry Open_road → identity для tavern.

    tavern.global_coords=true → local_to_world(8.18, 10.70, 'tavern') == (8.18, 10.70).
    ВНИМАНИЕ: это intermediate-состояние (данные tavern ещё локальные, P1-03 не выполнен).
    После P1-03 данные станут мировыми и identity будет корректной.
    """
    from app.services.spatial.spatial_registry import SpatialRegistry
    from world_context import ContextResolver, SpatialDataLoader

    sr_path = _FRONTEND / "map_editor" / "campaigns" / "Open_road" / "compiled" / "spatial_registry.json"
    registry = SpatialRegistry.load(sr_path)
    loader = SpatialDataLoader()
    resolver = ContextResolver(registry, loader)

    # tavern chunk должен иметь global_coords=true
    tv = registry.get_chunk("tavern")
    assert tv is not None, "tavern chunk not found"
    assert getattr(tv, "global_coords", None) is True, (
        f"tavern.global_coords should be True, got {getattr(tv, 'global_coords', 'MISSING')}"
    )

    # local_to_world — identity (т.к. global_coords=true)
    wx, wy = resolver.local_to_world(8.18, 10.70, "tavern")
    assert (wx, wy) == (8.18, 10.70), (
        f"Expected identity (global_coords=true), got ({wx}, {wy})"
    )