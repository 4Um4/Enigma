"""
backend/app/services/spatial/spatial_registry.py
Назначение: Read-only загрузчик скомпилированного пространственного реестра
Зависимости: compiled/spatial_registry.json (артефакт)
Основные сущности: SpatialRegistry, ChunkDescriptor, AdjacencyEntry, WorldBounds

SSOT пространственной истины мира для всех backend-потребителей.
Не рендерит. Не двигает NPC. Не загружает локации.
Не принимает решений. Предоставляет факты.
Не вычисляет adjacency в рантайме. Не знает про direction.
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ChunkDescriptor:
    """Описание одного чанка мира. Зеркало артефакта."""

    location_id: str
    filename: str
    origin_x: float
    origin_y: float
    width: float
    height: float
    is_outdoor: bool
    label: str
    content_hash: str


@dataclass(frozen=True)
class AdjacencyEntry:
    """Факт геометрической смежности двух чанков."""

    location_a: str
    location_b: str
    contact_axis: str
    contact_coord: float
    overlap_start: float
    overlap_end: float
    connection_type: str


@dataclass(frozen=True)
class WorldBounds:
    """Границы мира."""

    min_x: float
    min_y: float
    max_x: float
    max_y: float


# S82: Кеш реестров по campaign_id с версионированием.
# Инвалидация по mtime артефакта — если файл обновился (editor пересобрал), кеш сбрасывается.
# Ключ = campaign_id, значение = (SpatialRegistry, mtime_str).
_registry_cache: dict[str, tuple["SpatialRegistry", str]] = {}


class SpatialRegistry:
    """Read-only проекция скомпилированного пространственного реестра.

    Загружается из compiled/spatial_registry.json.
    Точка может принадлежать нескольким чанкам (дом внутри города).
    """

    def __init__(
        self,
        chunks: List[ChunkDescriptor],
        adjacency: List[AdjacencyEntry],
        world_bounds: WorldBounds,
        campaign_id: str = "",
    ):
        self._chunks = chunks
        self._adjacency = adjacency
        self._world_bounds = world_bounds
        self._campaign_id = campaign_id

        # Индексы для O(1) lookup
        self._chunks_by_id: dict[str, ChunkDescriptor] = {
            c.location_id: c for c in chunks
        }
        self._adjacency_by_location: dict[str, List[AdjacencyEntry]] = {}
        for entry in adjacency:
            self._adjacency_by_location.setdefault(entry.location_a, []).append(entry)
            self._adjacency_by_location.setdefault(entry.location_b, []).append(entry)

    @classmethod
    def load(cls, registry_path: Path) -> "SpatialRegistry":
        """Загружает реестр из файла артефакта.
        Не знает про кампанию — только про артефакт."""
        with open(registry_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_artifact(data)

    @classmethod
    def from_artifact(cls, data: Dict[str, Any]) -> "SpatialRegistry":
        """Создаёт реестр из словаря артефакта."""
        chunks = [ChunkDescriptor(**c) for c in data.get("chunks", [])]
        adjacency = [AdjacencyEntry(**a) for a in data.get("adjacency", [])]
        wb = data.get("world_bounds", {})
        world_bounds = WorldBounds(
            min_x=float(wb.get("min_x", 0.0)),
            min_y=float(wb.get("min_y", 0.0)),
            max_x=float(wb.get("max_x", 0.0)),
            max_y=float(wb.get("max_y", 0.0)),
        )
        return cls(
            chunks=chunks,
            adjacency=adjacency,
            world_bounds=world_bounds,
            campaign_id=data.get("campaign_id", ""),
        )

    @classmethod
    def find_artifact(cls, campaign_id: str) -> Optional[Path]:
        """Ищет файл артефакта для кампании.
        Возвращает Path или None."""
        try:
            project_root = Path(__file__).resolve().parents[4]
        except (IndexError, ValueError):
            project_root = Path(".")

        candidate = (
            project_root
            / "frontend"
            / "map_editor"
            / "campaigns"
            / campaign_id
            / "compiled"
            / "spatial_registry.json"
        )
        if candidate.exists():
            return candidate

    @classmethod
    def get_or_load(cls, campaign_id: str) -> Optional["SpatialRegistry"]:
        """Загрузить реестр с кешированием. Инвалидация по mtime файла артефакта.

        S82: Spatial Oracle требует O(1) доступ к реестру без IO на каждый запрос.
        Кеш инвалидируется при пересборке карты (editor обновляет артефакт).
        """
        artifact_path = cls.find_artifact(campaign_id)
        if artifact_path is None:
            return None

        # Версия кеша = mtime файла. Если файл обновился — кеш устарел.
        mtime = str(artifact_path.stat().st_mtime)

        cached = _registry_cache.get(campaign_id)
        if cached is not None and cached[1] == mtime:
            return cached[0]

        # Загрузка нового реестра
        registry = cls.load(artifact_path)
        _registry_cache[campaign_id] = (registry, mtime)
        logger.info(
            f"[SPATIAL_REGISTRY] Loaded and cached for campaign={campaign_id} ({len(registry)} chunks, mtime={mtime})"
        )
        return registry

    @classmethod
    def invalidate_cache(cls, campaign_id: str = "") -> None:
        """Сбросить кеш реестра. Вызвать при пересборке карты."""
        if campaign_id:
            _registry_cache.pop(campaign_id, None)
        else:
            _registry_cache.clear()

        return None

    # === Lookup ===

    def find_chunks(self, world_x: float, world_y: float) -> List[ChunkDescriptor]:
        """Все чанки, содержащие точку (world_x, world_y).
        Точка может принадлежать нескольким слоям (дом внутри города)."""
        result = []
        for chunk in self._chunks:
            if (
                chunk.origin_x <= world_x <= chunk.origin_x + chunk.width
                and chunk.origin_y <= world_y <= chunk.origin_y + chunk.height
            ):
                result.append(chunk)
        return result

    def find_nearby(
        self, world_x: float, world_y: float, radius: float
    ) -> List[ChunkDescriptor]:
        """Чанки в радиусе от точки (метры)."""
        result = []
        for chunk in self._chunks:
            cx1, cy1 = chunk.origin_x, chunk.origin_y
            cx2, cy2 = cx1 + chunk.width, cy1 + chunk.height

            # Ближайшая точка на bounding box чанка
            nearest_x = max(cx1, min(world_x, cx2))
            nearest_y = max(cy1, min(world_y, cy2))

            dx = world_x - nearest_x
            dy = world_y - nearest_y
            if (dx * dx + dy * dy) ** 0.5 <= radius:
                result.append(chunk)

        return result

    def get_chunk(self, location_id: str) -> Optional[ChunkDescriptor]:
        """Чанк по location_id."""
        return self._chunks_by_id.get(location_id)

    def get_chunks(self) -> List[ChunkDescriptor]:
        """Все чанки мира."""
        return list(self._chunks)

    def get_bounds(self, location_id: str) -> Optional[tuple]:
        """(origin_x, origin_y, origin_x+width, origin_y+height) для чанка."""
        chunk = self._chunks_by_id.get(location_id)
        if chunk is None:
            return None
        return (
            chunk.origin_x,
            chunk.origin_y,
            chunk.origin_x + chunk.width,
            chunk.origin_y + chunk.height,
        )

    # === Adjacency ===

    def get_neighbors(self, location_id: str) -> List[AdjacencyEntry]:
        """Все связи смежности для чанка (скомпилированные, не O(N²))."""
        return self._adjacency_by_location.get(location_id, [])

    # === World ===

    @property
    def world_bounds(self) -> WorldBounds:
        """Границы всего мира. Сдвигаются при расширении карты."""
        return self._world_bounds

    def is_world_edge(
        self, world_x: float, world_y: float, margin: float = 2.0
    ) -> bool:
        """Находится ли точка у края мира (для Civilizational Horizon)."""
        wb = self._world_bounds
        return (
            world_x <= wb.min_x + margin
            or world_x >= wb.max_x - margin
            or world_y <= wb.min_y + margin
            or world_y >= wb.max_y - margin
        )

    @property
    def campaign_id(self) -> str:
        return self._campaign_id

    def __len__(self) -> int:
        return len(self._chunks)

    def __repr__(self) -> str:
        return (
            f"SpatialRegistry({len(self._chunks)} chunks, "
            f"{len(self._adjacency)} adjacencies, "
            f"bounds=({self._world_bounds.min_x:.0f},{self._world_bounds.min_y:.0f})"
            f"-({self._world_bounds.max_x:.0f},{self._world_bounds.max_y:.0f}))"
        )
