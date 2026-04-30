# -*- coding: utf-8 -*-
"""
TransitTracker — хранит NPC в пути между узлами графа.

Когда MovementIntent.movement_mode="path":
  1. MovementEngine вычисляет путь через LocationGraph.find_path()
  2. Регистрирует в TransitTracker (не телепортирует)
  3. Каждый тик: advance_all() двигает всех на 1 шаг → SceneChange

Порядок в TickOrchestrator:
  advance_all()  → process_intents()
  (сначала завершаем движение, потом обрабатываем новые инты)

path: backend/app/services/spatial/transit_tracker.py
Назначение: Хранит NPC в пути между узлами графа. Продвигает на 1 шаг за тик.
Зависимости: spatial.location_graph, scene_change
Основные сущности: TransitTracker
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from app.services.scene_change import SceneChange, ChangeType

logger = logging.getLogger(__name__)


@dataclass
class _Transit:
    """Один NPC в пути."""
    npc_id: str
    location_id: str
    path: List[str]          # ["A", "B", "C"] — полный путь
    step: int = 0            # текущий индекс в path (0 = ещё не двигался)
    reason: str = ""

    @property
    def current_node(self) -> str:
        return self.path[self.step]

    @property
    def is_finished(self) -> bool:
        return self.step >= len(self.path) - 1

    def advance(self) -> Optional[str]:
        """Продвигает на 1 шаг. Возвращает новый node_id или None если путь завершён."""
        if self.is_finished:
            return None
        self.step += 1
        return self.path[self.step]


class TransitTracker:
    """Хранит всех NPC в пути. Без персистенции (working memory)."""

    def __init__(self) -> None:
        # {(location_id, npc_id): _Transit}
        self._transits: Dict[Tuple[str, str], _Transit] = {}

    def register(
        self,
        npc_id: str,
        location_id: str,
        path: List[str],
        reason: str = "",
        priority: float = 0.5,
    ) -> bool:
        """Регистрирует NPC в пути.
        
        Returns:
            True если зарегистрирован, False если путь слишком короткий
            или NPC уже в пути.
        """
        key = (location_id, npc_id)
        if key in self._transits:
            logger.debug(f"[TRANSIT] {npc_id} уже в пути, игнорируем")
            return False
        if len(path) < 2:
            return False

        self._transits[key] = _Transit(
            npc_id=npc_id,
            location_id=location_id,
            path=path,
            step=0,
            reason=reason,
            priority=priority,
        )
        logger.debug(f"[TRANSIT] {npc_id} начал путь: {' → '.join(path)}")
        return True

    def advance_all(
        self,
        graph_by_location: Dict[str, "LocationGraph"],
        tick: int,
    ) -> List[SceneChange]:
        """Продвигает всех NPC в пути на 1 шаг.
        
        Args:
            graph_by_location: {location_id: LocationGraph} для резолва координат
            tick: номер тика для SceneChange
            
        Returns:
            SceneChange для каждого продвинутого NPC
        """
        changes: List[SceneChange] = []
        finished_keys: list = []

        for key, transit in self._transits.items():
            location_id, npc_id = key
            new_node = transit.advance()

            if new_node is None:
                # Путь завершён
                finished_keys.append(key)
                logger.debug(f"[TRANSIT] {npc_id} прибыл в {transit.current_node}")
                continue

            # Резолвим координаты нового узла
            graph = graph_by_location.get(location_id)
            if graph is None:
                logger.warning(f"[TRANSIT] Нет графа для {location_id}")
                continue

            node = graph.get_node(new_node)
            if node is None:
                logger.warning(f"[TRANSIT] Узел '{new_node}' не найден в {location_id}")
                continue

            changes.append(SceneChange(
                type=ChangeType.NPC_POSITION,
                target=npc_id,
                field="local_position",
                value={"x": node.x, "y": node.y},
                cause=f"transit:{transit.reason}",
                tick=tick,
            ))

        # Удаляем завершившие
        for key in finished_keys:
            del self._transits[key]

        return changes

    def is_in_transit(self, location_id: str, npc_id: str) -> bool:
        return (location_id, npc_id) in self._transits

    def cancel(self, location_id: str, npc_id: str) -> bool:
        """Прерывает движение NPC."""
        key = (location_id, npc_id)
        if key in self._transits:
            del self._transits[key]
            logger.debug(f"[TRANSIT] {npc_id} — движение прервано")
            return True
        return False

    def get_current_priority(self, location_id: str, npc_id: str) -> float | None:
        """Возвращает приоритет текущего пути NPC или None если не в пути."""
        transit = self._transits.get((location_id, npc_id))
        return transit.priority if transit else None

    def get_current_node(self, location_id: str, npc_id: str) -> str | None:
        """Возвращает текущий узел NPC в пути или None если не в пути."""
        transit = self._transits.get((location_id, npc_id))
        return transit.current_node if transit else None

    def active_count(self) -> int:
        return len(self._transits)