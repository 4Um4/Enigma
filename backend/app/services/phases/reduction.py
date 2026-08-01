"""Фаза 8: Layered Reduction (Causal Depth Model).

Порядок слоёв: Physical (Combat) → Cognitive (Reaction) → Social.
Physical слой материализуется перед Cognitive для соблюдения причинности
без нарушения порядка исполнения (Dual Buffer Causal Model).

Вынесено из TickOrchestrator в рамках декомпозиции God-object (S99→S100).
"""

import logging
from typing import Callable, Optional, Tuple

from app.domain.identity_events import TraitDriftEvent
from app.domain.motion_core import TracePayload
from app.models.delta_payloads import PhysiologyPayload
from app.models.phase8 import Phase8Context, Phase8Handler, Phase8Result
from app.models.state_delta import DeltaDomain
from app.services.dto import _TickContext

logger = logging.getLogger(__name__)


def execute_reduction_phase(
    ctx: _TickContext,
    combat_sub: Phase8Handler,
    reaction_sub: Phase8Handler,
    social_sub: Phase8Handler,
    homeostasis_sub: Optional[Phase8Handler] = None,
    social_input_proj: Optional[Phase8Handler] = None,
    dynamic_field=None,
    l1_chronicle=None,
    resolve_spatial_fn: Optional[Callable] = None,
) -> None:
    """Выполнить Фазу 8: Layered Reduction.

    Args:
        ctx: Тиковый контекст.
        combat_sub: CombatSubscriber (Physical Layer).
        reaction_sub: ReactionSubscriber (Cognitive Layer).
        social_sub: SocialSubscriber (Social Layer).
        homeostasis_sub: HomeostasisProjector (Field Layer, Phase 0.5 only).
        social_input_proj: SocialInputProjector (Sensor Layer).
        dynamic_field: DynamicAffordanceField для стигмергических следов.
        l1_chronicle: L1Chronicle (опционально, для записи событий дрейфа).
        resolve_spatial_fn: Callable возвращающий SpatialService.
    """
    # 1. Perception Layer — УДАЛЕН. Вычисляется в Фазе 9 через LocalCausalSolver.

    # 2. Physical Layer (Combat: вычисление урона, генерация shock_impulse)
    combat_result = _execute_handler(ctx, combat_sub)

    # ADR-O-112 DIAG: Проверяем, что CombatSubscriber вернул
    if combat_result:
        logger.debug(
            f"[DIAG_PHASE8] combat_result: deltas={len(combat_result.deltas or [])} missed={len(getattr(combat_result, 'missed_targets', []))}"
        )
    else:
        logger.debug(
            "[DIAG_PHASE8] combat_result=None — CombatSubscriber вернул пустой результат"
        )

    # Извлекаем combat summary для DM (pain, shock, injuries, misses)
    if combat_result and ctx.shared_context is not None:
        _combat_data = {}
        _combat_l1_events = []  # SHI-FIX: L1Chronicle emission for attack/damage
        for d in combat_result.deltas or []:
            if (
                d.domain == DeltaDomain.PHYSIOLOGY
                and d.payload
                and isinstance(d.payload, PhysiologyPayload)
            ):
                _target = d.npc_id or d.target or "unknown"
                _combat_data[_target] = {
                    "pain_delta": d.payload.pain_delta,
                    "blood_loss_delta": d.payload.blood_loss_delta,
                    "shock_impulse": d.payload.shock_impulse,
                    "injuries": [
                        {
                            "zone": i.target_zone,
                            "severity": i.structural_damage,
                            "damage_type": i.damage_type,
                        }
                        for i in d.payload.add_injuries
                    ]
                    if d.payload.add_injuries
                    else [],
                }
                # SHI-FIX: L1Chronicle emission for attack/damage
                if d.payload.hp_delta < 0 or d.payload.add_injuries:
                    _combat_l1_events.append(
                        TraitDriftEvent(
                            tick_id=ctx.tick_number,
                            target_id=_target,
                            source_id="player",
                            effect_value=-0.2,
                            observation_weight=1.0,
                            event_type="attack",
                        )
                    )
                    _combat_l1_events.append(
                        TraitDriftEvent(
                            tick_id=ctx.tick_number,
                            target_id=_target,
                            source_id="combat",
                            effect_value=d.payload.hp_delta,
                            observation_weight=1.0,
                            event_type="damage",
                        )
                    )

        # SHI-FIX: Commit L1 events
        if _combat_l1_events and l1_chronicle is not None:
            l1_chronicle.commit_tick_buffer(_combat_l1_events, ctx.tick_number)

        # Промахи по расстоянию — DM должен знать что атака не достигла цели
        _missed = getattr(combat_result, "missed_targets", [])
        for _miss in _missed:
            _combat_data[_miss["npc_id"]] = {
                "miss": True,
                "distance": _miss["distance"],
                "max_range": _miss["max_range"],
            }
        if _combat_data:
            ctx.shared_context.combat_data = _combat_data
            logger.debug(
                f"[DIAG_PHASE8] combat_data targets={list(_combat_data.keys())} data={_combat_data}"
            )
        else:
            logger.debug(
                "[DIAG_PHASE8] combat_data EMPTY — no PhysiologyPayload in deltas"
            )

    # Материализация Physical Layer: иммутабельный снимок для Cognitive слоя
    physical_deltas_tuple: Tuple = ()
    if combat_result and combat_result.deltas:
        physical_deltas_tuple = tuple(combat_result.deltas)

    # 3-5. Cognitive → Social → Sensor — единый проход
    # Combat остаётся отдельным: генерирует physical_deltas для последующих слоёв
    # HomeostasisProjector не вызывается здесь (он чистый Field Layer для Фазы 0.5)
    for _handler in (reaction_sub, social_sub, social_input_proj):
        if _handler is not None:
            _execute_handler(
                ctx, _handler, physical_deltas_materialized=physical_deltas_tuple
            )

    # DSTC: Удалён досрочный apply_batch (S75-FIX).
    # Дельты останутся в delta_buffer и будут применены к interpretation_snapshot в Phase 9.


