# backend/app/services/memory/importance_engine.py
"""
R1.3 — Importance Score + Decay.
Python считает важность события без LLM.
Каждые 10 ходов применяется decay × 0.92.
"""

from __future__ import annotations
from typing import Any, Dict, List

IMPORTANCE_RULES: Dict[str, float] = {
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
DECAY_EVERY = 10   # ходов


def score_event(event: Dict[str, Any]) -> float:
    """
    Возвращает importance 0.0–1.0 для события.
    Берёт тип из event["type"] или event["action_type"].
    Если тип не найден — возвращает 0.30 (нейтральное событие).
    """
    event_type = (
        event.get("type")
        or event.get("action_type")
        or ""
    ).lower()

    for key, score in IMPORTANCE_RULES.items():
        if key in event_type:
            return score

    return 0.30


def apply_decay(events: List[Dict[str, Any]], rate: float = DECAY_RATE) -> List[Dict[str, Any]]:
    """
    Снижает importance каждого события на rate.
    События с importance < 0.05 помечаются archived=True.
    Оригинальный список не мутируется — возвращает новый.
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