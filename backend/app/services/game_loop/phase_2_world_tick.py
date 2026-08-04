# path: C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\game_loop\phase_2_world_tick.py
"""
ФАЗА 2: WorldTickEngine — проактивные действия NPC.

Recovery, proactive decisions, deltas, потребности.
Мутирует tick_ctx.all_npcs_raw и tick_ctx.wt_dirty.

Назначение: ФАЗА 2 — WorldTickEngine, LifeEngine, EconomyTracker (проактивные действия NPC)
Зависимости: logging
Основные сущности: tick_world_proactive
"""

import logging
from typing import Any

from app.services.game_loop.tick_context import TickBuffer

logger = logging.getLogger(__name__)


def tick_world_proactive(
    world_tick_engine: Any,
    reputation_engine: Any,
    memory_relationship_store: Any,
    economic_profiles_getter: Any,
    campaign_id: str,
    location: str,
    shared_context: Any,
    tick_ctx: TickBuffer,
    tick_orchestrator: Any = None,  # ADR-O-208: для effective_drives computation
) -> None:
    """ФАЗА 3.4: WorldTickEngine — проактивные действия NPC."""
    if not world_tick_engine.should_tick(campaign_id):
        return
    try:
        from app.services.npc.npc_loader import (
            load_l2_state_from_runtime_dict,
            load_profile_from_legacy_json,
        )

        _proactive_npc_data = []
        for _n in tick_ctx.all_npcs_raw:
            _pid = _n.get("id") or _n.get("npc_id")
            if not _pid:
                continue
            if _n.get("tier", "minor") != "major":
                continue
            _p_l2 = load_l2_state_from_runtime_dict(_n)
            if _p_l2.effective_hp <= 0:
                continue
            _p_l0 = load_profile_from_legacy_json(_n)
            # BUG-CORE-009 FIX: Кладём сырой dict (_n) вместо NPCState (_p_l2),
            # чтобы NeedEngine мог извлечь routine.current.
            _proactive_npc_data.append((_pid, _n, _p_l0))

        if not _proactive_npc_data:
            return

        # Reputation modifiers
        _rep_mods = {}
        if reputation_engine:
            for _pid, _, _ in _proactive_npc_data:
                _rm = reputation_engine.compute_reputation_modifier(_pid)
                if _rm:
                    _rep_mods[_pid] = _rm

        # ADR-O-208: Вычисляем effective_drives_map (L3 projection) для всех major NPC.
        _effective_drives_map = {}
        if tick_orchestrator is not None and hasattr(
            tick_orchestrator, "_compute_effective_drives"
        ):
            try:
                _tick_num = tick_orchestrator.get_current_tick(campaign_id)
                _effective_drives_map, _, _ = (
                    tick_orchestrator._compute_effective_drives(
                        tick_ctx.all_npcs_raw, _tick_num, campaign_id
                    )
                )
            except Exception as _ed_err:
                logger.warning(
                    f"[PHASE_2] effective_drives computation failed: {_ed_err}"
                )

        _tick_result = world_tick_engine.compute_proactive_decisions(
            campaign_id=campaign_id,
            location=location,
            npc_data=_proactive_npc_data,
            scene_state=shared_context.scene_state or {},
            reputation_modifiers=_rep_mods if _rep_mods else None,
            effective_drives_map=_effective_drives_map
            if _effective_drives_map
            else None,
        )
        shared_context.world_tick_result = _tick_result
        if _tick_result.decisions:
            logger.warning(
                f"[WORLD_TICK] {len(_tick_result.decisions)} proactive decisions"
            )

        # Применяем deltas к NPC стейту
        from app.models.npc_state import NPCState
        from app.services.npc.state_applicator import StateApplicator

        _wt_applicator = StateApplicator(relationship_store=memory_relationship_store)

        # 1. Recovery для ВСЕХ major NPC
        for _pid, _, _ in _proactive_npc_data:
            _wt_npc_raw = next(
                (
                    _n
                    for _n in tick_ctx.all_npcs_raw
                    if (_n.get("id") or _n.get("npc_id")) == _pid
                ),
                None,
            )
            if not _wt_npc_raw:
                continue
            _wt_state = load_l2_state_from_runtime_dict(_wt_npc_raw)
            _wt_state = _wt_applicator.apply_tick_recovery(_wt_state, is_sleeping=False)
            NPCState.write_to_legacy(_wt_state, _wt_npc_raw)
            tick_ctx.wt_dirty = True

        # 2. Deltas от конкретных proactive решений
        for _pd in _tick_result.decisions:
            _wt_npc_raw = next(
                (
                    _n
                    for _n in tick_ctx.all_npcs_raw
                    if (_n.get("id") or _n.get("npc_id")) == _pd.npc_id
                ),
                None,
            )
            if not _wt_npc_raw:
                continue
            _wt_state = load_l2_state_from_runtime_dict(_wt_npc_raw)
            # Единая точка мутации — StateApplicator (Устав §2.3)
            if isinstance(_pd.deltas, list):
                for _delta in _pd.deltas:
                    _wt_state = _wt_applicator.apply_deltas_only(_wt_state, _delta)
            else:
                _wt_state = _wt_applicator.apply_deltas_only(_wt_state, _pd.deltas)
            NPCState.write_to_legacy(_wt_state, _wt_npc_raw)
            tick_ctx.wt_dirty = True

        # NeedEngine.tick() — потребности растут даже без игрока
        try:
            from app.services.economy.need_engine import NeedEngine

            _wt_eco_profiles = economic_profiles_getter(campaign_id)
            _wt_ne = NeedEngine()
            for _pid, _wt_npc_raw, _ in _proactive_npc_data:
                _wt_ep = _wt_eco_profiles.get(_pid)
                if _wt_ep:
                    _wt_current_activity = ""
                    if isinstance(_wt_npc_raw, dict):
                        _wt_current_activity = _wt_npc_raw.get("routine", {}).get(
                            "current", ""
                        )
                    elif hasattr(_wt_npc_raw, "routine") and isinstance(
                        _wt_npc_raw.routine, dict
                    ):
                        _wt_current_activity = _wt_npc_raw.routine.get("current", "")
                    _wt_ne.tick(_wt_ep, current_activity=_wt_current_activity)
            tick_ctx.wt_dirty = True
        except Exception as _wt_ne_err:
            logger.warning(f"[WORLD_TICK] NeedEngine error: {_wt_ne_err}")

    except Exception as _wt_err:
        logger.warning(f"[WORLD_TICK] Error: {_wt_err}")
