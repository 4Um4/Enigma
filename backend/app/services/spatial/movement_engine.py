# backend/app/services/spatial/movement_engine.py
# Назначение: Слой 2 Execution. MovementIntent → SceneChange с {x, y}.
# Получает целевой узел графа, резолвит в координаты, генерирует SceneChange.
# Зависимости: app.domain.movement, app.services.scene_change, app.services.spatial.location_graph

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

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


    # ADR-0010: TransitTracker ампутирован. Методы удалены как мертвый код.


    def process_intents(
        self,
        intents: List[MovementIntent],
        tick: int,
        npc_positions: Optional[Dict] = None, # ADR-056: Collision Avoidance для LOD0
        campaign_id: Optional[str] = None,    # Для динамической сборки графа чужой локации
        scene_state: Optional[dict] = None,   # Для SpatialService.build_for_location
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
            print(
                f"[TRACE][ENGINE_RECEIVED] "
                f"npc={intent.npc_id} "
                f"reason={intent.reason} "
                f"local_xy={getattr(intent, 'local_target_xy', 'N/A')}"
            )
            loc = self._extract_location(intent)
            by_location.setdefault(loc, []).append(intent)

        for location_id, loc_intents in by_location.items():
            svc = self._resolve_spatial_service(location_id, campaign_id, scene_state)
            if not svc:
                for intent in loc_intents:
                    logger.error(
                        f"[MOVEMENT_ENGINE] Нет SpatialService для {intent.npc_id} → {intent.target_node_id} в {location_id}"
                    )
                continue

            for intent in loc_intents:
                changes.extend(self._process_single_intent(intent, svc, location_id, tick, npc_positions))

        return changes

    def _resolve_spatial_service(
        self,
        location_id: str,
        campaign_id: Optional[str],
        scene_state: Optional[dict],
    ) -> Optional[Any]:
        """Динамически резолвит SpatialService для запрошенной локации."""
        svc = self._spatial_service
        needs_dynamic = location_id and getattr(svc, '_location_id', '') != location_id
        
        # Если сервиса нет или локация чужая — пытаемся собрать на лету
        if not svc or needs_dynamic:
            if campaign_id and location_id and scene_state is not None:
                from app.services.spatial.spatial_service import SpatialService
                svc = SpatialService.build_for_location(campaign_id, location_id, scene_state)
            elif needs_dynamic:
                # Нет данных для сборки чужой локации — запрещаем использование текущего графа
                logger.error(
                    f"[MOVEMENT_ENGINE] Невозможно собрать граф для '{location_id}': "
                    f"нет campaign_id или scene_state. Текущий граф '{getattr(svc, '_location_id', '')}' отклонён."
                )
                return None
            
        return svc

    def _process_single_intent(
        self,
        intent: MovementIntent,
        svc: Any,
        location_id: str,
        tick: int,
        npc_positions: Optional[Dict],
    ) -> List[SceneChange]:
        """Обрабатывает один MovementIntent, возвращая список SceneChange."""
        # ADR-056: Приоритет LOD0. Если есть локальные координаты, макро-резолв узла не нужен.
        if intent.local_target_xy:
            return self._resolve_micro_movement(intent, tick, npc_positions)
        
        return self._resolve_macro_relocation(intent, svc, location_id, tick)

    def _resolve_micro_movement(
        self,
        intent: MovementIntent,
        tick: int,
        npc_positions: Optional[Dict],
    ) -> List[SceneChange]:
        """ADR-056: LOD0 микро-перемещение с Collision Avoidance (jitter)."""
        import random
        tx, ty = intent.local_target_xy
        collision_radius = 0.8
        best_x, best_y = tx, ty
        
        if npc_positions:
            for _ in range(10): # Увеличено с 5 для стабильности обхода коллизий
                cx = tx + random.uniform(-1.0, 1.0) # Расширено с 0.8 для выхода за collision_radius
                cy = ty + random.uniform(-1.0, 1.0)
                is_colliding = any(
                    ((cx - other_data.get("local_position", {}).get("x", 0.0))**2 +
                     (cy - other_data.get("local_position", {}).get("y", 0.0))**2)**0.5 < collision_radius
                    for other_id, other_data in npc_positions.items() if other_id != intent.npc_id
                )
                if not is_colliding:
                    best_x, best_y = cx, cy
                    break
        else:
            best_x = tx + random.uniform(-0.5, 0.5)
            best_y = ty + random.uniform(-0.5, 0.5)
            
        tx, ty = best_x, best_y
        print(f"[TRACE][SCENE_CHANGE_CREATED] npc={intent.npc_id} x={tx:.1f} y={ty:.1f}")
        logger.info(f"[PIPELINE][MOVEMENT][MICRO_SNAP] npc={intent.npc_id} → xy=({tx:.1f}, {ty:.1f})")
        return [SceneChange(
            type=ChangeType.NPC_POSITION,
            target=intent.npc_id,
            field="local_position",
            value={"x": tx, "y": ty},
            cause=f"micro_snap:{intent.reason}",
            tick=tick,
        )]

    def _resolve_macro_relocation(
        self,
        intent: MovementIntent,
        svc: Any,
        location_id: str,
        tick: int,
    ) -> List[SceneChange]:
        """ADR-0010: LOD1 макро-перемещение (Semantic Relocation)."""
        # Защита micro-position: если NPC уже в целевом узле — пропускаем
        if intent.from_node_id and intent.from_node_id == intent.target_node_id:
            logger.debug(f"[MOVEMENT_ENGINE] Skip macro: {intent.npc_id} уже в {intent.target_node_id}")
            return []
        
        # Резолвим целевой узел в координаты центра
        target_ref = svc.get_node(intent.target_node_id) or svc.get_node(f"{location_id}:{intent.target_node_id}")
        if not target_ref:
            logger.warning(f"[MOVEMENT_ENGINE] Узел '{intent.target_node_id}' не найден для {intent.npc_id} в {location_id}")
            return []
        
        logger.info(f"[PIPELINE][MOVEMENT][RELOCATE] npc={intent.npc_id} → zone={intent.target_node_id} reason={intent.reason}")
        return [SceneChange(
            type=ChangeType.NPC_POSITION,
            target=intent.npc_id,
            field="position",
            value=intent.target_node_id,
            cause=f"semantic_relocation:{intent.reason}",
            tick=tick,
        )]

    @staticmethod
    def _extract_location(intent: MovementIntent) -> str:
        """Берёт location_id напрямую из intent."""
        return intent.location_id