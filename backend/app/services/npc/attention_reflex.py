# -*- coding: utf-8 -*-
"""
path: backend/app/services/npc/attention_reflex.py
Назначение: CognitionContext v0 (P2 — Этап 1 ТЗ): первый живой цикл
    восприятие → обнаружение → ориентация. PURE-функции: читают TickState,
    возвращают дельты внимания и готовые orient SceneChange (значения
    предвычислены; применение мира — оркестратор). Границы Уровня B (ТЗ §6.3):
    не принимает социальных решений, не пишет убеждения/память/отношения,
    не вызывает LLM, не прерывает traversal (orient только стационарным).
    Симметрия субъектов: player — обычный СУБЪЕКТ восприятия (веток
    `== "player"` нет); orient-АКТУАЦИЯ гейтится ControlSource — владелец
    тела: NPC_DECISION актуируется ядром, аватар — player-input (тот же
    примитив, что INV-PLAYER-AUTHORSHIP, npc_tick_pipeline:1119).
    Ориентация ≠ взгляд: body_heading — v0-приближение ориентации внимания
    (решение Мастера №3). INTERACTION на этом уровне не существует (№1).
Зависимости: app.domain.attention, app.domain.control_source,
    app.domain.vital_state, app.services.scene_change,
    app.services.spatial.spatial_runtime, app.services.npc.attention_config.
Основные сущности: compute_attention_pass.
"""
import math
import os
from typing import Any, Dict, List, Optional, Tuple

# Временная диагностика P2 (Часть VIII.5): env-гейт, в проде молчит.
_DIAG = os.environ.get("COGNITION_DIAG", "").strip().lower() in ("1", "true", "yes")

from app.domain.attention import (
    ATTENTION_DEFAULT_FOV_RAD,
    ATTENTION_MAX_SUBJECTS,
    AttentionObservation,
    AttentionPhase,
    AttentionState,
    angular_diff,
    attention_from_dict,
    attention_to_dict,
    bearing_to,
    create_attention_state,
    with_observation,
    with_phase,
    wrap_pi,
)
from app.domain.attention_dispositions import get_attention_disposition
from typing import Mapping
from app.domain.attention_inference import (
    CognitionSnapshot,
    InterpretedIntent,
    InferredKinematics,
    ObservedFacts,
    evidence_delta,
    infer_approach,
    prediction_error,
    snapshot_to_dict,
    subject_turned_toward,
)
from app.domain.control_source import ControlSource, resolve_control_source
from app.domain.vital_state import is_conscious
from app.services.npc.attention_config import (
    ATTENTION_APPROACH_SCALE_M,
    ATTENTION_DETECT_RADIUS_M,
    ATTENTION_EVIDENCE_ALIGN_W,
    ATTENTION_EVIDENCE_LAMBDA,
    ATTENTION_EVIDENCE_RADIAL_REF,
    ATTENTION_EVIDENCE_RADIAL_W,
    ATTENTION_EVIDENCE_THRESHOLD,
    ATTENTION_EVIDENCE_STILL_PENALTY,
    ATTENTION_EVIDENCE_TURN_MIN_RAD,
    ATTENTION_EVIDENCE_TURN_W,
    ATTENTION_EVIDENCE_THRESHOLD,
    ATTENTION_EVIDENCE_HYSTERESIS,
    ATTENTION_LOST_EVIDENCE_DECAY,
    ATTENTION_LOST_GC_TICKS,
    ATTENTION_MODIFIER_MAX,
    ATTENTION_ORIENT_MIN_DELTA_RAD,
    ATTENTION_PERIPHERAL_RADIUS_M,
    ATTENTION_PREDICT_SCALE_M,
    COGNITION_V0,
)
from app.services.scene_change import ChangeType, SceneChange
from app.services.spatial.spatial_runtime import line_of_sight


def _xy(entry: Optional[Dict[str, Any]]) -> Optional[Tuple[float, float]]:
    """Извлечение local_position — зеркало _extract_xy резолвера (строгая форма)."""
    lp = (entry or {}).get("local_position") or {}
    x, y = lp.get("x"), lp.get("y")
    if isinstance(x, (int, float)) and isinstance(y, (int, float)):
        return float(x), float(y)
    return None


