"""
frontend/map_editor/spatial_registry_builder.py
Назначение: Компилирует location JSONs → spatial_registry.json (SSOT пространства)
Зависимости: location JSONs из campaigns/<id>/locations/
Основные сущности: SpatialRegistryBuilder, ChunkDescriptor, AdjacencyEntry, WorldBounds

Единственная система, которая знает как строить реестр пространства.
Не рендерит. Не двигает NPC. Не загружает локации.
Не принимает решений. Предоставляет факты.
"""

import hashlib
import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)

# Допуск для определения смежности (метры)
ADJACENCY_TOLERANCE = 0.5
# Минимальное перекрытие по перпендикулярной оси для смежности (метры)
MIN_OVERLAP = 0.5
# Версия формата артефакта
ARTIFACT_VERSION = 1


@dataclass(frozen=True)
class ChunkDescriptor:
    """Описание одного чанка мира."""

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
    """Факт геометрической смежности двух чанков.
    Direction — производная, вычисляется функцией, не хранится."""

    location_a: str
    location_b: str
    contact_axis: str  # "x" | "y"
    contact_coord: float  # координата линии контакта
    overlap_start: float  # начало перекрытия по перпендикулярной оси
    overlap_end: float  # конец перекрытия
    connection_type: str  # "contiguous" | "doorway" | "stairs" | "portal" | "road" | "river_crossing"


@dataclass(frozen=True)
class WorldBounds:
    """Границы мира. Сдвигаются при расширении карты."""

    min_x: float
    min_y: float
    max_x: float
    max_y: float


@dataclass
class SpatialRegistryArtifact:
    """Скомпилированный пространственный реестр мира."""

    version: int
    campaign_id: str
    compiled_at: str
    chunks: List[ChunkDescriptor]
    adjacency: List[AdjacencyEntry]
    world_bounds: WorldBounds


