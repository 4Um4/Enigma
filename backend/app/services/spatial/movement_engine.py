from __future__ import annotations

# backend/app/services/spatial/movement_engine.py
# Назначение: Слой 2 Execution. MovementIntent → SceneChange с {x, y}.
# Получает целевой узел графа, резолвит в координаты, генерирует SceneChange.
import logging

logger = logging.getLogger(__name__)
from typing import Any, Dict, List, Optional

import math
from app.domain.movement import LocalSteeringGoal, MacroMovementGoal
from app.domain.traversal_schema import (
    MovementPlanResult,
    MovementPlanStatus,
    TraversalProposal,
)
from app.services.scene_change import ChangeType, SceneChange

logger = logging.getLogger(__name__)


class MovementPlanner:
    """ADR-O-323: Единственный автор TraversalProposal.
    
    Инкапсулирует логику валидации пути, вычисления waypoints, distance
    и duration_ticks. Возвращает MovementPlanResult (ACCEPTED/REJECTED).
    REJECTED proposals не доходят до SceneChange.
    """
    _DEFAULT_SPEED = 2.0

    def plan(
        self,
        intent: MacroMovementGoal,
        svc: Any,
        current_pos: str,
        tick: int,
        current_xy: Dict[str, float],
    ) -> MovementPlanResult:
        """Планирует макро-перемещение. Возвращает TraversalProposal или REJECT."""
        target_node = intent.target_node_id
        source_node_obj = svc.get_node(current_pos)
        target_node_obj = svc.get_node(target_node) or svc.get_node(f"{intent.location_id}:{target_node}")
        
        if not source_node_obj or not target_node_obj:
            return MovementPlanResult(
                status=MovementPlanStatus.REJECTED,
                reason=f"NODE_NOT_FOUND source={current_pos} target={target_node}"
            )

        # ADR-O-323: Используем реальную local_position NPC для начальной точки,
        # чтобы избежать расхождения с EventCompiler (который читает local_position из снапшота).
        _cx = current_xy.get("x", source_node_obj.x) if isinstance(current_xy, dict) else source_node_obj.x
        _cy = current_xy.get("y", source_node_obj.y) if isinstance(current_xy, dict) else source_node_obj.y
        source_xy = (_cx, _cy)
        target_xy = (target_node_obj.x, target_node_obj.y)
        
        # FIX Overlap: Добавляем персональный offset ДО создания proposal,
        # чтобы TraversalProposal содержал финальные координаты.
        import zlib
        _hash = zlib.adler32(intent.actor_id.encode("utf-8")) if intent.actor_id else 0
        _offset_x = ((_hash % 10) / 10.0 - 0.5) * 1.5
        _offset_y = (((_hash // 10) % 10) / 10.0 - 0.5) * 1.5
        target_xy = (target_xy[0] + _offset_x, target_xy[1] + _offset_y)
        
        # Проверка блокировки пути
        is_path_blocked = self._check_wall_blocking(svc, source_xy, target_xy)
        waypoints: List[List[float]] = [[source_xy[0], source_xy[1]]]
        
        if is_path_blocked:
            path = self._find_path(svc, source_xy, target_node_obj)
            if path and len(path) >= 2:
                intermediate = [[pn.x, pn.y] for pn in path[1:-1]] if len(path) > 2 else []
                if intermediate:
                    waypoints.extend(intermediate)
                # ADR-DOORWAY-TRUST: 2-node path but blocked — граф говорит, что связь есть
            else:
                # ADR-DOORWAY-TRUST: find_path пуст, но целевой узел валиден — доверяем графу
                pass
        
        waypoints.append([target_xy[0], target_xy[1]])
        
        # Вычисление дистанции (сумма сегментов)
        distance = 0.0
        for i in range(len(waypoints) - 1):
            dx = waypoints[i][0] - waypoints[i+1][0]
            dy = waypoints[i][1] - waypoints[i+1][1]
            distance += math.hypot(dx, dy)
            
        duration_ticks = max(1, math.ceil(distance / self._DEFAULT_SPEED)) if self._DEFAULT_SPEED > 0 else 1
        
        # Получаем version из SpatialService (если доступно)
        topology_version = getattr(svc, "_topology_version", 0)
        
        proposal = TraversalProposal(
            npc_id=intent.actor_id,
            source_node=current_pos,
            target_node=target_node,
            path_waypoints=tuple(tuple(wp) for wp in waypoints),
            distance=distance,
            speed=self._DEFAULT_SPEED,
            duration_ticks=duration_ticks,
            source_intent_id=getattr(intent, "intent_id", f"{intent.actor_id}:{intent.reason}"),
            planned_tick=tick,
            topology_version=topology_version,
        )
        
        return MovementPlanResult(
            status=MovementPlanStatus.ACCEPTED,
            proposal=proposal,
        )
        
        waypoints.append([target_xy[0], target_xy[1]])
        
        # Вычисление дистанции (сумма сегментов)
        distance = 0.0
        for i in range(len(waypoints) - 1):
            dx = waypoints[i][0] - waypoints[i+1][0]
            dy = waypoints[i][1] - waypoints[i+1][1]
            distance += math.hypot(dx, dy)
            
        duration_ticks = max(1, math.ceil(distance / self._DEFAULT_SPEED)) if self._DEFAULT_SPEED > 0 else 1
        
        # Получаем version из SpatialService (если доступно)
        topology_version = getattr(svc, "_topology_version", 0)
        
        proposal = TraversalProposal(
            npc_id=intent.actor_id,
            source_node=current_pos,
            target_node=target_node,
            path_waypoints=tuple(tuple(wp) for wp in waypoints),
            distance=distance,
            speed=self._DEFAULT_SPEED,
            duration_ticks=duration_ticks,
            source_intent_id=getattr(intent, "intent_id", f"{intent.actor_id}:{intent.reason}"),
            planned_tick=tick,
            topology_version=topology_version,
        )
        
        return MovementPlanResult(
            status=MovementPlanStatus.ACCEPTED,
            proposal=proposal,
        )

    def _check_wall_blocking(self, svc: Any, source_xy: tuple, target_xy: tuple) -> bool:
        """Проверяет прямую видимость между точками."""
        # Делегируем в SpatialService если метод есть
        if hasattr(svc, "is_path_blocked"):
            return svc.is_path_blocked(source_xy, target_xy)
        return False

    def _find_path(self, svc: Any, source_xy: tuple, target_node: Any) -> Optional[list]:
        """A* pathfinding через SpatialService."""
        if hasattr(svc, "find_path"):
            return svc.find_path(source_xy, target_node)
        return None


class MovementEngine:
    """Слой 2: Execution. Конвертирует намерения в изменения позиции.

    Не принимает решений — только выполняет:
    1. Берёт MovementIntent (target_node_id)
    2. Резолвит через LocationGraph → {x, y}
    3. Генерирует SceneChange(field="local_position")
    """

    def __init__(self) -> None:
        # SpatialService v1.2 — инъекция извне (DI)
        self._spatial_service: Optional[Any] = None
        # ADR-O-323: Планировщик — единственный автор TraversalProposal
        self._planner = MovementPlanner()

    def set_spatial_service(self, svc: Any) -> None:
        """Инъекция SpatialService для A* с учётом оверлея."""
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
                npc_id = intent.actor_id
                # Авторитетная позиция из scene_state, НЕ из intent.from_node_id
                current_pos = npc_positions.get(npc_id, {}).get("position", "")
                target_pos = intent.target_node_id

                if current_pos and current_pos == target_pos:
                    logger.debug(
                        f"[GATE_B1_COLLAPSE] npc={npc_id} current={current_pos} target={target_pos} loc={getattr(intent, 'location_id', '?')}"
                    )
                    logger.debug(
                        f"[SPATIAL_GATE] COLLAPSE: npc={npc_id} already at {target_pos} "
                        f"reason={getattr(intent, 'reason', '?')}"
                    )
                    continue  # spatial no-op — desire сворачивается

            validated.append(intent)
            if isinstance(intent, MacroMovementGoal):
                logger.debug(
                    f"[GATE_B1_ACCEPT] npc={intent.actor_id} current={npc_positions.get(intent.actor_id, {}).get('position', '')} target={intent.target_node_id} loc={getattr(intent, 'location_id', '?')}"
                )

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
        npc_positions: Optional[Dict] = None,  # ADR-056: Collision Avoidance для LOD0
        campaign_id: Optional[
            str
        ] = None,  # Для динамической сборки графа чужой локации
        scene_state: Optional[Dict[str, Any]] = None,  # Для SpatialService.build_for_location
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
        logger.debug(
            f"[GATE_B1] total_intents={_pre_gate_count} accepted={len(intents)} rejected={_pre_gate_count - len(intents)}"
        )

        changes: List[SceneChange] = []

        # ADR-060: Строгое разделение физик. LOD0 не требует графа локации.
        by_location: dict[str, List[MacroMovementGoal]] = {}
        for intent in intents:
            # ADR-XXXX: Инвариант — один Intent обрабатывается ровно один раз
            if getattr(intent, "processed", False):
                raise RuntimeError(
                    f"[ARCHITECTURE_VIOLATION] MovementIntent для {getattr(intent, 'npc_id', '?')} "
                    f"уже обработан '{getattr(intent, 'processor', '?')}'. "
                    f"Двойная обработка = двойное будущее = телепортация."
                )
            intent.processed = True
            intent.processor = "MovementEngine"
            logger.debug(
                f"[PIPELINE][MOVEMENT] "
                f"npc={intent.actor_id} "
                f"reason={intent.reason} "
                f"local_xy={getattr(intent, 'target_local_xy', 'N/A')}"
            )
            if isinstance(intent, LocalSteeringGoal):
                # LOD0: Микро-перемещение обрабатывается напрямую, без SpatialService
                changes.extend(
                    self._resolve_micro_movement(intent, tick, npc_positions)
                )
            elif isinstance(intent, MacroMovementGoal):
                # ADR-O-323: MovementPlanner — единый автор TraversalState.
                # Вычисляет waypoints и distance ДО создания SceneChange.
                # SceneStateManager и EventCompiler становятся чистыми потребителями.
                # S91.1: Cross-location routing intercept (ДОЛГ 6.2)
                # Если цель в другом чанке, направляем NPC в boundary node текущего чанка.
                current_loc = (
                    npc_positions.get(intent.actor_id, {}).get(
                        "location_id", scene_state.get("location_id", "")
                    )
                    if scene_state
                    else ""
                )
                # ADR-FIX: Надёжно определяем целевую локацию из префикса target_node_id (напр. "city_gate:exit_west")
                if ":" in intent.target_node_id:
                    target_loc = intent.target_node_id.split(":")[0]
                else:
                    target_loc = intent.location_id or current_loc

                if scene_state and current_loc and target_loc != current_loc:
                    current_svc = self._resolve_spatial_service(
                        current_loc, campaign_id, scene_state
                    )
                    if current_svc:
                        boundary_node = current_svc.get_boundary_to_neighbor(target_loc)
                        if boundary_node:
                            logger.info(
                                f"[CROSS_LOC_INTERCEPT] npc={intent.actor_id} target={target_loc} rerouted to boundary {boundary_node.node_id} in {current_loc}"
                            )
                            # Перенаправляем интент на boundary node текущей локации
                            intent.target_node_id = boundary_node.node_id.split(":")[-1]
                            intent.location_id = current_loc
                            target_loc = current_loc
                        else:
                            logger.warning(
                                f"[CROSS_LOC_INTERCEPT] No boundary node in {current_loc} to {target_loc} for {intent.actor_id}"
                            )
                            # ADR-O-314: Нет boundary node — кросс-локационный роутинг невозможен.
                            # Дропаем интент, чтобы предотвратить невалидный SceneChange (SHADOW_COMPILER FAILED).
                            continue
                    else:
                        logger.warning(
                            f"[CROSS_LOC_INTERCEPT] No SpatialService for current_loc={current_loc}"
                        )
                        # Нет SpatialService — нет валидации маршрута. Дропаем интент.
                        continue

                by_location.setdefault(target_loc, []).append(intent)

        # LOD1: Макро-навигация требует SpatialService (граф локации)
        for location_id, loc_intents in by_location.items():
            svc = self._resolve_spatial_service(location_id, campaign_id, scene_state)
            if not svc:
                for intent in loc_intents:
                    logger.error(
                        f"[MOVEMENT_ENGINE] Нет SpatialService для {intent.actor_id} → {intent.target_node_id} в {location_id}"
                    )
                continue

            for intent in loc_intents:
                _npc_id = intent.actor_id
                _npc_data = npc_positions.get(_npc_id, {}) if npc_positions else {}
                _current_pos = _npc_data.get("position", intent.from_node_id)
                _current_xy = _npc_data.get("local_position", {})
                changes.extend(
                    self._resolve_macro_relocation(intent, svc, location_id, tick, _current_pos, _current_xy)
                )

        return changes

    def _resolve_spatial_service(
        self,
        location_id: str,
        campaign_id: Optional[str],
        scene_state: Optional[Dict[str, Any]],
    ) -> Optional[Any]:
        """Динамически резолвит SpatialService для запрошенной локации."""
        svc = self._spatial_service
        needs_dynamic = location_id and getattr(svc, "_location_id", "") != location_id

        # Если сервиса нет или локация чужая — пытаемся собрать на лету
        if not svc or needs_dynamic:
            if campaign_id and location_id and scene_state is not None:
                from app.services.spatial.spatial_factory import SpatialFactory

                svc = SpatialFactory.build_for_campaign(
                    campaign_id, location_id, scene_state
                )
                if svc:
                    logger.warning(
                        f"[MOVEMENT_ENGINE] Пересобрал SpatialService для {location_id} (needs_dynamic={needs_dynamic})"
                    )
                else:
                    logger.error(
                        f"[MOVEMENT_ENGINE] build_for_location вернул None для {location_id}!"
                    )
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
            for _ in range(10):  # Увеличено с 5 для стабильности обхода коллизий
                cx = tx + rng.uniform(
                    -1.0, 1.0
                )  # Расширено с 0.8 для выхода за collision_radius
                cy = ty + rng.uniform(-1.0, 1.0)
                is_colliding = any(
                    (
                        (cx - other_data.get("local_position", {}).get("x", 0.0)) ** 2
                        + (cy - other_data.get("local_position", {}).get("y", 0.0)) ** 2
                    )
                    ** 0.5
                    < collision_radius
                    for other_id, other_data in npc_positions.items()
                    if other_id != intent.actor_id
                )
                if not is_colliding:
                    best_x, best_y = cx, cy
                    break
        else:
            best_x = tx + rng.uniform(-0.5, 0.5)
            best_y = ty + rng.uniform(-0.5, 0.5)

        tx, ty = best_x, best_y
        logger.debug(
            f"[TRACE][SCENE_CHANGE_CREATED] actor={intent.actor_id} x={tx:.1f} y={ty:.1f}"
        )
        logger.info(
            f"[PIPELINE][MOVEMENT][MICRO_SNAP] actor={intent.actor_id} → xy=({tx:.1f}, {ty:.1f})"
        )

        # ADR-O-315: Вычисление body_heading на основе вектора движения (intent -> target)
        import math

        _curr_pos = (
            npc_positions.get(intent.actor_id, {}).get(
                "local_position", {"x": tx, "y": ty}
            )
            if npc_positions
            else {"x": tx, "y": ty}
        )
        _cx, _cy = _curr_pos.get("x", tx), _curr_pos.get("y", ty)
        _heading = (
            math.atan2(ty - _cy, tx - _cx) if (tx != _cx or ty != _cy) else 1.5708
        )

        return [
            SceneChange(
                type=ChangeType.NPC_POSITION,
                target=intent.actor_id,
                field="local_position",
                value={"x": tx, "y": ty},
                cause=f"micro_snap:{intent.reason}",
                tick=tick,
            ),
            SceneChange(
                type=ChangeType.NPC_POSITION,
                target=intent.actor_id,
                field="body_heading",
                value=_heading,
                cause=f"heading_snap:{intent.reason}",
                tick=tick,
            ),
        ]

    def _resolve_macro_relocation(
        self,
        intent: MacroMovementGoal,
        svc: Any,
        location_id: str,
        tick: int,
        current_pos: str,
        current_xy: Dict[str, float],
    ) -> List[SceneChange]:
        """ADR-0010/060/060: LOD1 макро-перемещение (Semantic Relocation).
        ADR-O-323: Делегирует планирование MovementPlanner'у."""
        # Защита micro-position: если NPC уже в целевом узле — пропускаем
        if current_pos and current_pos == intent.target_node_id:
            logger.debug(
                f"[GATE_B3] npc={intent.actor_id} reason=SAME_NODE node={intent.target_node_id}"
            )
            logger.debug(
                f"[MOVEMENT_ENGINE] Skip macro: {intent.actor_id} уже в {intent.target_node_id}"
            )
            return []

        # ADR-O-323: MovementPlanner — единственный автор TraversalProposal.
        # Передаём авторитетную позицию из scene_state (current_pos + current_xy).
        plan_result = self._planner.plan(intent, svc, current_pos, tick, current_xy)

        if plan_result.status == MovementPlanStatus.REJECTED:
            logger.warning(
                f"[GATE_B3] npc={intent.actor_id} reason=PLAN_REJECTED reason={plan_result.reason}"
            )
            return []

        if plan_result.proposal is None:
            logger.error(
                f"[GATE_B3] npc={intent.actor_id} reason=ACCEPTED_NULL_PROPOSAL (Kernel Violation)"
            )
            return []

        # ADR-O-323: MovementEngine не модифицирует proposal. 
        # Извлекаем целевые координаты из proposal для логирования и SceneChange.target_local_xy.
        target_xy = plan_result.proposal.path_waypoints[-1]

        logger.info(
            f"[PIPELINE][MOVEMENT][RELOCATE] npc={intent.actor_id} → zone={intent.target_node_id} reason={intent.reason} exact_xy={target_xy} dist={plan_result.proposal.distance:.2f} ticks={plan_result.proposal.duration_ticks}"
        )
        logger.debug(
            f"[GATE_B3] npc={intent.actor_id} reason=SUCCESS target={intent.target_node_id} loc={location_id}"
        )
        return [
            SceneChange(
                type=ChangeType.NPC_POSITION,
                target=intent.actor_id,
                field="position",
                value=intent.target_node_id,
                cause=f"semantic_relocation:{intent.reason}",
                tick=tick,
                target_location_id=location_id,
                target_local_xy=target_xy,  # ADR-065: Точные координаты цели
                traversal_proposal=plan_result.proposal,  # ADR-O-323: Авторизованный паспорт
            )
        ]

    @staticmethod
    def _extract_location(intent: MovementIntent) -> str:
        """Берёт location_id напрямую из intent."""
        return intent.location_id
