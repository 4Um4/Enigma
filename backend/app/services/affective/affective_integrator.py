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
    
    Входящее давление: веса определяются личностью (drives_base через psyche).
    fear → вес угрозы, control → вес неопределённости, significance → вес аномалии.
    Декэй: базовая скорость + бонус от воли.
    """
    # S72 / §ENIGMA-S72: Веса интерпретации из drives_base, не из хардкода движка.
    # Личность определяет, что для неё важно в сигналах мира.
    # Fallback на 0.25 — консервативная оценка (Neutral NPC).
    _w_threat = psyche.get("fear", 0.25)
    _w_uncertainty = psyche.get("control", 0.25)
    _w_anomaly = psyche.get("significance", 0.25)
    # S72-FIX: Физиология — мгновенный сигнал, не проходит через PerceptualKernel.
    _pain = psyche.get("pain", 0.0)
    _shock = psyche.get("shock", 0.0)

    # S75-R2 FIX: Hysteresis Model (Асимметричная Адаптация).
    # Убран аттрактор насыщения (incoming > recovery = вечный страх 1.0).
    # Страх растёт быстро (рефлекс), но спадает медленно (инерция психики).
    # Воля ускоряет выход из страха, но не может мгновенно его обнулить.
    target_load = min(1.0,
        getattr(kernel, 'threat_gradient', 0.0) * _w_threat +
        getattr(kernel, 'uncertainty', 0.0) * _w_uncertainty +
        getattr(kernel, 'anomaly_score', 0.0) * _w_anomaly +
        _pain + _shock
    )

    willpower = psyche.get("willpower", 0.5)

    if target_load > current_load:
        # Путь ВВЕРХ: Быстрая реакция на угрозу (рефлекс выживания)
        adaptation_rate = 0.30
    else:
        # Путь ВНИЗ: Медленное остывание (гистерезис/инерция)
        # Воля помогает быстрее прийти в себя
        adaptation_rate = 0.05 + (willpower * 0.1)

    # Асимптотическое притяжение к цели
    new_load = current_load + (target_load - current_load) * adaptation_rate

    return max(0.0, min(1.5, new_load))