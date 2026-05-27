"""
Affective Integrator: Интегрирует пространственное и когнитивное давление во времени.
ADR-049: Реализация принципа "Страх — это интеграл угрозы по времени".

TODO:
- Внедрить в NPCState (affective_load) и обновлять при каждом тике.
- Настроить пороги для эмоциональных коллапсов и реакций.
"""
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.npc_state import PerceptualKernel

def integrate_affective_pressure(
    kernel: "PerceptualKernel",
    current_load: float,
    psyche: dict,
    dt: float = 1.0
) -> float:
    """
    Накапливает аффективное давление из PerceptualKernel.
    
    Входящее давление: угроза (60%), неопределенность (30%), аномалия (10%).
    Декэй: базовая скорость + бонус от воли.
    """
    # Входящее давление (с safe-getattr на случай пустого ядра)
    incoming = (
        getattr(kernel, 'threat_gradient', 0.0) * 0.6 +
        getattr(kernel, 'uncertainty', 0.0) * 0.3 +
        getattr(kernel, 'anomaly_score', 0.0) * 0.1
    )
    
    # Скорость восстановления (вола помогает отрезвлять разум)
    willpower = psyche.get("willpower", 0.5)
    recovery_rate = 0.05 + (willpower * 0.1)
    
    # Интегрирование (накопление - восстановление)
    new_load = current_load + (incoming * dt) - (recovery_rate * dt)
    
    # Ограничение снизу (0.0) и сверху (1.5 для экстремальных состояний)
    return max(0.0, min(1.5, new_load))