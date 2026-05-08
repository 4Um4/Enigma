# backend/app/services/spatial/movement_engine.py
# Назначение: Слой 2 Execution. MovementIntent → SceneChange с {x, y}.
# Получает целевой узел графа, резолвит в координаты, генерирует SceneChange.
# Зависимости: app.domain.movement, app.services.scene_change, app.services.spatial.location_graph

from __future__ import annotations

import logging
from typing import List, Optional

from app.domain.movement import MovementIntent
from app.services.scene_change import SceneChange, ChangeType
from app.services.spatial.transit_tracker import TransitTracker

logger = logging.getLogger(__name__)


class MovementEngine:
    """Слой 2: Execution. Конвертирует намерения в изменения позиции.
    
    Не принимает решений — только выполняет:
    1. Берёт MovementIntent (target_node_id)
    2. Резолвит через LocationGraph → {x, y}
    3. Генерирует SceneChange(field="local_position")
    """

    def __init__(self) -> None:
        # ADR-0010: TransitTracker ампутирован. Макро-перемещение — Semantic Relocation.
        # SpatialService v1.2 — инжекция извне (DI)
        self._spatial_service: Optional[Any] = None

    def set_spatial_service(self, svc: Any) -> None:
        """Инжекция SpatialService для A* с учётом оверлея."""
        self._spatial_service = svc


    def get_current_node(self, location_id: str, npc_id: str) -> str | None:
        """Реальный текущий узел NPC если он в пути, иначе None."""
        return self._transit_tracker.get_current_node(location_id, npc_id)

    def set_transit_tracker(self, tracker: "TransitTracker") -> None:
        """Устанавливает TransitTracker для pathing-режима."""
        self._transit_tracker = tracker


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
            svc = self._spatial_service
            if not svc:
                for intent in loc_intents:
                    logger.error(
                        f"[MOVEMENT_ENGINE] Нет SpatialService для {intent.npc_id} → {intent.target_node_id}"
                    )
                continue

            for intent in loc_intents:
                # Резолвим целевой узел в координаты
                target_x, target_y = None, None
                target_ref = None  # NodeRef для SpatialService.find_path
                
                target_ref = svc.get_node(intent.target_node_id)
                if not target_ref:
                    # ADR-0008: Пробуем с префиксом локации (tavern_silver_wolf:main_hall)
                    target_ref = svc.get_node(f"{location_id}:{intent.target_node_id}")
                if not target_ref:
                    target_ref = svc.get_node(f"{location_id}:entrance") or svc.get_node(f"{location_id}:main_hall")
                    if target_ref:
                        logger.debug(f"[MOVEMENT_ENGINE] Целевая микро-зона '{intent.target_node_id}' не найдена, фоллбэк на {target_ref.node_id}")
                        
                if target_ref:
                    target_x, target_y = target_ref.x, target_ref.y
                else:
                    logger.warning(
                        f"[MOVEMENT_ENGINE] Узел '{intent.target_node_id}' не найден "
                        f"для {intent.npc_id} в {location_id}"
                    )
                    continue

                # ADR-0010: Semantic Relocation. Макро-движение всегда атомарно.
                # DecisionHub решает ЧТО (approach), эта функция решает КУДА (целевой узел).
                # SceneStateManager атомарно резолвит узел в local_position (x,y).
                
                # Резолвим целевой узел для фоллбэка и валидации
                target_ref = svc.get_node(intent.target_node_id)
                if not target_ref:
                    # ADR-0008: Пробуем с префиксом локации (tavern_silver_wolf:main_hall)
                    target_ref = svc.get_node(f"{location_id}:{intent.target_node_id}")
                if not target_ref:
                    target_ref = svc.get_node(f"{location_id}:entrance") or svc.get_node(f"{location_id}:main_hall")
                    if target_ref:
                        logger.debug(f"[MOVEMENT_ENGINE] Целевая зона '{intent.target_node_id}' не найдена, фоллбэк на {target_ref.node_id}")

                if not target_ref:
                    logger.warning(
                        f"[MOVEMENT_ENGINE] Узел '{intent.target_node_id}' не найден "
                        f"для {intent.npc_id} в {location_id}"
                    )
                    continue
                
                # Семантическая релокация: обновляем только position (семантический узел).
                # SceneStateManager применит это изменение и вычислит новые x, y.
                changes.append(SceneChange(
                    type=ChangeType.NPC_POSITION,
                    target=intent.npc_id,
                    field="position",
                    value=intent.target_node_id,
                    cause=f"semantic_relocation:{intent.reason}",
                    tick=tick,
                ))
                logger.info(f"[PIPELINE][MOVEMENT][RELOCATE] npc={intent.npc_id} → zone={intent.target_node_id} reason={intent.reason}")

        return changes

    @staticmethod
    def _extract_location(intent: MovementIntent) -> str:
        """Берёт location_id напрямую из intent."""
        return intent.location_id