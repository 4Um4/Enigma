# -*- coding: utf-8 -*-
"""
path: backend/app/domain/attention_inference.py
Назначение: P3a «Геометрия намерения» (M1–M3, вердикт Мастера): вывод
    кинематики приближения из кольцевого окна наблюдений. ЗАКОН-КАНДИДАТ
    (формулировка Мастера): «Attention is inference over time, not
    proximity detection» — здесь нет состояния и порогов решения, только
    чистая математика над уже воспринятым.
    Определения (в относительной рамке наблюдателя, наблюдатель ≈ origin):
      rel = субъект − наблюдатель (наши rel_dx/rel_dy);
      v   = оценка скорости субъекта из окна (разность на k тиков —
            сглаживание Мастера §14 без Kalman);
      alignment_to_me = (v · (−r̂)):  +1 «прямо на меня», 0 «поперёк»,
            −1 «от меня»;
      radial_speed = (v · r̂): отрицательное = дистанция сокращается;
      t* = −(rel·v)/|v|² — время до ближайшей точки траектории (>0 — впереди);
      d* = |rel + v·t*| — прогнозируемая минимальная дистанция.
      Сценарий «проходит мимо»: сближение есть (radial<0), но d* большой.
      «Точка сближения позади»: t* ≤ 0 → отрицательное свидетельство.
Зависимости: app.domain.attention (AttentionObservation) — только domain.
Основные сущности: ApproachInference, infer_approach, ESTIMATE_WINDOW_TICKS.
"""
import math
import os
from dataclasses import dataclass
from enum import Enum
from typing import Final, Optional, Sequence, Tuple

from app.domain.attention import (
    AttentionObservation,
    AttentionPhase,
    angular_diff,
)

# Глубина оценки скорости: простая разность «последняя − первая из k»
# (Мастер §14: v̂ = (x_t − x_{t−k})/(k·Δt)). Короткое k = быстрее видит
# остановку; длинное = глаже. Калибруемо, не закон мира.
ESTIMATE_WINDOW_TICKS: Final[int] = 3

# Ниже этого |v| (метров/тик) субъект считается неподвижным (шум позиции).
_STATIONARY_EPS: Final[float] = 1e-3


@dataclass(frozen=True)
class ApproachInference:
    """Вывод кинематики по ОДНОМУ субъекту. Optional = «вывода нет» честно
    (§ENIGMA-003: UNKNOWN ≠ 0)."""

    speed: float  # |v|, метров/тик
    radial_speed: float  # (v·r̂): <0 сближение, >0 расхождение
    alignment_to_me: Optional[float]  # (v·(−r̂)): +1 ко мне … −1 от меня
    time_to_closest: Optional[float]  # t*, тиков; None если |v|≈0 или t*≤0
    predicted_min_distance: Optional[float]  # d*, метры; None при t* None


def _empty() -> ApproachInference:
    return ApproachInference(
        speed=0.0,
        radial_speed=0.0,
        alignment_to_me=None,
        time_to_closest=None,
        predicted_min_distance=None,
    )


