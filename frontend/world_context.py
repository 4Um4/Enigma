"""
frontend/world_context.py
Назначение: Когнитивный слой мира — проекция world position → visible world facts
Зависимости: spatial_registry.py (backend), editor JSON (frontend)
Основные сущности: ChunkSpatialData, VisibleChunk, WorldViewContext,
                   SpatialDataLoader, ContextResolver

Не рендерит. Не двигает NPC. Не загружает локации.
Не принимает решений. Предоставляет факты.

Два подслоя:
- perception layer (visible_*) — что видит камера/рендерер
- physics layer (collidable_*) — с чем взаимодействует симуляция

Сейчас они идентичны, но архитектура позволяет им разойтись:
- fog of war → visible ⊂ collidable
- performance culling → visible ⊂ collidable
- NPC perception → разный radius для разных NPC
"""
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Радиус видимости по умолчанию (метры)
DEFAULT_VIEW_RADIUS = 30.0
# Радиус физического взаимодействия по умолчанию (метры)
DEFAULT_PHYSICS_RADIUS = 30.0


@dataclass(frozen=True)
class ChunkSpatialData:
    """Пространственные данные одного чанка в мировых координатах.
    
    Стены и объекты уже сдвинуты на origin (global_coords=true).
    Floor rect = (origin_x, origin_y, width, height).
    """
    location_id: str
    floor_rect: Tuple[float, float, float, float]
    walls: Tuple[dict, ...]
    obstacles: Tuple[dict, ...]


@dataclass(frozen=True)
class VisibleChunk:
    """Один видимый чанк с его пространственными данными."""
    descriptor: object  # ChunkDescriptor из spatial_registry
    spatial: ChunkSpatialData
    is_primary: bool


@dataclass(frozen=True)
class WorldViewContext:
    """Когнитивный слой мира — что система "видит" в данный момент.
    
    НЕ мутируется. Каждый кадр = новый WorldViewContext.
    
    Два подслоя:
    - perception layer (visible_*) — для рендерера
    - physics layer (collidable_*) — для симуляции/коллизий
    
    Сейчас они идентичны, но архитектура позволяет им разойтись.
    """
    visible_chunks: Tuple[VisibleChunk, ...]
    primary_chunk: Optional[VisibleChunk]
    world_player_x: float
    world_player_y: float
    visible_bounds: Tuple[float, float, float, float]
    
    # Perception layer (рендер)
    visible_walls: Tuple[dict, ...]
    visible_obstacles: Tuple[dict, ...]
    
    # Physics layer (симуляция/коллизии)
    collidable_walls: Tuple[dict, ...]
    collidable_obstacles: Tuple[dict, ...]


