"""
path: /project/backend/app/services/phases/integration.py
Назначение: Инкапсуляция логики Фазы 9 (CFRM P2, TIFL, L2.5 Belief Crystallization, WorldSnapshot Assembly).
Зависимости: app.services.cfrm, app.services.identity, app.services.presentation
Основные сущности: Phase9IntegrationDeps, run_phase_9_integration
"""
from __future__ import annotations

import copy
import logging
from dataclasses import dataclass
from typing import Any

from app.services.dto import _TickContext

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Phase9IntegrationDeps:
    """Зависимости Фазы 9 (Integration). Frozen для предотвращения мутаций."""

    state_applicator: Any
    spatial_service: Any
    causal_solver: Any
    crystallized_belief_store: Any
    drive_resolver: Any
    l1_chronicle: Any
    pattern_detector: Any
    belief_engine: Any
    snapshot_builder: Any
    manifest_svc: Any
    project_svc: Any


def run_phase_9_integration(ctx: _TickContext, deps: Phase9IntegrationDeps) -> None:
    """CFRM P2: Вычисление локальной реальности + WorldSnapshotBuilder."""

    # DSTC: Создание канонического среза реальности (Snapshot Barrier).
    # M₀ (all_npcs_raw) остаётся нетронутым. Дельты применяются к interpretation_snapshot.
    # Это даёт Phase 9 актуальную физику без разрушения исходного состояния тика.
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

    # --- CFRM P2: 3-фазный редюсер и интерпретация давления ---
    # ADR-116: Диагностика входа в CFRM P2
    _cfrm_enter = bool(ctx.event_buffer and ctx.cluster_occupancy and ctx.all_npcs_raw)
    if not _cfrm_enter:
        logger.warning(
            f"[CFRM_P2_SKIP] evbuf={bool(ctx.event_buffer)} occ={bool(ctx.cluster_occupancy)} raw={bool(ctx.all_npcs_raw)}"
        )
    if _cfrm_enter:
        if not deps.spatial_service:
            logger.warning(
                "[CFRM_P2_SKIP] spatial_service is None — affective pipeline disabled"
            )
        cluster_graph = (
            deps.spatial_service.build_cluster_graph() if deps.spatial_service else None
        )
        if cluster_graph is None and deps.spatial_service:
            logger.warning("[CFRM_P2_SKIP] build_cluster_graph() returned None")
        if cluster_graph:
            # Вычисление феноменологической реальности для каждого NPC
            phenomena_states = deps.causal_solver.solve(
                event_buffer=ctx.event_buffer,
                cluster_graph=cluster_graph,
                occupancy=ctx.cluster_occupancy,
                all_npcs_raw=ctx.all_npcs_raw,
            )

            # ADR-116: Диагностика phenomena_states
            _ph_count = len(phenomena_states) if phenomena_states else 0
            _ph_threats = (
                {
                    eid: round(getattr(ps, "threat_level", 0), 2)
                    for eid, ps in (phenomena_states or {}).items()
                }
                if _ph_count
                else {}
            )
            logger.warning(
                f"[CFRM_P2] phenomena_count={_ph_count} threats={_ph_threats}"
            )

            # Интерпретация: Превращение локальной истины в обновление восприятия (ADR-O)
            for entity_id, p_state in phenomena_states.items():
                # S72 / §ENIGMA-S72: CFRM = сырой сенсор, не интерпретатор.
                # Убраны фиксированные множители (×40, ×20, ×10) — движок больше не решает,
                # насколько это страшно. Личность решает через drives_base (I2).
                # Убран dominant_emotion_hint — движок не назначает эмоцию до личности.
                # PhenomenologicalState.threat_level уже 0-1 — передаём как есть.
                from app.models.cfrm import PsychologicalPressure
                from app.models.delta_payloads import PerceptionPayload
                from app.models.state_delta import DeltaDomain, StateDeltas

                pressure = PsychologicalPressure(
                    fear=p_state.threat_level,
                    uncertainty=p_state.anomaly_score,
                    aggression_trigger=0.0,  # S72: агрессия не выводится из угрозы автоматически
                )

                # S72: PerceptionPayload получает сырые сигналы, не интерпретированные движком.
                # Нормализация к 0-1 происходит на уровне PhenomenologicalState (источник),
                # а не на уровне движка (посредник).
                perception_payload = PerceptionPayload(
                    threat_gradient_delta=pressure.fear,
                    uncertainty_delta=pressure.uncertainty,
                    anomaly_score_delta=p_state.anomaly_score * 0.5,
                    dominant_emotion_hint=None,  # S72: эмоция назначается Affective Pipeline, не движком
                )

                # Perception delta — только если возмущение значимое
                # (слабые дельты не мутируют PK, но всё ещё кормят аффективный pipeline ниже)
                if p_state.threat_level >= 0.1 or p_state.visible_blood:
                    delta = StateDeltas(
                        npc_id=entity_id,
                        domain=DeltaDomain.PERCEPTION,
                        target="player",
                        payload=perception_payload,
                        source="cfrm_solver",
                    )
                    ctx.delta_buffer.append(delta)

                # ADR-O: Affective Pressure Pipeline (Perception -> Pressure -> Emotion)
                # Вычисляем давление на основе проекции ядра (T-1 + delta T)
                if npc_raw := next(
                    (n for n in ctx.all_npcs_raw if n.get("npc_id") == entity_id),
                    None,
                ):
                    # ADR-O-208: Смерть npc_raw["drives"].
                    # Котёл читает ТОЛЬКО эфемерную проекцию из DriveResolver (L0 + L1).
                    # ВНИМАНИЕ: блок перенесён ВЫШЕ compute_continuous_drift —
                    # TIFL требует _drives_projection и _psyche_raw на вход.
                    from app.models.npc_state import PerceptualKernel, personality_from_legacy
                    from app.services.affective.affective_integrator import (
                        integrate_affective_pressure,
                    )
                    from app.services.affective.emotion_transition import (
                        resolve_emotion_transition,
                    )

                    _profile_l0 = personality_from_legacy(npc_raw)
                    _beliefs = deps.crystallized_belief_store.get_beliefs(entity_id)
                    _drives_projection = deps.drive_resolver.resolve_drives(
                        _profile_l0, _beliefs
                    )

                    _psyche_raw = npc_raw.get("psyche", {})
                    psyche = {
                        "fear": _drives_projection.get("fear", 0.25),
                        "control": _drives_projection.get("control", 0.25),
                        "significance": _drives_projection.get("significance", 0.25),
                        "willpower": min(1.0, _psyche_raw.get("willpower", 50) / 100.0),
                    }

                    # Active Inference: prediction error для TIFL
                    _drive_fear = _drives_projection.get("fear", 0.25)
                    _drive_control = _drives_projection.get("control", 0.25)
                    _drive_significance = _drives_projection.get("significance", 0.25)

                    # ADR-O-208 / L3-P2: TIFL получает эфемерную проекцию, а не сырой стейт
                    from app.domain.identity_events import TraitDriftEvent
                    from app.services.npc.break_progress_engine import (
                        compute_continuous_drift,
                    )

                    _rigidity = (
                        _psyche_raw.get("identity_rigidity", 0.5)
                        if _psyche_raw
                        else 0.5
                    )

                    # Легковесная проекция ядра для TIFL (на основе дельт)
                    _pk_load_for_tifl = min(
                        1.0,
                        perception_payload.threat_gradient_delta * _drive_fear
                        + perception_payload.uncertainty_delta * _drive_control
                        + perception_payload.anomaly_score_delta * _drive_significance,
                    )
                    _prev_memory = float(npc_raw.get("affective_memory", 0.0))
                    _delta = _pk_load_for_tifl - _prev_memory
                    _abs_error = abs(_delta)
                    _error_vector = {
                        "fear": 0.33,
                        "control": 0.33,
                        "significance": 0.33,
                    }
                    if _abs_error > 0.05:
                        _w_fear = perception_payload.threat_gradient_delta * _drive_fear
                        _w_control = (
                            perception_payload.uncertainty_delta * _drive_control
                        )
                        _w_signif = (
                            perception_payload.anomaly_score_delta * _drive_significance
                        )
                        _total_w = _w_fear + _w_control + _w_signif + 1e-6
                        _error_vector = {
                            "fear": _w_fear / _total_w,
                            "control": _w_control / _total_w,
                            "significance": _w_signif / _total_w,
                        }

                    _drift_events = compute_continuous_drift(
                        effective_drives=_drives_projection,
                        npc_id=entity_id,
                        rigidity=_rigidity,
                        prediction_error=_abs_error,
                        error_vector=_error_vector,
                        current_tick=ctx.tick_number,
                    )
                    if _drift_events:
                        deps.l1_chronicle.commit_tick_buffer(
                            _drift_events, ctx.tick_number
                        )

                    pk_dict = npc_raw.get("perceptual_kernel", {})
                    _body_idle = npc_raw.get("body_state") or {}
                    _pain_norm_idle = float(_body_idle.get("pain", 0.0)) / 100.0
                    _shock_norm_idle = float(_body_idle.get("shock_impulse", 0.0))
                    _somatic_urg_idle = (_pain_norm_idle + _shock_norm_idle) / 2.0

                    projected_kernel = PerceptualKernel(
                        threat_gradient=min(
                            1.0,
                            max(
                                0.0,
                                pk_dict.get("threat_gradient", 0.0)
                                + perception_payload.threat_gradient_delta,
                            ),
                        ),
                        uncertainty=min(
                            1.0,
                            max(
                                0.0,
                                pk_dict.get("uncertainty", 0.0)
                                + perception_payload.uncertainty_delta,
                            ),
                        ),
                        anomaly_score=min(
                            1.0,
                            max(
                                0.0,
                                pk_dict.get("anomaly_score", 0.0)
                                + perception_payload.anomaly_score_delta,
                            ),
                        ),
                        compliance_bias=pk_dict.get("compliance_bias", 0.0),
                        aggression_inhibition=pk_dict.get("aggression_inhibition", 0.0),
                        initiative_suppression=pk_dict.get(
                            "initiative_suppression", 0.0
                        ),
                        somatic_urgency=_somatic_urg_idle,
                    )

                    from app.domain.perception import ProjectionFrame

                    if "_projection_frames" not in locals():
                        _projection_frames = []
                    if (
                        projected_kernel.threat_gradient > 0.05
                        or projected_kernel.initiative_suppression > 0.2
                    ):
                        signal = (
                            "avoid_gaze"
                            if projected_kernel.threat_gradient > 0.5
                            else (
                                "freeze"
                                if projected_kernel.initiative_suppression > 0.7
                                else "calm"
                            )
                        )
                        _projection_frames.append(
                            ProjectionFrame(
                                entity_id=entity_id,
                                threat=projected_kernel.threat_gradient,
                                suppression=projected_kernel.initiative_suppression,
                                salience=max(
                                    projected_kernel.threat_gradient,
                                    projected_kernel.initiative_suppression,
                                ),
                                embodied_signal=signal,
                                expires_tick=ctx.tick_number + 3,
                            )
                        )

                    # ADR-049: Единый интегратор аффективного давления
                    current_load = float(npc_raw.get("affective_load", 0.0))
                    current_memory = float(npc_raw.get("affective_memory", 0.0))
                    new_load, new_memory = integrate_affective_pressure(
                        kernel=projected_kernel,
                        psyche=psyche,
                        current_load=current_load,
                        current_memory=current_memory,
                    )

                    # BUG FIX: Сохраняем обновлённые affective_load и memory обратно в npc_raw.
                    # Без этого BreakProgressEngine видит 0.0 и не генерирует событие "pressure".
                    npc_raw["affective_load"] = new_load
                    npc_raw["affective_memory"] = new_memory

                    # BUG FIX: Обновляем только изменённые поля PerceptualKernel в npc_raw.
                    # Перезапись всего словаря убивала compliance_bias и recent_directive,
                    # применённые StateApplicator в Фазе 8.
                    if "perceptual_kernel" not in npc_raw or not isinstance(
                        npc_raw["perceptual_kernel"], dict
                    ):
                        npc_raw["perceptual_kernel"] = {}
                    _pk_raw = npc_raw["perceptual_kernel"]
                    _pk_raw["threat_gradient"] = projected_kernel.threat_gradient
                    _pk_raw["uncertainty"] = projected_kernel.uncertainty
                    _pk_raw["anomaly_score"] = projected_kernel.anomaly_score
                    _pk_raw["somatic_urgency"] = projected_kernel.somatic_urgency

                    emotion_payload = resolve_emotion_transition(
                        new_load, current_load, psyche
                    )

                    # §ENIGMA-DUAL-CIRCUIT: Sustaining Loop УБИТ (S73).
                    # Эмоция не удерживается искусственно при высоком load.
                    # Если EmotionTransition не дал фазового перехода — эмоция = neutral.
                    # Это обнажает честную динамику для диагностики S73-R1.

                    if emotion_payload:
                        # SHI-FIX: L1Chronicle emission for fear
                        if (
                            hasattr(deps, "l1_chronicle")
                            and deps.l1_chronicle is not None
                        ):
                            _emo_tag = getattr(emotion_payload, "emotion_tag", None)
                            if (
                                _emo_tag
                                and hasattr(_emo_tag, "value")
                                and "fear" in _emo_tag.value
                            ):
                                deps.l1_chronicle.commit_tick_buffer(
                                    [
                                        TraitDriftEvent(
                                            tick_id=ctx.tick_number,
                                            target_id=entity_id,
                                            source_id="combat",
                                            effect_value=0.2,
                                            observation_weight=1.0,
                                            event_type="fear",
                                        )
                                    ],
                                    ctx.tick_number,
                                )
                        # Передаем новое значение интеграла в Applicator для сохранения в NPCState
                        from dataclasses import replace

                        emotion_payload = replace(
                            emotion_payload, affective_load=new_load
                        )

                        # ADR-116: Диагностика эмоционального пайплайна
                        logger.debug(
                            f"[AFFECTIVE] npc={entity_id} load={new_load:.3f} prev={current_load:.3f} tag={emotion_payload.emotion_tag}"
                        )

                        from app.models.state_delta import DeltaDomain, StateDeltas

                        emotion_delta = StateDeltas(
                            npc_id=entity_id,
                            domain=DeltaDomain.EMOTION,
                            target="player",
                            payload=emotion_payload,
                            source="affective_pipeline",
                        )
                        ctx.delta_buffer.append(emotion_delta)

    # L1.5 / L2.5: Pattern Detection & Belief Crystallization (ADR-O-305)
    # Запускается ПОСЛЕ аффективного цикла, до сборки снапшота.
    # BUG-PERC-014 FIX: L14 — Память не генерирует идентичность без каузального входа.
    if not ctx.phase_2_events:
        logger.debug("[L2.5] Skipping crystallization — no phase_2_events this tick")
    else:
        _npc_truth_source = (
            ctx.interpretation_snapshot
            if ctx.interpretation_snapshot is not None
            else ctx.all_npcs_raw
        )
        for npc_dict in _npc_truth_source:
            _npc_id = npc_dict.get("npc_id")
            if not _npc_id:
                continue

            # L1: Чтение сырой хроники
            _l1_events = deps.l1_chronicle.query_raw(_npc_id)
            if not _l1_events:
                continue

            # L1.5: Детектирование паттернов (чистая статистика)
            _evidence_list = deps.pattern_detector.detect(_l1_events)
            if not _evidence_list:
                continue

            # L0: Извлечение базовых драйвов для модуляции
            _drives_base = npc_dict.get(
                "drives", npc_dict.get("psyche", {}).get("drives_base", {})
            )
            if not _drives_base:
                _drives_base = {
                    "control": 0.25,
                    "significance": 0.25,
                    "fear": 0.25,
                    "desire": 0.25,
                }

            # L2.5: Кристаллизация убеждений (проекция через личность)
            _existing_beliefs = deps.crystallized_belief_store.get_beliefs(_npc_id)
            _updated_beliefs = deps.belief_engine.crystallize(
                evidence_list=_evidence_list,
                drives_base=_drives_base,
                existing_beliefs=_existing_beliefs,
                current_tick=ctx.tick_number,
            )
            deps.crystallized_belief_store.update_beliefs(_npc_id, _updated_beliefs)

    # WorldSnapshotBuilder: собирает WorldSnapshotDTO из финального state
    # ADR-035: Трансляция стейта аватара в феноменологическую проекцию
    from app.services.presentation.avatar_presentation_assembler import (
        assemble_avatar_presentation,
    )

    # DSTC: Читаем NPC из interpretation_snapshot (M₀ + deltas), а не из M₀.
    _npc_truth_source = (
        ctx.interpretation_snapshot
        if ctx.interpretation_snapshot is not None
        else ctx.all_npcs_raw
    )
    player_dict = next(
        (n for n in _npc_truth_source if n.get("npc_id") == "player"), None
    )
    _avatar_projection = (
        assemble_avatar_presentation(player_dict) if player_dict else None
    )

    # TZ-08 v0.2: Perception pipeline — internal causal observability layer (post-mutation).
    # Формирует модель наблюдаемости мира на основе state_t+1.
    # ADR-O-322: ManifestationPhysicsEngine (Sprint P2)
    # ADR-O-323: PerceptionPhysicsEngine (Sprint P3)
    # ADR-O-324: FactExtractor (Sprint P4)
    # ADR-O-325: InferenceEngine (Sprint P4)
    # ADR-O-326: PresentationAssembler (Sprint P7)
    from app.domain.embodied_trace import EmbodiedTraceDTO
    from app.services.perception.fact_extractor import FactExtractor
    from app.services.perception.inference_engine import InferenceEngine
    from app.services.perception.manifestation_physics_engine import (
        ManifestationPhysicsEngine,
    )
    from app.services.perception.perception_physics_engine import (
        PerceptionPhysicsEngine,
    )
    from app.services.perception.presentation_assembler import PresentationAssembler
    from app.services.spatial.spatial_query_service import SpatialQueryService

    _manifest_engine = ManifestationPhysicsEngine()
    _perception_engine = PerceptionPhysicsEngine()
    _fact_extractor = FactExtractor()
    _inference_engine = InferenceEngine()
    _assembler = PresentationAssembler()
    _spatial_query = SpatialQueryService(
        npc_positions=ctx.scene_state.get("npc_positions", {}),
        scene_state=ctx.scene_state,
    )

    _traces = []
    _all_signals = []
    _npc_positions = ctx.scene_state.get("npc_positions", {})
    _body_map = (
        {n.get("id") or n.get("npc_id"): n.get("body_state") for n in _npc_truth_source}
        if _npc_truth_source
        else {}
    )

    for _nid, _ndata in _npc_positions.items():
        if _nid == "player":
            continue
        _bs = _body_map.get(_nid, {})
        _traversal = ctx.scene_state.get("active_traversals", {}).get(_nid)

        # 1. Вычисляем ManifestationState
        _manifest = _manifest_engine.manifest(_ndata, _bs, _traversal)

        # 2. Вычисляем ObservationRelation (игрок наблюдает за NPC)
        _relation = _perception_engine.compute_relation(
            observer_id="player",
            target_id=_nid,
            spatial_query=_spatial_query,
            scene_state=ctx.scene_state,
        )

        if _relation:
            # 3. Фильтруем ManifestationState в PerceivedSignal
            _signals = _perception_engine.filter_manifestation(
                manifest=_manifest,
                relation=_relation,
                target_id=_nid,
                current_tick=ctx.tick_number,
            )
            _all_signals.extend(_signals)

        # Конвертируем в EmbodiedTraceDTO для обратной совместимости
        _trace = EmbodiedTraceDTO(
            npc_id=_nid,
            locomotion_instability=_manifest.movement.tremor,
            posture_rigidity=_manifest.body.muscle_tension,
            micro_pause_density=_manifest.voice.pauses,
            action_interruption=0.0 if _manifest.body.standing_balance > 0.5 else 1.0,
        )

        if _trace.locomotion_instability > 0.05 or _trace.posture_rigidity > 0.05:
            _traces.append(_trace)

    # 4. Извлекаем атомарные факты
    _all_facts = _fact_extractor.extract(_all_signals, ctx.tick_number)

    # 5. Строим гипотезы
    _all_inferences = _inference_engine.infer(_all_facts, ctx.tick_number)

    # 6. Собираем FactsBundle для DM
    _facts_bundle = _assembler.assemble_facts_bundle(_all_facts)

    _facts_for_dm = []
    logger.debug(
        f"[DEBUG_EPISTEMOLOGY] Signals={len(_all_signals)} Facts={len(_all_facts)} Inferences={len(_all_inferences)}"
    )
    if _facts_bundle.facts:
        for f in _facts_bundle.facts:
            _facts_for_dm.append(
                f"- {f.fact_name} ({f.target_id}, confidence={f.confidence:.2f})"
            )
        logger.debug(f"[DEBUG_EPISTEMOLOGY] FactsBundle: {' | '.join(_facts_for_dm)}")

    ctx.observed_facts_for_dm = _facts_for_dm

    # ADR-O-320: RecognitionMemory Engine.
    # Уверенность распознавания растёт при визуальном контакте.
    _npc_ids = [n.get("id") or n.get("npc_id") for n in _npc_truth_source if n.get("id") or n.get("npc_id")]
    _distances = _spatial_query.player_distances(_npc_ids)
    _los_map = ctx.scene_state.get("line_of_sight", {})

    if "player_recognition" not in ctx.scene_state:
        ctx.scene_state["player_recognition"] = {}

    for _nid, _dist in _distances.items():
        # S127 FIX: Убираем жесткий блок LOS. Если карта видимости пуста/отстаёт,
        # мы всё равно позволяем запомнить NPC по дистанции.
        _is_visible = _los_map.get(_nid, True) if _los_map else True
        if not _is_visible:
            continue  # Нельзя запомнить того, кого точно не видишь

        _recog_entry = ctx.scene_state["player_recognition"].setdefault(_nid, {"confidence": 0.0})
        if _dist < 3.0:
            _recog_entry["confidence"] = min(1.0, _recog_entry["confidence"] + 0.15)
        elif _dist < 8.0:
            _recog_entry["confidence"] = min(1.0, _recog_entry["confidence"] + 0.08)
        else:
            _recog_entry["confidence"] = min(1.0, _recog_entry["confidence"] + 0.03)

    # Сборка PlayerPerceptionDTO (вне цикла!)
    _player_perception = deps.project_svc.project(
        _traces, ctx.scene_state, tick=ctx.tick_number, observed_facts=_facts_for_dm
    )

    # ТЗ Presentation v2.0: Сборка трёхканальной презентации
    from dataclasses import asdict

    _visual_dto = _assembler.assemble_visual_dto(
        perceived_signals=_all_signals,
        recognition_map=ctx.scene_state.get("player_recognition", {})
    )
    _audible_dto = _assembler.assemble_audible_dto(
        perceived_signals=_all_signals
    )

    # Сборка WorldSnapshotDTO (вне цикла!)
    builder = deps.snapshot_builder
    ctx.world_snapshot = builder.build(
        scene_state=ctx.scene_state,
        tick=ctx.tick_number,
        avatar_state=_avatar_projection,
        all_npcs_raw=ctx.all_npcs_raw,
        player_perception=_player_perception,
        player_body_topology=ctx.scene_state.get("player_body_topology"),
        visual_dto=asdict(_visual_dto),
        audible_dto=asdict(_audible_dto),
        eco_profile=ctx.eco_profile,  # S151: Профиль игрока для EmbodiedStatusDTO
    )