def _heading(entry: Optional[Dict[str, Any]]) -> float:
    # Дефолт 1.5708 — тот же fallback, что movement_engine:743 и
    # player_target_pipeline:199 (единая конвенция).
    h = (entry or {}).get("body_heading", 1.5708)
    return float(h) if isinstance(h, (int, float)) else 1.5708


def _emit_orient(
    orient_changes: List[SceneChange],
    observer_id: str,
    heading_value: float,
    cause_suffix: str,
    tick: int,
    subject_id: str = "",
) -> None:
    # Форма — зеркало heading_snap (movement_engine:755-762): NPC_POSITION +
    # field="body_heading" без target_location_id; generic-ветка SSM применит.
    if _DIAG:
        print(
            f"[ATT_DIAG] ORIENT obs={observer_id} subj={subject_id} "
            f"val={heading_value:.4f} cause={cause_suffix}"
        )
    orient_changes.append(
        SceneChange(
            type=ChangeType.NPC_POSITION,
            target=observer_id,
            field="body_heading",
            value=heading_value,
            cause=f"attention_orient:{cause_suffix}",
            tick=tick,
        )
    )


def compute_attention_pass(state: Any) -> Tuple[Dict[str, Any], List[SceneChange]]:
    """Легаси-обёртка (2-tuple) для существующих потребителей/тестов.
    Канонический вход — run_attention_pass (P3c-3)."""
    delta, changes, _snapshots = _compute_pass_core(state)
    return delta, changes


def run_attention_pass(state: Any) -> "Any":
    """Канонический вход P3c-3: полный результат прохода внимания.
    Возвращает frozen-объект AttentionPassResult (delta, orient_changes,
    cognition_snapshots: list[dict]). Снимки — producer=DATA-only
    (канон ADR-O-366): потребитель — P3d, до него никто не читает."""

    class AttentionPassResult:
        __slots__ = ("attention_delta", "orient_changes", "cognition_snapshots")

        def __init__(self, attention_delta: Dict[str, Any], orient_changes: List[SceneChange], cognition_snapshots: List[Dict[str, Any]]) -> None:
            self.attention_delta = attention_delta
            self.orient_changes = orient_changes
            self.cognition_snapshots = cognition_snapshots

    d, c, s = _compute_pass_core(state)
    return AttentionPassResult(d, c, s)


