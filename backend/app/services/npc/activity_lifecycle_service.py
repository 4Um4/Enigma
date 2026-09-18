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
from app.domain.movement import IntentDomain, MacroMovementGoal, PRIORITY_NEEDS, PRIORITY_REACTIVE
from app.domain.semantic_action import WorldActionType
from app.domain.world_object import ObjectRelationKind, WorldObject
from app.models.spatial_contracts import NodeRole
from app.services.npc.activity_catalog import ACTIVITY_CATALOG, _SPEC_BY_TYPE
from app.services.scene_change import ChangeType, SceneChange
from app.domain.activity import _KEY_AS_HOME  # S267: гейм-гейт активности
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
    ActivityType.SERVE: "serving",  # ADR-O-391: onset пишет work-pass, терминал чистит сам
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
        logger.info(f"[ACTIVITY] get_object {object_id}: {type(exc).__name__}: {exc}")
        return None


def _body_view(npc: Dict[str, Any]) -> Optional[Any]:
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
    # S267: адрес движения — сцена-дом активности, не mid-tick npc.location_id
    # (VANISH-класс: loc перезаписан чужим проходом → goal уходит в чужой граф,
    # узел не резолвится, движение молча не исполняется).
    _goal_loc = str(state.home_location or npc.get("location_id") or npc.get("location") or "")
    # S267 (L5-калибровка): деятельность потребности — домен SURVIVAL и
    # DRF-приоритет потребности (0.8, уровень need-intent :1198), не 0.5
    # (ниже расписания 0.6 — еда проигрывала движению по расписанию,
    # арбитр оставлял incumbent, adjacency недостижима структурно,
    # лента EATDIAG-ADJ: available=[] ×22). SPEC priority_hint=6.0
    # (SURVIVAL≈6, шкала s203.4) читается арбитром через domain при
    # включённом enforcement — политика и код арбитра не меняются.
    _survival = state.activity_type is ActivityType.EAT
    return MacroMovementGoal(
        actor_id=_npc_id(npc),
        target_node_id=str(step.target_ref),
        from_node_id=str(npc.get("position", "") or ""),
        location_id=_goal_loc,
        reason=f"activity:{state.activity_type.value}:{state.desire_id}:{state.target_ref}",
        domain=IntentDomain.SURVIVAL if _survival else IntentDomain.ROUTINE,
        priority=PRIORITY_REACTIVE if _survival else PRIORITY_NEEDS,
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

    # ADR-O-391 (WORK, S256): терминал SERVE = момент исполнения сделки.
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

    # IRON RIVER Phase B / Фронт 1 (гонки за порцию): ревалидация живости
    # объектной цели ДО диспатча шага. Диагноз eatlog: конкурент съедает
    # порцию (DESTROYED в сторе) или берёт её (holder != мы) между нашим
    # онсетом и прибытием — цель мертва, но _get_object её возвращает →
    # шаги вращаются вхолостую до 60-тикного timeout. Честный быстрый
    # провал: desire продолжает давить, _find_target возьмёт живую порцию.
    # SERVE не затронут: target_ref = order_id, не WorldObject-archetype.
    if (
        state.activity_type is not ActivityType.SERVE
        and state.target_ref.startswith("wo_")
    ):
        _target_obj = _get_object(ctx.scene_state, state.target_ref)
        _owner = _npc_id(npc)
        if (
            _target_obj is None
            or getattr(_target_obj, "state", "") == "DESTROYED"
            or (
                getattr(_target_obj, "holder", None) not in (None, "", _owner)
            )
        ):
            _reason = (
                "target_vanished"
                if _target_obj is None
                else "target_consumed_by_other"
                if _target_obj.state == "DESTROYED"
                else "target_taken_by_other"
            )
            _terminate(ctx, orchestrator, npc, state, success=False, reason=_reason)
            return None

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

    # ADR-O-391 (WORK, S256): SERVE — телесная деятельность БЕЗ предмета
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
        # S264 (выравнивание темпов, приказ Мастера «плавно и
        # последовательно»): порция гасит ПОТРЕБНОСТЬ ПОЛНОСТЬЮ,
        # распределённо по длительности шага — прежний rate=1/duration
        # списывал всего 0.33 за порцию при фоне голода +0.08/тик →
        # еда слабее голода вдвое → вечные 0.67 (EAT-диагноз S264).
        # Единая еда = полное насыщение (реал-семантика); темп «сколько
        # тиков жуём» остаётся duration-контролем плавности.
        _current = float(_needs[_need_name])
        _per_tick = _current / max(1, int(step.duration_ticks))
        _needs[_need_name] = max(0.0, _current - _per_tick)
        # S264: гасим ОБЕ истины голода (LEGACY-HUNGER :508 — body_state
        # — писатель LifeEngine; без синхронизации рост перетирает гашение)
        _bs = npc.get("body_state")
        _bs_hunger_tick = 0.0
        if _need_name == "hunger" and isinstance(_bs, dict) and "hunger" in _bs:
            _bs_current = float(_bs["hunger"])
            _bs_hunger_tick = _bs_current / max(1, int(step.duration_ticks))
            _bs["hunger"] = max(0.0, _bs_current - _bs_hunger_tick)
        # S268/PR-7+1 (E7-фикс, §11.5): npc здесь — _npc_dict_for_write
        # (deepcopy-копия Фазы 5, pipeline:217): локальное гашение умирает
        # с копией, насыщение не накапливается (E7 hunger=1.00). Гасим
        # КАНОНИЧЕСКИЙ экземпляр (life-кэш — владелец обеих истин, §13.3)
        # через _canon_npcs (ссылки на оригиналы, run_activity_lifecycle).
        _canon = getattr(ctx, "_canon_npcs", None) or {}
        _orig = _canon.get(_npc_id(npc))
        if _orig is not None and _orig is not npc and isinstance(_orig, dict):
            _o_needs = _orig.get("needs")
            if isinstance(_o_needs, dict) and _need_name in _o_needs:
                _oc = float(_o_needs[_need_name])
                _o_needs[_need_name] = max(0.0, _oc - _oc / max(1, int(step.duration_ticks)))
            _o_bs = _orig.get("body_state")
            if _need_name == "hunger" and isinstance(_o_bs, dict) and "hunger" in _o_bs:
                _obc = float(_o_bs["hunger"])
                _o_bs["hunger"] = max(0.0, _obc - _obc / max(1, int(step.duration_ticks)))
        # S268: третья истина — nutrition (S2B.4, 0-100, SSOT body_state) —
        # растёт легальной дельтой (съедено = сытость; StateApplicator:1090).
        # payload СТРОГО типизированный (LOCKED v1 — dict-произвол запрещён).
        if _need_name == "hunger" and _bs_hunger_tick > 1e-9 and getattr(ctx, "delta_buffer", None) is not None:
            from app.models.delta_payloads import PhysiologyPayload
            from app.models.state_delta import DeltaDomain, StateDeltas
            ctx.delta_buffer.append(StateDeltas(
                npc_id=_npc_id(npc),
                domain=DeltaDomain.PHYSIOLOGY,
                payload=PhysiologyPayload(nutrition_delta=+_bs_hunger_tick),
                source=f"activity_eat:{state.target_ref}",
            ))
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
    spec: Any,
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
        home_location=str(
            (ctx.scene_state.get("location_id") if isinstance(ctx.scene_state, dict) else "") or ""
        ),
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
    # S266-РАННЕЕ: если deepcopy-слой потерял world_objects (усечение
    # между create_tick_context и Фазой 0.7), восстановить subtree из
    # SSOT — SSM _tick_scenes (факт foodfate: SSM жив, ctx пуст).
    _ss = ctx.scene_state
    if isinstance(_ss, dict) and not _ss.get("world_objects"):
        _sm = getattr(orchestrator, "_scene_manager", None)
        if _sm is not None:
            _loc = _ss.get("location_id", "")
            _live = (_sm._tick_scenes or {}).get(_loc)
            if isinstance(_live, dict):
                _wo = _live.get("world_objects")
                if _wo:
                    _ss["world_objects"] = _wo
    # S266-Н18-СИНХРО: activity_state записывается конвертером в
    # ctx.all_npcs_raw, а H-18-гейт LifeEngine читает свой кэш —
    # ДВА экземпляра dict (гипотеза, доказанная eatdiag: гейт слеп).
    # Синхронизация: пробрасываем activity_state из ctx-словарей
    # в npc_states (кэш LifeEngine) — гейт начинает видеть деятельность.
    _states = getattr(orchestrator, "_get_life_engine", lambda: None)()
    if _states:
        _cached = _states.get_npc_states(ctx.campaign_id) if hasattr(_states, "get_npc_states") else []
        _by_id = {n.get("npc_id") or n.get("id"): n for n in (_cached or []) if isinstance(n, dict)}
        # S268/E7: канонические экземпляры (life-кэш, ссылки) — гашение
        # потребностей владельцем, а не копией Фазы 5 (см. _advance_body_action)
        setattr(ctx, "_canon_npcs", _by_id)
        for _n in (ctx.all_npcs_raw or []):
            if not isinstance(_n, dict):
                continue
            _nid = _n.get("npc_id") or _n.get("id") or ""
            _act = _n.get("activity_state")
            _cached_npc = _by_id.get(_nid)
            if _cached_npc is not None:
                if isinstance(_act, dict):
                    _cached_npc["activity_state"] = _act
                else:
                    # S266-ФИНАЛ: терминал popped activity_state из ctx —
                    # кэш обязан увидеть завершение (иначе вечный busy
                    # и кэш-голод расходится с ctx-гашением).
                    _cached_npc.pop("activity_state", None)
                # S266-ДВУСТОРОННЯЯ needs-синхронизация: кэш-письма
                # (тест-инъекции, легаси) → ctx (W5); ctx-гашения
                # (терминал/consume) → кэш (E7: hunger=1.00 при
                # DESTROYED=2 — гасили в ctx, читали из кэша).
                _cached_needs = _cached_npc.get("needs")
                _ctx_needs = _n.get("needs")
                if isinstance(_cached_needs, dict) and isinstance(_ctx_needs, dict):
                    _merged = dict(_cached_needs)
                    _merged.update(_ctx_needs)
                    _cached_npc["needs"] = _merged
                    _n["needs"] = _merged
    _goals: List[MacroMovementGoal] = []
    try:
        for _npc in ctx.all_npcs_raw or []:
            if not isinstance(_npc, dict):
                continue
            if not _npc_id(_npc):
                continue
            # S266-локация-гейт: конвертер работает на СЦЕНЕ ctx
            # (active_location). NPC из ДРУГИХ локаций здесь чужие:
            # их цель (порция tavern) недостижима из market_square-сцены
            # → ложный target_vanished (ctx_probe: loc=market_square
            # при живых порциях в tavern). Пропускаем не-местных;
            # их тик придёт на своей локации.
            _npc_loc = str(_npc.get("location_id") or _npc.get("location") or "")
            _ctx_loc = str((_ss.get("location_id") if isinstance(_ss, dict) else "") or "")
            # S267-ГОМЕ-ГЕЙТ: активная деятельность адресована сцене онсета,
            # не текущему npc.location_id (который mid-tick перезаписывается
            # чужими проходами — VANISH-факт S267). Гейм-гейт: home=пусто
            # (легаси) → старое поведение; home=сцена → гейт по нему.
            _gate_loc = _ctx_loc
            _raw_state = _npc.get("activity_state")
            if (
                isinstance(_raw_state, dict)
                and str(_raw_state.get(_KEY_AS_HOME, "") or "")
                and _ctx_loc
            ):
                _gate_loc = str(_raw_state[_KEY_AS_HOME])
            if _ctx_loc and _gate_loc and _gate_loc != _ctx_loc:
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