def infer_approach(
    window: Sequence[AttentionObservation],
    rel_dx: float,
    rel_dy: float,
    observer_velocity: Optional[Tuple[float, float]] = None,
) -> ApproachInference:
    """Вывод по последним k наблюдениям окна + текущему rel-вектору.

    rel (dx, dy) — свежий вектор субъект−наблюдатель (последнее наблюдение
    несёт его же; параметр явный — функция не делает предположений о
    порядке полей кортежа).
    """
    if len(window) < 2:
        return _empty()

    # k точек из хвоста окна (без дублей по тику — монохронность гарантирует
    # неубывание, но на всякий случай берём строго различающиеся тики).
    tail = list(window)[-ESTIMATE_WINDOW_TICKS:]
    first, last = tail[0], tail[-1]
    dt = float(last.tick - first.tick)
    if dt <= 0:
        return _empty()

    vx = (last.rel_dx - first.rel_dx) / dt
    vy = (last.rel_dy - first.rel_dy) / dt
    # R24 mitigation (P3d): v̂ — ОТНОСИТЕЛЬНАЯ скорость «субъект−наблюдатель».
    # Намерение субъекта живёт в его МИРОВОЙ скорости: v_subj = v_rel + v_obs.
    # Без коррекции собственное движение наблюдателя ложно накапливало бы
    # evidence «он идёт ко мне».
    if observer_velocity is not None:
        vx += observer_velocity[0]
        vy += observer_velocity[1]
    speed = math.hypot(vx, vy)
    r_len = math.hypot(rel_dx, rel_dy)
    if r_len < _STATIONARY_EPS:
        return _empty()  # субъект на наблюдателе — вырожденная геометрия

    if speed < _STATIONARY_EPS:
        # Остановился: направление намерения не выводимо (UNKNOWN ≠ 0),
        # но радиальная скорость — честный 0.
        return ApproachInference(
            speed=0.0,
            radial_speed=0.0,
            alignment_to_me=None,
            time_to_closest=None,
            predicted_min_distance=None,
        )

    # r̂ — единичный вектор НА субъекта; −r̂ — направление «ко мне».
    rux, ruy = rel_dx / r_len, rel_dy / r_len
    radial_speed = vx * rux + vy * ruy  # (v·r̂)
    denom = speed * r_len
    alignment_to_me = -(vx * rel_dx + vy * rel_dy) / denom  # (v·(−r̂))

    # t* и d* (Мастер M3): ближайшая точка прямолинейной траектории.
    v2 = vx * vx + vy * vy
    t_star: Optional[float] = None
    d_star: Optional[float] = None
    if v2 > _STATIONARY_EPS * _STATIONARY_EPS:
        t_raw = -(rel_dx * vx + rel_dy * vy) / v2
        if t_raw > 0.0:
            t_star = t_raw
            d_star = math.hypot(
                rel_dx + vx * t_star, rel_dy + vy * t_star
            )
        # t_raw ≤ 0: точка сближения позади → оба None (отрицательное
        # свидетельство для P3b-накопителя).

    return ApproachInference(
        speed=speed,
        radial_speed=radial_speed,
        alignment_to_me=alignment_to_me,
        time_to_closest=t_star,
        predicted_min_distance=d_star,
    )


def subject_turned_toward(
    window: Sequence[AttentionObservation], *, min_rad: float
) -> bool:
    """Субъект развернулся К наблюдателю между двумя последними наблюдениями
    (наблюдаемое событие взаимного цикла — уточнение №8 Мастера). Направление
    «субъект→наблюдатель» берётся из rel КАЖДОГО наблюдения (мировая рамка,
    стабильна при поворотах). Импорт angular_diff — из соседнего домена."""
    if len(window) < 2:
        return False

    def _gap(o: AttentionObservation) -> float:
        to_obs = math.atan2(-o.rel_dy, -o.rel_dx)
        return angular_diff(o.subject_heading, to_obs)

    return _gap(window[-1]) <= _gap(window[-2]) - min_rad


def evidence_delta(
    inference: ApproachInference,
    turned_toward: bool,
    *,
    radial_w: float,
    align_w: float,
    turn_w: float,
    still_penalty: float,
    radial_ref: float,
    approach_scale_m: float,
) -> float:
    """Свидетельство одного наблюдения e_t ∈ [−1, 1] для гипотезы
    «субъект направляется ко мне» (M4: e_t = Ev(H1|O_t) − Ev(H2|O_t)).

    Геометрия различения (урок барсука): ПОЛОЖИТЕЛЬНОЕ свидетельство
    приближения ЦЕЛИКОМ гейтится d*-фактором (1 − d*/scale) — сближение
    с точкой в approach_scale от наблюдателя. Проходящий мимо (d* ≫ scale)
    не накапливает свидетельство, как бы близко он ни проходил сейчас.
    Независимый канал — субъект активно ПОВЕРНУЛСЯ к наблюдателю
    (интенция, не траектория). Отрицательное: стоит на месте (гипотеза
    угасает — Мастер: «movement stops»), точка сближения позади
    (t*/d* = None при |v|>0), движется от меня (alignment < 0).
    Константы инжектируются (domain не знает services, §1.2)."""
    if inference.speed <= _STATIONARY_EPS:
        # Стоит: гипотеза приближения угасает. НО активный поворот К
        # наблюдателю — независимый канал взаимного внимания (сценарий Г,
        # санкция на проверку): действует и для стационарных пар.
        # Порядок проверок критичен: ранний return до turn-проверки
        # отбрасывал свидетельство (дефект, вскрытый test_mutual_attention).
        if turned_toward:
            return turn_w
        return max(-1.0, -still_penalty)

    d_star = inference.predicted_min_distance
    if d_star is None:
        # Движется, но ближайшая точка траектории ПОЗАДИ → не ко мне.
        base = -align_w
    else:
        d_factor = (
            max(0.0, 1.0 - d_star / approach_scale_m) if approach_scale_m > 0 else 0.0
        )
        closing = (
            min(1.0, max(0.0, -inference.radial_speed / radial_ref))
            if radial_ref > 0
            else 0.0
        )
        align_val = inference.alignment_to_me
        align_pos = max(0.0, align_val) if align_val is not None else 0.0
        base = d_factor * (radial_w * closing + align_w * align_pos)
        if align_val is not None and align_val < 0.0:
            base -= align_w * min(1.0, -align_val)
    if turned_toward:
        base += turn_w
    return max(-1.0, min(1.0, base))


