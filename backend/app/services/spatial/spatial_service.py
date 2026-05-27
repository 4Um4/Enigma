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

from __future__ import annotations

import heapq
import logging
import math
from typing import Dict, List, Optional, Set, Tuple

from app.models.cfrm import ClusterDef, ClusterGraph
from app.models.spatial_contracts import (
    NodeRef,
    NodeRole,
    SpatialOverlay,
    Urgency,
)

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
        scene_state: dict,
    ) -> Optional["SpatialService"]:
        """Фабрика: компилирует граф и оверлей для текущей локации и сцены."""
        from app.services.spatial.graph_compiler import compile_graph, load_editor_json
        from app.services.spatial.spatial_overlay import build_overlay_from_scene

        editor_data = load_editor_json(campaign_id, location_id)
        if not editor_data:
            logger.warning(f"[SPATIAL] editor JSON не найден для {campaign_id}/{location_id}")
            return None

        graph, connections, alias_map = compile_graph(editor_data, location_id)
        overlay = build_overlay_from_scene(scene_state)

        return SpatialService(graph, connections, alias_map, overlay, location_id=location_id)

    def __init__(
        self,
        graph: Dict[str, NodeRef],
        connections: Dict[str, Set[str]],
        alias_map: Dict[str, str],
        overlay: SpatialOverlay,
        location_id: str = "",  # Сохраняем принадлежность к локации для динамического резолва
    ) -> None:
        self._graph = graph            # canonical_id → NodeRef
        self._connections = connections # canonical_id → set[canonical_id]
        self._alias_map = alias_map    # legacy_id → canonical_id
        self._overlay = overlay
        self._location_id = location_id  # ADR-052: Сохраняем для мультисценового резолва
        self._path_cache: Dict[Tuple[str, str, str, Urgency], List[NodeRef]] = {}

    # ── Overlay обновление ────────────────────────────────────────────

    def set_overlay(self, overlay: SpatialOverlay) -> None:
        """Обновляет overlay. Инвалидирует кэш путей при изменении."""
        new_hash = overlay.compute_hash()
        old_hash = self._overlay.compute_hash()
        if new_hash != old_hash:
            self._path_cache.clear()
        self._overlay = overlay

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
        candidates = [
            n for n in self._graph.values()
            if n.role == role
        ]
        if origin_zone:
            candidates = [n for n in candidates if n.zone_id == origin_zone]
        if origin_level:
            candidates = [n for n in candidates if n.level == origin_level]

        if not candidates:
            # Fallback: TRANSITION узлы для выхода из зоны
            if origin_zone:
                transitions = [
                    n for n in self._graph.values()
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
            candidates = [
                n for n in candidates
                if all(t in n.tags for t in filters)
            ]
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
            score = self._compute_score(node, origin_xy, filters, urgency, requesting_npc_id)
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
        target_id = target_node.node_id

        # Находим стартовый узел (ближайший к start_xy в той же зоне)
        start_node = self.get_nearest(target_node.zone_id, start_xy, urgency)
        if start_node is None:
            return []
        if start_node.node_id == target_id:
            return [start_node]

        # Кэш
        cache_key = (start_node.node_id, target_id, self._overlay.compute_hash(), urgency)
        cached = self._path_cache.get(cache_key)
        if cached is not None:
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
                return path

            current_node = self._graph.get(current_id)
            if current_node is None:
                continue

            for neighbor_id in self._connections.get(current_id, set()):
                neighbor_node = self._graph.get(neighbor_id)
                if neighbor_node is None:
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
        return []

    def _edge_cost(self, from_node: NodeRef, to_node: NodeRef, urgency: Urgency) -> float:
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

    def _reconstruct_path(self, came_from: Dict[str, str], current_id: str) -> List[NodeRef]:
        """Восстанавливает путь из came_from маппинга."""
        path_ids = [current_id]
        while current_id in came_from:
            current_id = came_from[current_id]
            path_ids.append(current_id)
        path_ids.reverse()
        return [self._graph[nid] for nid in path_ids if nid in self._graph]

    # ── Утилиты ───────────────────────────────────────────────────────

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
    ) -> Optional[NodeRef]:
        """Самый дальний узел в зоне. Для FLEE: позиция угрозы → самый дальний узел."""
        candidates = [n for n in self._graph.values() if n.zone_id == zone_id]
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