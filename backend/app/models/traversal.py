"""
Файл: backend/app/models/traversal.py
Назначение: Хранилище визуальной кинематики и состояния перемещения, отделенное от каузальной позиции NPC.
Зависимости: dataclasses, typing
Основные сущности: TraversalState, TraversalRegistry

TODO: В будущем может потребоваться расширить TraversalState для поддержки сложных анимаций, разных типов перемещения (ползание, прыжки) и взаимодействия с окружением (препятствия, укрытия).
"""

from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional

@dataclass
class TraversalState:
    """Визуальная проекция перемещения. НЕ ЯВЛЯЕТСЯ частью личности или каузального пузыря NPC.
    Каузально NPC всё ещё в узле А, визуально — interpolирует к узлу Б.
    """
    npc_id: str
    from_node: str                      # Каузальный узел, откуда вышел
    target_node: str                    # Каузальный узел, куда идет
    path_waypoints: List[Tuple[float, float]] = field(default_factory=list) # Визуальные x,y точки
    current_waypoint_idx: int = 0
    progress: float = 0.0               # 0.0 - 1.0 прогресс между текущими waypoint
    speed: float = 1.5                  # Скорость визуальной интерполяции (м/с)
    started_at: float = 0.0             # game_time_seconds старта
    locomotion: str = "WALK"            # WALK, RUN, SNEAK, STAGGER
    status: str = "PENDING"             # PENDING, MOVING, ARRIVED, CANCELLED

@dataclass
class TraversalRegistry:
    """ECS-контейнер для транзитных процессов. Хранится в scene_state, НЕ в npc_state.
    Разделяет онтологию (каузальный узел) и кинематику (где спрайт прямо сейчас).
    """
    active_traversals: Dict[str, TraversalState] = field(default_factory=dict)

    def start(self, traversal: TraversalState) -> None:
        self.active_traversals[traversal.npc_id] = traversal

    def cancel(self, npc_id: str) -> None:
        if npc_id in self.active_traversals:
            self.active_traversals[npc_id].status = "CANCELLED"

    def remove(self, npc_id: str) -> None:
        self.active_traversals.pop(npc_id, None)

    def get_visual_position(self, npc_id: str) -> Optional[Tuple[float, float]]:
        """Возвращает визуальную позицию для presentation layer или None, если нет активного транзита"""
        trav = self.active_traversals.get(npc_id)
        if trav and trav.status in ("MOVING", "PENDING") and trav.current_waypoint_idx < len(trav.path_waypoints):
            return trav.path_waypoints[trav.current_waypoint_idx]
        return None