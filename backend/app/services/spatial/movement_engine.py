# backend/app/services/spatial/movement_engine.py
# Назначение: Слой 2 Execution. MovementIntent → SceneChange с {x, y}.
# Получает целевой узел графа, резолвит в координаты, генерирует SceneChange.
# Зависимости: app.domain.movement, app.services.scene_change, app.services.spatial.location_graph

from __future__ import annotations

import logging
from typing import List, Optional

from app.domain.movement import MovementIntent
from app.services.scene_change import SceneChange, ChangeType
from app.services.spatial.location_graph import LocationGraph, load_graph, invalidate_graph_cache
from app.services.spatial.transit_tracker import TransitTracker

logger = logging.getLogger(__name__)


class MovementEngine:
    """Слой 2: Execution. Конвертирует намерения в изменения позиции.
    
    Не принимает решений — только выполняет:
    1. Берёт MovementIntent (target_node_id)
    2. Резолвит через LocationGraph → {x, y}
    3. Генерирует SceneChange(field="local_position")
    """

    def __init__(self, transit_tracker: TransitTracker | None = None) -> None:
        self._graphs: dict[str, LocationGraph] = {}
        self._transit_tracker = transit_tracker or TransitTracker()

    def _get_graph(self, location_id: str) -> Optional[LocationGraph]:
        """Ленивая загрузка графа с кэшированием."""
        if location_id not in self._graphs:
            try:
                self._graphs[location_id] = load_graph(location_id)
            except Exception as e:
                logger.warning(f"[MOVEMENT_ENGINE] Граф не найден для {location_id}: {e}")
                return None
        return self._graphs[location_id]

    def set_transit_tracker(self, tracker: "TransitTracker") -> None:
        """Устанавливает TransitTracker для pathing-режима."""
        self._transit_tracker = tracker

    def invalidate_cache(self, location_id: Optional[str] = None) -> None:
        """Сброс кэша графов."""
        if location_id:
            self._graphs.pop(location_id, None)
            invalidate_graph_cache(location_id)
        else:
            self._graphs.clear()
            invalidate_graph_cache()

    def process_intents(
        self,
        intents: List[MovementIntent],
        tick: int,
    ) -> List[SceneChange]:
        """Обрабатывает список намерений → список SceneChange.
        
        Для каждого intent:
        - Если целевой узел найден в графе → SceneChange с {x, y}
        - Если не найден → логируем warning, пропускаем
        """
        changes: List[SceneChange] = []

        # Группируем по location_id для загрузки графа один раз
        by_location: dict[str, List[MovementIntent]] = {}
        for intent in intents:
            # Извлекаем location_id из reason или из npc dict — 
            # для MVP берём из графа по первому попавшемуся intent
            loc = self._extract_location(intent)
            by_location.setdefault(loc, []).append(intent)

        for location_id, loc_intents in by_location.items():
            graph = self._get_graph(location_id)
            if not graph:
                for intent in loc_intents:
                    logger.warning(
                        f"[MOVEMENT_ENGINE] Нет графа для {intent.npc_id} → {intent.target_node_id}"
                    )
                continue

            for intent in loc_intents:
                node = graph.get_node(intent.target_node_id)
                if not node:
                    logger.warning(
                        f"[MOVEMENT_ENGINE] Узел '{intent.target_node_id}' не найден "
                        f"для {intent.npc_id} в {location_id}"
                    )
                    continue

                if intent.movement_mode == "path":
                    # Патхинг: регистрируем в TransitTracker, не телепортируем
                    from_node = intent.from_node_id
                    if from_node:
                        path = graph.find_path(from_node, intent.target_node_id)
                        if path:
                            self._transit_tracker.register(
                                npc_id=intent.npc_id,
                                location_id=location_id,
                                path=path,
                                reason=intent.reason,
                            )
                        else:
                            logger.warning(
                                f"[MOVEMENT_ENGINE] Путь не найден: "
                                f"{from_node} → {intent.target_node_id} для {intent.npc_id}"
                            )
                    else:
                        # Не знаем текущую позицию — фоллбэк на телепорт
                        changes.append(SceneChange(
                            type=ChangeType.NPC_POSITION,
                            target=intent.npc_id,
                            field="local_position",
                            value={"x": node.x, "y": node.y},
                            cause=f"movement_engine:{intent.reason}",
                            tick=tick,
                        ))
                else:
                    # Instant — текущее поведение (телепорт)
                    changes.append(SceneChange(
                        type=ChangeType.NPC_POSITION,
                        target=intent.npc_id,
                        field="local_position",
                        value={"x": node.x, "y": node.y},
                        cause=f"movement_engine:{intent.reason}",
                        tick=tick,
                    ))

        return changes

    @staticmethod
    def _extract_location(intent: MovementIntent) -> str:
        """Берёт location_id напрямую из intent."""
        return intent.location_id