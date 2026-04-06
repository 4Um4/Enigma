# backend\app\services\npc\break_progress_engine.py
"""
R6.4 — BreakProgressEngine: процесс давления → трещины → слом.
Не принимает решений. Выдаёт дельты для StateApplicator.
"""

from dataclasses import dataclass
from typing import Optional
from app.services.npc.npc_state import NPCState, WillState
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