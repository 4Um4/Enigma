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
    economy_tracker: Any = None,
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
            # SLEEP_FIX #4a: спящие/resting NPC не участвуют в проактивных решениях
            # WorldTickEngine. Это симметрично с SLEEP_GUARD реактивного пути.
            _cur_activity = _n.get("routine", {}).get("current", "") if isinstance(_n, dict) else ""
            if "sleeping" in _cur_activity or "resting" in _cur_activity:
                continue
            _p_l2 = load_l2_state_from_runtime_dict(_n)
            # FIX: Безопасная проверка HP для dict и NPCState.
            if isinstance(_p_l2, dict):
                _hp = _p_l2.get("body_state", {}).get("current_hp", _p_l2.get("hp", 100))
            else:
                _hp = getattr(_p_l2, "effective_hp", 100)
            if _hp <= 0:
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
            reputation_modifiers=_rep_mods if _rep_mods else None,  # noqa: ENIGMA001
            effective_drives_map=_effective_drives_map  # noqa: ENIGMA001
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
            # SLEEP_FIX #4b: передаём корректный is_sleeping флаг.
            # Раньше был хардкод False, из-за чего спящие NPC не получали x3
            # восстановление стресса (15.0/тик вместо 5.0/тик).
            _wt_cur_activity = ""
            if isinstance(_wt_npc_raw, dict):
                _wt_cur_activity = _wt_npc_raw.get("routine", {}).get("current", "")
            _is_sleeping = "sleeping" in _wt_cur_activity or "resting" in _wt_cur_activity
            _wt_state = _wt_applicator.apply_tick_recovery(_wt_state, is_sleeping=_is_sleeping)
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
            from app.services.economy.trade_resolver import TradeResolver
            from app.services.economy.transaction_engine import TransactionEngine
            from app.models.state_delta import StateDeltas, DeltaDomain
            from app.models.delta_payloads import EconomicPayload
            from app.core.constants import TICKS_PER_DAY

            _wt_eco_profiles = economic_profiles_getter(campaign_id)
            _wt_ne = NeedEngine()
            
            # 1. Синхронизация Gold (Вход в тик) — SSOT body_state["money"]/npc_dict["gold"]
            for _pid, _wt_npc_raw, _ in _proactive_npc_data:
                _wt_ep = _wt_eco_profiles.get(_pid)
                if _wt_ep:
                    _wt_ep.gold = float(_wt_npc_raw.get("gold", 0.0))
            
            # Игрок (если есть в профилях)
            if "player" in _wt_eco_profiles:
                _avatar = getattr(shared_context, "avatar_state", None)  # noqa: ENIGMA002
                if _avatar and _avatar.body_state:
                    _wt_eco_profiles["player"].gold = float(_avatar.body_state.get("money", 0.0))

            # 2. Тик NeedEngine
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

            # 3. Интеграция TradeResolver
            _wt_tx_engine = TransactionEngine()
            _wt_trade_resolver = TradeResolver(_wt_tx_engine)
            _wt_trade_results = _wt_trade_resolver.resolve_tick(
                profiles=_wt_eco_profiles,
                trade_intents={},  # TradeResolver сам найдёт нуждающихся (второй проход)
                location=location,
            )

            # 4. Применение транзакций через StateApplicator (запрет прямой мутации)
            _wt_economy_deltas = []
            for _res in _wt_trade_results:
                if not _res.success:
                    continue
                logger.warning(f"[TRADE] {_res.buyer_id} покупает {_res.goods} у {_res.seller_id} за {_res.price}G")
                
                _buyer_delta = StateDeltas(
                    npc_id=_res.buyer_id,
                    domain=DeltaDomain.ECONOMY,
                    payload=EconomicPayload(money_delta=-_res.price, goods_delta=_res.goods)
                )
                _wt_economy_deltas.append(_buyer_delta)
                
                _seller_delta = StateDeltas(
                    npc_id=_res.seller_id,
                    domain=DeltaDomain.ECONOMY,
                    payload=EconomicPayload(money_delta=_res.price, goods_delta=None)
                )
                _wt_economy_deltas.append(_seller_delta)

            if _wt_economy_deltas:
                # S150 FIX: Применяем дельты к NPC
                _wt_applicator.apply_batch(_wt_economy_deltas, tick_ctx.all_npcs_raw, campaign_id)
                
                # S150 FIX: Регистрируем доход продавца в EconomyTracker
                if economy_tracker:
                    for _res in _wt_trade_results:
                        if _res.success:
                            economy_tracker.record_income(_res.seller_id, _res.price)
                
                # S150 FIX: Если в сделке участвует игрок, обновляем его avatar_state напрямую
                _avatar = getattr(shared_context, "avatar_state", None)  # noqa: ENIGMA002
                if _avatar and _avatar.body_state:
                    for _delta in _wt_economy_deltas:
                        if _delta.npc_id == "player" and isinstance(_delta.payload, EconomicPayload):
                            _money_delta = float(_delta.payload.money_delta or 0.0)
                            _avatar.body_state["money"] = float(_avatar.body_state.get("money", 0.0)) + _money_delta

            # 5. Активация EconomyTracker (раз в TICKS_PER_DAY)
            if economy_tracker:
                _tick_num = tick_orchestrator.get_current_tick(campaign_id) if tick_orchestrator else 0
                if _tick_num > 0 and _tick_num % TICKS_PER_DAY == 0:
                    _base_drives = {}
                    for _pid, _wt_npc_raw, _p_l0 in _proactive_npc_data:
                        _base_drives[_pid] = _p_l0.drives_base
                    _inc_sat, _soc_sat = economy_tracker.check_daily_needs(
                        profiles=_wt_eco_profiles,
                        npc_drives=_base_drives,
                        tick=_tick_num,
                        location_locked=False,
                    )
                    economy_tracker.reset_daily()
                    logger.warning(f"[ECO_TRACKER] day_end: income={_inc_sat} social={_soc_sat} satisfied")

            tick_ctx.wt_dirty = True
        except Exception as _wt_ne_err:
            logger.warning(f"[WORLD_TICK] NeedEngine error: {_wt_ne_err}")

    except Exception as _wt_err:
        logger.warning(f"[WORLD_TICK] Error: {_wt_err}")
