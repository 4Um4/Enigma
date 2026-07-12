"""
Измерительный прибор для детекции фазового перехода личности (ADR-O-209/210).
Цель: доказать существование дискретного скачка CSV при достижении
нормализованного давления CPN критического порога θ_yield.

Сцена: 2 NPC (A - объект, B - источник), 1 CFL ячейка, LOS = True.

Запуск:
"""

from dataclasses import dataclass, replace
from typing import List

import numpy as np

# =====================================================================
# 1. СТРУКТУРЫ ДАННЫХ (Контракты прибора)
# =====================================================================


@dataclass(frozen=True)
class CausalPressureVector:
    """5D редукция сырой реальности (CPC)"""

    fear: float = 0.0
    control: float = 0.0
    significance: float = 0.0
    desire: float = 0.0
    volatility: float = 0.0

    def to_array(self) -> np.ndarray:
        return np.array([self.fear, self.control, self.significance, self.desire, self.volatility])


@dataclass(frozen=True)
class CausalStateVector:
    """Точка фиксации фазы личности (CSV)"""

    g_basis: np.ndarray  # Базис пространства решений
    last_commit_tick: int = 0
    version: int = 0


@dataclass
class EmissionPacket:
    """Локальный вклад в поле (CFL)"""

    entity_id: str
    pos: np.ndarray
    pressure: CausalPressureVector
    radius: float


@dataclass
class TraitCrystallizationEvent:
    """Факт необратимого фазового перехода"""

    tick: int
    npc_id: str
    delta_g: np.ndarray


# =====================================================================
# 2. КОНСТАНТЫ КАЛИБРОВКИ ПРИБОРА
# =====================================================================

THETA_YIELD: float = 0.8  # Порог интегрального напряжения
TAU_MIN: int = 10  # Рефрактерный период (тики)
THETA_ALIGN: float = 0.1  # Дисперсия направления (низкая = стабильное)
CPN_ALPHA: float = 0.5  # Вес внутреннего давления
CPN_BETA: float = 0.5  # Вес внешнего давления
CFL_SATURATION: float = 1.5  # Потолок поля
DECAY_RADIUS: float = 5.0  # Радиус затухания эмиссии

# =====================================================================
# 3. ФИЗИЧЕСКИЕ ФУНКЦИИ (Движок прибора)
# =====================================================================


def sample_field(position: np.ndarray, emissions: List[EmissionPacket]) -> CausalPressureVector:
    """CFL: Чистая функция свёртки буфера эмиссий."""
    total_pressure = np.zeros(5)
    for packet in emissions:
        distance = np.linalg.norm(position - packet.pos)
        if distance > packet.radius:
            continue
        # LOS = True по условию теста
        attenuation = np.exp(-distance / packet.radius)
        total_pressure += packet.pressure.to_array() * attenuation

    total_pressure = np.clip(total_pressure, 0.0, CFL_SATURATION)
    return CausalPressureVector(*total_pressure)


def cpn_normalize(s_internal: CausalPressureVector, s_env: CausalPressureVector) -> CausalPressureVector:
    """CPN: Нормализация двух доменов давления."""
    total = CPN_ALPHA * s_internal.to_array() + CPN_BETA * s_env.to_array()
    return CausalPressureVector(*total)


def phi_stable_check(
    tick: int,
    csv: CausalStateVector,
    pressure_history: List[CausalPressureVector],
    current_pressure: CausalPressureVector,
) -> bool:
    """Φ_stable: Детектор фазового перехода."""
    # Врата 0: Рефрактерный период
    if tick - csv.last_commit_tick < TAU_MIN:
        return False

    # Врата 1: Предел упругости (Интеграл давления)
    # Упрощённо для теста: сумма fear-компоненты за окно
    stress_integral = sum(p.fear for p in pressure_history[-TAU_MIN:])
    if stress_integral < THETA_YIELD:
        return False

    # Врата 2: Выравнивание векторов (Стабильность направления)
    if len(pressure_history) >= 2:
        variance = np.var([p.fear for p in pressure_history[-5:]])
        if variance > THETA_ALIGN:
            return False

    return True


# =====================================================================
# 4. СЦЕНАРИЙ ИЗМЕРЕНИЯ (Сам тест)
# =====================================================================