def _compute_pass_core(state: Any) -> Tuple[Dict[str, Any], List[SceneChange], List[Dict[str, Any]]]:
    """Один проход внимания: наблюдатели × субъекты текущей сцены.

    Возвращает (attention_delta, orient_changes):
      attention_delta = {observer: {subject: dict | None}}; None = GC-удаление.
      orient_changes  = SceneChange(field="body_heading"), максимум один на
                        наблюдателя за тик (одно тело — один heading).
    Флаг OFF → ({}, []) — байтовый no-op.
    """
    if not COGNITION_V0:
        # S292-фикс чужого merge-разрыва: аннотация обещает 3-кортеж
        # (attention_delta, orient_changes, cognition_snapshots), no-op-ветка
        # возвращала 2 → ValueError на unpack у caller'а каждый тик.
        return {}, [], []

    positions: Dict[str, Any] = state.scene_state.get("npc_positions") or {}
    traversals: Dict[str, Any] = state.scene_state.get("active_traversals") or {}
    prev_all: Dict[str, Any] = state.attention_states_map or {}
    tick: int = state.tick_id

    # Тела (сознание/сон) живут в all_npcs_raw, не в позициях — карта один раз.
    raw_by_id: Dict[str, Dict[str, Any]] = {}
    for _raw in state.all_npcs_raw or []:
        _rid = _raw.get("npc_id") or _raw.get("id")
        if _rid:
            raw_by_id[_rid] = _raw

    attention_delta: Dict[str, Any] = {}
    orient_changes: List[SceneChange] = []
    cognition_snapshots: List[Dict[str, Any]] = []

    for observer_id in sorted(positions.keys()):
        obs_entry = positions.get(observer_id) or {}
        obs_xy = _xy(obs_entry)
        if obs_xy is None:
            if _DIAG:
                print(f"[ATT_DIAG] obs={observer_id} SKIP no_xy keys={list(obs_entry.keys())[:8]}")
            continue
        obs_body = (raw_by_id.get(observer_id) or {}).get("body_state") or {}
        # Мёртвый/без сознания не воспринимает (is_conscious — единственный
        # владелец решения о сознании, ADR-123).
        if not is_conscious(obs_body):
            if _DIAG:
                print(f"[ATT_DIAG] obs={observer_id} SKIP unconscious consciousness={obs_body.get('consciousness', 'ABSENT')}")
            continue
        coupling = obs_body.get("coupling_profile") or {}
        _mode_raw = coupling.get("coupling_mode", "FULL_WAKE")
        _mode = str(getattr(_mode_raw, "value", _mode_raw)).upper()
        # Слепота — только по canonical режиму тела (ADR-O-356: CouplingProfile
        # — единственный индикатор сна; скриптовые флаги табуированы).
        # TZ-OBS-5: мульт-гейт снят — runtime-данные инконсистентны
        # (FULL_WAKE + external_vision_mult=0.05 у всех NPC — противоречие
        # семантике профиля); починка писателя coupling — после ТЗ.
        # Возврат graded-множителя (DROWSY-деградация зрения) — P4+.
        if _mode in ("SLEEP", "DEEP_SLEEP", "REM"):
            if _DIAG:
                print(f"[ATT_DIAG] obs={observer_id} SKIP eyes_closed mode={_mode}")
            continue
        if _DIAG and _mode != "FULL_WAKE":
            print(f"[ATT_DIAG] obs={observer_id} mode={_mode} (graded-множитель не применяется, TZ-OBS-5)")
        _vis_miss: Dict[str, int] = {}

        # Актация поворота: владелец тела NPC_DECISION + стационарность.
        # Движущийся NPC: heading принадлежит движению (heading_snap).
        can_orient = resolve_control_source(observer_id) is ControlSource.NPC_DECISION and (
            traversals.get(observer_id) or {}
        ).get("status") != "MOVING"

        obs_heading = _heading(obs_entry)
        prev_subs: Dict[str, Any] = prev_all.get(observer_id) or {}
        delta_subs: Dict[str, Any] = {}
        oriented_this_tick = False

        # Кандидаты: все прочие субъекты с координатами; сортировка
        # (дистанция, id) — детерминизм и «ближайший приоритетен».
        candidates: List[Tuple[float, str]] = []
        for subject_id in positions.keys():
            if subject_id == observer_id:
                continue
            subj_xy = _xy(positions.get(subject_id))
            if subj_xy is None:
                continue
            dist = math.hypot(subj_xy[0] - obs_xy[0], subj_xy[1] - obs_xy[1])
            candidates.append((dist, subject_id))
        candidates.sort()

        for dist, subject_id in candidates:
            subj_entry = positions.get(subject_id) or {}
            subj_xy = _xy(subj_entry)
            if subj_xy is None:
                # Кандидаты строились с непустыми координатами — на данных
                # no-op; guard для mypy (Optional-сужение перед bearing_to/index).
                continue
            prev_raw = prev_subs.get(subject_id)
            prev_state: Optional[AttentionState] = None
            if prev_raw is not None:
                prev_state = attention_from_dict(prev_raw)

            if dist > ATTENTION_DETECT_RADIUS_M:
                visible = False
                if _DIAG:
                    _vis_miss["far"] = _vis_miss.get("far", 0) + 1
            else:
                abs_bearing = bearing_to(obs_xy, subj_xy)
                in_fov = angular_diff(obs_heading, abs_bearing) < ATTENTION_DEFAULT_FOV_RAD
                # Периферия: за спиной, но вплотную — «внезапное появление»
                # (ТЗ §5.2), честный Сценарий C: издали за спиной не видно.
                peripheral = dist <= ATTENTION_PERIPHERAL_RADIUS_M
                los_ok = line_of_sight(
                    distance=dist,
                    scene_state=state.scene_state,
                    ax=obs_xy[0], ay=obs_xy[1], bx=subj_xy[0], by=subj_xy[1],
                )
                visible = (in_fov or peripheral) and los_ok
                if _DIAG and not visible:
                    _k = "los" if not los_ok else "fov"
                    _vis_miss[_k] = _vis_miss.get(_k, 0) + 1
            abs_bearing = bearing_to(obs_xy, subj_xy)

            if visible:
                obs_record = AttentionObservation(
                    tick=tick,
                    distance=dist,
                    bearing=wrap_pi(abs_bearing - obs_heading),
                    subject_heading=_heading(subj_entry),
                    # Мировой относительный вектор — субстрат P3-MATH (M1-M3).
                    rel_dx=subj_xy[0] - obs_xy[0],
                    rel_dy=subj_xy[1] - obs_xy[1],
                )
                is_entry = prev_state is None or prev_state.phase in (
                    AttentionPhase.NOT_DETECTED,
                    AttentionPhase.LOST,
                )
                if is_entry:
                    # Вход в восприятие → внимание ориентировано (ORIENTED).
                    # SceneChange только когда нужен ФИЗИЧЕСКИЙ поворот:
                    # субъект уже в центре взгляда → ORIENTED без записи
                    # heading (тело уже смотрит — поворачивать нечего).
                    # suppress-случаи (движется/не владеет телом/поворот уже
                    # отдан другому) остаются в DETECTED — рефлекс отложен,
                    # не потерян.
                    if can_orient and not oriented_this_tick:
                        needs_turn = (
                            angular_diff(obs_heading, abs_bearing)
                            >= ATTENTION_ORIENT_MIN_DELTA_RAD
                        )
                        if needs_turn:
                            _emit_orient(
                                orient_changes,
                                observer_id,
                                abs_bearing,
                                "reentry" if prev_state is not None else "detected",
                                tick,
                                subject_id=subject_id,
                            )
                            oriented_this_tick = True
                        new_state = create_attention_state(
                            subject_id,
                            AttentionPhase.ORIENTED,
                            tick,
                            obs_record,
                            observer_xy=obs_xy,
                        )
                    else:
                        new_state = create_attention_state(
                            subject_id,
                            AttentionPhase.DETECTED,
                            tick,
                            obs_record,
                            observer_xy=obs_xy,
                        )
                else:
                    # Отложенный рефлекс: ранее suppress (двигался/чужой тик),
                    # теперь может повернуть. Выравнен → ORIENTED без SceneChange.
                    if prev_state is None:
                        # Недостижимо на данных (is_entry ложен ⇒ prev_state есть);
                        # guard для mypy (Optional-сужение before phase/with_observation).
                        continue
                    # v0.3: поддержание ориентации (restore). heading
                    # стационарного наблюдателя перезаписывают другие
                    # писатели (TZ-OBS-1: movement heading_snap) — внимание
                    # ВОССТАНАВЛИВАЕТ ориентацию на видимого субъекта.
                    # Порог ниже = встроенный гистерезис: после восстановления
                    # diff≈0 → повторов нет; внешний сброс → diff ≥ порога
                    # → restore. Эмиссия ≤1/тик/наблюдатель.
                    _misaligned = (
                        angular_diff(obs_heading, abs_bearing)
                        >= ATTENTION_ORIENT_MIN_DELTA_RAD
                    )
                    upgraded = (
                        prev_state.phase
                        in (
                            AttentionPhase.DETECTED,
                            AttentionPhase.ORIENTED,
                            AttentionPhase.APPROACHING,
                            AttentionPhase.NEAR,
                        )
                        and can_orient
                        and not oriented_this_tick
                    )
                    if upgraded and _misaligned:
                        _emit_orient(
                            orient_changes,
                            observer_id,
                            abs_bearing,
                            (
                                "upgrade"
                                if prev_state.phase is AttentionPhase.DETECTED
                                else "restore"
                            ),
                            tick,
                            subject_id=subject_id,
                        )
                        oriented_this_tick = True
                    # Активная фаза: поток наблюдений — сырьё P3-выводов
                    # (скорость/длительность/смена траектории, уточнение №5).
                    # P3b (M4): накопление свидетельства «направляется ко мне».
                    # Восприятие ≠ действие: копится и при подавленном
                    # рефлексе (наблюдатель движется). (Ре)вход стартует
                    # с E=0 (новая гипотеза — create_attention_state).
                    _inf_window = (*prev_state.observation_window, obs_record)
                    # R24 mitigation: скорость НАБЛЮДАТЕЛЯ за последний
                    # интервал — вычитается из относительной (см. infer_approach).
                    _obs_vel = None
                    if prev_state.observer_xy is not None:
                        _obs_dt = tick - prev_state.last_update_tick
                        if _obs_dt > 0:
                            _obs_vel = (
                                (obs_xy[0] - prev_state.observer_xy[0]) / _obs_dt,
                                (obs_xy[1] - prev_state.observer_xy[1]) / _obs_dt,
                            )
                    _inf = infer_approach(
                        _inf_window,
                        obs_record.rel_dx,
                        obs_record.rel_dy,
                        observer_velocity=_obs_vel,
                    )
                    _turned = subject_turned_toward(
                        _inf_window, min_rad=ATTENTION_EVIDENCE_TURN_MIN_RAD
                    )
                    _e_t = evidence_delta(
                        _inf,
                        _turned,
                        radial_w=ATTENTION_EVIDENCE_RADIAL_W,
                        align_w=ATTENTION_EVIDENCE_ALIGN_W,
                        turn_w=ATTENTION_EVIDENCE_TURN_W,
                        still_penalty=ATTENTION_EVIDENCE_STILL_PENALTY,
                        radial_ref=ATTENTION_EVIDENCE_RADIAL_REF,
                        approach_scale_m=ATTENTION_APPROACH_SCALE_M,
                    )
                    _e_new = max(
                        0.0,
                        min(
                            1.0,
                            ATTENTION_EVIDENCE_LAMBDA * prev_state.approach_evidence
                            + _e_t,
                        ),
                    )
                    new_state = with_observation(
                        prev_state,
                        AttentionPhase.ORIENTED if upgraded else prev_state.phase,
                        tick,
                        obs_record,
                        approach_evidence=_e_new,
                        observer_xy=obs_xy,
                    )
                # P3c-3: снимок «что наблюдатель выводит о субъекте».
                # Слои различимы (Мастер 3.2); surprise_used=None честно
                # (3.3) — S-ось заморожена до аудита PK (P3c-2A).
                _snap_win = (*new_state.observation_window,)
                _snap_inf = infer_approach(_snap_win, obs_record.rel_dx, obs_record.rel_dy)
                cognition_snapshots.append(
                    snapshot_to_dict(
                        CognitionSnapshot(
                            observer_id=observer_id,
                            subject_id=subject_id,
                            observed=ObservedFacts(
                                phase=new_state.phase,
                                last_distance=new_state.last_distance,
                                last_bearing=new_state.last_bearing,
                                subject_heading=obs_record.subject_heading,
                                observation_count=len(_snap_win),
                                first_seen_tick=new_state.first_seen_tick,
                            ),
                            inferred=InferredKinematics(
                                speed=_snap_inf.speed,
                                radial_speed=_snap_inf.radial_speed,
                                alignment_to_me=_snap_inf.alignment_to_me,
                                time_to_closest=_snap_inf.time_to_closest,
                                predicted_min_distance=_snap_inf.predicted_min_distance,
                                subject_turned_toward=subject_turned_toward(
                                    _snap_win, min_rad=ATTENTION_EVIDENCE_TURN_MIN_RAD
                                ),
                            ),
                            evidence=new_state.approach_evidence,
                            interpretation=InterpretedIntent(
                                mode=None,  # S-ось недоступна (P3c-2A) — None ≠ 0
                                probably_approaching_me=(
                                    new_state.approach_evidence
                                    >= ATTENTION_EVIDENCE_THRESHOLD
                                ),
                            ),
                            # S-ось v2 (вердикт Мастера): локальная prediction
                            # error per-pair. Прогноз по истории ДО текущего
                            # наблюдения (окно new_state уже содержит его —
                            # отрезаем хвост); утечка запрещена (контроль №8).
                            surprise_used=prediction_error(
                                new_state.observation_window,
                                obs_record.rel_dx,
                                obs_record.rel_dy,
                                scale_m=ATTENTION_PREDICT_SCALE_M,
                            ),
                        )
                    )
                )
                delta_subs[subject_id] = attention_to_dict(new_state)
            else:
                if prev_state is None:
                    continue  # не видели и не видим — состояния нет (нет события)
                if prev_state.phase is AttentionPhase.LOST:
                    # LOST-заморозка: наблюдения не пишутся, память не стирается.
                    if tick - prev_state.last_update_tick > ATTENTION_LOST_GC_TICKS:
                        delta_subs[subject_id] = None  # GC: субъект забыт
                    continue
                # Сценарий Д: субъект исчез — гипотеза приближения плавно
                # угасает (λ-затухание); окно-память не стирается.
                delta_subs[subject_id] = attention_to_dict(
                    with_phase(
                        prev_state,
                        AttentionPhase.LOST,
                        tick,
                        approach_evidence=round(
                            prev_state.approach_evidence
                            * ATTENTION_LOST_EVIDENCE_DECAY,
                            4,
                        ),
                    )
                )

        if _DIAG:
            print(
                f"[ATT_DIAG] obs={observer_id} cand={len(candidates)} "
                f"delta={len(delta_subs)} can_orient={can_orient} "
                f"mode={_mode} miss={_vis_miss}"
            )
        # Cap на новых субъектах: старые важнее (окно наблюдений уже накоплено).
        if delta_subs and len(prev_subs) >= ATTENTION_MAX_SUBJECTS:
            delta_subs = {
                k: v
                for k, v in delta_subs.items()
                if v is not None or k in prev_subs
            }
        if delta_subs:
            attention_delta[observer_id] = delta_subs

    return attention_delta, orient_changes, cognition_snapshots