def _execute_handler(
    ctx: _TickContext,
    handler: Phase8Handler,
    physical_deltas_materialized: Tuple = (),
) -> Optional[Phase8Result]:
    """Исполняет один обработчик Фазы 8 с изолированным контекстом."""
    # ADR-O-112 DIAG: Проверяем, есть ли накопленные события до drain
    if handler.name == "combat":
        _pending = getattr(handler, "_pending_events", [])
        logger.debug(
            f"[DIAG_PHASE8] combat_sub pending_events={len(_pending)} types={[getattr(e, 'type', '?') for e in _pending[:3]]}"
        )
    events = handler.drain_events()
    if handler.name == "combat" and not events:
        logger.debug(
            f"[DIAG_PHASE8] combat_sub DRAINED 0 events — _pending was={len(_pending)}"
        )
    _handler_name = getattr(handler, "__class__", type(handler)).__name__
    if events:
        logger.debug(
            f"[PHASE8_DRAIN] handler={_handler_name} events={len(events)} types={[getattr(e, 'type', '?') for e in events[:3]]}"
        )
    if not events:
        return None

    # БАГ 4 FIX: Гарантируем наличие spatial_query для CombatSubscriber (range gate).
    # В idle-тиках shared_context может быть None или не содержать spatial_query.
    if not hasattr(ctx, "shared_context") or ctx.shared_context is None:
        from types import SimpleNamespace

        # BUG-CORE-007 FIX: SimpleNamespace должен содержать scene_state,
        # иначе social_input_projector упадёт с AttributeError.
        ctx.shared_context = SimpleNamespace(scene_state=ctx.scene_state)

    if (
        not hasattr(ctx.shared_context, "spatial_query")
        or ctx.shared_context.spatial_query is None
    ):
        from app.services.spatial.spatial_query_service import SpatialQueryService

        ctx.shared_context.spatial_query = SpatialQueryService(
            npc_positions=ctx.scene_state.get("npc_positions", {}),
            scene_state=ctx.scene_state,
        )

    _npc_contexts = ctx.npc_contexts if ctx.npc_contexts else []
    try:
        phase8_ctx = Phase8Context(
            all_npcs_raw=ctx.all_npcs_raw,
            all_npc_contexts=_npc_contexts,
            shared_context=ctx.shared_context,
            campaign_id=ctx.campaign_id,
            tick_ctx=ctx,
            physical_deltas_materialized=physical_deltas_materialized,
        )
    except Exception as _ctx_err:
        # Инвариант 3: Наблюдаемость отказа — CDS должен видеть краши Phase8
        logger.warning(
            f"[PIPELINE][CRITICAL] phase=8_ctx handler={_handler_name} "
            f"error={type(_ctx_err).__name__}: {_ctx_err}"
        )
        return None

    try:
        result = handler.handle(events, phase8_ctx)
    except Exception as e:
        # Инвариант 3: Safeguard не = молчание. Крах виден CDS.
        logger.warning(
            f"[PHASE8_CRASH] handler={handler.name} error={type(e).__name__}: {e}"
        )
        logger.error(
            f"[PHASE_8] {handler.name} handle() failed: {e}. Events lost this tick."
        )
        return None

    # Применяем Phase8Result к _TickContext
    _apply_handler_result(
        ctx, result, handler.name, dynamic_field=None, resolve_spatial_fn=None
    )
    return result