class AttentionMode(str, Enum):
    """Режим внимания = квадрант фазового пространства (Мастер §9/§18):
    A = (Surprise, Evidence). Дискретная проекция НЕПРЕРЫВНОГО состояния —
    FSM-фазы восприятия остаются технической моделью наблюдения, режим —
    его смысловая проекция. Не персистится: вычисляется в момент
    потребления из E (AttentionState) и S (PE наблюдателя) — ноль double
    truth (derived ≠ stored)."""

    ROUTINE = "routine"            # S↓ E↓ — продолжает своё (прохожий)
    ALERT = "alert"                # S↑ E↓ — заметил/смотрит (барсук)
    ANTICIPATING = "anticipating"  # S↓ E↑ — понял приближение/ждёт
    STARTLED = "startled"          # S↑ E↑ — резкая настороженность/подготовка


@dataclass(frozen=True)
class ObservedFacts:
    """Слой 1 (Мастер 3.2): НАБЛЮДАЕМОЕ — только восприятое из мира."""

    phase: AttentionPhase
    last_distance: Optional[float]
    last_bearing: Optional[float]
    subject_heading: float
    observation_count: int
    first_seen_tick: int


@dataclass(frozen=True)
class InferredKinematics:
    """Слой 2: ВЫВЕДЕННОЕ — математика траектории НАД наблюдаемым.
    Потребитель обязан помнить: это оценка, не факт мира."""

    speed: float
    radial_speed: float
    alignment_to_me: Optional[float]
    time_to_closest: Optional[float]
    predicted_min_distance: Optional[float]
    subject_turned_toward: bool


@dataclass(frozen=True)
class InterpretedIntent:
    """Слой 4: ИНТЕРПРЕТАЦИЯ — смысловые метки наблюдателя.
    mode=None = «S-ось недоступна, квадрант не определён» (Мастер 3.3:
    None ≠ 0 — ноль означал бы «неожиданности не было»). Квадрант
    вычисляется ТОЛЬКО при доступной S-оси (после P3c-2A).
    probably_approaching_me — belief наблюдателя, НЕ факт (TRUTH ≠ BELIEF);
    вычислим без S: зависит только от Evidence."""

    mode: Optional[AttentionMode]
    probably_approaching_me: bool


@dataclass(frozen=True)
class CognitionSnapshot:
    """CognitionContext v1 (P3c-3, вердикт Мастера): снимок «что OBSERVER
    выводит о SUBJECT» на тик. Направление пары ЯВНОЕ (Мастер 3.1):
    observer_id = кто выводит, subject_id = о ком. Слои различимы (3.2):
    observed → inferred → evidence → interpretation. surprise_used=None —
    честное «не можем оценить» (3.3); v0: S-ось заморожена до аудита PK,
    поэтому None всегда."""

    observer_id: str
    subject_id: str
    observed: ObservedFacts
    inferred: InferredKinematics
    evidence: float
    interpretation: InterpretedIntent
    surprise_used: Optional[float] = None

    def __post_init__(self) -> None:
        # Громкие границы (L4): снимок без направления пары — онтологический разрыв.
        if not self.observer_id or not self.subject_id:
            raise ValueError("CognitionSnapshot: пустой observer_id/subject_id")
        if self.observer_id == self.subject_id:
            raise ValueError("CognitionSnapshot: наблюдатель == субъект")
        if not (0.0 <= self.evidence <= 1.0):
            raise ValueError("CognitionSnapshot: evidence вне [0, 1]")


def attention_mode(
    surprise: float,
    evidence: float,
    *,
    surprise_threshold: float,
    evidence_threshold: float,
) -> AttentionMode:
    """Квадрант (S,E) с границами «>=» (порог включён — детерминизм на границе).
    NaN/inf — громкий отказ (L4): тихий зажим маскировал бы разрыв источника S."""
    if not (math.isfinite(surprise) and math.isfinite(evidence)):
        raise ValueError("attention_mode: non-finite (S,E) — ontological violation")
    s_high = surprise >= surprise_threshold
    e_high = evidence >= evidence_threshold
    if s_high and e_high:
        return AttentionMode.STARTLED
    if e_high:
        return AttentionMode.ANTICIPATING
    if s_high:
        return AttentionMode.ALERT
    return AttentionMode.ROUTINE


