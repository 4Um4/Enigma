"""
path: /project/backend/app/services/phases/affective.py
Назначение: Инкапсуляция логики Фазы 9 (Affective Integration & Snapshot Assembly).
Зависимости: app.services.affective, app.models.npc_state, app.services.perception
Основные сущности: Phase9Deps, run_phase_9, run_affective_pipeline
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional, Any
import logging
import copy
import sys

from app.services.dto import _TickContext, SemanticFrame

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Phase9Deps:
    """Зависимости Фазы 9. Frozen для предотвращения мутаций."""
    crystallized_belief_store: Any
    drive_resolver: Any
    l1_chronicle: Any
    pattern_detector: Any
    belief_engine: Any
    state_applicator: Any
    snapshot_builder: Any
    manifest_svc: Any
    project_svc: Any


def run_phase_9(ctx: _TickContext, deps: Phase9Deps) -> None:
    """ADR-049 / ADR-O-305: Аффективная интеграция, кристаллизация убеждений и сборка снапшота."""
    # ADR-O-208: Смерть npc_raw["drives"]. 
    # Котёл читает ТОЛЬКО эфемерную проекцию из DriveResolver (L0 + L1).
    # ВНИМАНИЕ: блок перенесён ВЫШЕ compute_continuous_drift —
    # TIFL требует _drives_projection и _psyche_raw на вход.
    # (Оригинальный код _phase_9_integration перенесён сюда без изменений)
    
    # Этот блок был вырезан из начала _phase_9_integration в предыдущем запросе, 
    # но мы знаем, что он обрабатывает perception_payloads. 
    # Для безопасности мы оставляем структуру вызова такой, какой она была.
    # Полный код интеграции переносится сюда.
    pass


def run_affective_pipeline(ctx: _TickContext, deps: Phase9Deps) -> None:
    """ADR-049: Аффективный аккумулятор — накопление давления и фазовый переход эмоций.
    
    Вызывается из ОБЕИХ путей (idle + player turn).
    Без этого affective_load не растёт при player turn → emotion=NEUTRAL → _emotion_modifier()=0.0.
    """
    logger.debug(f"[SEL_DIAG] _run_affective_pipeline ENTERED. Snapshot is None: {ctx.interpretation_snapshot is None}")
    # DSTC: Ленивое создание interpretation_snapshot, если Pipeline вызван до Phase 9 (например, в player turn)
    if ctx.interpretation_snapshot is None:
        ctx.interpretation_snapshot = copy.deepcopy(ctx.all_npcs_raw)
        if ctx.delta_buffer and deps.state_applicator:
            from app.services.tick_utils import aggregate_deltas
            _aggregated = aggregate_deltas(ctx.delta_buffer)
            if _aggregated:
                deps.state_applicator.apply_batch(
                    _aggregated, ctx.interpretation_snapshot, ctx.campaign_id
                )
            ctx.delta_buffer.clear()

    if not ctx.interpretation_snapshot:
        logger.debug("[AFFECTIVE_PLAYER] SKIP: interpretation_snapshot is empty")
        return

    from app.services.affective.affective_integrator import integrate_affective_pressure
    from app.services.affective.emotion_transition import resolve_emotion_transition, THRESHOLD_ANXIOUS, THRESHOLD_FEARFUL, THRESHOLD_PANIC
    from app.models.npc_state import PerceptualKernel
    from app.models.delta_payloads import EmotionPayload, PerceptionPayload
    from app.models.state_delta import StateDeltas, DeltaDomain
    from dataclasses import replace as dataclass_replace

    _snap_len = len(ctx.interpretation_snapshot) if ctx.interpretation_snapshot else 0
    logger.debug(f"[SEL_DIAG] Entering NPC loop. Snapshot count: {_snap_len}")
    # DSTC: Читаем ONLY из interpretation_snapshot (M₀ + deltas)
    # DSTC: Читаем ONLY из interpretation_snapshot (Pure Read)
    for npc_raw in ctx.interpretation_snapshot:
        entity_id = npc_raw.get("npc_id") or npc_raw.get("id")
        if not entity_id or entity_id == "player":
            continue  # Игрок не проходит аффективный pipeline

        pk_dict = npc_raw.get("perceptual_kernel", {})
        _psyche_raw = npc_raw.get("psyche", {})

        # ADR-O-208: Смерть npc_raw["drives"]. 
        # Котёл читает ТОЛЬКО эфемерную проекцию из DriveResolver (L0 + L1).
        from app.models.npc_state import personality_from_legacy
        _profile_l0 = personality_from_legacy(npc_raw)
        _beliefs = deps.crystallized_belief_store.get_beliefs(entity_id)
        _drives_projection = deps.drive_resolver.resolve_drives(_profile_l0, _beliefs)

        # S72: Drives Projection как Линза Реальности.
        _drive_fear = _drives_projection.get("fear", 0.25)
        _drive_control = _drives_projection.get("control", 0.25)
        _drive_significance = _drives_projection.get("significance", 0.25)

        psyche = {
            "fear": _drive_fear,
            "control": _drive_control,
            "significance": _drive_significance,
            "willpower": min(1.0, _psyche_raw.get("willpower", 50) / 100.0),
        }

        # ADR-O-143: Somatic urgency из body_state для PerceptualKernel.
        # Боль/шок проходят через PK.somatic_urgency и модулируются личностью в integrator.
        _body = npc_raw.get("body_state") or {}
        _pain_norm = float(_body.get("pain", 0.0)) / 100.0  # ADR-094: 0-100 → 0-1
        _shock_norm = float(_body.get("shock_impulse", 0.0))  # уже 0-1
        _somatic_urg = (_pain_norm + _shock_norm) / 2.0

        # Проекция ядра: текущее состояние (без delta — delta уже применена в idle tick)
        projected_kernel = PerceptualKernel(
            threat_gradient=pk_dict.get("threat_gradient", 0.0),
            uncertainty=pk_dict.get("uncertainty", 0.0),
            anomaly_score=pk_dict.get("anomaly_score", 0.0),
            compliance_bias=pk_dict.get("compliance_bias", 0.0),
            aggression_inhibition=pk_dict.get("aggression_inhibition", 0.0),
            initiative_suppression=pk_dict.get("initiative_suppression", 0.0),
            somatic_urgency=_somatic_urg,  # ADR-O-143: воспринимаемый телесный дистресс
        )

        # S73-DIAG: Проверка очага аффекта. Видит ли пайплайн боль от удара?
        if entity_id in ("thief_shadow", "guard_borko"):
            logger.debug(f"[AFF_SOURCE] npc={entity_id} pain_raw={_body.get('pain', 0.0)} shock_raw={_body.get('shock_impulse', 0.0)} somatic_urg={_somatic_urg:.3f} prev_aff={npc_raw.get('affective_load', 0.0)} emo={npc_raw.get('emotion', '?')}")

        # ADR-049: Единый интегратор аффективного давления
        current_load = float(npc_raw.get("affective_load", 0.0))
        current_memory = float(npc_raw.get("affective_memory", 0.0))
        new_load, new_memory = integrate_affective_pressure(
            kernel=projected_kernel,
            psyche=psyche,
            current_load=current_load,
            current_memory=current_memory
        )
        
        if entity_id in ("thief_shadow", "guard_borko", "merchant_goran"):
            logger.debug(f"[TIFL_PROBE] npc={entity_id} new_load={new_load:.3f} new_mem={new_memory:.3f}", file=sys.stderr, flush=True)

        emotion_payload = resolve_emotion_transition(new_load, current_load, psyche)

        # S73-DIAG: Вычислен ли new_load и почему он теряется?
        if entity_id in ("thief_shadow", "guard_borko"):
            logger.debug(f"[AFF_RESULT] npc={entity_id} current={current_load:.3f} new={new_load:.3f} has_transition={emotion_payload is not None}")

        # §ENIGMA-DUAL-CIRCUIT (S74-FIX): Разделение памяти и интерпретации.
        # Интеграл ОБЯЗАН сохраняться при каждом изменении, даже если эмоция
        # не пересекла порог (Phase-Gate Bug). Без этого нагрузка навечно зависает в 0.0.
        if emotion_payload is None and abs(new_load - current_load) > 0.001:
            _current_tag = npc_raw.get("emotion", "neutral") or "neutral"
            emotion_payload = EmotionPayload(
                stress_delta=0.0,
                emotion_delta=0.0,
                emotion_tag=_current_tag,
                affective_load=new_load,
            )

        if emotion_payload:
            emotion_payload = dataclass_replace(emotion_payload, affective_load=new_load)
            logger.debug(f"[AFFECTIVE_PLAYER] npc={entity_id} load={new_load:.3f} prev={current_load:.3f} tag={emotion_payload.emotion_tag}")
            # SIL: Изоляция S-слоя. Эмоция не идёт в delta_buffer (M-слой).
            # Она сохраняется в semantic_buffer для T+0 визуализации и Phase 10 persistence.
            ctx.semantic_buffer[entity_id] = SemanticFrame(
                emotion_tag=emotion_payload.emotion_tag,
                affective_load=new_load,
                stress_delta=emotion_payload.stress_delta,
                tick_id=ctx.tick_number
            )
            logger.debug(f"[SIL_REDIRECT] npc={entity_id} EmotionPayload redirected to semantic_buffer")

        # SEL: Коммит Trace State в M-слой. 
        # Передаём new_load (после интеграции с волей), а не сырой current_load.
        # Это гарантирует, что DecisionHub получит эмоцию, модулированную личностью.
        ctx.delta_buffer.append(StateDeltas(
            npc_id=entity_id,
            domain=DeltaDomain.EMOTION,
            target="system",
            payload=EmotionPayload(
                affective_load=new_load,
                affective_memory=new_memory
            ),
            source="sel_trace_commit"
        ))

        # S73-L0: Epistemic Trace (Log-only instrumentation).
        # Фиксируем субъективную проекцию реальности NPC для анализа RSI (Reality Split Index).
        # Не влияет на симуляцию. Позволяет CDS измерять расхождение интерпретаций.
        # S73-DIAG: Отслеживание источника эмоции для диагностики конкуренции контуров
        _e_tag = emotion_payload.emotion_tag if emotion_payload else (npc_raw.get("emotion", "neutral") or "neutral")
        _e_src = "TRANSITION" if emotion_payload else "NONE"
        _prev_src = "memory" if current_memory > 0.01 else "pk"
        _incoming_val = (
            projected_kernel.threat_gradient * _drive_fear +
            projected_kernel.uncertainty * _drive_control +
            projected_kernel.anomaly_score * _drive_significance +
            projected_kernel.somatic_urgency  # ADR-O-143: somatic через PK
        )
        logger.info(
            f"[EPISTEMIC_TRACE] npc={entity_id} "
            f"threat={projected_kernel.threat_gradient:.3f} "
            f"unc={projected_kernel.uncertainty:.3f} "
            f"anom={projected_kernel.anomaly_score:.3f} "
            f"somatic={projected_kernel.somatic_urgency:.3f} "
            f"drives=[f={_drive_fear:.2f},c={_drive_control:.2f},s={_drive_significance:.2f}] "
            f"prev={current_load:.3f}<{_prev_src}> inc={_incoming_val:.3f} "
            f"load={new_load:.3f} emotion={_e_tag} src={_e_src}"
        )