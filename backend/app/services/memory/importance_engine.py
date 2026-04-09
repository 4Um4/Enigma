"""
R1.3 + R5.3 — Importance Engine.
Теперь учитывает не только тип события, но и восприятие NPC (clarity, stress, emotion).
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional

from app.services.npc.npc_state import EmotionTag

# Базовые веса по типу события (R1.3)
BASE_IMPORTANCE: Dict[str, float] = {
    "combat":          0.85,
    "vandalism":       0.75,
    "theft":           0.70,
    "dialogue_key":    0.60,
    "quest":           0.65,
    "intimidation":    0.55,
    "dialogue_casual": 0.30,
    "movement":        0.15,
    "observation":     0.10,
}

DECAY_RATE  = 0.92
DECAY_EVERY = 10


def score_event(
    event: Dict[str, Any],
    npc_clarity: float = 1.0,
    npc_stress: float = 0.0,
    emotion_tag: Optional[str] = None,
) -> float:
    """
    R5.3 — Расширенный расчёт importance.
    
    Базовая важность + модификаторы от восприятия NPC.
    clarity снижает важность при плохом восприятии.
    Высокий стресс усиливает эмоционально значимые события.
    """
    event_type = (
        event.get("type")
        or event.get("action_type")
        or event.get("event_type", "")
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
    clarity_mod = max(0.4, npc_clarity)   # минимум 40% даже при плохом восприятии

    # 3. Модификатор стресса и эмоции
    stress_mod = 1.0
    if npc_stress > 70 and emotion_tag in (EmotionTag.ANGRY.value, EmotionTag.FEARFUL.value):
        stress_mod = 1.25   # стресс усиливает значимость угрозы/обиды
    elif npc_stress > 50:
        stress_mod = 1.10

    # 4. Финальная важность
    importance = base * clarity_mod * stress_mod

    return round(max(0.05, min(1.0, importance)), 4)


def apply_decay(events: List[Dict[str, Any]], rate: float = DECAY_RATE) -> List[Dict[str, Any]]:
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
