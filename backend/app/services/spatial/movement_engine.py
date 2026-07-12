# backend/app/services/spatial/movement_engine.py
# Назначение: Слой 2 Execution. MovementIntent → SceneChange с {x, y}.
# Получает целевой узел графа, резолвит в координаты, генерирует SceneChange.

from __future__ import annotations

import logging
logger = logging.getLogger(__name__)
from typing import Any, Dict, List, Optional

from app.domain.movement import MacroMovementGoal, LocalSteeringGoal
from app.services.scene_change import SceneChange, ChangeType

logger = logging.getLogger(__name__)


class MovementEngine:
    """Слой 2: Execution. Конвертирует намерения в изменения позиции.
    
    Не принимает решений — только выполняет:
    1. Берёт MovementIntent (target_node_id)
    2. Резолвит через LocationGraph → {x, y}
    3. Генерирует SceneChange(field="local_position")
    """

    def __init__(self) -> None:
        # SpatialService v1.2 — инжекция извне (DI)
        self._spatial_service: Optional[Any] = None

    def set_spatial_service(self, svc: Any) -> None:
        """Инжекция SpatialService для A* с учётом оверлея."""
        self._spatial_service = svc




    # ── Spatial Intent Gate: единый пространственный арбитр ────────────
    # ADR-138: Spatial eligibility logic ЗАПРЕЩЕНА нигде кроме этого метода.
    # Все источники MovementIntent (schedule, decision, approach, flee, random)
    # проходят через этот фильтр. ONE gate to rule them all.
    # Желание (Desire) не мутируется — остаётся immutable record.

    def _spatial_intent_gate(
        self,
        intents: List,
        npc_positions: Optional[Dict],
    ) -> List:
        """Spatial Arbitration Layer: конвертация Desire → Spatial Commitment.

        Отклоняет intent'ы где NPC уже на целевом узле (spatial no-op collapse).
        НЕ мутирует intent — desire остаётся неизменным record'ом.
        Источник истины: npc_positions из scene_state (авторитетная реальность).
        НЕ использует intent.from_node_id (может быть stale от npc dict).
        """
        if not npc_positions:
            return intents  # нет данных для арбитража — пропускаем всё

        validated = []
        for intent in intents:
            # Gate применяется только к макро-перемещениям (Semantic Relocation)
            if isinstance(intent, MacroMovementGoal):
                npc_id = intent.npc_id
                # Авторитетная позиция из scene_state, НЕ из intent.from_node_id
                current_pos = npc_positions.get(npc_id, {}).get("position", "")
                target_pos = intent.target_node_id

                if current_pos and current_pos == target_pos:
                    logger.debug(f"[GATE_B1_COLLAPSE] npc={npc_id} current={current_pos} target={target_pos} loc={getattr(intent, 'location_id', '?')}")
                    logger.debug(
                        f"[SPATIAL_GATE] COLLAPSE: npc={npc_id} already at {target_pos} "
                        f"reason={getattr(intent, 'reason', '?')}"
                    )
                    continue  # spatial no-op — desire сворачивается

            validated.append(intent)
            if isinstance(intent, MacroMovementGoal):
                logger.debug(f"[GATE_B1_ACCEPT] npc={intent.npc_id} current={npc_positions.get(intent.npc_id, {}).get('position', '')} target={intent.target_node_id} loc={getattr(intent, 'location_id', '?')}")

        _skipped = len(intents) - len(validated)
        if _skipped > 0:
            logger.info(
                f"[SPATIAL_GATE] {len(intents)} intents → {len(validated)} validated "
                f"({_skipped} collapsed)"
            )

        return validated

    def process_intents(
        self,
        intents: List[MacroMovementGoal | LocalSteeringGoal],
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
        # Spatial Intent Gate: Desire → Commitment конверсия.
        # ЗАПРЕТ (ADR-138): spatial eligibility logic НЕ существует нигде кроме _spatial_intent_gate.
        _pre_gate_count = len(intents)
        intents = self._spatial_intent_gate(intents, npc_positions)
        logger.debug(f"[GATE_B1] total_intents={_pre_gate_count} accepted={len(intents)} rejected={_pre_gate_count - len(intents)}")

        changes: List[SceneChange] = []

        # ADR-060: Строгое разделение физик. LOD0 не требует графа локации.
        by_location: dict[str, List[MacroMovementGoal]] = {}
        for intent in intents:
            # ADR-XXXX: Инвариант — один Intent обрабатывается ровно один раз
            if getattr(intent, 'processed', False):
                raise RuntimeError(
                    f"[ARCHITECTURE_VIOLATION] MovementIntent для {getattr(intent, 'npc_id', '?')} "
                    f"уже обработан '{getattr(intent, 'processor', '?')}'. "
                    f"Двойная обработка = двойное будущее = телепортация."
                )
            intent.processed = True
            intent.processor = "MovementEngine"
            logger.debug(
                f"[PIPELINE][MOVEMENT] "
                f"npc={intent.npc_id} "
                f"reason={intent.reason} "
                f"local_xy={getattr(intent, 'target_local_xy', 'N/A')}"
            )
            if isinstance(intent, LocalSteeringGoal):
                # LOD0: Микро-перемещение обрабатывается напрямую, без SpatialService
                changes.extend(self._resolve_micro_movement(intent, tick, npc_positions))
            elif isinstance(intent, MacroMovementGoal):
                # S91.1: Cross-location routing intercept (ДОЛГ 6.2)
                # Если цель в другом чанке, направляем NPC в boundary node текущего чанка.
                current_loc = npc_positions.get(intent.npc_id, {}).get("location_id", scene_state.get("location_id", "")) if scene_state else ""
                # ADR-FIX: Надёжно определяем целевую локацию из префикса target_node_id (напр. "city_gate:exit_west")
                if ":" in intent.target_node_id:
                    target_loc = intent.target_node_id.split(":")[0]
                else:
                    target_loc = intent.location_id or current_loc
                
                if scene_state and current_loc and target_loc != current_loc:
                        current_svc = self._resolve_spatial_service(current_loc, campaign_id, scene_state)
                        if current_svc:
                            boundary_node = current_svc.get_boundary_to_neighbor(target_loc)
                            if boundary_node:
                                logger.info(f"[CROSS_LOC_INTERCEPT] npc={intent.npc_id} target={target_loc} rerouted to boundary {boundary_node.node_id} in {current_loc}")
                                # Перенаправляем интент на boundary node текущей локации
                                intent.target_node_id = boundary_node.node_id.split(":")[-1]
                                intent.location_id = current_loc
                                target_loc = current_loc
                            else:
                                logger.warning(f"[CROSS_LOC_INTERCEPT] No boundary node in {current_loc} to {target_loc} for {intent.npc_id}")
                        else:
                            logger.warning(f"[CROSS_LOC_INTERCEPT] No SpatialService for current_loc={current_loc}")
                
                by_location.setdefault(target_loc, []).append(intent)

        # LOD1: Макро-навигация требует SpatialService (граф локации)
        for location_id, loc_intents in by_location.items():
            svc = self._resolve_spatial_service(location_id, campaign_id, scene_state)
            if not svc:
                for intent in loc_intents:
                    logger.error(
                        f"[MOVEMENT_ENGINE] Нет SpatialService для {intent.npc_id} → {intent.target_node_id} в {location_id}"
                    )
                continue

            for intent in loc_intents:
                changes.extend(self._resolve_macro_relocation(intent, svc, location_id, tick))

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
                from app.services.spatial.spatial_factory import SpatialFactory
                svc = SpatialFactory.build_for_campaign(campaign_id, location_id, scene_state)
                if svc:
                    logger.warning(f"[MOVEMENT_ENGINE] Пересобрал SpatialService для {location_id} (needs_dynamic={needs_dynamic})")
                else:
                    logger.error(f"[MOVEMENT_ENGINE] build_for_location вернул None для {location_id}!")
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
        intent: MacroMovementGoal | LocalSteeringGoal,
        svc: Any,
        location_id: str,
        tick: int,
        npc_positions: Optional[Dict],
    ) -> List[SceneChange]:
        """Обрабатывает один MovementIntent, возвращая список SceneChange."""
        # ADR-060: Строгое разделение физик. Полиморфизм вместо проверки атрибутов.
        if isinstance(intent, LocalSteeringGoal):
            return self._resolve_micro_movement(intent, tick, npc_positions)
        
        return self._resolve_macro_relocation(intent, svc, location_id, tick)

    def _resolve_micro_movement(
        self,
        intent: LocalSteeringGoal,
        tick: int,
        npc_positions: Optional[Dict],
    ) -> List[SceneChange]:
        """ADR-056/060: LOD0 микро-перемещение с Collision Avoidance (jitter).
        
        KERNEL-ISOLATION: Использует KernelRNG с salt="movement_jitter" для 
        независимого потока случайностей, изолированного от DecisionHub и событий.
        """
        from app.services.npc.kernel_rng import KernelRNG
        rng = KernelRNG(tick=tick, npc_id=intent.actor_id, salt="movement_jitter")
        tx, ty = intent.local_target_xy
        collision_radius = 0.8
        best_x, best_y = tx, ty
        
        if npc_positions:
            for _ in range(10): # Увеличено с 5 для стабильности обхода коллизий
                cx = tx + rng.uniform(-1.0, 1.0) # Расширено с 0.8 для выхода за collision_radius
                cy = ty + rng.uniform(-1.0, 1.0)
                is_colliding = any(
                    ((cx - other_data.get("local_position", {}).get("x", 0.0))**2 +
                     (cy - other_data.get("local_position", {}).get("y", 0.0))**2)**0.5 < collision_radius
                    for other_id, other_data in npc_positions.items() if other_id != intent.actor_id
                )
                if not is_colliding:
                    best_x, best_y = cx, cy
                    break
        else:
            best_x = tx + rng.uniform(-0.5, 0.5)
            best_y = ty + rng.uniform(-0.5, 0.5)
            
        tx, ty = best_x, best_y
        logger.debug(f"[TRACE][SCENE_CHANGE_CREATED] actor={intent.actor_id} x={tx:.1f} y={ty:.1f}")
        logger.info(f"[PIPELINE][MOVEMENT][MICRO_SNAP] actor={intent.actor_id} → xy=({tx:.1f}, {ty:.1f})")
        
        # ADR-O-315: Вычисление body_heading на основе вектора движения (intent -> target)
        import math
        _curr_pos = npc_positions.get(intent.npc_id, {}).get("local_position", {"x": tx, "y": ty}) if npc_positions else {"x": tx, "y": ty}
        _cx, _cy = _curr_pos.get("x", tx), _curr_pos.get("y", ty)
        _heading = math.atan2(ty - _cy, tx - _cx) if (tx != _cx or ty != _cy) else 1.5708
        
        return [
            SceneChange(
                type=ChangeType.NPC_POSITION,
                target=intent.npc_id,
                field="local_position",
                value={"x": tx, "y": ty},
                cause=f"micro_snap:{intent.reason}",
                tick=tick,
            ),
            SceneChange(
                type=ChangeType.NPC_POSITION,
                target=intent.npc_id,
                field="body_heading",
                value=_heading,
                cause=f"heading_snap:{intent.reason}",
                tick=tick,
            )
        ]

    def _resolve_macro_relocation(
        self,
        intent: MacroMovementGoal,
        svc: Any,
        location_id: str,
        tick: int,
    ) -> List[SceneChange]:
        """ADR-0010/060: LOD1 макро-перемещение (Semantic Relocation)."""
        # Защита micro-position: если NPC уже в целевом узле — пропускаем
        if intent.from_node_id and intent.from_node_id == intent.target_node_id:
            logger.debug(f"[GATE_B3] npc={intent.npc_id} reason=SAME_NODE node={intent.target_node_id}")
            logger.debug(f"[MOVEMENT_ENGINE] Skip macro: {intent.npc_id} уже в {intent.target_node_id}")
            return []
        
        # Резолвим целевой узел в координаты центра
        target_ref = svc.get_node(intent.target_node_id) or svc.get_node(f"{location_id}:{intent.target_node_id}")
        if not target_ref:
            logger.debug(f"[GATE_B3] npc={intent.npc_id} reason=NODE_NOT_FOUND target={intent.target_node_id} loc={location_id}")
            logger.warning(f"[MOVEMENT_ENGINE] Узел '{intent.target_node_id}' не найден для {intent.npc_id} в {location_id}")
            return []
        
        # ADR-090: Если intent не имеет точных координат (schedule/flee), берём центр узла из графа.
        # Без этого scene_state_manager не создаёт TraversalState, и NPC телепортируется.
        target_xy = intent.target_local_xy
        if target_xy is None and hasattr(target_ref, 'x') and hasattr(target_ref, 'y'):
            target_xy = (target_ref.x, target_ref.y)
            
        # FIX Overlap: Добавляем персональный offset, чтобы NPC не стояли друг в друге.
        # Offset детерминирован (на основе npc_id), чтобы не вызывать дрожание каждый тик.
        if target_xy:
            import zlib
            _hash = zlib.adler32(intent.npc_id.encode('utf-8')) if intent.npc_id else 0
            _offset_x = ((_hash % 10) / 10.0 - 0.5) * 1.5  # от -0.75 до +0.75 м
            _offset_y = (((_hash // 10) % 10) / 10.0 - 0.5) * 1.5
            target_xy = (target_xy[0] + _offset_x, target_xy[1] + _offset_y)
            
        logger.info(f"[PIPELINE][MOVEMENT][RELOCATE] npc={intent.npc_id} → zone={intent.target_node_id} reason={intent.reason} exact_xy={target_xy}")
        logger.debug(f"[GATE_B3] npc={intent.npc_id} reason=SUCCESS target={intent.target_node_id} loc={location_id}")
        return [SceneChange(
            type=ChangeType.NPC_POSITION,
            target=intent.npc_id,
            field="position",
            value=intent.target_node_id,
            cause=f"semantic_relocation:{intent.reason}",
            tick=tick,
            target_location_id=location_id,
            target_local_xy=target_xy,  # ADR-065: Точные координаты цели
        )]

    @staticmethod
    def _extract_location(intent: MovementIntent) -> str:
        """Берёт location_id напрямую из intent."""
        return intent.location_id