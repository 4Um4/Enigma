# -*- coding: utf-8 -*-
"""
path: backend/app/domain/attention.py
Назначение: Домен «внимание» (CognitionContext v0). Frozen-DTO состояния внимания
    наблюдателя (observer) к субъекту (subject) + кольцевое окно наблюдений —
    сырьё для будущих P3-выводов (скорость сближения, длительность наблюдения,
    смена траектории, «повернулся ко мне»). Композиция фаз (FSM) и реакции —
    вне этого модуля (P2: services/npc/attention_reflex.py). Расширение
    DecisionHub — не раньше P3 и только после 4-пунктного обоснования
    (решение Мастера, уточнение №4).
    Архитектурные фиксации:
      * body_heading в v0 — ПРИБЛИЖЕНИЕ ориентации внимания, НЕ модель взгляда
        (глаза и head_yaw не моделируются; head_yaw остаётся dormant).
      * INTERACTION — не фаза восприятия: расстояние = условие возможности,
        а не смысл взаимодействия. Социальный смысл возникает в P3 из
        совокупности факторов и реализуется выбором DecisionHub.
Зависимости: только stdlib (dataclasses, enum, math, typing). domain/ не знает
    о services/ (Устав §1.2); сервисных объектов и рантайма не читает.
Основные сущности: AttentionPhase, AttentionObservation, AttentionState,
    create_attention_state, with_observation, attention_to_dict,
    attention_from_dict, ATTENTION_MAX_SUBJECTS, ATTENTION_OBS_WINDOW.
"""
from dataclasses import dataclass
from enum import Enum
import math
from typing import Any, Dict, Final, Optional, Tuple

# Зачем cap: бюджет тика O(N·k) (ADR-PRE-FLIGHT п.4). Наблюдатель не держит
# всех субъектов мира — только салиентных; отбор — зона P2-продюсера.
ATTENTION_MAX_SUBJECTS: Final[int] = 8

# Зачем окно: уточнение Мастера №5 — время приближения ОБЯЗАНО быть выводимым
# (скорость, длительность, смена траектории) без новых источников данных.
ATTENTION_OBS_WINDOW: Final[int] = 8

# §12.1: ключи сериализации — константы, не inline-строки.
_K_SUBJECT_ID = "subject_id"
_K_PHASE = "phase"
_K_FIRST_SEEN = "first_seen_tick"
_K_LAST_UPDATE = "last_update_tick"
_K_WINDOW = "observation_window"
_K_LAST_DISTANCE = "last_distance"
_K_LAST_BEARING = "last_bearing"
_K_TICK = "tick"
_K_DISTANCE = "distance"
_K_BEARING = "bearing"
_K_SUBJECT_HEADING = "subject_heading"


class AttentionPhase(str, Enum):
    """Фазы НАБЛЮДЕНИЯ (техническая модель восприятия, не социальный смысл).

    NEAR — дистанционный факт, не влечёт взаимодействие (решение Мастера №1).
    ORIENTED — v0: body_heading как приближение ориентации внимания (не взгляд).
    APPROACHING — интерпретация траектории «движется ко мне» (P2/P3), не просто Δd<0.
    LOST — LOS потерян: новые наблюдения замирают, накопленное НЕ стирается (ТЗ, сценарий H).
    """

    NOT_DETECTED = "not_detected"
    DETECTED = "detected"
    ORIENTED = "oriented"
    APPROACHING = "approaching"
    NEAR = "near"
    LOST = "lost"