def _apply_handler_result(
    ctx: _TickContext,
    result: Phase8Result,
    handler_name: str,
    dynamic_field=None,
    resolve_spatial_fn=None,
) -> None:
    """Применяет Phase8Result к _TickContext.

    perception → фильтр npc_contexts + perceiving_npcs
    social → deltas применяются к all_npcs_raw
    deltas с npc_id → применение к конкретному NPC
    """
    # Perception: фильтруем NPC контексты
    if result.perceiving_npc_ids is not None and ctx.shared_context is not None:
        _all_ctxs = ctx.npc_contexts if ctx.npc_contexts else []
        _filtered = [
            c for c in _all_ctxs if c.get("npc_id") in result.perceiving_npc_ids
        ]
        ctx.shared_context.npc_contexts = _filtered
        ctx.shared_context.perceiving_npcs = list(result.perceiving_npc_ids)

    # Deltas: маршрутизация через delta_buffer → apply_batch (ADR-002 единый мутатор)
    if result.deltas:
        ctx.delta_buffer.extend(result.deltas)
        ctx.prop_dirty = True
        logger.debug(
            f"[PHASE_8] {handler_name}: {len(result.deltas)} deltas routed to delta_buffer"
        )

        # S91: Эмит стигмергического следа (safety_confidence) при акте насилия
        if (
            handler_name == "combat"
            and dynamic_field is not None
            and resolve_spatial_fn is not None
        ):
            _loc_id = ctx.scene_state.get("location_id", "")
            _svc = resolve_spatial_fn()
            for delta in result.deltas:
                if delta.domain == DeltaDomain.PHYSIOLOGY:
                    _target_id = getattr(delta, "npc_id", None)
                    if _target_id and _svc:
                        _pos_data = ctx.scene_state.get("npc_positions", {}).get(
                            _target_id, {}
                        )
                        _pos = _pos_data.get("local_position", {})
                        _zone_id = _svc.get_zone_id(
                            _pos.get("x", 0.0), _pos.get("y", 0.0)
                        )
                        if _zone_id:
                            _trace = TracePayload(
                                region=_loc_id,
                                zone_id=_zone_id,
                                trace_type="safety_confidence",
                                magnitude=-0.2,
                                created_tick=ctx.tick_number,
                                ttl=100,
                                source_id="combat",
                            )
                            dynamic_field.apply_trace(_trace)

    # Legacy: prop_dirty от старых обработчиков (совместимость)
    if result.prop_dirty:
        ctx.prop_dirty = True
