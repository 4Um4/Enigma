"""
path: /project/backend/app/services/npc/activity_lifecycle_service.py
Назначение: Living Activity (шаг 4) — конвертер Фазы 0.7: обобщение сонного
    шаблона (eligibility → факт npc["activity_state"] → шаги → терминал
    с outcome-фактом). Исполняющий гейт G3 (ADR-O-376): ревалидация
    W2-предусловий — долг вызывающего, конвертер и есть вызывающий; мутации
    мира — ТОЛЬКО типизированные операции WorldObjectStore. Движение —
    побочный эффект деятельности: MacroMovementGoal присоединяется к
    life_intents ДО Гейта① (арбитраж конфликтов — арбитр).
    Guarded: ACTIVITY_LIFECYCLE_ENABLED (default OFF) = байт-идентичный
    no-op; отказ конвертера = деградация канала, не тика (G2-паттерн D5).
Зависимости: app.domain.activity, app.domain.movement, app.services.world.*
Основные сущности: run_activity_lifecycle, _try_onset, _advance, _terminate
"""
from __future__ import annotations

import dataclasses
import logging
import math
import os
from typing import Any, Dict, List, Optional, Tuple

from app.domain.activity import ActivityState, ActivityStep, ActivityType, StepKind
from app.domain.desire import Desire
from app.domain.movement import IntentDomain, MacroMovementGoal, PRIORITY_NEEDS
from app.domain.semantic_action import WorldActionType
from app.domain.world_object import ObjectRelationKind, WorldObject
from app.models.spatial_contracts import NodeRole
from app.services.npc.activity_catalog import ACTIVITY_CATALOG, _SPEC_BY_TYPE
from app.services.scene_change import ChangeType, SceneChange
from app.services.world.affordance_resolver import AffordanceResolver, effective_state
from app.services.world.world_object_store import WorldObjectStore

logger = logging.getLogger(__name__)

_ACTIVITY_ENABLED_ENV = "ACTIVITY_LIFECYCLE_ENABLED"

# Порог желания для старта деятельности (CALIBRATION_CANDIDATE, не онтология)
_ONSET_URGENCY: float = 0.5
# Таймаут без прогресса — честный FAILURE-исход: желание продолжает давить,
# плохая раскладка контента ловится, а не затыкается
_ACTIVITY_TIMEOUT_TICKS: int = 60

# Проекция факта в наблюдаемый ярлык: HUD/R3 читают npc_positions.activity
# (сон-канал: wake пишет field="activity" той же фабрикой SceneChange).
# Ярлык — ПРОЕКЦИЯ, насыщение пишет только терминал (Шаг 5).
_ACTIVITY_DISPLAY_LABEL = {
    ActivityType.EAT: "eating",
    ActivityType.SERVE: "serving",  # ADR-O-389: onset пишет work-pass, терминал чистит сам
}


def _emit_label_change(ctx: Any, orchestrator: Any, npc_id: str, label: str) -> None:
    """Наблюдаемая занятость → npc_positions.activity (сон-прецедент)."""
    try:
        _change = SceneChange(
            type=ChangeType.NPC_POSITION,
            target=npc_id,
            field="activity",
            value=label,
            cause="activity_lifecycle",
        )
        orchestrator._apply_with_shadow_observation(
            ctx, [_change], phase_label="ACTIVITY_LIFECYCLE"
        )
    except Exception as exc:
        # Деградация канала видимости, не тика (G2 D5); L4: громко
        logger.warning(f"[ACTIVITY] label emit fault {npc_id}: {exc}")


