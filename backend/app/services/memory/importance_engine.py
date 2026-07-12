"""
R1.3 + R5.3 — Importance Engine.
Теперь учитывает не только тип события, но и восприятие NPC (clarity, stress, emotion).
"""
from __future__ import annotations

from typing import Any, Dict, List


# Базовые веса по типу события (R1.3)
BASE_IMPORTANCE: Dict[str, float] = {
    "combat": 0.85,
    "vandalism": 0.75,
    "theft": 0.70,
    "dialogue_key": 0.60,
    "quest": 0.65,
    "intimidation": 0.55,
    "dialogue_casual": 0.30,
    "movement": 0.15,
    "observation": 0.10,
}

DECAY_RATE = 0.92


def score_event(
    event: Dict[str, Any],
    npc_clarity: float = 1.0,
    npc_stress: float = 0.0,
) -> float:
    """
    ADR-O-206: Расчёт importance на основе каузальной глубины (Surprise).
    EmotionTag полностью изолирован от логики памяти.

    Базовая важность + модификаторы от восприятия NPC.
    clarity снижает важность при плохом восприятии.
    Высокий стресс усиливает значимость структурных разрывов.
    """
    event_type = (
        event.get("type") or event.get("action_type") or event.get("event_type", "")
    ).lower()

    # 1. Базовая важность
    base = 0.30
    if event_type in BASE_IMPORTANCE:
        base = BASE_IMPORTANCE[event_type]
    else:
        for key, val in BASE_IMPORTANCE.items():
            if key in event_type:
                base = val
                break

    # 2. Модификатор clarity (R5.3)
    clarity_mod = max(0.4, npc_clarity)  # минимум 40% даже при плохом восприятии

    # 3. Модификатор стресса и эмоции
    stress_mod = 1.0
    # ADR-O-205: Memory Projection.
    # Память фиксирует не "страх", а структурный разрыв (величину ошибки предсказания).
    # Высокий Surprise (delta в Котле) = яркая память, независимо от того, какой драйв победил.
    # ADR-O-206 Cut 4: Causal Purity.
    # Никаких производных аффективного состояния. Только ошибка модели мира.
    prediction_error = abs(
        event.get("prediction_error", 0.0)
    )  # Чистый |O - P| из Котла

    if npc_stress > 70 and prediction_error > 0.2:
        stress_mod = 1.25  # Ошибка предсказания при высоком стрессе = яркая память
    elif npc_stress > 50 or prediction_error > 0.1:
        stress_mod = 1.10  # Умеренная значимость

    # 4. Финальная важность
    importance = base * clarity_mod * stress_mod

    return round(max(0.05, min(1.0, importance)), 4)


def apply_decay(
    events: List[Dict[str, Any]], rate: float = DECAY_RATE
) -> List[Dict[str, Any]]:
    """
    Оставляем без изменений — используется для legacy dict событий.
    Для EventMemory decay происходит внутри .decayed().
    """
    result = []
    for event in events:
        updated = dict(event)
        current = float(updated.get("importance", 0.30))
        new_importance = round(current * rate, 4)
        updated["importance"] = new_importance
        if new_importance < 0.05:
            updated["archived"] = True
        result.append(updated)
    return result