_SNAP_OBSERVER = "observer_id"
_SNAP_SUBJECT = "subject_id"
_SNAP_OBSERVED = "observed"
_SNAP_INFERRED = "inferred"
_SNAP_EVIDENCE = "evidence"
_SNAP_INTERP = "interpretation"
_SNAP_SURPRISE = "surprise_used"


def snapshot_to_dict(s: CognitionSnapshot) -> "dict[str, object]":
    """§12.2 WARA: пишет КАЖДОЕ поле, которое читает snapshot_from_dict.
    Dict-форма — для TickMutation (replay-сериализуемость)."""

    def _f(x: "float | None") -> "float | None":
        return None if x is None else round(float(x), 6)

    return {
        _SNAP_OBSERVER: s.observer_id,
        _SNAP_SUBJECT: s.subject_id,
        _SNAP_OBSERVED: {
            "phase": s.observed.phase.value,
            "last_distance": _f(s.observed.last_distance),
            "last_bearing": _f(s.observed.last_bearing),
            "subject_heading": _f(s.observed.subject_heading),
            "observation_count": s.observed.observation_count,
            "first_seen_tick": s.observed.first_seen_tick,
        },
        _SNAP_INFERRED: {
            "speed": _f(s.inferred.speed),
            "radial_speed": _f(s.inferred.radial_speed),
            "alignment_to_me": _f(s.inferred.alignment_to_me),
            "time_to_closest": _f(s.inferred.time_to_closest),
            "predicted_min_distance": _f(s.inferred.predicted_min_distance),
            "subject_turned_toward": s.inferred.subject_turned_toward,
        },
        _SNAP_EVIDENCE: _f(s.evidence),
        _SNAP_INTERP: {
            "mode": s.interpretation.mode.value if s.interpretation.mode is not None else None,
            "probably_approaching_me": s.interpretation.probably_approaching_me,
        },
        _SNAP_SURPRISE: _f(s.surprise_used),
    }


# ── S-ось v2 (вердикт Мастера): локальная prediction error ───────────
# Диагностический гейт (Часть VIII.5-прецедент): env-флаг для снимков
# S-оси в тестах, без постоянного шума в прод-логах.
_S_DIAG: bool = os.environ.get("COGNITION_DIAG", "").strip().lower() in (
    "1",
    "true",
    "yes",
)

# Прогноз строится по окну ДО текущего наблюдения (исключая его) —
# контрольный №8 Мастера (запрет утечки текущего наблюдения в прогноз).
_PREDICT_HISTORY: Final[int] = 3


def prediction_error(
    window: Sequence[AttentionObservation],
    current_dx: float,
    current_dy: float,
    *,
    scale_m: float,
) -> Optional[float]:
    """Локальная ошибка предсказания движения ОДНОГО субъекта (per-pair).

    Прогноз: экстраполяция v̂ (по ПРЕДЫДУЩИМ точкам окна, хвост длиной
    _PREDICT_HISTORY) на один шаг вперёд → ожидаемое относительное
    перемещение. Факт: перемещение от предпоследней точки К текущей
    (current_dx/dy). Возврат: |факт − прогноз| / scale ∈ [0..1] (clamped),
    None = «вывода нет» (история < 2 точек или v̂≈0 — §ENIGMA-003: UNKNOWN
    ≠ 0; стоящий субъект не «неудивителен», он невыводим).

    Семантика НЕ объявляется Surprise (вердикт Мастера): это сырая
    локальная величина расхождения траектории; проверка «предсказуемое
    движение → низкая, резкий поворот/остановка → высокая» — 10
    контрольных случаев тестом."""
    if len(window) < 2:
        return None
    # История для v̂: окно БЕЗ текущего наблюдения. Текущее — пара
    # (current_dx, current_dy), переданная явно вызывающим.
    hist = list(window)[:-1]
    if len(hist) < 2:
        return None
    tail = hist[-_PREDICT_HISTORY:]
    first, last = tail[0], tail[-1]
    dt = float(last.tick - first.tick)
    if dt <= 0:
        return None
    vx = (last.rel_dx - first.rel_dx) / dt
    vy = (last.rel_dy - first.rel_dy) / dt
    speed = math.hypot(vx, vy)
    if speed < 1e-3:
        return None  # v̂≈0: прогноз отсутствует (не «surprise=0»)
    prev = hist[-1]
    pred_dx = prev.rel_dx + vx * (1.0)  # шаг = 1 тик
    pred_dy = prev.rel_dy + vy * (1.0)
    err = math.hypot(current_dx - pred_dx, current_dy - pred_dy)
    if scale_m <= 0:
        return None
    return max(0.0, min(1.0, err / scale_m))
