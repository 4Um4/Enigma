"""
path: /project/backend/app/services/phases/idle_services.py
Назначение: Инкапсуляция логики Фазы 0.5 (Time-driven decay & idle services).
Зависимости: app.services.affect, app.models.affect, app.core.constants, app.services.tick_utils
Основные сущности: Phase0_5Deps, run_phase_0_5
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional, Any
import logging

from app.services.dto import _TickContext
from app.domain.identity_events import TraitDriftEvent

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Phase0_5Deps:
    """Зависимости Фазы 0.5. Frozen для предотвращения мутаций."""
    l1_chronicle: Any
    dynamic_field: Any
    homeostasis_sub: Any
    expectation_store: Any
    idle_handlers: List[Any]
    life_engine: Any


def run_phase_0_5(ctx: _TickContext, deps: Phase0_5Deps) -> None:
    """Time-driven decay: social drift, reputation drift, affective decay.
    Выполняется КАЖДЫЙ тик (idle + player path).
    Время идёт непрерывно — эксплойты через движение исключены.
    Дельты собираются в ctx.delta_buffer → apply_batch() в Фазе 10.
    """
    # ADR-002: Время не останавливается. Каждый тик продвигает часы на GAME_TICK_INTERVAL_SECONDS
    # _advance_idle_time вызывается в самом tick_orchestrator, так как он 1 строку
    
    # S94-T2.3: L1Chronicle TTL — архивация старых событий каждые 500 тиков для предотвращения OOM
    if ctx.tick_number > 0 and ctx.tick_number % 500 == 0:
        if deps.l1_chronicle is not None:
            deps.l1_chronicle.archive_old_events(ctx.tick_number)
            
    # S91: Очистка истекших деформаций среды (Temporalization Layer)
    deps.dynamic_field.purge_hard_overrides(current_tick=ctx.tick_number)
    deps.dynamic_field.step_decay()   

    # Homeostasis: social_battery isolation decay (time-driven)
    _isolation_deltas = deps.homeostasis_sub.compute_isolation_decay(ctx.all_npcs_raw)
    if _isolation_deltas:
        ctx.delta_buffer.extend(_isolation_deltas)

    # S-93: PE Decay (Per-Tick, Elastic Time).
    # Инвариант: PE остаётся строго индивидуальным bias-layer.
    # Ожидания затухают со временем, привязанным к game_time_seconds.
    if deps.expectation_store is not None:
        from app.core.constants import GAME_TICK_INTERVAL_SECONDS
        _dt_game = ctx.scene_state.get("game_time_seconds", 0)
        _prev_time = ctx.scene_state.get("prev_game_time_seconds", _dt_game - GAME_TICK_INTERVAL_SECONDS)
        _delta_dt = max(0.1, _dt_game - _prev_time)
        deps.expectation_store.decay(_delta_dt)

    # ADR-036 / ADR-O-302: Affective Decay (Leaky Integrator для памяти)
    # Травмы затухают со временем, если не подкрепляются.
    from app.services.affect import decay_affective_imprints
    from app.models.affect import AffectiveImprint
    from app.core.constants import GAME_TICK_INTERVAL_SECONDS
    from dataclasses import asdict
    _current_time = ctx.scene_state.get("game_time_seconds", 0)
    for npc_dict in ctx.all_npcs_raw:
        imp_dicts = npc_dict.get("affective_imprints", [])
        if not imp_dicts: continue
        try:
            imprints = tuple(AffectiveImprint(**imp) for imp in imp_dicts)
            # ADR-O-302: delta_time = GAME_TICK_INTERVAL_SECONDS (60 сек). Магическое число 5.0 убито.
            decayed = decay_affective_imprints(imprints, float(GAME_TICK_INTERVAL_SECONDS), _current_time)
            npc_dict["affective_imprints"] = [asdict(d) for d in decayed]
        except Exception as e:
            # Инвариант 3: Аффективный decay — критический процесс, не debug
            logger.warning(f"[AFFECT_DECAY] Failed for {npc_dict.get('npc_id')}: {e}")

    if not deps.idle_handlers:
        return

    current_tick = deps.life_engine.get_current_tick(ctx.campaign_id)
    from app.services.tick_utils import build_npc_snapshots
    snapshots = build_npc_snapshots(ctx.all_npcs_raw)

    # S73-DIAG: Проверка призрачного decay (мёртвая ли психика в snapshot?)
    if snapshots:
        _sample = snapshots[0]
        logger.debug(f"[AFF_DEBUG] handlers={[type(h).__name__ for h in deps.idle_handlers]} aff_load={_sample.get('affective_load', '<MISSING>')} emo={_sample.get('emotion', '<MISSING>')}")

    for handler in deps.idle_handlers:
        try:
            deltas = handler.handle(snapshots, ctx.campaign_id, current_tick)
        except Exception as e:
            logger.error(
                f"[PHASE_0.5] {handler.name} handle() failed: {e}. "
                f"Deltas lost this tick."
            )
            continue

        if deltas:
            ctx.delta_buffer.extend(deltas)
            # SHI-FIX: L1Chronicle emission for decay
            if hasattr(handler, 'name') and handler.name == "physiology_decay":
                if deps.l1_chronicle is not None:
                    _decay_events = []
                    for _d in deltas:
                        if _d.npc_id and (abs(getattr(_d.payload, 'pain_delta', 0.0)) > 0 or abs(getattr(_d.payload, 'blood_loss_delta', 0.0)) > 0):
                             _decay_events.append(TraitDriftEvent(tick_id=ctx.tick_number, target_id=_d.npc_id,
                                                           source_id="physiology_decay", effect_value=-0.01, observation_weight=1.0, event_type="decay"))
                    if _decay_events:
                        deps.l1_chronicle.commit_tick_buffer(_decay_events, ctx.tick_number)

    # S75-R1.1 FIX: Perceptual Decay (Rule 38, ADR-122).
    # threat_gradient, uncertainty, anomaly_score затухают в idle-тиках.
    # Без этого _run_affective_pipeline (Фаза 9) пересчитывает affective_load
    # из устаревшего PK, перезаписывая честный декей из AffectiveDecayHandler.
    # Результат: Вечный Двигатель Страха (maid_lusya: 1.00/fearful навсегда).
    _PERCEPTUAL_DECAY = {"threat_gradient": 0.05, "uncertainty": 0.03, "anomaly_score": 0.02}
    for npc_dict in ctx.all_npcs_raw:
        pk = npc_dict.get("perceptual_kernel")
        if pk and isinstance(pk, dict):
            for _key, _rate in _PERCEPTUAL_DECAY.items():
                if _key in pk:
                    pk[_key] = max(0.0, float(pk[_key]) - _rate)

    # S75-R1 FIX: Cache Desync (Техзадание S75).
    # Синхронизация LifeEngine cache с применёнными idle-дельтами.
    # Хотя Фаза 10 тоже вызывает update_cache, этот вызов гарантирует,
    # что кэш обновлён ДО Фазы 9, предотвращая расхождение истин.
    if ctx.all_npcs_raw:
        deps.life_engine.update_cache(ctx.campaign_id, ctx.all_npcs_raw)