def _activity_enabled() -> bool:
    return os.environ.get(_ACTIVITY_ENABLED_ENV, "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def living_activity_owns_needs() -> bool:
    """Публичный гейт для смежных модулей (life_engine, шаг 5).

    Оба флага ON (ACTIVITY_LIFECYCLE_ENABLED ∧ DESIRES_ENABLED): контур
    деятельностей владеет насыщением потребностей. Частичное включение
    (activity без desires) голодало бы без желаний — флаги включаются
    ПАРОЙ (dev-профиль среза EAT)."""
    from app.services.npc.desire_generator import _desires_enabled

    return _activity_enabled() and _desires_enabled()


def legacy_need_suppressed(need_name: str) -> bool:
    """Публичный гейт: легаси need-driven движение подавлено для
    потребности, чей субъект покрыт каталогом деятельностей —
    двойного трека нет, доменом владеет конвертер."""
    if not living_activity_owns_needs():
        return False
    from app.services.npc.desire_generator import _NEED_TO_DESIRE

    _entry = _NEED_TO_DESIRE.get(need_name)
    if not _entry:
        return False
    return _entry[0] in ACTIVITY_CATALOG


def _npc_id(npc: Dict[str, Any]) -> str:
    return str(npc.get("npc_id") or npc.get("id") or "")


def _npc_xy(npc: Dict[str, Any]) -> Tuple[float, float]:
    _p = npc.get("local_position") or {}
    return (float(_p.get("x", 0.0)), float(_p.get("y", 0.0)))


def _is_settled(scene_state: Dict[str, Any], npc_id: str) -> bool:
    """Сон-прецедент: прибытие предшествует действию с объектом."""
    _trav = scene_state.get("active_traversals")
    return not (isinstance(_trav, dict) and npc_id in _trav)


def _get_object(scene_state: Dict[str, Any], object_id: str) -> Optional[WorldObject]:
    """Отсутствие цели — легальный провал (target_vanished), не тихий None."""
    if not object_id:
        return None
    try:
        return WorldObjectStore.get(scene_state, object_id)
    except Exception as exc:
        # Отсутствие цели — легальный исход (target_vanished), не тихий None (L4)
        logger.debug(f"[ACTIVITY] get_object {object_id}: {exc}")
        return None


def _body_view(npc: Dict[str, Any]):
    """View для W2-предикатов. Falsy body_state → нет деятельности
    (§ENIGMA-003: отсутствие ≠ нейтральность; мёртвый/без сознания не ест)."""
    _bs = npc.get("body_state")
    if not isinstance(_bs, dict) or not _bs:
        return None
    from app.domain.body_state_view import build_body_state_view

    try:
        return build_body_state_view(_bs, _npc_id(npc))
    except ValueError as exc:
        # §ENIGMA-003: отсутствие ≠ нейтральность; деятельность не рождается (L4)
        logger.debug(f"[ACTIVITY] body_view fault {_npc_id(npc)}: {exc}")
        return None


def _at_node(npc: Dict[str, Any], node_id: str) -> bool:
    _pos = str(npc.get("position", "") or "")
    return bool(_pos) and bool(node_id) and (
        _pos == node_id or _pos.endswith(f":{node_id}")
    )


def _step_forward(npc: Dict[str, Any], state: ActivityState, tick: int) -> None:
    """Шаг завершён: персистентный resume-токен двигается (§14: elapsed —
    производная времени, ничего не накапливаем)."""
    _next = dataclasses.replace(
        state, step_index=state.step_index + 1, step_started_tick=tick
    )
    npc["activity_state"] = _next.to_dict()


def _find_target(
    scene_state: Dict[str, Any], npc: Dict[str, Any], target_archetype: str
) -> Optional[WorldObject]:
    """World query: ближайший доступный источник. Детерминизм: ties →
    лексикографический минимум id. Занятые (не-FREE) — не цель: контракт
    query_objects_at (позиция занятых — производная, не истина)."""
    _loc = str(npc.get("location_id") or npc.get("location") or "")
    _xy = _npc_xy(npc)
    _ids = WorldObjectStore.query_objects_at(scene_state, _loc, _xy, radius=1.0e6)
    _best: Optional[WorldObject] = None
    _best_d = float("inf")
    for _oid in sorted(_ids):
        _obj = _get_object(scene_state, _oid)
        if _obj is None or _obj.archetype != target_archetype:
            continue
        if effective_state(_obj) != "AVAILABLE":
            continue
        _d = math.hypot(_obj.position[0] - _xy[0], _obj.position[1] - _xy[1])
        if _d < _best_d:
            _best, _best_d = _obj, _d
    return _best


def _build_goal(
    npc: Dict[str, Any], state: ActivityState, step: ActivityStep
) -> MacroMovementGoal:
    return MacroMovementGoal(
        actor_id=_npc_id(npc),
        target_node_id=str(step.target_ref),
        from_node_id=str(npc.get("position", "") or ""),
        location_id=str(npc.get("location_id") or npc.get("location") or ""),
        reason=f"activity:{state.activity_type.value}:{state.desire_id}:{state.target_ref}",
        domain=IntentDomain.ROUTINE,
        priority=PRIORITY_NEEDS,
    )


def _terminate(
    ctx: Any,
    orchestrator: Any,
    npc: Dict[str, Any],
    state: ActivityState,
    *,
    success: bool,
    reason: str,
) -> None:
    """Терминал = outcome-факт. NO_LABEL_SATISFACTION: потребность обнуляется
    ТОЛЬКО здесь (для success), никогда ярлыком."""
    _tick = ctx.tick_number
    _nid = _npc_id(npc)
    if success:
        _spec = _SPEC_BY_TYPE.get(state.activity_type)
        _need_name = _spec.success.need_name if _spec else ""
        _needs = npc.get("needs")
        if _need_name and isinstance(_needs, dict) and _need_name in _needs:
            _needs[_need_name] = 0.0
        for _d in npc.get("desires") or []:
            if isinstance(_d, dict) and _d.get("desire_id") == state.desire_id:
                _d["last_fulfilled_tick"] = _tick
    npc.pop("activity_state", None)
    _emit_label_change(ctx, orchestrator, _nid, "")
    _publish_outcome(orchestrator, _nid, state, success, reason, _tick)

    # ADR-O-389 (WORK, S256): терминал SERVE = момент исполнения сделки.
    # Settlement — только по success-пути; провал деятельности → заказ
    # FAILED без экономических мутаций (L-W3). Гейт call-time (L-W5).
    if state.activity_type is ActivityType.SERVE:
        from app.services.economy.work_orders import fail_order, settle_order

        if success:
            settle_order(ctx, orchestrator, seller_id=_nid, order_id=state.target_ref)
        else:
            fail_order(ctx, order_id=state.target_ref, reason=reason)

    logger.info(
        f"[ACTIVITY] {_nid}: {state.activity_type.value} terminal "
        f"success={success} reason={reason} tick={_tick}"
    )


def _publish_outcome(
    orchestrator: Any,
    npc_id: str,
    state: ActivityState,
    success: bool,
    reason: str,
    tick: int,
) -> None:
    """Событие исхода — сон-прецедент (строковый event_type, той же фабрикой
    EventDTO). Наблюдаемость; отказ публикации — деградация канала, не тика."""
    try:
        _bus = orchestrator._get_event_bus()
        if _bus is None:
            return
        from app.domain.events import EventDTO

        _bus.publish(
            EventDTO.create(
                event_type="activity_outcome",
                source=npc_id,
                payload={
                    "activity_type": state.activity_type.value,
                    "desire_id": state.desire_id,
                    "target_ref": state.target_ref,
                    "success": success,
                    "reason": reason,
                },
                timestamp=float(tick),
            )
        )
    except Exception as exc:
        logger.warning(f"[ACTIVITY] outcome event fault (degraded): {exc}")


def _advance(
    ctx: Any, orchestrator: Any, npc: Dict[str, Any], state_raw: Dict[str, Any]
) -> Optional[MacroMovementGoal]:
    _tick = ctx.tick_number
    state = ActivityState.from_dict(state_raw)
    if _tick - state.started_tick > _ACTIVITY_TIMEOUT_TICKS:
        _terminate(ctx, orchestrator, npc, state, success=False, reason="timeout")
        return None
    if state.step_index >= len(state.steps):
        _terminate(ctx, orchestrator, npc, state, success=False, reason="no_step")
        return None
    _step = state.steps[state.step_index]
    if _step.step_kind is StepKind.MOVE:
        return _advance_move(ctx, orchestrator, npc, state, _step)
    if _step.step_kind is StepKind.OBJECT_ACTION:
        _advance_object_action(ctx, orchestrator, npc, state, _step)
        return None
    _advance_body_action(ctx, orchestrator, npc, state, _step)
    return None


def _advance_move(
    ctx: Any,
    orchestrator: Any,
    npc: Dict[str, Any],
    state: ActivityState,
    step: ActivityStep,
) -> Optional[MacroMovementGoal]:
    """Движение = побочный эффект. Прибытие определяется АВТОРИТЕТОМ W2:
    искомое объектное действие доступно в resolve() ⇒ adjacency выполнена."""
    _nid = _npc_id(npc)
    if not _is_settled(ctx.scene_state, _nid):
        return None  # в пути — ждём прибытия (следующий тик проверит settled)
    _obj = _get_object(ctx.scene_state, state.target_ref)
    if _obj is None:
        _terminate(ctx, orchestrator, npc, state, success=False, reason="target_vanished")
        return None
    _view = _body_view(npc)
    if _view is None:
        return None
    _wanted = _wanted_object_action(state)
    _actions = AffordanceResolver.resolve(_obj, _view, _npc_xy(npc))
    if _wanted is not None and any(a.action_type == _wanted for a in _actions):
        _step_forward(npc, state, ctx.tick_number)  # прибыл: TAKE доступен
        return None
    if not _at_node(npc, step.target_ref):
        return _build_goal(npc, state, step)
    return None  # у узла, но не в adjacency → таймаут поймает честно


def _wanted_object_action(state: ActivityState) -> Optional[WorldActionType]:
    """Следующий объектный шаг после MOVE — искомое действие (TAKE)."""
    for _s in state.steps:
        if _s.step_kind is StepKind.OBJECT_ACTION:
            try:
                return WorldActionType(_s.action_type)
            except ValueError as exc:
                # Повреждённая каталожная запись — наблюдаемо, не тихо (L4)
                logger.debug(f"[ACTIVITY] bad catalog action {_s.action_type!r}: {exc}")
                return None
    return None


def _advance_object_action(
    ctx: Any,
    orchestrator: Any,
    npc: Dict[str, Any],
    state: ActivityState,
    step: ActivityStep,
) -> None:
    """G3-гейт: ревалидация W2 (предусловия против текущего мира) →
    типизированная мутация стора. Никакой объектной хирургии."""
    _obj = _get_object(ctx.scene_state, state.target_ref)
    if _obj is None:
        _terminate(ctx, orchestrator, npc, state, success=False, reason="target_vanished")
        return
    _view = _body_view(npc)
    if _view is None:
        return
    try:
        _wanted = WorldActionType(step.action_type)
    except ValueError:
        _terminate(ctx, orchestrator, npc, state, success=False, reason="bad_action")
        return
    _actions = AffordanceResolver.resolve(_obj, _view, _npc_xy(npc))
    if not any(a.action_type == _wanted for a in _actions):
        _terminate(ctx, orchestrator, npc, state, success=False, reason="take_unavailable")
        return
    WorldObjectStore.establish_relation(
        ctx.scene_state,
        state.target_ref,
        ObjectRelationKind.HELD_BY,
        _npc_id(npc),
    )
    _step_forward(npc, state, ctx.tick_number)


def _advance_body_action(
    ctx: Any,
    orchestrator: Any,
    npc: Dict[str, Any],
    state: ActivityState,
    step: ActivityStep,
) -> None:
    """Телесная петля (сон-прецедент: recovery без LLM). Предусловие —
    объект в руках (HOLDER == npc). Насыщение линейно за длительность —
    видимый прогресс деятельности."""
    _tick = ctx.tick_number

    # ADR-O-389 (WORK, S256): SERVE — телесная деятельность БЕЗ предмета
    # (target_ref = order_id, не WorldObject; D6). Длительность → терминал;
    # без consume-петли и damage-закона. OFF не достижим: материализуется
    # только work-pass'ом под WORK_ENABLED (L-W5 by construction).
    if state.activity_type is ActivityType.SERVE:
        if state.step_started_tick < 0:
            state = dataclasses.replace(
                state, step_started_tick=_tick
            )
            npc["activity_state"] = state.to_dict()
        if _tick - state.step_started_tick >= int(step.duration_ticks):
            _terminate(ctx, orchestrator, npc, state, success=True, reason="served")
        return

    _obj = _get_object(ctx.scene_state, state.target_ref)
    if _obj is None or _obj.holder != _npc_id(npc):
        _terminate(ctx, orchestrator, npc, state, success=False, reason="not_holding")
        return
    _spec = _SPEC_BY_TYPE.get(state.activity_type)
    _need_name = _spec.success.need_name if _spec else ""
    _needs = npc.get("needs")
    if _need_name and isinstance(_needs, dict) and _need_name in _needs:
        _rate = 1.0 / max(1, int(step.duration_ticks))
        _needs[_need_name] = max(0.0, float(_needs[_need_name]) - _rate)
    if _tick - state.step_started_tick >= int(step.duration_ticks):
        _consume_terminal(ctx, orchestrator, npc, state)


def _consume_terminal(
    ctx: Any, orchestrator: Any, npc: Dict[str, Any], state: ActivityState
) -> None:
    """Истощение порции: damage-закон О6 (DESTROYED-терминал) + ЯВНЫЙ
    release (auto-release запрещён — constraint W-store). Идемпотентно:
    повторный вход не дублирует мутации."""
    _scene = ctx.scene_state
    _obj = _get_object(_scene, state.target_ref)
    if _obj is not None:
        if _obj.state != "DESTROYED":
            WorldObjectStore.apply_damage(_scene, state.target_ref, 1.0)
        if _obj.holder == _npc_id(npc):
            WorldObjectStore.release_relation(
                _scene, state.target_ref, ObjectRelationKind.HELD_BY
            )
    _terminate(ctx, orchestrator, npc, state, success=True, reason="consumed")


def _try_onset(ctx: Any, orchestrator: Any, npc: Dict[str, Any]) -> Optional[MacroMovementGoal]:
    """Eligibility (сон-шаблон): settled + желание с исполнителем в каталоге.
    Отсутствие источника — не он: желание продолжает давить (pressure)."""
    _nid = _npc_id(npc)
    if not _is_settled(ctx.scene_state, _nid):
        return None
    for _d in npc.get("desires") or []:
        if not isinstance(_d, dict):
            continue
        _spec = ACTIVITY_CATALOG.get(str(_d.get("subject_class", "")))
        if _spec is None:
            continue
        if float(_d.get("urgency", 0.0)) < _ONSET_URGENCY:
            continue
        return _onset_for_desire(ctx, orchestrator, npc, Desire.from_dict(_d), _spec)
    return None


def _onset_for_desire(
    ctx: Any,
    orchestrator: Any,
    npc: Dict[str, Any],
    desire: Desire,
    spec,
) -> Optional[MacroMovementGoal]:
    _tick = ctx.tick_number
    _nid = _npc_id(npc)
    _obj = _find_target(ctx.scene_state, npc, spec.target_archetype)
    if _obj is None:
        logger.debug(
            f"[ACTIVITY] {_nid}: no source for {desire.subject_class} — desire keeps pressing"
        )
        return None
    # Резолв пути: узел возле объекта. v1: источники еды живут у стойки
    # (BAR); генерализация выбора роли узла — при расширении каталога.
    _node_id = ""
    try:
        _spatial = orchestrator._resolve_spatial_service(ctx)
    except Exception as exc:
        # Мир не ответил путём — деятельность не рождается; громко (L4)
        logger.warning(f"[ACTIVITY] spatial resolve fault: {exc}")
        _spatial = None
    if _spatial is not None:
        _ref = _spatial.resolve_node(role=NodeRole.BAR, origin_xy=_obj.position)
        if _ref is None:
            _ref = _spatial.resolve_node(role=NodeRole.DEFAULT, origin_xy=_obj.position)
        if _ref is not None:
            _node_id = str(_ref.node_id)
    if not _node_id:
        return None  # мир не ответил путём — деятельность не рождается
    _steps = tuple(
        ActivityStep(
            step_kind=_s.step_kind,
            action_type=_s.action_type,
            target_ref=(
                _node_id if _s.step_kind is StepKind.MOVE else str(_obj.object_id)
            ),
            duration_ticks=_s.duration_ticks,
        )
        for _s in spec.steps
    )
    _state = ActivityState(
        activity_id=ActivityState.build_id(_nid, spec.activity_type, _tick),
        activity_type=spec.activity_type,
        desire_id=desire.desire_id,
        target_ref=str(_obj.object_id),
        steps=_steps,
        step_index=0,
        step_started_tick=_tick,
        started_tick=_tick,
        interruption_policy=spec.interruption_policy,
    )
    npc["activity_state"] = _state.to_dict()
    _emit_label_change(
        ctx,
        orchestrator,
        _nid,
        _ACTIVITY_DISPLAY_LABEL.get(spec.activity_type, spec.activity_type.value),
    )
    logger.info(
        f"[ACTIVITY] {_nid}: onset {spec.activity_type.value} "
        f"desire={desire.desire_id} target={_obj.object_id} node={_node_id}"
    )
    return _build_goal(npc, _state, _steps[0])


def _reconcile_activity_ownership(ctx: Any) -> None:
    """Владение — в реестр (сон-прецедент D-3): факт деятельности без
    владельца → activity-зеркало born-EXECUTING (инвариант
    INTERRUPTION_PRESERVES_GOAL: поедающего не прерывает болтовня)."""
    from app.services.action.commitment_registry import CommitmentRegistry

    CommitmentRegistry.reconcile_activity_ownership(
        ctx.scene_state, ctx.all_npcs_raw or [], ctx.tick_number
    )


def run_activity_lifecycle(ctx: Any, orchestrator: Any) -> List[MacroMovementGoal]:
    """Фаза 0.7 (Living Activity): advance + onset + reconcile.
    Возвращает MOVE-цели для life_intents — ДО Гейта① (simulation.py)."""
    if not _activity_enabled():
        return []
    _goals: List[MacroMovementGoal] = []
    try:
        for _npc in ctx.all_npcs_raw or []:
            if not isinstance(_npc, dict):
                continue
            if not _npc_id(_npc):
                continue
            _raw = _npc.get("activity_state")
            if isinstance(_raw, dict):
                _goal = _advance(ctx, orchestrator, _npc, _raw)
            else:
                _goal = _try_onset(ctx, orchestrator, _npc)
            if _goal is not None:
                _goals.append(_goal)
        _reconcile_activity_ownership(ctx)
    except Exception as exc:
        logger.warning(f"[ACTIVITY] converter fault (degraded, tick continues): {exc}")
    return _goals