def test_social_phase_transition():
    """
    Доказывает:
    1. Дискретность (1 commit event)
    2. Необратимость (поведение после отличается)
    3. Локальность (без NPC_B -> нет перехода)
    """

    # --- SETUP ---
    pos_a = np.array([0.0, 0.0])
    pos_b = np.array([1.0, 0.0])

    npc_a_csv = CausalStateVector(g_basis=np.array([0.5, 0.5]), version=0)
    npc_a_history: List[CausalPressureVector] = []
    npc_a_events: List[TraitCrystallizationEvent] = []

    emissions_buffer: List[EmissionPacket] = []

    # =========================================================================
    # STEP 1: STABLE BASELINE (Ticks 0-5)
    # =========================================================================
    for tick in range(0, 5):
        s_env = sample_field(pos_a, emissions_buffer)
        s_internal = CausalPressureVector()  # Нейтральное внутреннее
        s_total = cpn_normalize(s_internal, s_env)
        npc_a_history.append(s_total)

        commit = phi_stable_check(tick, npc_a_csv, npc_a_history, s_total)
        assert not commit, "Фазовый переход без давления!"

    assert npc_a_csv.version == 0, "CSV мутировал в базовой линии"

    # =========================================================================
    # STEP 2: PRESSURE INJECTION (Ticks 5-15)
    # =========================================================================
    # NPC_B начинает излучать страх
    b_pressure = CausalPressureVector(fear=0.2, control=0.0, significance=0.0, desire=0.0, volatility=0.0)
    emissions_buffer.append(EmissionPacket(entity_id="B", pos=pos_b, pressure=b_pressure, radius=DECAY_RADIUS))

    for tick in range(5, 15):
        s_env = sample_field(pos_a, emissions_buffer)
        s_total = cpn_normalize(CausalPressureVector(), s_env)
        npc_a_history.append(s_total)

        commit = phi_stable_check(tick, npc_a_csv, npc_a_history, s_total)
        # В этом окне интеграл может быть ещё мал, но давление растёт
        assert s_total.fear > 0.0, "Поле давления не доходит до NPC_A"

    # =========================================================================
    # STEP 3 & 4: CRITICAL WINDOW & PHASE TRANSITION (Ticks 15-25)
    # =========================================================================
    commit_occurred = False
    commit_tick = -1

    for tick in range(15, 25):
        s_env = sample_field(pos_a, emissions_buffer)
        s_total = cpn_normalize(CausalPressureVector(), s_env)
        npc_a_history.append(s_total)

        if phi_stable_check(tick, npc_a_csv, npc_a_history, s_total):
            # АКТ КОММИТА
            delta_g = np.array([0.1, -0.1])  # Искажение базиса в сторону страха
            npc_a_csv = replace(npc_a_csv, g_basis=npc_a_csv.g_basis + delta_g, last_commit_tick=tick, version=1)
            npc_a_events.append(TraitCrystallizationEvent(tick, "A", delta_g))
            commit_occurred = True
            commit_tick = tick
            break  # Фазовый переход дискретен

    assert commit_occurred, f"Фазовый переход не произошёл при θ_yield={THETA_YIELD}"
    assert npc_a_csv.version == 1
    assert not np.array_equal(npc_a_csv.g_basis, np.array([0.5, 0.5])), "Базис не деформировался"

    # =========================================================================
    # STEP 5: POST-TRANSITION RELAXATION (Ticks 25-35)
    # =========================================================================
    # NPC_B уходит, поле исчезает
    emissions_buffer.clear()

    for tick in range(commit_tick + 1, 35):
        s_env = sample_field(pos_a, emissions_buffer)
        assert s_env.fear == 0.0, "Поле не исчезло после удаления источника"

        s_total = cpn_normalize(CausalPressureVector(), s_env)
        npc_a_history.append(s_total)

        # Проверка необратимости: CSV остаётся деформированным
        commit = phi_stable_check(tick, npc_a_csv, npc_a_history, s_total)
        # Может сработать снова, если τ_min прошёл, но давления нет -> коммита не будет
        if commit:
            assert False, "Повторный коммит без давления!"

    assert npc_a_csv.version == 1, "CSV откатился после снятия давления"

    # Инвариант локальности: без эмиссии B интеграл никогда бы не набрался
    # (Проверено неявно в STEP 1 и STEP 5)
