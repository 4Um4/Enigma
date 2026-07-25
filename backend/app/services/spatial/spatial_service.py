from __future__ import annotations

# backend/app/services/spatial/spatial_service.py
# Назначение: Единый API SpatialService v1.2 — ядро
# Чистый механизм. Не принимает решений. Не мутирует состояние.
# Трёхслойная модель: Геометрия → Топология → Семантика
# Зависимости: app.models.spatial_contracts, stdlib

"""
TODO:
- [ ] Кэширование путей с учётом overlay (инвалидируется при изменении overlay)
- [ ] Методы для получения всех узлов с ролью (для массовых действий NPC)
- [ ] Методы для получения ближайшего/дальнего узла (для FLEE и SEEK)
- [ ] Интеграция с CFRM Layer 1: ClusterGraph (каждый макро-узел = кластер, границы = связи)
- [ ] Расширение скоринга: учитывать не только расстояние, но и риск, освещённость, плотность толпы и резервации
"""


import heapq
import logging
import math
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Set, Tuple

from app.models.cfrm import ClusterDef, ClusterGraph
from app.models.spatial_contracts import (
    NodeRef,
    NodeRole,
    SpatialOverlay,
    Urgency,
)
from app.services.spatial.spatial_runtime import _line_rect_intersect, _segments_intersect

logger = logging.getLogger(__name__)