@dataclass(frozen=True)
class AttentionObservation:
    """Точка наблюдения в полярной системе наблюдателя.

    Самодостаточна для P3-математики без хранения абсолютных позиций:
    d(distance)/dt — радиальная скорость (сближение/расхождение);
    d(bearing)/dt — тангенциальный дрейф (смена траектории, проход мимо);
    Δsubject_heading — «субъект повернулся ко мне» (наблюдаемое событие).
    """

    tick: int
    distance: float  # метры, >= 0
    bearing: float  # радианы: направление на субъект относительно body_heading наблюдателя
    subject_heading: float  # body_heading субъекта в момент наблюдения
    # P3-MATH substrate (M1-M3, вердикт Мастера): относительный вектор
    # субъект−наблюдатель в МИРОВОЙ рамке на момент наблюдения. Мировая
    # рамка стабильна при повороте наблюдателя (bearing — локальная) →
    # скорость/alignment/прогноз сближения выводимы из окна без новых
    # источников данных.
    rel_dx: float = 0.0
    rel_dy: float = 0.0

    def __post_init__(self) -> None:
        # Громкий отказ на NaN/inf: тихий зажим = маскировка онтологического
        # разрыва (L4; дух ADR-O-207).
        if not (
            math.isfinite(self.distance)
            and math.isfinite(self.bearing)
            and math.isfinite(self.subject_heading)
            and math.isfinite(self.rel_dx)
            and math.isfinite(self.rel_dy)
        ):
            raise ValueError(
                "AttentionObservation: non-finite perception value — ontological violation"
            )
        if self.tick < 0:
            raise ValueError("AttentionObservation: отрицательный tick")
        object.__setattr__(self, "distance", max(0.0, self.distance))

    def as_tuple(self) -> Tuple[Any, ...]:
        # Зачем кортеж: компактная персистентность окна в scene_state.
        return (
            self.tick,
            self.distance,
            self.bearing,
            self.subject_heading,
            self.rel_dx,
            self.rel_dy,
        )

    @staticmethod
    def from_tuple(raw: Tuple[Any, ...]) -> "AttentionObservation":
        if len(raw) != 6:
            raise ValueError(
                f"AttentionObservation.from_tuple: ожидалось 6 полей, получено {len(raw)}"
            )
        return AttentionObservation(
            tick=int(raw[0]),
            distance=float(raw[1]),
            bearing=float(raw[2]),
            subject_heading=float(raw[3]),
            rel_dx=float(raw[4]),
            rel_dy=float(raw[5]),
        )


@dataclass(frozen=True)
class AttentionState:
    """Состояние внимания наблюдателя к ОДНОМУ субъекту.

    last_distance/last_bearing: Optional — «нет данных» честно кодируется None,
    а не нулём (§ENIGMA-003: UNKNOWN ≠ NEUTRAL(0.0)).
    """

    subject_id: str
    phase: AttentionPhase
    first_seen_tick: int
    last_update_tick: int
    observation_window: Tuple[AttentionObservation, ...] = ()  # хронологический FIFO
    last_distance: Optional[float] = None
    last_bearing: Optional[float] = None


def create_attention_state(
    subject_id: str,
    phase: AttentionPhase,
    tick: int,
    observation: Optional[AttentionObservation] = None,
) -> AttentionState:
    """Рождение состояния. observation.tick обязан совпадать с tick рождения."""
    if not subject_id:
        raise ValueError("create_attention_state: пустой subject_id")
    if observation is not None and observation.tick != tick:
        raise ValueError(
            "create_attention_state: tick наблюдения не совпадает с tick рождения"
        )
    window = (observation,) if observation is not None else ()
    return AttentionState(
        subject_id=subject_id,
        phase=phase,
        first_seen_tick=tick,
        last_update_tick=tick,
        observation_window=window,
        last_distance=observation.distance if observation is not None else None,
        last_bearing=observation.bearing if observation is not None else None,
    )


def with_observation(
    prev: AttentionState,
    phase: AttentionPhase,
    tick: int,
    observation: AttentionObservation,
) -> AttentionState:
    """Добавляет наблюдение, двигает фазу, держит окно в пределах cap.

    FSM-валидация перехода (какая фаза за какой) — зона P2; здесь фаза
    проводится как вычисленный извне результат. Прошлое не мутируется:
    наблюдение со tick < last_update_tick — отказ (Invariant III).
    """
    if observation.tick < prev.last_update_tick:
        raise ValueError(
            "with_observation: наблюдение в прошлом — нарушение Temporal Isolation"
        )
    window = (*prev.observation_window, observation)
    if len(window) > ATTENTION_OBS_WINDOW:
        window = window[-ATTENTION_OBS_WINDOW:]
    return AttentionState(
        subject_id=prev.subject_id,
        phase=phase,
        first_seen_tick=prev.first_seen_tick,
        last_update_tick=tick,
        observation_window=window,
        last_distance=observation.distance,
        last_bearing=observation.bearing,
    )