class SpatialRegistryBuilder:
    """Единственная система, которая знает как строить реестр пространства.

    Запускается:
    - При сохранении локации в Map Editor
    - При загрузке кампании, если артефакт устарел

    O(N²) adjacency — только при компиляции, не в рантайме.
    """

    def build(self, campaign_path: Path) -> SpatialRegistryArtifact:
        """Компилирует все локации кампании в пространственный реестр."""
        campaign_id = campaign_path.name
        chunks = self._collect_chunks(campaign_path)
        adjacency = self._compute_adjacency(chunks)
        world_bounds = self._compute_world_bounds(chunks)

        artifact = SpatialRegistryArtifact(
            version=ARTIFACT_VERSION,
            campaign_id=campaign_id,
            compiled_at=datetime.now().isoformat(),
            chunks=chunks,
            adjacency=adjacency,
            world_bounds=world_bounds,
        )

        logger.info(
            f"[SPATIAL_REGISTRY] Скомпилирован: "
            f"{len(chunks)} чанков, {len(adjacency)} связей, "
            f"bounds=({world_bounds.min_x:.1f},{world_bounds.min_y:.1f})"
            f"-({world_bounds.max_x:.1f},{world_bounds.max_y:.1f})"
        )

        return artifact

    def build_and_save(self, campaign_path: Path) -> SpatialRegistryArtifact:
        """Компилирует и сохраняет артефакт."""
        artifact = self.build(campaign_path)
        self.save(artifact, campaign_path)
        return artifact

    def needs_rebuild(self, campaign_path: Path) -> bool:
        """Проверяет, нужно ли перекомпилировать реестр.
        Сравнивает content_hash чанков в артефакте с текущими файлами."""
        registry_path = campaign_path / "compiled" / "spatial_registry.json"
        if not registry_path.exists():
            return True

        try:
            with open(registry_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except (json.JSONDecodeError, OSError):
            return True

        # Проверяем версию формата
        if existing.get("version") != ARTIFACT_VERSION:
            return True

        # Собираем текущие хэши
        existing_hashes = {
            c["location_id"]: c["content_hash"] for c in existing.get("chunks", [])
        }

        locations_dir = campaign_path / "locations"
        if not locations_dir.exists():
            return len(existing_hashes) > 0

        current_files = {}
        for loc_file in locations_dir.glob("*.json"):
            try:
                with open(loc_file, "r", encoding="utf-8-sig") as f:
                    data = json.load(f)
                lid = data.get("location_id", loc_file.stem)
                current_files[lid] = self._hash_file(loc_file)
            except (json.JSONDecodeError, OSError):
                continue

        # Количество чанков изменилось
        if set(existing_hashes.keys()) != set(current_files.keys()):
            return True

        # Хэш хотя бы одного чанка изменился
        for lid, current_hash in current_files.items():
            if existing_hashes.get(lid) != current_hash:
                return True

        return False

    def save(self, artifact: SpatialRegistryArtifact, campaign_path: Path) -> None:
        """Сохраняет артефакт в compiled/spatial_registry.json"""
        compiled_dir = campaign_path / "compiled"
        compiled_dir.mkdir(exist_ok=True)

        output_path = compiled_dir / "spatial_registry.json"

        data = {
            "version": artifact.version,
            "campaign_id": artifact.campaign_id,
            "compiled_at": artifact.compiled_at,
            "chunks": [asdict(c) for c in artifact.chunks],
            "adjacency": [asdict(a) for a in artifact.adjacency],
            "world_bounds": asdict(artifact.world_bounds),
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        logger.info(f"[SPATIAL_REGISTRY] Артефакт сохранён: {output_path}")

    # === Внутренние методы ===

    def _collect_chunks(self, campaign_path: Path) -> List[ChunkDescriptor]:
        """Собирает описания всех чанков из editor JSON."""
        chunks = []
        locations_dir = campaign_path / "locations"

        if not locations_dir.exists():
            logger.warning(
                f"[SPATIAL_REGISTRY] Нет директории локаций: {locations_dir}"
            )
            return chunks

        for loc_file in sorted(locations_dir.glob("*.json")):
            try:
                with open(loc_file, "r", encoding="utf-8-sig") as f:
                    data = json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"[SPATIAL_REGISTRY] Пропуск {loc_file.name}: {e}")
                continue

            # Миграция: world_pos → origin (как в data_manager)
            if "world_pos" in data:
                data["origin"] = data.pop("world_pos")
            data.setdefault("origin", {"x": 0.0, "y": 0.0})

            origin = data.get("origin", {})
            size = data.get("size", {})

            chunk = ChunkDescriptor(
                location_id=data.get("location_id", loc_file.stem),
                filename=loc_file.name,
                origin_x=float(origin.get("x", 0.0)),
                origin_y=float(origin.get("y", 0.0)),
                width=float(size.get("w", 0.0)),
                height=float(size.get("h", 0.0)),
                is_outdoor=bool(data.get("is_outdoor", False)),
                label=data.get("label", loc_file.stem),
                content_hash=self._hash_file(loc_file),
            )

            if chunk.width > 0 and chunk.height > 0:
                chunks.append(chunk)
            else:
                logger.warning(
                    f"[SPATIAL_REGISTRY] Пропуск {chunk.location_id}: "
                    f"нулевой размер ({chunk.width}x{chunk.height})"
                )

        return chunks

    def _compute_adjacency(self, chunks: List[ChunkDescriptor]) -> List[AdjacencyEntry]:
        """Вычисляет смежность между чанками. O(N²) — только при компиляции."""
        adjacency = []
        n = len(chunks)

        for i in range(n):
            for j in range(i + 1, n):
                entries = self._check_adjacent(chunks[i], chunks[j])
                adjacency.extend(entries)

        return adjacency

    def _check_adjacent(
        self, a: ChunkDescriptor, b: ChunkDescriptor
    ) -> List[AdjacencyEntry]:
        """Проверяет смежность двух чанков по осям X и Y."""
        entries = []

        # Bounding boxes
        ax1, ay1 = a.origin_x, a.origin_y
        ax2, ay2 = ax1 + a.width, ay1 + a.height
        bx1, by1 = b.origin_x, b.origin_y
        bx2, by2 = bx1 + b.width, by1 + b.height

        # X-контакт: вертикальная линия соприкосновения (восток-запад)
        x_contact_coord = None
        if abs(ax2 - bx1) < ADJACENCY_TOLERANCE:
            x_contact_coord = (ax2 + bx1) / 2.0
        elif abs(bx2 - ax1) < ADJACENCY_TOLERANCE:
            x_contact_coord = (bx2 + ax1) / 2.0

        if x_contact_coord is not None:
            # Перекрытие по Y
            overlap_start = max(ay1, by1)
            overlap_end = min(ay2, by2)
            if overlap_end - overlap_start >= MIN_OVERLAP:
                entries.append(
                    AdjacencyEntry(
                        location_a=a.location_id,
                        location_b=b.location_id,
                        contact_axis="x",
                        contact_coord=round(x_contact_coord, 2),
                        overlap_start=round(overlap_start, 2),
                        overlap_end=round(overlap_end, 2),
                        connection_type="contiguous",
                    )
                )

        # Y-контакт: горизонтальная линия соприкосновения (север-юг)
        y_contact_coord = None
        if abs(ay2 - by1) < ADJACENCY_TOLERANCE:
            y_contact_coord = (ay2 + by1) / 2.0
        elif abs(by2 - ay1) < ADJACENCY_TOLERANCE:
            y_contact_coord = (by2 + ay1) / 2.0

        if y_contact_coord is not None:
            # Перекрытие по X
            overlap_start = max(ax1, bx1)
            overlap_end = min(ax2, bx2)
            if overlap_end - overlap_start >= MIN_OVERLAP:
                entries.append(
                    AdjacencyEntry(
                        location_a=a.location_id,
                        location_b=b.location_id,
                        contact_axis="y",
                        contact_coord=round(y_contact_coord, 2),
                        overlap_start=round(overlap_start, 2),
                        overlap_end=round(overlap_end, 2),
                        connection_type="contiguous",
                    )
                )

        return entries

    def _compute_world_bounds(self, chunks: List[ChunkDescriptor]) -> WorldBounds:
        """Вычисляет границы мира. Сдвигаются при расширении карты."""
        if not chunks:
            return WorldBounds(min_x=0.0, min_y=0.0, max_x=0.0, max_y=0.0)

        min_x = min(c.origin_x for c in chunks)
        min_y = min(c.origin_y for c in chunks)
        max_x = max(c.origin_x + c.width for c in chunks)
        max_y = max(c.origin_y + c.height for c in chunks)

        return WorldBounds(
            min_x=round(min_x, 2),
            min_y=round(min_y, 2),
            max_x=round(max_x, 2),
            max_y=round(max_y, 2),
        )

    @staticmethod
    def _hash_file(path: Path) -> str:
        """MD5 хэш содержимого файла для определения изменений."""
        content = path.read_bytes()
        return hashlib.md5(content).hexdigest()
