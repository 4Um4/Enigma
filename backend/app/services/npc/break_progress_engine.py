# backend\app\services\npc\break_progress_engine.py
"""
ADR-TIFL-003: Двигатель Кристаллизации Идентичности (ICDF + ICL).
Воскрешён из статуса DEPRECATED. Подключён к TickOrchestrator через контур TIFL.

Выполняет две функции:
1. Острые мутации (TRAUMA_TOPOLOGY): символические травмы (например, "will_broken"),
   вызываемые через StateApplicator.
2. Непрерывный дрейф (compute_continuous_drift): фоновая адаптация личности
   на основе чистой ошибки предсказания (prediction_error) из Котла.

ВНИМАНИЕ (Технический долг - ADR-CNSRL):
Функции дрейфа используют isinstance(dict | NPCState) для совместимости
с сырым словарем npc_raw из TickOrchestrator.
Это нарушает принцип единой онтологии данных (Canonical State Unification).
Требуется ADR по унификации представления состояния для устранения
неявного полиморфизма и гарантии Replay Determinism.
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

from app.core.constants import (
    BREAK_DELTA_ADAPTATION,
    BREAK_DELTA_CRACKS,
    BREAK_DELTA_DEFORMATION,
    BREAK_DELTA_RATIONALIZATION,
    BREAK_DELTA_RESISTANCE,
    BREAK_FAILURE_AFFECT_THRESHOLD,
    BREAK_RECOVERY_BASE_RATE,
    BREAK_RECOVERY_PRESSURE_THRESHOLD,
    BREAK_RESISTANCE_DECAY,
    BREAK_RESISTANCE_GAIN,
    BREAK_RESISTANCE_PRESSURE_THRESHOLD,
    BREAK_STAGE_ADAPTATION,
    BREAK_STAGE_CRACKS,
    BREAK_STAGE_DEFORMATION,
    BREAK_STAGE_RATIONALIZATION,
    BREAK_STAGE_RESISTANCE,
    BREAK_SUPPORT_PRESSURE_REDUCTION,
    BREAK_WILL_BROKEN_PRESSURE_THRESHOLD,
)

from app.models.npc_state import NPCState, WillState

# EventContext не нужен — BreakProgressEngine работает на накопленном состоянии,
# не на конкретном событии. Вызов возможен в любой момент тика.

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BreakDeltas:
    """Результат расчёта процесса слома."""

    identity_integrity_delta: float = 0.0  # -0.01 до -0.3 за тик
    pressure_resistance_delta: float = 0.0  # +0.1 до +0.5 (anti-abuse)
    will_state_override: Optional[WillState] = None  # только при deformation
    identity_crisis: bool = False  # L2.7: Флаг кризиса (deformation) — DEPRECATED
    identity_pressure: float = 0.0  # L2.7: Эфемерное напряжение идентичности (0-100)
    recent_failures_delta: int = 0  # L2.7: Прирост/затухание счётчика неудач
    stage: str = (
        "resistance"  # resistance/cracks/rationalization/adaptation/deformation
    )


class BreakProgressEngine:
    """
    Чистая функция: state + event → дельты слома.
    Вызывается перед DecisionHub для обновления психологических параметров.
    """

    @staticmethod
    def calculate(
        state: NPCState,
        willpower: float = 50.0,  # из NPCPersonality
        recent_failures: int = 0,
        support_present: bool = False,
        social_pressure: float = 0.0,  # Шаг 1.1: Социальный стресс
    ) -> BreakDeltas:
        """
        Тик-независимый расчёт давления на личность NPC.
        Формула: pressure = fear + stress + failures - support
        Вызывается ДО DecisionHub — в python_engines, для всех NPC в локации.
        """
        # ADR-O-146: Давление вычисляется из восприятия (affective_load, threat)
        # и физиологии (stress), а не из сырого кэша отношений.
        _threat = (
            state.perceptual_kernel.threat_gradient * 100
            if state.perceptual_kernel
            else 0.0
        )
        _affect = state.affective_load * 100
        fear = max(_threat, _affect)  # Берём доминирующий источник страха
        stress = state.stress
        failures = recent_failures * 10  # каждая неудача +10 к давлению

        # Willpower снижает эффективное давление
        # Шаг 1.1: social_pressure добавляется к сыромy давлению
        raw_pressure = fear + stress + failures + social_pressure

        # Willpower ослабляет давление, а не обнуляет его
        willpower_factor = willpower / 100  # 0–1
        effective_pressure = raw_pressure / (1 + willpower_factor)
        if support_present:
            effective_pressure -= BREAK_SUPPORT_PRESSURE_REDUCTION

        pressure = max(0, min(100, effective_pressure))

        # Текущая целостность определяет стадию
        integrity = state.identity_integrity

        # Базовые дельты стадий (инвариант поведения)
        if integrity > BREAK_STAGE_CRACKS:
            stage = "resistance"
            base_delta = BREAK_DELTA_RESISTANCE
        elif integrity > BREAK_STAGE_RATIONALIZATION:
            stage = "cracks"
            base_delta = BREAK_DELTA_CRACKS
        elif integrity > BREAK_STAGE_ADAPTATION:
            stage = "rationalization"
            base_delta = BREAK_DELTA_RATIONALIZATION
        elif integrity > BREAK_STAGE_DEFORMATION:
            stage = "adaptation"
            base_delta = BREAK_DELTA_ADAPTATION
        else:
            stage = "deformation"
            base_delta = BREAK_DELTA_DEFORMATION

        # P1 FIX: Давление должно значительно превысить порог восстановления, чтобы активно ломать личность.
        # Фоновый стресс (голод/нищета) создаёт давление, но оно не должно испепелять идентичность за 3 дня.
        _excess_pressure = max(0.0, pressure - BREAK_RECOVERY_PRESSURE_THRESHOLD)
        pressure_factor = max(0.1, _excess_pressure / 100.0)

        # BUG 6 FIX: Восстановление identity_integrity.
        # Если давление спадает (ниже 10%), личность медленно восстанавливается к 1.0.
        # Формула асимптотическая: чем ближе к 1.0, тем медленнее рост.
        if pressure < BREAK_RECOVERY_PRESSURE_THRESHOLD and integrity < BREAK_STAGE_RESISTANCE:
            integrity_delta = BREAK_RECOVERY_BASE_RATE * (1.0 - integrity)
        else:
            # P1 FIX: Асимптотический распад. Чем ниже integrity, тем медленнее она падает.
            # Это предотвращает падение ровно в 0.000 и делает последние стадии слома более стойкими.
            integrity_delta = base_delta * integrity * (1 + pressure_factor)

        # Anti-abuse: сопротивление растёт при спаме
        resistance_delta = BREAK_RESISTANCE_GAIN if pressure > BREAK_RESISTANCE_PRESSURE_THRESHOLD else BREAK_RESISTANCE_DECAY

        # L2.7: Динамика recent_failures. Если аффективная нагрузка высока, неудачи накапливаются.
        # Если NPC спокоен (pressure < 10), счётчик затухает.
        if _affect > BREAK_FAILURE_AFFECT_THRESHOLD:
            failures_delta = 1
        elif pressure < BREAK_RECOVERY_PRESSURE_THRESHOLD:
            failures_delta = -1
        else:
            failures_delta = 0

        # Переход в BROKEN только при deformation и высоком pressure
        will_override = None
        identity_crisis = False
        if stage == "deformation":
            identity_crisis = True
            if pressure > BREAK_WILL_BROKEN_PRESSURE_THRESHOLD and state.will_state != WillState.BROKEN:
                will_override = WillState.BROKEN
        elif stage == "resistance" and state.will_state == WillState.BROKEN:
            # V8-PSY-3 FIX: Recovery path from BROKEN to FREE
            will_override = WillState.FREE

        logger.info(
            f"[BREAK] npc={state.npc_id} stage={stage} "
            f"integrity={state.identity_integrity:.3f} "
            f"integrity_delta={round(integrity_delta, 4):+.4f} "
            f"pressure={pressure:.1f}"
        )
        if will_override == WillState.BROKEN:
            logger.info(f"[BREAK] npc={state.npc_id} stage=deformation will_override=BROKEN")

        return BreakDeltas(
            identity_integrity_delta=round(integrity_delta, 4),
            pressure_resistance_delta=round(resistance_delta, 4),
            will_state_override=will_override,
            identity_crisis=identity_crisis,
            identity_pressure=round(pressure, 2),
            recent_failures_delta=failures_delta,
            stage=stage,
        )


# ─────────────────────────────────────────────────────────────────────────────
# S71: Identity Mutation Kernel v0 (Scalar Deformation Layer)
# ─────────────────────────────────────────────────────────────────────────────

# Топология структурных мутаций личности.
# S71: horizontal deformation (drives).
# S72: vertical deformation (interpretation, thresholds) - заглушка.
TRAUMA_TOPOLOGY = {
    "will_broken": {
        "drives": {"fear": +0.05, "control": -0.05},  # Трусливая покорность
        # S72: "interpretation": {"threat_sensitivity": +0.2},
    },
    "humiliated": {
        "drives": {"significance": -0.05, "fear": +0.05},  # Потеря лица
        # S72: "interpretation": {"shame_amplifier": +0.3},
    },
    "betrayed": {
        "drives": {"control": +0.05, "desire": -0.05},  # Параноидальный контроль
        # S72: "interpretation": {"trust_decay_acceleration": +0.4},
    },
    "near_death": {
        "drives": {"fear": +0.08, "significance": -0.08},  # Экзистенциальный шок
    },
}


def compute_mutation(state: "NPCState", trauma_type: str) -> Dict[str, float]:
    """
    Вычисляет дельты мутации drives_base на основе типа травмы
    и текущей пластичности личности (inverse rigidity).
    """
    topology = TRAUMA_TOPOLOGY.get(trauma_type, {})
    drive_deltas = topology.get("drives", {})

    if not drive_deltas:
        return {}

    # V8-PSY-1 FIX: Читаем identity_rigidity из personality (SSOT), с фолбэком на psyche dict
    rigidity = 0.5
    if hasattr(state, "personality") and hasattr(state.personality, "identity_rigidity"):
        rigidity = state.personality.identity_rigidity
    elif hasattr(state, "psyche"):
        if isinstance(state.psyche, dict):
            rigidity = state.psyche.get("identity_rigidity", 0.5)
        elif hasattr(state.psyche, "identity_rigidity"):
            rigidity = state.psyche.identity_rigidity

    # Пластичность: чем ниже rigidity, тем сильнее деформация.
    # Жёсткие личности сопротивляются изменениям структуры.
    # Max(0.2) гарантирует, что слом всё равно меняет структуру.
    plasticity = max(0.2, 1.0 - rigidity)

    return {k: v * plasticity for k, v in drive_deltas.items()}


# ADR-O-208: Ампутация apply_drives_mutation.
# TIFL больше не мутирует состояние напрямую. Он генерирует события деформации L1.
# Закон Сохранения Я теперь обеспечивается DriveResolver при проекции, а не записью в сырой словарь.


# ADR-TIFL-003: Identity Constraint Layer (Fixed Topology)
# Матрица связности драйвов. Определяет "физику психики".
# Положительные значения = Антагонизм (конфликтуют, создают напряжение если оба высоки).
# Отрицательные значения = Синергия (усиливают друг друга, тянутся к одному полюсу).
DRIVE_COUPLING: Dict[str, Dict[str, float]] = {
    "fear": {"fear": 0.0, "control": 0.6, "significance": 0.2, "desire": 0.1},
    "control": {"fear": 0.6, "control": 0.0, "significance": -0.3, "desire": -0.2},
    "significance": {"fear": 0.2, "control": -0.3, "significance": 0.0, "desire": -0.4},
    "desire": {"fear": 0.1, "control": -0.2, "significance": -0.4, "desire": 0.0},
}


def compute_continuous_drift(
    effective_drives: "EffectiveDrives",
    npc_id: str,
    rigidity: float,
    prediction_error: float,
    error_vector: Dict[str, float],
    current_tick: int,
) -> List["TraitDriftEvent"]:
    """
    ADR-TIFL-003: ICDF + ICL / ADR-O-208: DRP Phase II.
    TIFL работает ТОЛЬКО с эфемерной проекцией (L3). L0 и state для него не существуют.
    ВЫВОД: List[TraitDriftEvent] (давление мира).
    """
    from app.domain.identity_events import TraitDriftEvent

    # L3-P2: Чтение ТОЛЬКО из проекции. Никаких сырых словарей или объектов.
    _drives_base = dict(effective_drives.values)

    if not error_vector or prediction_error < 0.05:
        prediction_error = 0.0
    elif not _drives_base:
        return []

    # Пластичность передана извне. TIFL больше не лезет в psyche.
    plasticity = max(0.1, 1.0 - rigidity)
    total_mass = sum(_drives_base.values())
    if total_mass <= 0:
        return []

    # --- 1. ВНЕШНИЙ ДРЕЙФ (ICDF: Ошибка мира) ---
    LEARNING_RATE = 0.005
    shift_magnitude = prediction_error * LEARNING_RATE * plasticity

    external_drifts = {}
    for drive in _drives_base.keys():
        gain = shift_magnitude * error_vector.get(drive, 0.0)
        loss_tax = shift_magnitude * (_drives_base[drive] / total_mass)
        external_drifts[drive] = gain - loss_tax

    # --- 2. ВНУТРЕННЯЯ РЕЛАКСАЦИЯ (ICL: Тяга к аттрактору) ---
    # Сила, толкающая личность к минимуму внутреннего напряжения.
    RELAXATION_RATE = 0.002 * plasticity
    relaxation_drifts = {}

    for drive_k in _drives_base.keys():
        # Градиент напряжения по драйву k: сумма влияний всех связанных драйвов
        coupling_row = DRIVE_COUPLING.get(drive_k, {})
        # dTension/dDrive_k = sum(Coupling_kj * Drive_j)
        # Чтобы уменьшить напряжение, мы двигаемся ПРОТИВ градиента: -dTension/dDrive_k
        force = 0.0
        for drive_j, coupling_val in coupling_row.items():
            if drive_j in _drives_base:
                # Антагонист (coupling > 0): если другой драйв высок, толкает этот вниз (разводит).
                # Синергист (coupling < 0): если другой драйв высок, тянет этот вверх (сводит).
                force -= coupling_val * _drives_base[drive_j]

        relaxation_drifts[drive_k] = force * RELAXATION_RATE

    # --- 3. СУММАРНЫЙ ДРЕЙФ (Генерация событий L1) ---
    total_drifts = {}
    for drive in _drives_base.keys():
        total_drifts[drive] = external_drifts.get(drive, 0.0) + relaxation_drifts.get(
            drive, 0.0
        )

    # ADR-O-208: TIFL больше не мутирует. Он генерирует события деформации L1.
    events = []
    for trait, delta in total_drifts.items():
        if abs(delta) > 1e-6:  # Отсекаем шум
            events.append(
                TraitDriftEvent(
                    tick_id=current_tick,
                    target_id=npc_id,
                    source_id="tifl_pressure_model",
                    effect_value=float(delta),
                    event_type="pressure",
                )
            )
    return events
