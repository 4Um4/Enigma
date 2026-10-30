# -*- coding: utf-8 -*-
"""
Phases/Commit Phase — Изоляция Фазы 10 (Persistence).

path: backend/app/services/phases/commit_phase.py
Назначение: Атомарный коммит состояния за тик (Устав §4.2.1).
Зависимости: app.services.scene_state_manager, app.services.npc.life_engine
Основные сущности: execute_persistence
"""

import logging
from collections import defaultdict
from typing import Any

from app.models.state_delta import DeltaDomain

logger = logging.getLogger(__name__)


def execute_persistence(ctx: Any, orchestrator: Any, is_player_turn: bool) -> None:
    """Выполняет атомарный коммит состояния (idle и player path).

    Объединяет логику _phase_10_persistence и _phase_10_player_persistence.
    """
    # DRF Observer: Схлопываем поле причинных напряжений ПЕРЕД коммитом
    logger.debug(
        f"[DRF_DRAIN_BUS] bus_id={id(ctx.drf_bus)} stream_size={len(ctx.drf_bus.stream)}"
    )
    _claims = ctx.drf_bus.drain()
    if _claims:
        _npc_claims = defaultdict(list)
        for c in _claims:
            _npc_claims[c.get("target_npc", c.get("npc_id", "unknown"))].append(
                f"{c.get('pressure_type', '?')}:{c.get('vector', '?')}({c.get('energy', 0.0):.1f})"
            )
        for npc, claims_str in _npc_claims.items():
            logger.debug(f"[DRF_FIELD] npc={npc} pressures={claims_str}")

    if is_player_turn:
        if ctx.shared_context is None:
            return
    else:
        if orchestrator._scene_manager is None:
            logger.warning("[TICK_ORCH] Фаза 10: нет scene_manager — коммит пропущен")
            return

    # DSTC: Мутируем M₀ IN-PLACE, сохраняя идентичность списка для всех держателей ссылок.
    if ctx.interpretation_snapshot is not None:
        ctx.all_npcs_raw[:] = ctx.interpretation_snapshot
        ctx.interpretation_snapshot = None

    # Flush: применяем остатки дельт
    if ctx.delta_buffer:
        from app.services.tick_utils import aggregate_deltas

        # ADR-O-418 (RE M2/D): сплит ДО DRSL-агрегации. RELATIONSHIP-дельты
        # живут в scene_state (RelationshipStateStore, ADR-O-370), а не в
        # all_npcs_raw; aggregate_deltas их алгебру не знает — молчаливое
        # игнорирование неизвестного домена = L4-опасность. Носитель
        # scene_state: player-path → shared_context.scene_state (None-gate
        # выше по функции), idle-path → ctx.scene_state.
        _re_deltas = [
            d for d in ctx.delta_buffer if d.domain == DeltaDomain.RELATIONSHIP
        ]
        if _re_deltas and orchestrator._state_applicator:
            _re_scene = (
                ctx.shared_context.scene_state if is_player_turn else ctx.scene_state
            )
            orchestrator._state_applicator.apply_relationship_deltas(
                _re_deltas, _re_scene
            )
        _rest = [
            d for d in ctx.delta_buffer if d.domain != DeltaDomain.RELATIONSHIP
        ]
        _aggregated = aggregate_deltas(_rest)
        if _aggregated and orchestrator._state_applicator:
            orchestrator._state_applicator.apply_batch(
                _aggregated, ctx.all_npcs_raw, ctx.campaign_id
            )
        ctx.delta_buffer.clear()

    # ADR-O-436: Producer NPC_ADDRESSES_PLAYER (LC-IMPL-3 Ступень A).
    # Единственная точка публикации в тике: ПОСЛЕ финального apply_batch,
    # когда intent/intent_target/intent_formed_at в all_npcs_raw зафиксированы
    # (to_persistence_dict — state_applicator:1617), и ДО scene_manager.commit.
    # intent_formed_at == ctx.tick_number истинно ровно один раз на жизненный
    # цикл намерения (_apply_intent state_applicator:678 пишет current_tick
    # только при смене intent) — кросс-тиковая идемпотентность без флагов и
    # реестров. APPROACH исключён — движение, не обращение (audit Г).
    # Идентичность события — Single Writer next_event_identity, не отдельная
    # формула. Read-only: публикация не мутирует all_npcs_raw (§15.4-8).
    _tick_now = int(getattr(ctx, "tick_number", 0) or 0)
    _addr_intents = frozenset({
        "talk", "warn", "trade", "offer_job",
        "request_service", "help", "report", "intimidate",
    })
    if _tick_now > 0 and ctx.all_npcs_raw:
        from app.domain.events import EventDTO
        from app.services.events.event_bus import get_event_bus
        from app.services.events.event_types import EventType
        for _addr_dict in ctx.all_npcs_raw:
            _addr_id = _addr_dict.get("npc_id") or _addr_dict.get("id")
            if not _addr_id or _addr_id == "player":
                continue
            _addr_intent = _addr_dict.get("intent")
            _addr_target = _addr_dict.get("intent_target")
            _addr_formed = _addr_dict.get("intent_formed_at")
            # Отсутствующие поля = не валидное намерение (вердикт: не
            # подменять нулями/дефолтами, способными создать ложное событие).
            if not _addr_intent or not _addr_target or _addr_formed is None:
                continue
            if _addr_target != "player":
                continue
            _intent_key = str(_addr_intent).lower()
            if _intent_key not in _addr_intents:
                continue
            try:
                _addr_formed_int = int(_addr_formed)
            except (TypeError, ValueError):
                continue
            if _addr_formed_int != _tick_now:
                continue
            get_event_bus().publish(
                EventDTO.create(
                    event_type=EventType.NPC_ADDRESSES_PLAYER.value,
                    source=_addr_id,
                    payload={
                        "intent": _intent_key,
                        "target_id": "player",
                        "intent_formed_at": _addr_formed_int,
                    },
                    visibility="whisper",
                    persistence_level="working",
                )
            )

    # SIL: Reconciliation S → M. Сбрасываем semantic_buffer в all_npcs_raw.
    if ctx.semantic_buffer and ctx.all_npcs_raw:
        for npc_dict in ctx.all_npcs_raw:
            nid = npc_dict.get("npc_id") or npc_dict.get("id")
            if nid in ctx.semantic_buffer:
                frame = ctx.semantic_buffer[nid]
                if frame.emotion_tag is not None and frame.emotion_tag.strip():
                    npc_dict["emotion"] = frame.emotion_tag
                if frame.affective_load is not None:
                    npc_dict["affective_load"] = frame.affective_load
        ctx.semantic_buffer.clear()

    if is_player_turn:
        # RCG: Flush scene_changes buffer through apply_changes before commit
        if ctx.scene_changes and orchestrator._scene_manager:
            orchestrator._scene_manager.apply_changes(
                ctx.campaign_id, ctx.scene_changes, ctx.shared_context.scene_state
            )
            ctx.scene_changes.clear()

        if ctx.dirty_npcs or ctx.prop_dirty:
            orchestrator._scene_manager.commit(
                campaign_id=ctx.campaign_id,
                scene_state=ctx.shared_context.scene_state,
                npc_dicts=ctx.all_npcs_raw,
            )
            _sources: list[str] = []
            if ctx.dirty_npcs:
                _sources.append(f"npc={len(ctx.dirty_npcs)}")
            if ctx.prop_dirty:
                _sources.append("social")
            logger.warning(f"[COMMIT] single commit: {', '.join(_sources)}")

        # ADR-117: Синхронизация LifeEngine кэша с мутированными данными.
        if ctx.all_npcs_raw:
            engine = orchestrator._get_life_engine()
            engine.update_cache(ctx.campaign_id, ctx.all_npcs_raw)
    else:
        # ADR-117: Синхронизация LifeEngine кэша с мутированными данными
        if ctx.all_npcs_raw:
            engine = orchestrator._get_life_engine()
            engine.update_cache(ctx.campaign_id, ctx.all_npcs_raw)

        # Собираем события тика для аудита
        ctx.tick_events = ctx.decision_events

        # RCG: Flush scene_changes buffer through apply_changes before commit
        if ctx.scene_changes and orchestrator._scene_manager:
            orchestrator._scene_manager.apply_changes(
                ctx.campaign_id, ctx.scene_changes, ctx.scene_state
            )
            ctx.scene_changes.clear()

        saved = orchestrator._scene_manager.commit(
            campaign_id=ctx.campaign_id,
            scene_state=ctx.scene_state,
            npc_dicts=ctx.all_npcs_raw,
            significant_events=ctx.significant_events or [],
        )

        if saved > 0:
            logger.debug(f"[TICK_ORCH] Фаза 10: commit OK ({saved} подсистем)")
        else:
            logger.warning("[TICK_ORCH] Фаза 10: commit вернул 0 — данные не сохранены")
