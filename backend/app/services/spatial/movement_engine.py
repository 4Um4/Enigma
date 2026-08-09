"""
backend/app/services/spatial/movement_engine.py
Назначение: Слой 2 Execution. MovementIntent → SceneChange с {x, y}.
Получает целевой узел графа, резолвит в координаты, генерирует SceneChange.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

import math
from typing import Any, Dict, List, Optional

from app.domain.movement import LocalSteeringGoal, MacroMovementGoal, MovementIntent
from app.domain.traversal import (
    LocalGeometry,
    Pose,
    TraversalMode,
    TraversalPlan,
    TraversalQuery,
)
from app.domain.movement_contract import (
    MovementFailure,
    MovementTrace,
    PathStatus,
)
from app.domain.traversal_schema import (
    MovementPlanResult,
    MovementPlanStatus,
    TraversalProposal,
)
from app.models.spatial_contracts import NodeRole
from app.services.scene_change import ChangeType, SceneChange
from app.services.spatial.local_traversal_planner import LocalTraversalPlanner

logger = logging.getLogger(__name__)

from app.errors import SimulationIntegrityError

# S131: Радиус восприятия для локальной геометрии.
# В будущем должен браться из BodyCapabilities или PerceptionKernel.
_DEFAULT_PERCEPTION_RADIUS = 15.0


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
        # S131: LocalTraversalPlanner — честная физика проходимости (Embodied Traversal)
        self._planner = LocalTraversalPlanner()

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
        # S139.3: Total Intent Arbitration. Schedule (spatial commitment) beats Social (desire), but loses to Reactive (flee/combat).
        # Если MacroMovementGoal расписания выигрывает, мы должны УДАЛИТЬ LocalSteeringGoal (социальные микро-движения), чтобы они не перетягивали NPC.
        _best_macro_intents: Dict[str, MacroMovementGoal] = {}
        _micro_intents: List[LocalSteeringGoal] = []

        for intent in intents:
            if getattr(intent, "actor_id", "") == "guard_borko":
                logger.debug(f"[BORKO_TRACE] tick={tick} type={type(intent).__name__} reason={getattr(intent, 'reason', '')} target={getattr(intent, 'target_node_id', getattr(intent, 'local_target_xy', '?'))}")
            if isinstance(intent, MacroMovementGoal):
                _npc_id = intent.actor_id
                _reason = getattr(intent, "reason", "")
                _is_schedule = "schedule" in _reason
                _is_reactive = "flee" in _reason or "combat" in _reason or "reactive" in _reason

                if _npc_id not in _best_macro_intents:
                    _best_macro_intents[_npc_id] = intent
                else:
                    _existing = _best_macro_intents[_npc_id]
                    _existing_reason = getattr(_existing, "reason", "")
                    _existing_is_schedule = "schedule" in _existing_reason
                    _existing_is_reactive = "flee" in _existing_reason or "combat" in _existing_reason or "reactive" in _existing_reason

                    # Reactive (flee/combat) always wins
                    if _is_reactive and not _existing_is_reactive:
                        _best_macro_intents[_npc_id] = intent
                    # Schedule beats Social (if existing is not reactive and not schedule)
                    elif _is_schedule and not _existing_is_reactive and not _existing_is_schedule:
                        _best_macro_intents[_npc_id] = intent
            elif isinstance(intent, LocalSteeringGoal):
                _micro_intents.append(intent)

        # Фильтруем микро-интенты: если у NPC есть выигравший MacroMovementGoal (Schedule/Reactive), микро-интенты (Social) удаляются.
        _winning_actors = set(_best_macro_intents.keys())
        _filtered_micro_intents = [
            intent for intent in _micro_intents
            if getattr(intent, "actor_id", "") not in _winning_actors
        ]

        intents = list(_best_macro_intents.values()) + _filtered_micro_intents

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
                _npc_pos_data = npc_positions.get(intent.actor_id, {}) if scene_state else {}
                _pos_str = _npc_pos_data.get("position", "")
                current_loc = _npc_pos_data.get("location_id")
                if current_loc is None:
                    current_loc = scene_state.get("location_id", "") if scene_state else ""
                # S-145 FIX: Если position содержит префикс локации (напр. "city_gate:entrance"),
                # а location_id устарел (DOUBLE TRUTH), доверяем position.
                if ":" in _pos_str:
                    _pos_loc = _pos_str.split(":")[0]
                    if _pos_loc != current_loc:
                        logger.debug(f"[CROSS_LOC_SYNC] npc={intent.actor_id} syncing current_loc='{current_loc}' to pos_loc='{_pos_loc}'")
                        current_loc = _pos_loc
                # ADR-FIX: Надёжно определяем целевую локацию из префикса target_node_id (напр. "city_gate:exit_west")
                if ":" in intent.target_node_id:
                    target_loc = intent.target_node_id.split(":")[0]
                else:
                    target_loc = intent.location_id or current_loc

                if getattr(intent, "actor_id", "") == "guard_borko":
                    _ss = "YES" if scene_state else "NO"
                    logger.debug(f"[BORKO_CROSS] tick={tick} target_node={intent.target_node_id} intent_loc={getattr(intent, 'location_id', 'N/A')} cur_loc={current_loc} target_loc={target_loc} scene_state={_ss}")
                if scene_state and current_loc and target_loc != current_loc:
                    logger.debug(f"[BORKO_CROSS_IN] tick={tick} ENTERED CROSS_LOC_INTERCEPT block")
                    current_svc = self._resolve_spatial_service(
                        current_loc, campaign_id, scene_state
                    )
                    if current_svc:
                        logger.debug(f"[DIAG_BOUNDARY] npc={intent.actor_id} current_loc={current_loc} target_loc={target_loc}")
                        boundary_node = current_svc.get_boundary_to_neighbor(target_loc)
                        logger.debug(f"[DIAG_BOUNDARY] result={boundary_node}")
                        logger.debug(f"[BORKO_CROSS_BOUNDARY] tick={tick} boundary_node={boundary_node}")
                        if boundary_node:
                            if not target_loc:
                                logger.error(f"[CROSS_LOC_MATERIALIZE] target_loc is empty for {intent.actor_id}! Skipping.")
                                continue
                            # S-04: Проверяем, не стоит ли NPC уже на boundary node.
                            # Используем XY-дистанцию, так как position (node_id) ещё не обновлён до Фазы 8.
                            _npc_data = npc_positions.get(intent.actor_id, {}) if npc_positions else {}
                            _lp = _npc_data.get("local_position", {})
                            _cur_x = _lp.get("x", 0.0) if isinstance(_lp, dict) else 0.0
                            _cur_y = _lp.get("y", 0.0) if isinstance(_lp, dict) else 0.0

                            _dist_to_boundary = math.hypot(boundary_node.x - _cur_x, boundary_node.y - _cur_y)
                            if getattr(intent, "actor_id", "") == "guard_borko":
                                # P7-MVP FIX: Защита от MagicMock в тестах
                                if hasattr(boundary_node, "x") and isinstance(boundary_node.x, (int, float)):
                                    logger.debug(f"[BORKO_DIST] tick={tick} cur_xy=({_cur_x:.1f}, {_cur_y:.1f}) boundary_xy=({boundary_node.x:.1f}, {boundary_node.y:.1f}) dist={_dist_to_boundary:.2f}")

                            # S-145 FIX: Материализация если NPC стоит на boundary node ИЛИ очень близко к ней.
                            _is_at_boundary = (_npc_pos_data.get("position", "") == boundary_node.node_id)
                            if _is_at_boundary or _dist_to_boundary < 1.5:
                                logger.info(f"[CROSS_LOC_MATERIALIZE] npc={intent.actor_id} crossing {current_loc} → {target_loc}")
                                target_svc = self._resolve_spatial_service(target_loc, campaign_id, scene_state)

                                # V8-SP-5 FIX: Проверка target_svc на None (защита от AttributeError)
                                if not target_svc:
                                    logger.warning(f"[CROSS_LOC_INTERCEPT] target_svc is None for {target_loc}, skipping materialize for {intent.actor_id}")
                                    continue

                                # Ищем целевой узел в новой локации (строгий контракт, без случайных fallback'ов)
                                # BUG-SPATIAL-001 FIX: Используем оригинальный target (напр. guard_bed), а не переписанный boundary node.
                                _original_target = getattr(intent, 'original_target_node_id', intent.target_node_id)
                                _target_node_id_short = _original_target.split(":")[-1]
                                target_node_obj = target_svc.get_node(_target_node_id_short) or target_svc.get_node(f"{target_loc}:{_target_node_id_short}")

                                if not target_node_obj:
                                    # V8-SP-16.3 FIX: Если целевой узел не найден, используем entry_node_hint (напр. exit_west)
                                    _b_info = current_svc.get_boundary_info(boundary_node.node_id) or {}
                                    _entry_hint = _b_info.get("entry_node_hint", "")
                                    if _entry_hint:
                                        target_node_obj = target_svc.get_node(_entry_hint.split(":")[-1]) or target_svc.get_node(_entry_hint)

                                if not target_node_obj:
                                    # S-04: Topology Violation. Целевой узел отсутствует в новой локации.
                                    # Silent fallback убит (S134.1). Игра должна упасть громко.
                                    from app.errors import SimulationIntegrityError
                                    raise SimulationIntegrityError(
                                        invariant_id="INV-CROSS-LOC-TARGET",
                                        message=f"Materialize failed: target node '{_target_node_id_short}' not found in loc '{target_loc}'",
                                        suspect_files=["frontend/map_editor/campaigns/Open_road/locations/"],
                                        file=__file__, line=188,
                                    )

                                # V8-SP-4 FIX: active_traversals — это dict, а не list.
                                # Итерация по dict выдаёт ключи (строки), а .remove() ломает everything.
                                _active_traversals = scene_state.get("active_traversals", {})
                                _traversal_items = _active_traversals.values() if isinstance(_active_traversals, dict) else _active_traversals
                                _entry = next((e for e in _traversal_items if isinstance(e, dict) and e.get("npc_id") == intent.actor_id), None)
                                if _entry:
                                    if isinstance(_active_traversals, dict):
                                        # Удаляем по ключу (npc_id), если это dict
                                        _active_traversals.pop(intent.actor_id, None)
                                    else:
                                        _active_traversals.remove(_entry)
                                    logger.debug(f"Cleared traversal for {intent.actor_id} after materialize")

                                changes.extend([
                                    SceneChange(
                                        type=ChangeType.NPC_POSITION,
                                        target=intent.actor_id,
                                        field="position",
                                        value=target_node_obj.node_id,
                                        cause=f"cross_loc_materialize:{intent.reason}",
                                        tick=tick,
                                        target_location_id=target_loc,
                                        target_local_xy=(target_node_obj.x, target_node_obj.y),
                                        traversal_proposal=None, # Мгновенный перенос (портал), контракт не требуется
                                    )
                                ])
                                continue # Переходим к следующему NPC, этот уже материализован

                            logger.info(
                                f"[CROSS_LOC_INTERCEPT] npc={intent.actor_id} target={target_loc} rerouted to boundary {boundary_node.node_id} in {current_loc}"
                            )
                            # Перенаправляем интент на boundary node текущей локации
                            # BUG-SPATIAL-001 FIX: Сохраняем оригинальный target перед перезаписью.
                            # Иначе materialize lookup не найдёт кровать в target loc.
                            if not hasattr(intent, 'original_target_node_id'):
                                intent.original_target_node_id = intent.target_node_id
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
                if _npc_id == "guard_borko":
                    logger.debug(f"[BORKO_RELOC] tick={tick} loc={location_id} target={intent.target_node_id} cur_pos={_current_pos} cur_xy={_current_xy}")
                changes.extend(
                    self._resolve_macro_relocation(
                        intent, svc, location_id, tick, npc_positions, campaign_id, scene_state
                    )
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
        campaign_id: Optional[str] = None,
        scene_state: Optional[Dict[str, Any]] = None,
    ) -> List[SceneChange]:
        """Обрабатывает один MovementIntent, возвращая список SceneChange."""
        # ADR-060: Строгое разделение физик. Полиморфизм вместо проверки атрибутов.
        if isinstance(intent, LocalSteeringGoal):
            return self._resolve_micro_movement(intent, tick, npc_positions)

        return self._resolve_macro_relocation(
            intent, svc, location_id, tick, npc_positions, campaign_id, scene_state
        )

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

    def _fallback_to_astar(
        self,
        svc: Any,
        intent: MacroMovementGoal,
        current_pos: str,
        tick: int,
        source_xy: tuple,
        target_xy: tuple,
        target_node_obj: Any
    ) -> MovementPlanResult:
        """S131.1: Fallback на A* ТОЛЬКО если локальная геометрия недоступна.
        Если геометрия была доступна, но план отклонён (физический запрет) — этот метод не вызывается.
        """
        # N4 FIX: defensive default для segment_arc_heights, чтобы избежать NameError
        segment_arc_heights = []
        path = svc.find_path(source_xy, target_node_obj) if hasattr(svc, "find_path") else None
        if not path or len(path) < 2:
            return MovementPlanResult(
                status=MovementPlanStatus.REJECTED,
                reason="NO_GEOMETRY_AND_NO_A_STAR_PATH"
            )

        waypoints: List[List[float]] = [[source_xy[0], source_xy[1]]]
        segment_modes: List[str] = []
        distance = 0.0
        prev_xy = source_xy

        for node in path[1:]:
            wp = [node.x, node.y]
            if math.hypot(wp[0] - prev_xy[0], wp[1] - prev_xy[1]) > 0.01:
                waypoints.append(wp)
                segment_modes.append(TraversalMode.WALK.value)
                distance += math.hypot(wp[0] - prev_xy[0], wp[1] - prev_xy[1])
                prev_xy = (wp[0], wp[1])

        speed = intent.body_capabilities.movement_speed
        duration_ticks = max(1, math.ceil(distance / speed)) if speed > 0 else 1
        topology_version = getattr(svc, "_topology_version", 0)

        proposal = TraversalProposal(
            npc_id=intent.actor_id,
            source_node=current_pos,
            target_node=target_node_obj.node_id,
            path_waypoints=tuple(tuple(wp) for wp in waypoints),
            distance=distance,
            speed=speed,
            duration_ticks=duration_ticks,
            source_intent_id=getattr(intent, "intent_id", f"{intent.actor_id}:{intent.reason}"),
            planned_tick=tick,
            topology_version=topology_version,
            segment_modes=tuple(segment_modes) if segment_modes else ("WALK",),
            planning_source="ASTAR_FALLBACK",
            segment_arc_heights=tuple(segment_arc_heights) if segment_arc_heights else (0.0,)
        )

        return MovementPlanResult(
            status=MovementPlanStatus.ACCEPTED,
            proposal=proposal,
        )

    def _compile_traversal_plan(
        self,
        intent: MacroMovementGoal,
        svc: Any,
        current_pos: str,
        tick: int,
        source_xy: tuple,
        target_xy: tuple,
        target_node_obj: Any
    ) -> MovementPlanResult:
        """S131: Компилирует TraversalPlan (от LocalTraversalPlanner) в TraversalProposal.
        Если локальная физика блокирована стеной, fallback на A* (все сегменты WALK).
        """
        # S131.1: Traversal Failure Semantics & Fallback Gate.
        # 1. Получаем локальную геометрию. Если сервис не предоставляет геометрию — fallback на A*.
        try:
            geometry: LocalGeometry = svc.get_local_geometry(source_xy, perception_radius=_DEFAULT_PERCEPTION_RADIUS)
        except (AttributeError, NotImplementedError) as e:
            logger.debug(f"Geometry not implemented, falling back to A*: {e}")
            return self._fallback_to_astar(svc, intent, current_pos, tick, source_xy, target_xy, target_node_obj)

        # S131 FIX (советник): allowed_modes зависит от body.can_jump
        allowed_modes = [TraversalMode.WALK]
        if intent.body_capabilities.can_jump:
            allowed_modes.append(TraversalMode.JUMP)

        # 2. Собираем запрос к планировщику
        query = TraversalQuery(
            source_pose=Pose(source_xy[0], source_xy[1]),
            target_pose=Pose(target_xy[0], target_xy[1]),
            body=intent.body_capabilities,
            allowed_modes=tuple(allowed_modes)
        )

        # 3. Выполняем локальное планирование (честная физика)
        plan: TraversalPlan = self._planner.compile_plan(query, geometry)

        # S131.1: Если физика запрещает — это HARD_REJECT. A* не имеет права отменить физический запрет.
        if not plan.possible:
            return MovementPlanResult(
                status=MovementPlanStatus.REJECTED,
                reason=plan.reason or "TRAVERSAL_IMPOSSIBLE"
            )

        # 4. Компилируем сегменты из TraversalPlan (с сохранением JUMP)
        waypoints: List[List[float]] = [[source_xy[0], source_xy[1]]]
        segment_modes: List[str] = []
        segment_arc_heights: List[float] = []
        distance = 0.0
        prev_xy = source_xy

        for seg in plan.segments:
            wp = [seg.end_pose.x, seg.end_pose.y]
            if math.hypot(wp[0] - prev_xy[0], wp[1] - prev_xy[1]) > 0.01:
                waypoints.append(wp)
                segment_modes.append(seg.mode.value)
                # S132.1: Если JUMP, используем max_jump_height из BodyCapabilities, иначе 0.0
                arc_h = intent.body_capabilities.max_jump_height if seg.mode == TraversalMode.JUMP else 0.0
                segment_arc_heights.append(arc_h)
                distance += math.hypot(wp[0] - prev_xy[0], wp[1] - prev_xy[1])
                prev_xy = (wp[0], wp[1])

        # 5. Вычисляем длительность
        speed = intent.body_capabilities.movement_speed
        duration_ticks = max(1, math.ceil(distance / speed)) if speed > 0 else 1

        topology_version = getattr(svc, "_topology_version", 0)

        proposal = TraversalProposal(
            npc_id=intent.actor_id,
            source_node=current_pos,
            target_node=target_node_obj.node_id,
            path_waypoints=tuple(tuple(wp) for wp in waypoints),
            distance=distance,
            speed=speed,
            duration_ticks=duration_ticks,
            source_intent_id=getattr(intent, "intent_id", f"{intent.actor_id}:{intent.reason}"),
            planned_tick=tick,
            topology_version=topology_version,
            segment_modes=tuple(segment_modes) if segment_modes else ("WALK",), # S131: Сохраняем семантику
            planning_source="LOCAL_TRAVERSAL",
            segment_arc_heights=tuple(segment_arc_heights) if segment_arc_heights else (0.0,)
        )

        return MovementPlanResult(
            status=MovementPlanStatus.ACCEPTED,
            proposal=proposal,
        )

    def _resolve_macro_relocation(
        self,
        intent: MacroMovementGoal,
        svc: Any,
        location_id: str,
        tick: int,
        npc_positions: Optional[Dict] = None,
        campaign_id: Optional[str] = None,
        scene_state: Optional[Dict[str, Any]] = None,
    ) -> List[SceneChange]:
        """S131: LOD1 макро-перемещение. Делегирует планирование LocalTraversalPlanner'у."""
        # Получаем текущий узел и координаты NPC из авторитетного состояния
        _npc_id = intent.actor_id
        _npc_data = npc_positions.get(_npc_id, {}) if npc_positions else {}
        current_pos = _npc_data.get("position", "")
        current_xy = _npc_data.get("local_position", {})

        # Защита micro-position: если NPC уже в целевом узле — пропускаем
        if current_pos and current_pos == intent.target_node_id:
            logger.debug(
                f"[GATE_B3] npc={intent.actor_id} reason=SAME_NODE node={intent.target_node_id}"
            )
            logger.debug(
                f"[MOVEMENT_ENGINE] Skip macro: {intent.actor_id} уже в {intent.target_node_id}"
            )
            return []

        # S140: Route-Aware Traversal Planning.
        # Сначала строим маршрут через граф (A*), затем берём первый шаг (waypoint)
        # и проверяем его физическую проходимость через LocalTraversalPlanner.
        target_node_obj = svc.get_node(intent.target_node_id) or svc.get_node(f"{intent.location_id}:{intent.target_node_id}")
        source_node_obj = svc.get_node(current_pos)
        if not target_node_obj:
             return []

        # S131 FIX (советник): current_xy — авторитетная позиция тела, а не графового узла.
        if isinstance(current_xy, dict) and "x" in current_xy and "y" in current_xy:
            _cx = float(current_xy["x"])
            _cy = float(current_xy["y"])
        elif source_node_obj:
            _cx = source_node_obj.x
            _cy = source_node_obj.y
        else:
            return []

        source_xy = (_cx, _cy)

        # S140: Ищем топологический маршрут через A*
        path_nodes = svc.find_path(source_xy, target_node_obj)
        
        # S-141: Инициализируем MovementTrace для диагностики
        _trace = MovementTrace(
            actor_id=intent.actor_id,
            source_position=source_xy,
            source_node=source_node_obj,
            target_node=target_node_obj
        )
        
        # S140.1 FIX: Если A* вернул ровно 1 узел — NPC уже стоит на цели.
        if path_nodes and len(path_nodes) == 1:
            _trace.path_status = PathStatus.ALREADY_AT_TARGET
            logger.debug(f"[MOVEMENT_TRACE] npc={intent.actor_id} status=ALREADY_AT_TARGET node={path_nodes[0].node_id}")
            return []
            
        if not path_nodes or len(path_nodes) < 2:
            _trace.path_status = PathStatus.NO_PATH
            _trace.failure = MovementFailure.NO_PATH
            _trace.reason = f"A* no path to {intent.target_node_id}"
            logger.warning(f"[MOVEMENT_TRACE] npc={intent.actor_id} failure={_trace.failure.value} reason={_trace.reason}")
            return []
        
        _trace.path_status = PathStatus.VALID_PATH
        _trace.path_nodes = path_nodes
        
        if intent.actor_id == "guard_borko":
            logger.debug(f"[BORKO_ASTAR] current_pos={current_pos} source_xy={source_xy} target={target_node_obj.node_id} path={[n.node_id for n in path_nodes]}")

        # Берём первый шаг маршрута (следующий waypoint)
        next_node = path_nodes[1]
        
        # V8-SP-16.1 FIX: Убрано случайное смещение (_offset_x/_offset_y).
        # Оно уводило NPC за стены (CLEARANCE_FAIL) при движении к boundary nodes.
        target_xy = (next_node.x, next_node.y)

        _dist = math.hypot(target_xy[0] - source_xy[0], target_xy[1] - source_xy[1])

        # V8-SP-24 FIX: Boundary node micro_snap deadlock
        if getattr(next_node, "role", None) == NodeRole.BOUNDARY:
            _b_info = svc.get_boundary_info(next_node.node_id) or {}
            _materialize_target_loc = _b_info.get("neighbor_chunk", "")
            _entry_hint = _b_info.get("entry_node_hint", "") or f"{_materialize_target_loc}:entrance"
            _target_svc = self._resolve_spatial_service(_materialize_target_loc, campaign_id, scene_state) if scene_state else None
            if _target_svc:
                _target_node_obj = _target_svc.get_node(_entry_hint.split(":")[-1]) or _target_svc.get_node(_entry_hint)
                if _target_node_obj:
                    _active_travs = scene_state.get("active_traversals", {}) if scene_state else {}
                    if isinstance(_active_travs, dict) and intent.actor_id in _active_travs:
                        del _active_travs[intent.actor_id]
                    return [SceneChange(
                        type=ChangeType.NPC_POSITION, target=intent.actor_id,
                        field="position", value=_target_node_obj.node_id,
                        cause=f"cross_loc_materialize:{intent.reason}", tick=tick,
                        target_location_id=_materialize_target_loc,
                        target_local_xy=(_target_node_obj.x, _target_node_obj.y),
                        traversal_proposal=None,
                    )]
            logger.error(f"[MICRO_SNAP_BOUNDARY_DEADLOCK] npc={intent.actor_id} next_node={next_node.node_id}")
            return []

        if _dist < 0.1:
            # V8-SP-16 FIX: Обновляем node_id (position), чтобы A* продвигался по маршруту.
            return [
                SceneChange(
                    type=ChangeType.NPC_POSITION,
                    target=intent.actor_id,
                    field="position",
                    value=next_node.node_id,
                    cause=f"micro_snap:{intent.reason}",
                    tick=tick,
                    target_location_id=location_id,
                    target_local_xy=(next_node.x, next_node.y),
                )
            ]

        plan_result = self._compile_traversal_plan(
            intent, svc, current_pos, tick, source_xy, target_xy, next_node
        )

        if plan_result.status == MovementPlanStatus.REJECTED:
            logger.debug(f"[GATE_B3] npc={intent.actor_id} reason=PLAN_REJECTED reason={plan_result.reason}")
            return []

        if plan_result.status != MovementPlanStatus.ACCEPTED or plan_result.proposal is None:
            logger.error(f"[GATE_B3] npc={intent.actor_id} reason=ACCEPTED_NULL_PROPOSAL (Kernel Violation)")
            return []

        # S131: Извлекаем целевые координаты из proposal для логирования и SceneChange.target_local_xy.
        target_xy = plan_result.proposal.path_waypoints[-1]

        logger.info(
            f"[PIPELINE][MOVEMENT][RELOCATE] npc={intent.actor_id} → zone={next_node.node_id} reason={intent.reason} exact_xy={target_xy} dist={plan_result.proposal.distance:.2f} ticks={plan_result.proposal.duration_ticks}"
        )
        logger.debug(
            f"[GATE_B3] npc={intent.actor_id} reason=SUCCESS target={next_node.node_id} loc={location_id}"
        )
        _trace.traversal_created = True
        logger.info(f"[MOVEMENT_TRACE] npc={intent.actor_id} status=VALID_PATH path_len={len(path_nodes)} traversal=CREATED")
        
        # NEW-ORIENT-001 FIX: Вычисляем угол поворота тела к цели и добавляем SceneChange.
        _heading = math.atan2(target_xy[1] - source_xy[1], target_xy[0] - source_xy[0])
        
        return [
            SceneChange(
                type=ChangeType.NPC_POSITION,
                target=intent.actor_id,
                field="position",
                value=next_node.node_id,  # S140: Следующий waypoint маршрута A*
                cause=f"semantic_relocation:{intent.reason}",
                tick=tick,
                target_location_id=location_id,
                target_local_xy=target_xy,  # ADR-065: Точные координаты цели
                traversal_proposal=plan_result.proposal,  # ADR-O-323: Авторизованный паспорт
            ),
            SceneChange(
                type=ChangeType.NPC_POSITION,
                target=intent.actor_id,
                field="body_heading",
                value=_heading,
                cause="semantic_relocation_heading",
                tick=tick,
                target_location_id=location_id,
            )
        ]

    @staticmethod
    def _extract_location(intent: MovementIntent) -> str:
        """Берёт location_id напрямую из intent."""
        return intent.location_id