class SpatialDataLoader:
    """Загружает пространственные данные чанка из editor JSON.
    
    Чистый I/O слой. Не знает про:
    - visible radius
    - adjacency
    - chunk selection
    - player position
    
    Кеширует результат — стены не меняются в рантайме.
    Координаты в файлах уже мировые (global_coords=true).
    """
    
    def __init__(self) -> None:
        self._cache: Dict[str, ChunkSpatialData] = {}
    
    def load(self, campaign_id: str, location_id: str) -> Optional[ChunkSpatialData]:
        """Загрузить пространственные данные чанка по location_id. Кешируется."""
        cache_key = f"{campaign_id}:{location_id}"
        
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        editor_data = self._find_editor_json(campaign_id, location_id)
        if editor_data is None:
            return None
        
        spatial = self._build_spatial_data(location_id, editor_data)
        self._cache[cache_key] = spatial
        return spatial
    
    def load_for_descriptor(self, campaign_id: str, descriptor) -> Optional[ChunkSpatialData]:
        """Загрузить по ChunkDescriptor (использует filename напрямую)."""
        cache_key = f"{campaign_id}:{descriptor.location_id}"
        
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        editor_data = self._find_editor_json_by_filename(campaign_id, descriptor.filename)
        if editor_data is None:
            return None
        
        spatial = self._build_spatial_data(descriptor.location_id, editor_data)
        self._cache[cache_key] = spatial
        return spatial
    
    def invalidate(self, campaign_id: str, location_id: str) -> None:
        """Сбросить кеш для чанка (после редактирования)."""
        cache_key = f"{campaign_id}:{location_id}"
        self._cache.pop(cache_key, None)
    
    def invalidate_all(self) -> None:
        """Сбросить весь кеш."""
        self._cache.clear()
    
    # === Внутренние методы ===
    
    @staticmethod
    def _find_project_root() -> Path:
        """Найти корень проекта."""
        try:
            return Path(__file__).resolve().parents[1]
        except (IndexError, ValueError):
            return Path(".")
    
    def _find_editor_json(self, campaign_id: str, location_id: str) -> Optional[dict]:
        """Найти editor JSON по location_id."""
        root = self._find_project_root()
        locations_dir = root / "frontend" / "map_editor" / "campaigns" / campaign_id / "locations"
        
        if not locations_dir.exists():
            return None
        
        for json_file in locations_dir.glob("*.json"):
            try:
                with open(json_file, "r", encoding="utf-8-sig") as f:
                    data = json.load(f)
                lid = data.get("location_id", "")
                label = data.get("label", "")
                if lid == location_id or label == location_id:
                    return data
            except (json.JSONDecodeError, OSError):
                continue
        
        return None
    
    def _find_editor_json_by_filename(self, campaign_id: str, filename: str) -> Optional[dict]:
        """Найти editor JSON по имени файла."""
        root = self._find_project_root()
        file_path = root / "frontend" / "map_editor" / "campaigns" / campaign_id / "locations" / filename
        
        if not file_path.exists():
            return None
        
        try:
            with open(file_path, "r", encoding="utf-8-sig") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None
    
    @staticmethod
    def _split_wall_by_openings(wall: dict, openings: list[dict]) -> list[dict]:
        """Разрезает сегмент стены на части, исключая проёмы (двери, проходы).
        
        Port из scene_state_manager._split_wall_by_openings.
        Временно дублирует логику бэкенда — будет устранено при ADR-S82.
        """
        if not openings:
            return [{
                "x1": float(wall.get("x1", 0)),
                "y1": float(wall.get("y1", 0)),
                "x2": float(wall.get("x2", 0)),
                "y2": float(wall.get("y2", 0)),
            }]
        
        x1, y1 = float(wall["x1"]), float(wall["y1"])
        x2, y2 = float(wall["x2"]), float(wall["y2"])
        
        dx = x2 - x1
        dy = y2 - y1
        wall_len = (dx * dx + dy * dy) ** 0.5
        if wall_len == 0:
            return [{"x1": x1, "y1": y1, "x2": x2, "y2": y2}]
        
        # единичный вектор вдоль стены
        ux = dx / wall_len
        uy = dy / wall_len
        
        # Собираем интервалы проёмов вдоль стены
        gaps = []
        for op in openings:
            pos = op.get("position", {})
            size = op.get("size", {})
            px, py = float(pos.get("x", 0)), float(pos.get("y", 0))
            # Вектор от начала стены до центра объекта
            vx, vy = px - x1, py - y1
            # Расстояние вдоль стены от начала
            dist_along = vx * ux + vy * uy
            # Перпендикулярное расстояние
            perp_dist = abs(vx * (-uy) + vy * ux)
            
            if perp_dist > 0.5:
                continue
            
            # Длина проёма вдоль оси стены
            if abs(dx) < abs(dy):  # Вертикальная стена
                span = float(size.get("h", 1.0))
            else:  # Горизонтальная стена
                span = float(size.get("w", 1.0))
            
            gap_start = dist_along - span / 2
            gap_end = dist_along + span / 2
            gaps.append((gap_start, gap_end))
        
        if not gaps:
            return [{"x1": x1, "y1": y1, "x2": x2, "y2": y2}]
        
        # Сортируем и склеиваем пересекающиеся проёмы
        gaps.sort()
        merged = [list(gaps[0])]
        for gs, ge in gaps[1:]:
            if gs <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], ge)
            else:
                merged.append([gs, ge])
        
        # Разрезаем стену на сегменты вокруг проёмов
        segments = []
        current = 0.0
        for gs, ge in merged:
            gs = max(0.0, gs)
            ge = min(wall_len, ge)
            if gs > current:
                segments.append({
                    "x1": x1 + ux * current, "y1": y1 + uy * current,
                    "x2": x1 + ux * gs, "y2": y1 + uy * gs,
                })
            current = ge
        
        if current < wall_len:
            segments.append({
                "x1": x1 + ux * current, "y1": y1 + uy * current,
                "x2": x2, "y2": y2,
            })
        
        return segments

    @staticmethod
    def _build_spatial_data(location_id: str, editor_data: dict) -> ChunkSpatialData:
        """Построить пространственные данные из editor JSON.
        
        Координаты уже мировые (global_coords=true после миграции).
        Не нужна конвертация — стены в файлах уже сдвинуты на origin.
        """
        origin = editor_data.get("origin", {"x": 0.0, "y": 0.0})
        size = editor_data.get("size", {})
        origin_x = float(origin.get("x", 0.0))
        origin_y = float(origin.get("y", 0.0))
        width = float(size.get("w", 0.0))
        height = float(size.get("h", 0.0))
        
        # Стены — уже в мировых координатах, но нужно вырезать проёмы для дверей
        # S81-ФИКС: Port _split_wall_by_openings из scene_state_manager
        # (временно — до ADR-S82 "Walls are Obstacles", где стены = obstacles с permeability)
        walls = []
        wall_openings: dict[str, list[dict]] = {}
        for obj in editor_data.get("objects", []):
            wall_id = obj.get("rotation")
            if not wall_id:
                continue
            if obj.get("passability", {}).get("walk", False):
                wall_openings.setdefault(wall_id, []).append(obj)
        
        for wall in editor_data.get("walls", []):
            wall_id = wall.get("id", "")
            openings = wall_openings.get(wall_id, [])
            segments = SpatialDataLoader._split_wall_by_openings(wall, openings)
            walls.extend(segments)
        
        # Объекты — уже в мировых координатах, position = center
        # S81-ФИКС: Конвертируем center→top-left (как бэкенд scene_state_manager:709-710)
        # и добавляем passability для data-driven фильтрации коллизий
        obstacles = []
        for obj in editor_data.get("objects", []):
            pos = obj.get("position", {})
            obj_size = obj.get("size", {})
            ow = float(obj_size.get("w", 1.0))
            oh = float(obj_size.get("h", 1.0))
            obstacles.append({
                "x": float(pos.get("x", 0.0)) - ow / 2,  # center → top-left
                "y": float(pos.get("y", 0.0)) - oh / 2,  # center → top-left
                "w": ow,
                "h": oh,
                "type": obj.get("type", "decoration"),
                "id": obj.get("id", ""),
                "passability": obj.get("passability", {}),
                "blocks_los": obj.get("cover", 0) >= 0.8,
            })
        
        return ChunkSpatialData(
            location_id=location_id,
            floor_rect=(origin_x, origin_y, width, height),
            walls=tuple(walls),
            obstacles=tuple(obstacles),
        )