def produce_cognition_modifiers(
    snapshots: Optional[List[Dict[str, Any]]],
    drives: Optional[Mapping[str, float]] = None,
) -> Dict[str, float]:
    """P3d (санкция Мастера): мост перцепция → evidence → utility.
    Возвращает модификаторы СУЩЕСТВУЮЩИХ интентов для DecisionHub.
    БЕЗ новых интентов/FSM/памяти/владения (красная линия). Максимум по
    парам: салиентнейшее приближение определяет реакцию (толпа не
    суммируется). Рампа с гистерезисом (анти-дребезг R22). Disposition
    архетипа — источник различий реакций. OFF → {} (байтовый no-op)."""
    if not COGNITION_V0:
        return {}
    top_evidence: Optional[float] = None
    for _s in snapshots or []:
        _interp = _s.get("interpretation") or {}
        if not _interp.get("probably_approaching_me"):
            continue
        _e = float(_s.get("evidence", 0.0))
        if top_evidence is None or _e > top_evidence:
            top_evidence = _e
    if top_evidence is None:
        return {}
    if top_evidence >= ATTENTION_EVIDENCE_THRESHOLD:
        _ramp = 1.0
    elif top_evidence >= (
        ATTENTION_EVIDENCE_THRESHOLD - ATTENTION_EVIDENCE_HYSTERESIS
    ):
        _ramp = 0.5  # зона удержания: реакция ещё жива, но ослаблена
    else:
        return {}
    _base = ATTENTION_MODIFIER_MAX * _ramp
    _mods: Dict[str, float] = {}
    for _intent_key, _weight in get_attention_disposition(drives).items():
        if _weight <= 0.0:
            continue
        _val = round(_base * _weight, 4)
        # Санкционная граница ±0.5 — громкий отказ (L4), не тихий зажим.
        if abs(_val) > ATTENTION_MODIFIER_MAX + 1e-9:
            raise ValueError(
                f"cognition modifier {_intent_key}={_val} вне санкции "
                f"±{ATTENTION_MODIFIER_MAX}"
            )
        _mods[_intent_key] = _val
    return _mods