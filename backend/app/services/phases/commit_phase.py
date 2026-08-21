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

        _aggregated = aggregate_deltas(ctx.delta_buffer)
        if _aggregated and orchestrator._state_applicator:
            orchestrator._state_applicator.apply_batch(
                _aggregated, ctx.all_npcs_raw, ctx.campaign_id
            )
        ctx.delta_buffer.clear()

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

        if ctx.dirty_npcs or ctx.wt_dirty or ctx.prop_dirty:
            orchestrator._scene_manager.commit(
                campaign_id=ctx.campaign_id,
                scene_state=ctx.shared_context.scene_state,
                npc_dicts=ctx.all_npcs_raw,
            )
            _sources: list[str] = []
            if ctx.dirty_npcs:
                _sources.append(f"npc={len(ctx.dirty_npcs)}")
            if ctx.wt_dirty:
                _sources.append("world_tick")
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
