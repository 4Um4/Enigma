"""
path: backend/app/services/spatial/spatial_query_service.py
Назначение: Authoritative Spatial Spine (ADR-048). Единственный легитимный способ
получить пространственную истину для decision/perception/combat/movement.
Зависимости: app.services.spatial.spatial_runtime, app.models.cfrm
Основные сущности: SpatialQueryService


"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.models.cfrm import ClusterOccupancy
from app.services.spatial.spatial_runtime import (
    euclidean_distance,
    is_line_of_sight_clear,
)


class SpatialQueryService:
    """Единственный авторитет для пространственных запросов.

    ADR-048: Ни один decision-capable подсистема не имеет права читать
    spatial truth из scene_state напрямую. Только через этот сервис.
    """

    def __init__(
        self,
        npc_positions: Dict[str, dict],
        cluster_occupancy: Optional[ClusterOccupancy] = None,
        scene_state: Optional[Dict[str, Any]] = None,
    ) -> None:
        # Внутреннее хранилище. Не экспортируется наружу.
        self._npc_positions = npc_positions or {}
        self._cluster_occupancy = cluster_occupancy
        self._scene_state = scene_state or {}

    def get_entity_position(self, entity_id: str) -> Optional[Dict[str, Any]]:
        """Возвращает словарь с 'local_position', 'position', 'node_id' или None."""
        return self._npc_positions.get(entity_id)

    def distance(self, entity_a: str, entity_b: str) -> float:
        """Евклидово расстояние между двумя сущностями. 999.0 если данных нет."""
        pos_a = self._npc_positions.get(entity_a, {})
        pos_b = self._npc_positions.get(entity_b, {})
        return euclidean_distance(pos_a, pos_b)

    def distance_player(self, npc_id: str) -> float:
        """Расстояние от NPC до игрока. ADR-048: игрок = entity 'player'."""
        return self.distance(npc_id, "player")

    def player_distances(self, npc_ids: List[str]) -> Dict[str, float]:
        """Словарь дистанций от игрока до списка NPC."""
        return {nid: self.distance_player(nid) for nid in npc_ids}

    def get_nearest_npc(self, source_id: str, npc_ids: List[str]) -> Optional[str]:
        """Возвращает ID ближайшего NPC к source_id, исключая его самого."""
        _min_dist = float("inf")
        _nearest = None
        for nid in npc_ids:
            if nid == source_id:
                continue
            _d = self.distance(source_id, nid)
            if _d < _min_dist:
                _min_dist = _d
                _nearest = nid
        return _nearest

    def visibility(self, entity_a: str, entity_b: str) -> bool:
        """Проверка прямой видимости между двумя сущностями."""
        pos_a = self._npc_positions.get(entity_a, {})
        pos_b = self._npc_positions.get(entity_b, {})
        local_a = pos_a.get("local_position", {})
        local_b = pos_b.get("local_position", {})
        ax, ay = local_a.get("x", 0.0), local_a.get("y", 0.0)
        bx, by = local_b.get("x", 0.0), local_b.get("y", 0.0)
        dist = euclidean_distance(pos_a, pos_b)
        return is_line_of_sight_clear(ax, ay, bx, by, self._scene_state)

    def cluster_relation(self, entity_a: str, entity_b: str) -> Optional[str]:
        """Отношение кластеров: 'same', 'adjacent', 'distant', None если данных нет."""
        if not self._cluster_occupancy:
            return None
        cl_a = self._cluster_occupancy.get_cluster(entity_a)
        cl_b = self._cluster_occupancy.get_cluster(entity_b)
        if not cl_a or not cl_b:
            return None
        if cl_a == cl_b:
            return "same"
        # Соседство проверяем через граф кластеров
        neighbors = self._cluster_occupancy.cluster_to_entities.get(cl_a, set())
        # Упрощённая эвристика: если есть хотя бы одна общая сущность в соседних кластерах
        return (
            "adjacent"
            if cl_b in self._cluster_occupancy.cluster_to_entities
            else "distant"
        )
