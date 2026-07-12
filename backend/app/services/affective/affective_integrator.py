"""
Affective Integrator: Интегрирует пространственное и когнитивное давление во времени.
ADR-049: Реализация принципа "Страх — это интеграл угрозы по времени".

TODO:
- Внедрить в NPCState (affective_load) и обновлять при каждом тике.
- Настроить пороги для эмоциональных коллапсов и реакций.
"""
from __future__ import annotations

from typing import List, Dict, Any, TYPE_CHECKING, Tuple

if TYPE_CHECKING:
    from app.models.npc_state import PerceptualKernel

# Константы Active Inference (вынесены из TickOrchestrator)
_MEMORY_DECAY_RATE: float = 0.85
_TRAUMA_SCAR_RATE: float = 0.2
_SURPRISE_GAIN: float = 1.2


def integrate_affective_pressure(
    kernel: "PerceptualKernel",
    psyche: Dict[str, Any],
    current_load: float,
    current_memory: float,
    dt: float = 1.0,
) -> Tuple[float, float]:
    """
    ADR-049 / ADR-O-206: Интегрирует давление во времени (Active Inference + Hysteresis).

    Возвращает:
        Tuple[new_load, new_affective_memory]
    """
    _w_threat = psyche.get("fear", 0.25)
    _w_uncertainty = psyche.get("control", 0.25)
    _w_anomaly = psyche.get("significance", 0.25)

    willpower = psyche.get("willpower", 0.5)
    _w_somatic = 1.0 - willpower * 0.5

    # 1. Мгновенное восприятие (pk_load)
    pk_load = min(
        1.0,
        getattr(kernel, "threat_gradient", 0.0) * _w_threat
        + getattr(kernel, "uncertainty", 0.0) * _w_uncertainty
        + getattr(kernel, "anomaly_score", 0.0) * _w_anomaly
        + getattr(kernel, "somatic_urgency", 0.0) * _w_somatic,
    )

    # 2. Active Inference: Ошибка предсказания (Surprise)
    delta = pk_load - current_memory
    _abs_error = abs(delta)

    # 3. Обновление базового ожидания (Prior / Котёл)
    # ADR-O-206 Cut 2: Вес памяти модулируется Surprise (ошибкой предсказания).
    # Нелинейная функция: маленькие surprise почти ничего не делают, большие оставляют шрам.
    _scar_rate = 0.1 + (0.4 * (_abs_error**1.5))
    new_memory = min(1.0, current_memory * _MEMORY_DECAY_RATE + pk_load * _scar_rate)

    # 4. Эмоциональный ответ (Posterior / Affective Load)
    # ADR-O-206: Память (prior) не является источником энергии.
    # Она формирует ожидание, которое гасит surprise, когда реальность совпадает с ожиданием.
    # Эмоциональная нагрузка = функция от ошибки предсказания (surprise), а не от памяти + ошибки.
    current_load_adjusted = min(1.0, _abs_error * _SURPRISE_GAIN)

    # 5. Hysteresis: Асимптотическое притяжение к цели
    target_load = pk_load
    if target_load > current_load_adjusted:
        adaptation_rate = 0.30
    else:
        adaptation_rate = 0.05 + (willpower * 0.1)

    new_load = (
        current_load_adjusted + (target_load - current_load_adjusted) * adaptation_rate
    )

    return max(0.0, min(1.0, new_load)), new_memory
