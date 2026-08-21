# backend\app\services\npc\break_progress_engine.py
"""
DEPRECATED: BreakProgressEngine не подключён к пайплайну (Устав §7.9).
Нарушает закон: "ResonanceEngine / ContradictionResolver без lifecycle hooks — мёртвый код"
Будет удалён после подключения к TickOrchestrator или переписан на StateDeltas.
R6.4 — BreakProgressEngine: процесс давления → трещины → слом.
Не принимает решений. Выдаёт дельты для StateApplicator.
"""

from dataclasses import dataclass
from typing import Dict, Optional
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
        fear = state.relationship_cache.get("fear", 0.0) * 100  # нормализуем 0-100
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


def apply_drives_mutation(state: 'NPCState', mutations: Dict[str, float]) -> None:
    """
    Применяет мутацию к drives_base с Законом Сохранения Я (sum=1.0).
    Защита от Renormalization Collapse: драйв не может упасть ниже 0.01.
    """
    if not mutations or not hasattr(state, 'drives_base') or not isinstance(state.drives_base, dict):
        return
        
    # Применение дельт с энтропийным полом (0.01)
    for drive, delta in mutations.items():
        old_val = state.drives_base.get(drive, 0.25)
        state.drives_base[drive] = max(0.01, old_val + delta)
    
    # Ренормализация (Закон Сохранения Я)
    total = sum(state.drives_base.values())
    if total > 0:
        state.drives_base = {k: v / total for k, v in state.drives_base.items()}