class SpatialService:
    """Единый пространственный сервис. Чистый механизм.

    Отвечает на вопросы:
    - Где узел с ролью X в моей зоне?
    - Как дойти с учётом толпы/риска/резерваций?
    - Сколько это стоит?

    НЕ решает куда идти. НЕ хранит пути NPC. НЕ мутирует мир.
    """

    @staticmethod
    def build_for_location(
        campaign_id: str,
        location_id: str,
        scene_state: Dict[str, Any],
    ) -> Optional["SpatialService"]:
        """Фабрика: компилирует граф и оверлей для текущей локации и сцены."""
        from app.services.spatial.graph_compiler import compile_graph, load_editor_json
        from app.services.spatial.spatial_overlay import build_overlay_from_scene

        editor_data = load_editor_json(campaign_id, location_id)
        if not editor_data:
            logger.warning(
                f"[SPATIAL] editor JSON не найден для {campaign_id}/{location_id}"
            )
            return None

        result = compile_graph(editor_data, location_id)
        # ДОЛГ 6.2: compile_graph возвращает 4 элемента (добавлен boundary_map)
        # ETKE-IK v1: compile_graph возвращает 5 элементов (добавлен rooms_geometry)
        # ADR-O-324: compile_graph возвращает 7 элементов (добавлены spatial_walls, spatial_obstacles)
        if len(result) == 8:
            graph, connections, alias_map, boundary_map, rooms_geometry, spatial_walls, spatial_obstacles, affordance_objects = result
        elif len(result) == 7:
            graph, connections, alias_map, boundary_map, rooms_geometry, spatial_walls, spatial_obstacles = result
            affordance_objects = []
        elif len(result) == 5:
            graph, connections, alias_map, boundary_map, rooms_geometry = result
            spatial_walls, spatial_obstacles, affordance_objects = [], [], []
        elif len(result) == 4:
            graph, connections, alias_map, boundary_map = result
            rooms_geometry, spatial_walls, spatial_obstacles, affordance_objects = {}, [], [], []
        else:
            graph, connections, alias_map = result
            boundary_map, rooms_geometry, spatial_walls, spatial_obstacles, affordance_objects = {}, {}, [], [], []
        overlay = build_overlay_from_scene(scene_state)

        return SpatialService(
            graph,
            connections,
            alias_map,
            overlay,
            location_id=location_id,
            boundary_map=boundary_map,
            rooms_geometry=rooms_geometry,
            spatial_walls=spatial_walls,
            spatial_obstacles=spatial_obstacles,
            affordance_objects=affordance_objects,
        )

    def __init__(
        self,
        graph: Dict[str, NodeRef],
        connections: Dict[str, Set[str]],
        alias_map: Dict[str, str],
        overlay: SpatialOverlay,
        location_id: str = "",  # Сохраняем принадлежность к локации для динамического резолва
        boundary_map: Optional[
            Dict[str, dict]
        ] = None,  # ДОЛГ 6.2: boundary node → neighbor info
        rooms_geometry: Optional[
            Dict[str, List[Tuple[float, float]]]
        ] = None,  # ETKE-IK v1
        spatial_walls: Optional[List[Dict[str, Any]]] = None,  # ADR-O-324
        spatial_obstacles: Optional[List[Dict[str, Any]]] = None,  # ADR-O-324
        affordance_objects: Optional[List[Dict[str, Any]]] = None,  # ADR-O-330
    ) -> None:
        self._graph = graph  # canonical_id → NodeRef
        self._connections = connections  # canonical_id → set[canonical_id]
        self._alias_map = alias_map  # legacy_id → canonical_id
        self._overlay = overlay
        self._location_id = (
            location_id  # ADR-052: Сохраняем для мультисценового резолва
        )
        self._boundary_map = boundary_map or {}  # ДОЛГ 6.2
        self._rooms_geometry = rooms_geometry or {}  # ETKE-IK v1
        self._spatial_walls = spatial_walls or []  # ADR-O-324
        self._spatial_obstacles = spatial_obstacles or []  # ADR-O-324
        self._affordance_objects = affordance_objects or []  # ADR-O-330
        self._spatial_obstacles = spatial_obstacles or []  # ADR-O-324
        self._path_cache: OrderedDict[Tuple[str, str, str, Urgency], List[NodeRef]] = OrderedDict()
        self._path_cache_max_size = 128  # P1-15: LRU cache limit

    # ── ADR-O-333: Local Geometry Snapshot ──────────────────────────────
    def get_local_geometry(self, center_xy: Tuple[float, float], perception_radius: float = 15.0) -> "LocalGeometry":
        """Возвращает immutable snapshot локальной физической геометрии (в пределах восприятия)."""
        from app.domain.traversal import LocalGeometry, Obstacle, WallSegment
        from app.services.spatial.geometry_kernel import point_to_rect_min_dist_sq, point_to_segment_dist_sq

        cx, cy = center_xy
        r_sq = perception_radius ** 2

        def _seg_in_range(x1, y1, x2, y2) -> bool:
            return point_to_segment_dist_sq((cx, cy), (x1, y1), (x2, y2)) <= r_sq

        def _rect_in_range(rx, ry, rw, rh) -> bool:
            return point_to_rect_min_dist_sq((cx, cy), rx, ry, rw, rh) <= r_sq

        walls = tuple(
            WallSegment(w["x1"], w["y1"], w["x2"], w["y2"])
            for w in self._spatial_walls if _seg_in_range(w["x1"], w["y1"], w["x2"], w["y2"])
        )
        obstacles = tuple(
            Obstacle(o.get("id", "unknown"), o["x"], o["y"], o["w"], o["h"], o.get("height", 1.0))
            for o in self._spatial_obstacles
            if not o.get("passability", {}).get("walk", True) and _rect_in_range(o["x"], o["y"], o["w"], o["h"])
        )
        return LocalGeometry(walls=walls, obstacles=obstacles, perception_radius=perception_radius, center_xy=center_xy)

    # ── ADR-O-324: Geometric Validation ─────────────────────────────────
    def is_segment_blocked(self, ax: float, ay: float, bx: float, by: float) -> bool:
        """Проверяет, пересекает ли отрезок AB любую стену или непроходимое препятствие.

        ADR-O-324: Единственный метод для геометрической валидации сегментов пути.
        Используется MovementPlanner для проверки каждого отрезка маршрута.
        """
        # Проверка стен
        for wall in self._spatial_walls:
            if _segments_intersect(ax, ay, bx, by, wall["x1"], wall["y1"], wall["x2"], wall["y2"]):
                return True

        # Проверка непроходимых препятствий
        for obs in self._spatial_obstacles:
            _pass = obs.get("passability", {})
            # S129 FIX: P4-04 — Pathfinding учитывает ТОЛЬКО физическую непроходимость (walk).
            # blocks_los не должен разрывать навигационный граф (LoS проверяется отдельно).
            _blocks_walk = not _pass.get("walk", True)
            if _blocks_walk:
                if _line_rect_intersect(ax, ay, bx, by, obs["x"], obs["y"], obs["w"], obs["h"]):
                    return True

        return False

    def is_near_wall(self, x: float, y: float, threshold: float = 0.5) -> bool:
        """Проверяет, находится ли точка вблизи любой стены (в пределах threshold)."""
        for wall in self._spatial_walls:
            # Вычисляем расстояние от точки до отрезка стены
            x1, y1 = wall["x1"], wall["y1"]
            x2, y2 = wall["x2"], wall["y2"]
            dx, dy = x2 - x1, y2 - y1
            if dx == 0 and dy == 0:
                dist = math.hypot(x - x1, y - y1)
            else:
                t = max(0, min(1, ((x - x1) * dx + (y - y1) * dy) / (dx * dx + dy * dy)))
                px, py = x1 + t * dx, y1 + t * dy
                dist = math.hypot(x - px, y - py)
            if dist < threshold:
                return True
        return False

    # ── Overlay обновление ────────────────────────────────────────────

    def set_overlay(self, overlay: SpatialOverlay) -> None:
        """Обновляет overlay. Инвалидирует кэш путей при изменении."""
        new_hash = overlay.compute_hash()
        old_hash = self._overlay.compute_hash()
        if new_hash != old_hash:
            self._path_cache.clear()
        self._overlay = overlay

    # ── Boundary Nodes (ДОЛГ 6.2) ────────────────────────────────────

    @property
    def boundary_map(self) -> Dict[str, dict]:
        """Карта граничных узлов: boundary_node_id → {direction, neighbor_chunk, entry_direction, entry_node_hint}."""
        return self._boundary_map

    def is_boundary_node(self, node_id: str) -> bool:
        """Проверяет, является ли узел граничным (выход из чанка)."""
        canonical = self.normalize_id(node_id)
        return canonical in self._boundary_map

    def get_boundary_info(self, node_id: str) -> Optional[Dict[str, Any]]:
        """Возвращает информацию о переходе для boundary node."""
        canonical = self.normalize_id(node_id)
        return self._boundary_map.get(canonical)

    def get_boundary_to_neighbor(self, neighbor_loc: str) -> Optional[NodeRef]:
        """S91.1: Возвращает boundary node, ведущую в соседний чанк."""
        for b_id, b_info in self._boundary_map.items():
            if b_info.get("neighbor_chunk") == neighbor_loc:
                return self.get_node(b_id)
        return None

    def get_zone_id(self, x: float, y: float) -> Optional[str]:
        """S91: Возвращает zone_id (room_id) полигона, в котором находится точка.
        Используется WorldTopologyProvider для кэширования деформаций (DynamicAffordanceField).
        Возвращает None, если точка вне полигонов.
        """
        if not self._rooms_geometry:
            return None  # Fallback: если геометрии нет, зоны не определены

        for zone_id, polygon in self._rooms_geometry.items():
            # Алгоритм Ray Casting (even-odd rule)
            n = len(polygon)
            inside = False
            p1x, p1y = polygon[0]
            for i in range(n + 1):
                p2x, p2y = polygon[i % n]
                if y > min(p1y, p2y):
                    if y <= max(p1y, p2y):
                        if x <= max(p1x, p2x):
                            if p1y != p2y:
                                xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                            if p1x == p2x or x <= xinters:
                                inside = not inside
                p1x, p1y = p2x, p2y
            if inside:
                return zone_id
        return None

    def is_point_in_bounds(self, x: float, y: float) -> bool:
        """ETKE-IK v1: Проверяет, находится ли точка внутри физической геометрии комнат.
        Используется WorldTopologyProvider для вычисления AffordanceVector.
        """
        if not self._rooms_geometry:
            return True  # Fallback: если геометрии нет, считаем всё проходимым
        return self.get_zone_id(x, y) is not None

    # ── Нормализация ID ───────────────────────────────────────────────

    def normalize_id(self, raw_id: str) -> str:
        """Транслирует legacy-ID в канонический.

        "bar_area" → "tavern_silver_wolf:bar_area"
        "tavern_silver_wolf:bar_area" → "tavern_silver_wolf:bar_area"
        """
        if raw_id in self._graph:
            return raw_id
        canonical = self._alias_map.get(raw_id)
        if canonical:
            return canonical
        # Уже канонический но не в графе — возвращаем как есть
        return raw_id

    def denormalize_id(self, canonical_id: str) -> str:
        """Обратная трансляция для legacy-кодов. @deprecated: использовать только в мостах."""
        # "tavern_silver_wolf:bar_area" → "bar_area"
        if ":" in canonical_id:
            return canonical_id.split(":", 1)[1]
        return canonical_id

    # ── Доступ к узлам ────────────────────────────────────────────────

    def get_node(self, node_id: str) -> Optional[NodeRef]:
        """Возвращает NodeRef по любому формату ID."""
        canonical = self.normalize_id(node_id)
        return self._graph.get(canonical)

    def get_node_label(self, node_id: str) -> str:
        """Возвращает читаемый label для узла. Fallback на denormalized ID."""
        node = self.get_node(node_id)
        if node is None:
            return self.denormalize_id(self.normalize_id(node_id))
        # role → русский label
        role_labels = {
            NodeRole.BAR: "у стойки",
            NodeRole.BED: "в спальне",
            NodeRole.ENTRANCE: "у входа",
            NodeRole.TABLE: "за столом",
            NodeRole.WORKBENCH: "у верстака",
            NodeRole.MARKET: "на рынке",
            NodeRole.TRANSITION: "у перехода",
            NodeRole.DEFAULT: self.denormalize_id(node.node_id),
        }
        return role_labels.get(node.role, self.denormalize_id(node.node_id))

    # ── ADR-O-330: Affordance Resolution ──────────────────────────────

    def resolve_affordance(
        self,
        affordance_type: str,
        origin_xy: Tuple[float, float],
        origin_zone: Optional[str] = None,
        owner: Optional[str] = None,
    ) -> Optional[NodeRef]:
        """Ищет физический объект с нужным аффордансом.

        ADR-O-330: Кровать — это объект, а не узел графа.
        Метод находит объект, берёт его XY и возвращает ближайший
        навигационный узел как точку маршрута (Interaction Point).
        """
        if not self._affordance_objects:
            return None

        candidates = [
            obj for obj in self._affordance_objects
            if affordance_type in obj.get("affordances", [])
            and not obj.get("destroyed", False)
        ]

        # Фильтр по владельцу (через теги owner:orm или поле owner)
        if owner:
            candidates = [
                obj for obj in candidates
                if f"owner:{owner}" in obj.get("tags", []) or obj.get("owner") == owner
            ]

        if not candidates:
            return None

        # Скоринг по дистанции до NPC
        best_obj = None
        min_dist_sq = float('inf')
        ox, oy = origin_xy

        for obj in candidates:
            dx = obj["x"] - ox
            dy = obj["y"] - oy
            dist_sq = dx * dx + dy * dy
            if dist_sq < min_dist_sq:
                min_dist_sq = dist_sq
                best_obj = obj

        if not best_obj:
            return None

        # Возвращаем ближайший навигационный узел к точке взаимодействия с объектом
        zone = origin_zone or self._location_id
        return self.get_nearest(zone, (best_obj["x"], best_obj["y"]))

    # ── Резолв целей ──────────────────────────────────────────────────

    def resolve_node(
        self,
        role: NodeRole,
        origin_xy: Optional[Tuple[float, float]] = None,
        origin_zone: Optional[str] = None,
        origin_level: Optional[str] = None,
        filters: Optional[List[str]] = None,
        urgency: Urgency = Urgency.NORMAL,
        requesting_npc_id: Optional[str] = None,
    ) -> Optional[NodeRef]:
        """Ищет лучший узел по роли с учётом топологии, семантики и overlay.

        Порядок:
        1. Фильтр по топологии (zone_id, level)
        2. Фильтр по семантике (role)
        3. Фильтр по тегам (filters)
        4. Фильтр по резервациям (reserved_nodes)
        5. Скоринг: dist_weight + tag_bonus + safety_penalty + reservation_penalty
        6. Возврат лучшего
        """
        # 1+2. Топология + Семантика
        candidates = [n for n in self._graph.values() if n.role == role]
        if origin_zone:
            candidates = [n for n in candidates if n.zone_id == origin_zone]
        if origin_level:
            candidates = [n for n in candidates if n.level == origin_level]

        if not candidates:
            # Fallback: TRANSITION узлы для выхода из зоны
            if origin_zone:
                transitions = [
                    n
                    for n in self._graph.values()
                    if n.role == NodeRole.TRANSITION and n.zone_id == origin_zone
                ]
                if transitions:
                    candidates = transitions
                    logger.debug(
                        f"[SPATIAL] Роль {role.value} не найдена в зоне {origin_zone}, "
                        f"fallback на {len(transitions)} TRANSITION узлов"
                    )
            if not candidates:
                return None

        # 3. Фильтр по тегам
        if filters:
            candidates = [n for n in candidates if all(t in n.tags for t in filters)]
            if not candidates:
                return None

        # 4. Фильтр по резервациям
        filtered = []
        for n in candidates:
            holder = self._overlay.reserved_nodes.get(n.node_id)
            if holder is None or holder == requesting_npc_id:
                filtered.append(n)
            elif urgency == Urgency.URGENT:
                # URGENT: допускаем, но с штрафом в скоринге
                filtered.append(n)
        candidates = filtered

        if not candidates:
            return None

        # 5. Скоринг
        scored = []
        for node in candidates:
            score = self._compute_score(
                node, origin_xy, filters, urgency, requesting_npc_id
            )
            scored.append((score, node.node_id, node))

        # Детерминированная сортировка: score ↓, node_id ↑
        scored.sort(key=lambda x: (-x[0], x[1]))

        return scored[0][2]

    def _compute_score(
        self,
        node: NodeRef,
        origin_xy: Optional[Tuple[float, float]],
        filters: Optional[List[str]],
        urgency: Urgency,
        requesting_npc_id: Optional[str],
    ) -> float:
        """Взвешенный скоринг узла. Семантика > Геометрия."""
        score = 0.0

        # Дистанция (геометрия — вторична)
        if origin_xy:
            dist = self.world_distance(origin_xy, node.xy)
            score += self._dist_weight(dist, urgency)

        # Бонус за теги (семантика — первична)
        if filters:
            match_count = sum(1 for t in filters if t in node.tags)
            score += match_count * 5.0

        # Штраф за риск (безопасность)
        score += self._safety_penalty(node, urgency)

        # Штраф за резервацию
        holder = self._overlay.reserved_nodes.get(node.node_id)
        if holder is not None and holder != requesting_npc_id:
            if urgency == Urgency.URGENT:
                score -= 3.0  # URGENT снижает, но не обнуляет
            else:
                score -= 15.0  # Обычный — сильный штраф

        # Штраф за плотность
        crowd = self._overlay.crowd_density.get(node.node_id, 0.0)
        score -= crowd * 4.0

        return score

    def _dist_weight(self, dist: float, urgency: Urgency) -> float:
        """Вес дистанции. URGENT усиливает предпочтение ближних целей."""
        base = -dist * 0.5
        return base * 1.5 if urgency == Urgency.URGENT else base

    def _safety_penalty(self, node: NodeRef, urgency: Urgency) -> float:
        """Штраф за риск и темноту. URGENT снижает страх, но не отключает."""
        risk = self._overlay.risk_zones.get(node.node_id, 0.0)
        light = self._overlay.light_levels.get(node.node_id, 0.8)
        base_penalty = -risk * 4.0 - (1.0 - light) * 2.0
        return base_penalty * 0.3 if urgency == Urgency.URGENT else base_penalty

    # ── Поиск пути ────────────────────────────────────────────────────

    def find_path(
        self,
        start_xy: Tuple[float, float],
        target_node: NodeRef,
        urgency: Urgency = Urgency.NORMAL,
    ) -> List[NodeRef]:
        """A* с динамической стоимостью рёбер. Учитывает overlay и urgency.

        Возвращает список NodeRef от ближайшего к start_xy узла до target_node.
        Пустой список если путь не найден.
        """
        if target_node is None:
            return []
        target_id = target_node.node_id

        # Находим стартовый узел (ближайший к start_xy в той же зоне)
        start_node = self.get_nearest(target_node.zone_id, start_xy, urgency)
        if start_node is None:
            print(f"[FIND_PATH_DIAG] FAIL: start_node is None. zone={target_node.zone_id} xy={start_xy}")
            return []
        if start_node.node_id == target_id:
            print(f"[FIND_PATH_DIAG] SUCCESS: start_node is target. node={start_node.node_id}")
            return [start_node]

        print(f"[FIND_PATH_DIAG] start_xy={start_xy} target={target_id} start_node={start_node.node_id} zone={target_node.zone_id}")

        # Кэш
        cache_key = (
            start_node.node_id,
            target_id,
            self._overlay.compute_hash(),
            urgency,
        )
        cached = self._path_cache.get(cache_key)
        if cached is not None:
            self._path_cache.move_to_end(cache_key)  # LRU: помечаем как недавно использованный
            return cached

        # A*
        open_set: List[Tuple[float, float, str]] = []  # (f_score, counter, node_id)
        counter = 0
        heapq.heappush(open_set, (0.0, counter, start_node.node_id))

        came_from: Dict[str, str] = {}
        g_score: Dict[str, float] = {start_node.node_id: 0.0}

        while open_set:
            _, _, current_id = heapq.heappop(open_set)

            if current_id == target_id:
                # Восстановление пути
                path = self._reconstruct_path(came_from, current_id)
                self._path_cache[cache_key] = path
                if len(self._path_cache) > self._path_cache_max_size:
                    self._path_cache.popitem(last=False)  # LRU: удаляем самый старый
                return path

            current_node = self._graph.get(current_id)
            if current_node is None:
                continue

            for neighbor_id in self._connections.get(current_id, set()):
                neighbor_node = self._graph.get(neighbor_id)
                if neighbor_node is None:
                    continue

                # S129 FIX: P4-04 — A* obstacle-aware.
                # Если ребро заблокировано геометрией (стена, стол), считаем его непроходимым.
                if self.is_segment_blocked(
                    current_node.x, current_node.y, neighbor_node.x, neighbor_node.y
                ):
                    continue

                edge_cost = self._edge_cost(current_node, neighbor_node, urgency)
                tentative_g = g_score[current_id] + edge_cost

                if tentative_g < g_score.get(neighbor_id, float("inf")):
                    came_from[neighbor_id] = current_id
                    g_score[neighbor_id] = tentative_g
                    # Эвристика = евклидова дистанция до цели
                    h = self.world_distance(neighbor_node.xy, target_node.xy)
                    f = tentative_g + h
                    counter += 1
                    heapq.heappush(open_set, (f, counter, neighbor_id))

        # Путь не найден
        logger.warning(
            f"[SPATIAL] Путь не найден: {start_node.node_id} → {target_id} "
            f"(urgency={urgency.value})"
        )
        print(f"[FIND_PATH_DIAG] FAIL: A* no path. start={start_node.node_id} target={target_id} connections={self._connections.get(start_node.node_id, set())}")
        return []

    def _edge_cost(
        self, from_node: NodeRef, to_node: NodeRef, urgency: Urgency
    ) -> float:
        """Динамическая стоимость ребра. Дистанция + overlay-модификаторы."""
        base_dist = self.world_distance(from_node.xy, to_node.xy)

        crowd = self._overlay.crowd_density.get(to_node.node_id, 0.0)
        risk = self._overlay.risk_zones.get(to_node.node_id, 0.0)
        light = self._overlay.light_levels.get(to_node.node_id, 0.8)
        blocked = to_node.node_id in self._overlay.blocked_nodes

        cost = base_dist
        cost += crowd * 3.0
        cost += risk * 4.0
        cost += (1.0 - light) * 2.0
        if blocked:
            cost += 50.0 if urgency == Urgency.NORMAL else 15.0

        return cost

    def _reconstruct_path(
        self, came_from: Dict[str, str], current_id: str
    ) -> List[NodeRef]:
        """Восстанавливает путь из came_from маппинга."""
        path_ids = [current_id]
        while current_id in came_from:
            current_id = came_from[current_id]
            path_ids.append(current_id)
        path_ids.reverse()
        return [self._graph[nid] for nid in path_ids if nid in self._graph]

    # ── Утилиты ───────────────────────────────────────────────────────

    def get_central_node(self):
        """Возвращает центральную ноду графа (ближайшую к среднему арифметическому координат)."""
        if not self._graph.nodes:
            return None
        best_node = None
        min_dist = float("inf")
        cx = sum(n.x for n in self._graph.nodes.values()) / len(self._graph.nodes)
        cy = sum(n.y for n in self._graph.nodes.values()) / len(self._graph.nodes)
        for node in self._graph.nodes.values():
            d = (node.x - cx) ** 2 + (node.y - cy) ** 2
            if d < min_dist:
                min_dist = d
                best_node = node
        return best_node

    def get_nearest(
        self,
        zone_id: str,
        origin_xy: Tuple[float, float],
        urgency: Urgency = Urgency.NORMAL,
    ) -> Optional[NodeRef]:
        """Ближайший узел в зоне по евклидовой дистанции."""
        candidates = [n for n in self._graph.values() if n.zone_id == zone_id]
        if not candidates:
            return None

        best: Optional[NodeRef] = None
        best_dist = float("inf")
        for node in candidates:
            d = self.world_distance(origin_xy, node.xy)
            if d < best_dist:
                best_dist = d
                best = node
        return best

    def get_furthest(
        self,
        zone_id: str,
        origin_xy: Tuple[float, float],
        exclude_node_ids: Optional[Set[str]] = None,
    ) -> Optional[NodeRef]:
        """Самый дальний узел в зоне. Для FLEE: позиция угрозы → самый дальний узел.
        exclude_node_ids — узлы, которые нужно исключить (например, текущий узел NPC)."""
        candidates = [n for n in self._graph.values() if n.zone_id == zone_id]
        if exclude_node_ids:
            candidates = [n for n in candidates if n.node_id not in exclude_node_ids]
        if not candidates:
            return None

        best: Optional[NodeRef] = None
        best_dist = -1.0
        for node in candidates:
            d = self.world_distance(origin_xy, node.xy)
            if d > best_dist:
                best_dist = d
                best = node
        return best

    def is_reachable(self, node: NodeRef, urgency: Urgency = Urgency.NORMAL) -> bool:
        """Проверяет достижимость узла с учётом overlay."""
        if node.node_id in self._overlay.blocked_nodes:
            return urgency == Urgency.URGENT
        return node.node_id in self._graph

    @staticmethod
    def world_distance(
        xy1: Tuple[float, float],
        xy2: Tuple[float, float],
    ) -> float:
        """Евклидова дистанция в мировых координатах. 1 unit = 1 meter."""
        return math.dist(xy1, xy2)

    # ── Поиск по роли ─────────────────────────────────────────────────

    # ── CFRM Layer 1: Cluster Graph ───────────────────────────────────

    def build_cluster_graph(self) -> ClusterGraph:
        """Строит ClusterGraph (CFRM Layer 1) из текущего макро-графа.

        1 макро-узел = 1 причинный кластер.
        Границы кластера (boundary_cells) = его связи с другими макро-узлами.
        Вызывается при загрузке локации и при изменении топологии.
        """
        clusters: Dict[str, ClusterDef] = {}
        for node_id, node_ref in self._graph.items():
            connections = self._connections.get(node_id, set())
            # Границы — это те связи, которые ведут в другие существующие узлы (кластеры)
            boundaries = frozenset(
                conn_id for conn_id in connections if conn_id in self._graph
            )
            clusters[node_id] = ClusterDef(
                cluster_id=node_id,
                boundary_cells=boundaries,
            )
        return ClusterGraph(clusters=clusters)

    # ── Поиск по роли ─────────────────────────────────────────────────

    def find_nodes_by_role(
        self,
        role: NodeRole,
        zone_id: Optional[str] = None,
    ) -> List[NodeRef]:
        """Возвращает все узлы с указанной ролью (опционально в зоне)."""
        results = [n for n in self._graph.values() if n.role == role]
        if zone_id:
            results = [n for n in results if n.zone_id == zone_id]
        return results
