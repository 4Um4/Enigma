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
        # SpatialService v1.2 — инжекция извне (DI)
        self._spatial_service: Optional[Any] = None

    def set_spatial_service(self, svc: Any) -> None:
        """Инжекция SpatialService для A* с учётом оверлея."""
        self._spatial_service = svc

    def _get_graph(self, location_id: str) -> Optional[LocationGraph]:
        """Ленивая загрузка графа с кэшированием."""
        if location_id not in self._graphs:
            try:
                self._graphs[location_id] = load_graph(location_id)
            except Exception as e:
                logger.warning(f"[MOVEMENT_ENGINE] Граф не найден для {location_id}: {e}")
                return None
        return self._graphs[location_id]

    def get_current_node(self, location_id: str, npc_id: str) -> str | None:
        """Реальный текущий узел NPC если он в пути, иначе None."""
        return self._transit_tracker.get_current_node(location_id, npc_id)

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
            # SpatialService v1.2 — канонический путь, иначе fallback на LocationGraph
            svc = self._spatial_service
            graph = self._get_graph(location_id) if not svc else None
            
            if not svc and not graph:
                for intent in loc_intents:
                    logger.warning(
                        f"[MOVEMENT_ENGINE] Нет графа/SpatialService для {intent.npc_id} → {intent.target_node_id}"
                    )
                continue

            for intent in loc_intents:
                # Резолвим целевой узел в координаты
                target_x, target_y = None, None
                target_ref = None  # NodeRef для SpatialService.find_path
                
                if svc:
                    target_ref = svc.get_node(intent.target_node_id)
                    if target_ref:
                        target_x, target_y = target_ref.x, target_ref.y
                else:
                    # @deprecated: fallback на LocationGraph
                    node = graph.get_node(intent.target_node_id)
                    if node:
                        target_x, target_y = node.x, node.y
                        
                if target_x is None:
                    logger.warning(
                        f"[MOVEMENT_ENGINE] Узел '{intent.target_node_id}' не найден "
                        f"для {intent.npc_id} в {location_id}"
                    )
                    continue

                if intent.movement_mode == "path":
                    # D7: если NPC уже в пути — сравниваем приоритеты
                    current_priority = self._transit_tracker.get_current_priority(
                        location_id, intent.npc_id
                    )
                    if current_priority is not None and intent.priority <= current_priority:
                        logger.debug(
                            f"[MOVEMENT_ENGINE] {intent.npc_id}: "
                            f"новый intent (p={intent.priority}) не превосходит текущий путь "
                            f"(p={current_priority}), пропускаем"
                        )
                        continue

                    # Прерываем текущий путь если есть (новый приоритетнее)
                    if current_priority is not None:
                        self._transit_tracker.cancel(location_id, intent.npc_id)

                    # Патхинг: регистрируем в TransitTracker, не телепортируем
                    # Берём реальную позицию из TransitTracker если NPC уже в пути
                    from_node = self._transit_tracker.get_current_node(
                        location_id, intent.npc_id
                    ) or intent.from_node_id
                    if from_node:
                        path = []
                        if svc and target_ref:
                            # SpatialService v1.2: A* с учётом оверлея (риск, плотность)
                            from_ref = svc.get_node(from_node)
                            if from_ref:
                                path_refs = svc.find_path(from_ref.xy, target_ref)
                                # TransitTracker ожидает legacy-ID, денормализуем
                                path = [svc.denormalize_id(n.node_id) for n in path_refs]
                        else:
                            # @deprecated: fallback на LocationGraph
                            path = graph.find_path(from_node, intent.target_node_id)
                            
                        if len(path) >= 2:
                            self._transit_tracker.register(
                                npc_id=intent.npc_id,
                                location_id=location_id,
                                path=path,
                                reason=intent.reason,
                                priority=intent.priority,
                            )
                        elif len(path) == 1:
                            # NPC уже на целевом узле — ничего не делаем
                            logger.debug(
                                f"[MOVEMENT_ENGINE] {intent.npc_id}: "
                                f"уже на {intent.target_node_id}, пропускаем"
                            )
                        else:
                            # Путь не найден — фоллбэк на телепорт
                            logger.warning(
                                f"[MOVEMENT_ENGINE] Путь не найден: "
                                f"{from_node} → {intent.target_node_id} "
                                f"для {intent.npc_id}, фоллбэк на телепорт"
                            )
                            changes.append(SceneChange(
                                type=ChangeType.NPC_POSITION,
                                target=intent.npc_id,
                                field="local_position",
                                value={"x": target_x, "y": target_y},
                                cause=f"movement_engine_fallback:{intent.reason}",
                                tick=tick,
                            ))
                    else:
                        # Не знаем текущую позицию — фоллбэк на телепорт
                        changes.append(SceneChange(
                            type=ChangeType.NPC_POSITION,
                            target=intent.npc_id,
                            field="local_position",
                            value={"x": target_x, "y": target_y},
                            cause=f"movement_engine:{intent.reason}",
                            tick=tick,
                        ))
                else:
                    # Instant — текущее поведение (телепорт)
                    changes.append(SceneChange(
                        type=ChangeType.NPC_POSITION,
                        target=intent.npc_id,
                        field="local_position",
                        value={"x": target_x, "y": target_y},
                        cause=f"movement_engine:{intent.reason}",
                        tick=tick,
                    ))

        return changes

    @staticmethod
    def _extract_location(intent: MovementIntent) -> str:
        """Берёт location_id напрямую из intent."""
        return intent.location_id