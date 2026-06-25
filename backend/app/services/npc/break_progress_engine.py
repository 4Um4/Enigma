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

from dataclasses import dataclass
from typing import Dict, Optional, List
from app.models.npc_state import NPCState, WillState
# EventContext не нужен — BreakProgressEngine работает на накопленном состоянии,
# не на конкретном событии. Вызов возможен в любой момент тика.

@dataclass(frozen=True)
class BreakDeltas:
    """Результат расчёта процесса слома."""
    identity_integrity_delta: float = 0.0    # -0.01 до -0.3 за тик
    pressure_resistance_delta: float = 0.0   # +0.1 до +0.5 (anti-abuse)
    will_state_override: Optional[WillState] = None  # только при deformation
    stage: str = "resistance"  # resistance/cracks/rationalization/adaptation/deformation

class BreakProgressEngine:
    """
    Чистая функция: state + event → дельты слома.
    Вызывается перед DecisionHub для обновления психологических параметров.
    """
    
    # TODO: миграция в core/constants.py после калибровки
    # Пороги стадий (identity_integrity)
    STAGE_RESISTANCE = 1.0
    STAGE_CRACKS = 0.8
    STAGE_RATIONALIZATION = 0.6
    STAGE_ADAPTATION = 0.4
    STAGE_DEFORMATION = 0.2
    
    @staticmethod
    def calculate(
        state: NPCState,
        willpower: float = 50.0,  # из NPCPersonality
        recent_failures: int = 0,
        support_present: bool = False,
    ) -> BreakDeltas:
        """
        Тик-независимый расчёт давления на личность NPC.
        Формула: pressure = fear + stress + failures - support
        Вызывается ДО DecisionHub — в python_engines, для всех NPC в локации.
        """
        # ADR-O-146: Давление вычисляется из восприятия (affective_load, threat)
        # и физиологии (stress), а не из сырого кэша отношений.
        _threat = state.perceptual_kernel.threat_gradient * 100 if state.perceptual_kernel else 0.0
        _affect = state.affective_load * 100
        fear = max(_threat, _affect)  # Берём доминирующий источник страха
        stress = state.stress
        failures = recent_failures * 10  # каждая неудача +10 к давлению
        
        # Willpower снижает эффективное давление
        raw_pressure = fear + stress + failures

        # Willpower ослабляет давление, а не обнуляет его
        willpower_factor = willpower / 100  # 0–1
        effective_pressure = raw_pressure / (1 + willpower_factor)
        if support_present:
            effective_pressure -= 20  # поддержка снижает давление
            
        pressure = max(0, min(100, effective_pressure))
        
        # Текущая целостность определяет стадию
        integrity = state.identity_integrity
        
        # Базовые дельты стадий (инвариант поведения)
        if integrity > BreakProgressEngine.STAGE_CRACKS:
            stage = "resistance"
            base_delta = -0.01
        elif integrity > BreakProgressEngine.STAGE_RATIONALIZATION:
            stage = "cracks"
            base_delta = -0.03
        elif integrity > BreakProgressEngine.STAGE_ADAPTATION:
            stage = "rationalization"
            base_delta = -0.02
        elif integrity > BreakProgressEngine.STAGE_DEFORMATION:
            stage = "adaptation"
            base_delta = -0.05
        else:
            stage = "deformation"
            base_delta = -0.1

        # Минимальное давление — чтобы не было -0.0
        pressure_factor = max(0.1, pressure / 100)

        # Давление усиливает разрушение (единая формула для всех стадий)
        integrity_delta = base_delta * (1 + pressure_factor)
        
        # Anti-abuse: сопротивление растёт при спаме
        resistance_delta = 0.1 if pressure > 50 else -0.05  # затухает если нет давления
        
        # Переход в BROKEN только при deformation и высоком pressure
        will_override = None
        if stage == "deformation" and pressure > 80 and state.will_state != WillState.BROKEN:
            will_override = WillState.BROKEN
            
        return BreakDeltas(
            identity_integrity_delta=round(integrity_delta, 4),
            pressure_resistance_delta=round(resistance_delta, 4),
            will_state_override=will_override,
            stage=stage
        )
# ─────────────────────────────────────────────────────────────────────────────
# S71: Identity Mutation Kernel v0 (Scalar Deformation Layer)
# ─────────────────────────────────────────────────────────────────────────────

# Топология структурных мутаций личности.
# S71: horizontal deformation (drives).
# S72: vertical deformation (interpretation, thresholds) - заглушка.
TRAUMA_TOPOLOGY = {
    "will_broken": {
        "drives": {"fear": +0.05, "control": -0.05}, # Трусливая покорность
        # S72: "interpretation": {"threat_sensitivity": +0.2},
    },
    "humiliated": {
        "drives": {"significance": -0.05, "fear": +0.05}, # Потеря лица
        # S72: "interpretation": {"shame_amplifier": +0.3},
    },
    "betrayed": {
        "drives": {"control": +0.05, "desire": -0.05}, # Параноидальный контроль
        # S72: "interpretation": {"trust_decay_acceleration": +0.4},
    },
    "near_death": {
        "drives": {"fear": +0.08, "significance": -0.08}, # Экзистенциальный шок
    }
}

def compute_mutation(state: 'NPCState', trauma_type: str) -> Dict[str, float]:
    """
    Вычисляет дельты мутации drives_base на основе типа травмы 
    и текущей пластичности личности (inverse rigidity).
    """
    topology = TRAUMA_TOPOLOGY.get(trauma_type, {})
    drive_deltas = topology.get("drives", {})
    
    if not drive_deltas:
        return {}
        
    # Безопасное чтение rigidity
    rigidity = 0.5 
    if hasattr(state, 'psyche'):
        if isinstance(state.psyche, dict):
            rigidity = state.psyche.get("identity_rigidity", 0.5)
        elif hasattr(state.psyche, 'identity_rigidity'):
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
    "fear":        {"fear": 0.0, "control": 0.6, "significance": 0.2, "desire": 0.1},
    "control":     {"fear": 0.6, "control": 0.0, "significance": -0.3, "desire": -0.2},
    "significance":{"fear": 0.2, "control": -0.3, "significance": 0.0, "desire": -0.4},
    "desire":      {"fear": 0.1, "control": -0.2, "significance": -0.4, "desire": 0.0},
}

from typing import List # Добавь это в начало файла, если там нет typing

def compute_continuous_drift(effective_drives: "EffectiveDrives", npc_id: str, rigidity: float, prediction_error: float, error_vector: Dict[str, float], current_tick: int) -> List["TraitDriftEvent"]:
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
        return {}

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
        total_drifts[drive] = external_drifts.get(drive, 0.0) + relaxation_drifts.get(drive, 0.0)
        
    # ADR-O-208: TIFL больше не мутирует. Он генерирует события деформации L1.
    events = []
    for trait, delta in total_drifts.items():
        if abs(delta) > 1e-6:  # Отсекаем шум
            events.append(TraitDriftEvent(
                tick_id=current_tick,
                target_id=npc_id,
                source_id="tifl_pressure_model",
                effect_value=float(delta)
            ))
    return events
