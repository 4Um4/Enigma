"""
backend/npc_movement.py
Система плавного визуального движения NPC.
Резолвит строковые позиции ("behind_bar") в координаты через LocationGraph,
строит A* путь, двигает NPC по пути каждый кадр.

path: /backend/npc_movement.py
Назначение: Плавное визуальное перемещение NPC при изменении строковой позиции из tick
Зависимости: movement_system, pathfinding, location_graph, math, dataclasses
Основные сущности: NpcMoveRequest, NpcMovementSystem
"""
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from movement_system import move_towards
from pathfinding import find_path
from app.services.spatial.location_graph import load_graph, LocationGraph


@dataclass
class NpcMoveRequest:
    """Активный запрос на перемещение NPC"""
    npc_id: str
    target_position: str  # строковый id узла ("behind_bar")
    target_x: float
    target_y: float
    path: List[Tuple[float, float]] = field(default_factory=list)
    path_index: int = 0
    arrived: bool = False


@dataclass
class _NpcVisualState:
    """Отслеживает строковую позицию для детекта изменений"""
    last_position_str: str = ""


class NpcMovementSystem:
    """
    Управляет плавным движением NPC.
    При получении новой строковой позиции — строит путь и двигает по нему каждый кадр.
    """

    def __init__(
        self,
        scene_w: float,
        scene_h: float,
        walls: List[dict],
        obstacles: List[dict],
        location_graph: LocationGraph,
    ) -> None:
        self.scene_w = scene_w
        self.scene_h = scene_h
        self.walls = walls
        self.obstacles = obstacles
        self.graph = location_graph

        # Активные перемещения
        self._active: Dict[str, NpcMoveRequest] = {}

        # Отслеживание строковых позиций для детекта изменений
        self._visual_states: Dict[str, _NpcVisualState] = {}

        # Скорость NPC — чуть медленнее игрока для реализма
        self.npc_step_size: float = 0.25
        self.npc_arrival_threshold: float = 0.6

    def _resolve_position(self, position_str: str) -> Optional[Tuple[float, float]]:
        """Переводит строковый id узла в координаты через граф"""
        if not position_str:
            return None
        node = self.graph.get_node(position_str)
        if node is None:
            return None
        return (node.x, node.y)

    def should_request_move(
        self,
        npc_id: str,
        new_position_str: str,
        scene_state: dict,
    ) -> bool:
        """
        Проверяет, изменилась ли строковая позиция NPC.
        Вызывать перед request_move чтобы не строить путь если не нужно.
        """
        state = self._visual_states.get(npc_id)
        if state is None:
            # Первый раз видим этого NPC
            npc_data = scene_state.get("npc_positions", {}).get(npc_id, {})
            lp = npc_data.get("local_position")
            has_coords = isinstance(lp, dict) and "x" in lp and "y" in lp
            if not has_coords and new_position_str:
                # Нет координат — нужно инициализировать из графа
                self._visual_states[npc_id] = _NpcVisualState(last_position_str="")
                return True
            # Координаты есть — просто запоминаем позицию без движения
            self._visual_states[npc_id] = _NpcVisualState(
                last_position_str=new_position_str
            )
            return False

        if state.last_position_str == new_position_str:
            return False

        # Если NPC уже двигается к этой цели — не перезапускаем
        active = self._active.get(npc_id)
        if active and active.target_position == new_position_str:
            return False

        return True

    def request_move(
        self,
        npc_id: str,
        new_position_str: str,
        scene_state: dict,
    ) -> bool:
        """
        Запрашивает перемещение NPC к новой строковой позиции.
        Возвращает True если путь построен, False если невозможно (телепорт).
        """
        target = self._resolve_position(new_position_str)
        if target is None:
            return False

        target_x, target_y = target

        # Текущая позиция NPC
        npc_data = scene_state.get("npc_positions", {}).get(npc_id, {})
        lp = npc_data.get("local_position")
        has_coords = isinstance(lp, dict) and "x" in lp and "y" in lp

        if not has_coords:
            # Нет координат — сразу ставим на целевую позицию без пути
            npc_data["local_position"] = {"x": round(target_x, 3), "y": round(target_y, 3)}
            self._visual_states.setdefault(
                npc_id, _NpcVisualState()
            ).last_position_str = new_position_str
            return True

        current_x = lp["x"]
        current_y = lp["y"]

        # Уже на месте — обновляем отслеживание без движения
        dist = math.hypot(current_x - target_x, current_y - target_y)
        if dist < self.npc_arrival_threshold:
            self._visual_states.setdefault(
                npc_id, _NpcVisualState()
            ).last_position_str = new_position_str
            return True

        # Строим путь через A* с humanize для живости
        path = find_path(
            start_x=current_x,
            start_y=current_y,
            goal_x=target_x,
            goal_y=target_y,
            scene_w=self.scene_w,
            scene_h=self.scene_h,
            walls=self.walls,
            obstacles=self.obstacles,
            humanize=True,
        )

        if path is None or len(path) < 2:
            # Путь не найдён — телепорт (лучше чем застрять навсегда)
            self._visual_states.setdefault(
                npc_id, _NpcVisualState()
            ).last_position_str = new_position_str
            return False

        self._active[npc_id] = NpcMoveRequest(
            npc_id=npc_id,
            target_position=new_position_str,
            target_x=target_x,
            target_y=target_y,
            path=path,
            path_index=1,  # индекс 0 = текущая позиция
        )
        return True

    def tick(self, scene_state: dict) -> None:
        """
        Продвигает всех NPC по их путям на один кадр.
        Обновляет local_position в scene_state напрямую.
        """
        npc_positions = scene_state.get("npc_positions", {})
        if not npc_positions:
            return

        completed: List[str] = []

        for npc_id, request in self._active.items():
            if request.arrived:
                completed.append(npc_id)
                continue

            npc_data = npc_positions.get(npc_id)
            if npc_data is None:
                completed.append(npc_id)
                continue

            lp = npc_data.get("local_position") or {}
            current_x = lp.get("x", 0.0)
            current_y = lp.get("y", 0.0)

            # Текущая waypoint
            if request.path_index >= len(request.path):
                request.arrived = True
                completed.append(npc_id)
                continue

            waypoint_x, waypoint_y = request.path[request.path_index]

            # Исключаем текущего NPC из коллизий
            other_positions = {
                nid: ndata
                for nid, ndata in npc_positions.items()
                if nid != npc_id
            }

            # Шаг к waypoint через movement_system
            result, waypoint_arrived = move_towards(
                from_x=current_x,
                from_y=current_y,
                to_x=waypoint_x,
                to_y=waypoint_y,
                walls=self.walls,
                obstacles=self.obstacles,
                npc_positions=other_positions,
                step_size=self.npc_step_size,
                arrival_threshold=self.npc_arrival_threshold * 0.5,
            )

            if result.success:
                # Обновляем local_position — это подхватит spatial_layer и рендерер
                if "local_position" not in npc_data or not isinstance(
                    npc_data["local_position"], dict
                ):
                    npc_data["local_position"] = {}
                npc_data["local_position"]["x"] = round(result.new_x, 3)
                npc_data["local_position"]["y"] = round(result.new_y, 3)

            if waypoint_arrived:
                request.path_index += 1
                if request.path_index >= len(request.path):
                    request.arrived = True
                    completed.append(npc_id)

        # Очищаем завершённые — обновляем отслеживание строковой позиции
        for npc_id in completed:
            request = self._active.pop(npc_id, None)
            if request:
                self._visual_states.setdefault(
                    npc_id, _NpcVisualState()
                ).last_position_str = request.target_position

    def is_moving(self, npc_id: str) -> bool:
        """NPC сейчас в движении?"""
        return npc_id in self._active

    def active_count(self) -> int:
        """Сколько NPC сейчас двигается"""
        return len(self._active)