class ContextResolver:
    """Строит WorldViewContext из позиции игрока и SpatialRegistry.
    
    Не рендерит. Не двигает NPC. Не загружает локации.
    Только проекция: world position → visible world context.
    
    Единственный источник world_position (local + origin → world).
    """
    
    def __init__(self, registry, data_loader: SpatialDataLoader) -> None:
        self._registry = registry
        self._loader = data_loader
    
    def resolve(
        self,
        world_x: float,
        world_y: float,
        campaign_id: str = "",
        view_radius: float = DEFAULT_VIEW_RADIUS,
        physics_radius: float = DEFAULT_PHYSICS_RADIUS,
    ) -> WorldViewContext:
        """Построить контекст мира из мировой позиции игрока.
        
        world_x, world_y — уже в мировых координатах.
        """
        # 1. Найти primary chunk (где игрок)
        primary_chunks = self._registry.find_chunks(world_x, world_y)
        primary_descriptor = primary_chunks[0] if primary_chunks else None
        
        # 2. Найти видимые чанки (perception layer)
        visible_descriptors = self._registry.find_nearby(world_x, world_y, view_radius)
        
        # 3. Найти физические чанки (physics layer)
        physics_descriptors = self._registry.find_nearby(world_x, world_y, physics_radius)
        
        # 4. Загрузить пространственные данные для visible
        visible_chunks_list: List[VisibleChunk] = []
        primary_chunk: Optional[VisibleChunk] = None
        
        for desc in visible_descriptors:
            spatial = self._loader.load_for_descriptor(campaign_id, desc)
            if spatial is None:
                continue
            
            is_primary = (desc == primary_descriptor)
            vc = VisibleChunk(
                descriptor=desc,
                spatial=spatial,
                is_primary=is_primary,
            )
            visible_chunks_list.append(vc)
            
            if is_primary:
                primary_chunk = vc
        
        # Fallback: primary не в visible (view_radius слишком мал)
        if primary_chunk is None and primary_descriptor is not None:
            spatial = self._loader.load_for_descriptor(campaign_id, primary_descriptor)
            if spatial is not None:
                primary_chunk = VisibleChunk(
                    descriptor=primary_descriptor,
                    spatial=spatial,
                    is_primary=True,
                )
                visible_chunks_list.insert(0, primary_chunk)
        
        # Fallback: игрок вне всех чанков
        if primary_chunk is None:
            return WorldViewContext(
                visible_chunks=(),
                primary_chunk=None,
                world_player_x=world_x,
                world_player_y=world_y,
                visible_bounds=(world_x - 1, world_y - 1, world_x + 1, world_y + 1),
                visible_walls=(),
                visible_obstacles=(),
                collidable_walls=(),
                collidable_obstacles=(),
            )
        
        # 5. Perception layer — стены/объекты из visible чанков
        visible_walls: List[dict] = []
        visible_obstacles: List[dict] = []
        for vc in visible_chunks_list:
            visible_walls.extend(vc.spatial.walls)
            visible_obstacles.extend(vc.spatial.obstacles)
        
        # 6. Physics layer — visible + дополнительные чанки из physics_radius
        collidable_walls: List[dict] = list(visible_walls)
        collidable_obstacles: List[dict] = list(visible_obstacles)
        
        visible_ids = {vc.descriptor.location_id for vc in visible_chunks_list}
        for desc in physics_descriptors:
            if desc.location_id in visible_ids:
                continue
            spatial = self._loader.load_for_descriptor(campaign_id, desc)
            if spatial is not None:
                collidable_walls.extend(spatial.walls)
                collidable_obstacles.extend(spatial.obstacles)
        
        # 7. Visible bounds
        min_x = min(vc.spatial.floor_rect[0] for vc in visible_chunks_list)
        min_y = min(vc.spatial.floor_rect[1] for vc in visible_chunks_list)
        max_x = max(vc.spatial.floor_rect[0] + vc.spatial.floor_rect[2] for vc in visible_chunks_list)
        max_y = max(vc.spatial.floor_rect[1] + vc.spatial.floor_rect[3] for vc in visible_chunks_list)
        
        # S80.3b-guard: Инвариант 2 — visible ⊆ collidable
        assert len(visible_walls) <= len(collidable_walls), (
            f"INVARIANT VIOLATION: visible_walls({len(visible_walls)}) > "
            f"collidable_walls({len(collidable_walls)})"
        )
        assert len(visible_obstacles) <= len(collidable_obstacles), (
            f"INVARIANT VIOLATION: visible_obstacles({len(visible_obstacles)}) > "
            f"collidable_obstacles({len(collidable_obstacles)})"
        )

        return WorldViewContext(
            visible_chunks=tuple(visible_chunks_list),
            primary_chunk=primary_chunk,
            world_player_x=world_x,
            world_player_y=world_y,
            visible_bounds=(min_x, min_y, max_x, max_y),
            visible_walls=tuple(visible_walls),
            visible_obstacles=tuple(visible_obstacles),
            collidable_walls=tuple(collidable_walls),
            collidable_obstacles=tuple(collidable_obstacles),
        )
    
    def local_to_world(
        self, 
        local_x: float, 
        local_y: float, 
        location_id: str,
    ) -> Tuple[float, float]:
        """Конвертировать локальные координаты чанка в мировые.
        
        Единственный источник world_position.
        Не делается в game_screen. Не делается в loader.
        """
        chunk = self._registry.get_chunk(location_id)
        if chunk is None:
            return local_x, local_y
        return local_x + chunk.origin_x, local_y + chunk.origin_y
    
    def world_to_local(
        self,
        world_x: float,
        world_y: float,
        location_id: str,
    ) -> Tuple[float, float]:
        """Конвертировать мировые координаты в локальные чанка."""
        chunk = self._registry.get_chunk(location_id)
        if chunk is None:
            return world_x, world_y
        return world_x - chunk.origin_x, world_y - chunk.origin_y