def attention_to_dict(state: AttentionState) -> Dict[str, Any]:
    """§12.2 WARA: пишет КАЖДОЕ поле, которое читает attention_from_dict."""
    return {
        _K_SUBJECT_ID: state.subject_id,
        _K_PHASE: state.phase.value,
        _K_FIRST_SEEN: state.first_seen_tick,
        _K_LAST_UPDATE: state.last_update_tick,
        _K_WINDOW: [obs.as_tuple() for obs in state.observation_window],
        _K_LAST_DISTANCE: state.last_distance,
        _K_LAST_BEARING: state.last_bearing,
    }


ATTENTION_DEFAULT_FOV_RAD: Final[float] = math.pi / 2  # 90° — конвенция NEW-ORIENT-004


def wrap_pi(angle: float) -> float:
    """Нормализация угла в [-pi, pi]. Зачем: относительный bearing обязан
    быть знаковым и периодичным, иначе dθ/dt (смена траектории, P3) врёт."""
    while angle > math.pi:
        angle -= 2.0 * math.pi
    while angle < -math.pi:
        angle += 2.0 * math.pi
    return angle


def bearing_to(observer_xy: Tuple[float, float], target_xy: Tuple[float, float]) -> float:
    """Абсолютный азимут на цель — та же конвенция atan2(dy, dx), что
    movement_engine:743 (heading_snap): значения взаимозаменяемы."""
    return math.atan2(target_xy[1] - observer_xy[1], target_xy[0] - observer_xy[0])


def angular_diff(heading_a: float, heading_b: float) -> float:
    """Минимальная угловая разница [0, pi] — зеркало NEW-ORIENT-004:207-208."""
    diff = abs(heading_a - heading_b)
    if diff > math.pi:
        diff = 2.0 * math.pi - diff
    return diff


def is_facing(
    observer_heading: float,
    target_bearing: float,
    fov_rad: float = ATTENTION_DEFAULT_FOV_RAD,
) -> bool:
    """В поле зрения? FOV=90° симметрично (±45°) — соответствие формуле
    player_target_pipeline:209 (_diff < pi/2), вынесено для общего пользования."""
    return angular_diff(observer_heading, target_bearing) < fov_rad


def with_phase(
    prev: AttentionState, phase: AttentionPhase, tick: int
) -> AttentionState:
    """Смена фазы БЕЗ нового наблюдения (LOST-заморозка: окно не трогаем —
    память о наблюдаемом сохраняется, ТЗ сценарий H). Монохронность (Инвариант III)."""
    if tick < prev.last_update_tick:
        raise ValueError("with_phase: перевод фазы в прошлое — Temporal Isolation")
    return AttentionState(
        subject_id=prev.subject_id,
        phase=phase,
        first_seen_tick=prev.first_seen_tick,
        last_update_tick=tick,
        observation_window=prev.observation_window,
        last_distance=prev.last_distance,
        last_bearing=prev.last_bearing,
    )


def attention_from_dict(raw: Dict[str, Any]) -> AttentionState:
    """Строгая реконструкция: отсутствие обязательного ключа = громкий KeyError
    (L4: тихий None на границе сериализации запрещён)."""
    window_raw = raw[_K_WINDOW]
    if not isinstance(window_raw, list):
        raise ValueError("attention_from_dict: observation_window должен быть list")
    return AttentionState(
        subject_id=str(raw[_K_SUBJECT_ID]),
        phase=AttentionPhase(raw[_K_PHASE]),
        first_seen_tick=int(raw[_K_FIRST_SEEN]),
        last_update_tick=int(raw[_K_LAST_UPDATE]),
        observation_window=tuple(AttentionObservation.from_tuple(t) for t in window_raw),
        last_distance=(
            float(raw[_K_LAST_DISTANCE]) if raw[_K_LAST_DISTANCE] is not None else None
        ),
        last_bearing=(
            float(raw[_K_LAST_BEARING]) if raw[_K_LAST_BEARING] is not None else None
        ),
    )