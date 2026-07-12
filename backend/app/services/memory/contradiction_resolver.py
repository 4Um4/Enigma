from __future__ import annotations
# backend/app/services/memory/contradiction_resolver.py
"""
R1.5 — Contradiction Resolver.
Если новое событие противоречит belief NPC — обновляем confidence.
Чистая Python-логика, без LLM.
"""

from typing import List, Any, Dict

# Какие типы событий подрывают какие beliefs
CONTRADICTIONS: Dict[str, Dict[str, float]] = {
    "hero": {
        "combat_ally": -0.25,
        "theft": -0.20,
        "vandalism": -0.15,
        "intimidation": -0.10,
    },
    "threat": {
        "help": -0.20,
        "dialogue_key": -0.10,
        "quest": -0.15,
    },
    "friendly": {
        "combat": -0.30,
        "intimidation": -0.20,
        "theft": -0.25,
    },
    "trustworthy": {
        "theft": -0.35,
        "deception": -0.30,
        "vandalism": -0.15,
    },
}

# Какие события усиливают belief
CONFIRMATIONS: Dict[str, Dict[str, float]] = {
    "hero": {
        "quest": +0.15,
        "help": +0.20,
        "dialogue_key": +0.05,
    },
    "threat": {
        "combat": +0.20,
        "intimidation": +0.25,
        "vandalism": +0.15,
    },
    "friendly": {
        "help": +0.20,
        "dialogue_casual": +0.10,
        "quest": +0.10,
    },
    "trustworthy": {
        "quest": +0.15,
        "help": +0.20,
        "dialogue_key": +0.10,
    },
}


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


# Минимальный интервал тиков между обновлениями одного belief.
# Защита от дребезга при спаме одного события несколькими свидетелями.
COOLDOWN_TICKS: int = 2


def resolve(
    belief: Dict[str, Any],
    new_event: Dict[str, Any],
    current_tick: int = 0,
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Обновляет confidence belief на основе нового события.
    Возвращает (updated_belief, trace) — trace нужен для калибровки R4.2.

    belief = {"statement": "игрок герой", "tag": "hero", "confidence": 0.7}
    event  = {"type": "theft", "intensity": 1.5}
    →      ({"tag": "hero", "confidence": 0.575, ...}, {"changed": True, ...})
    """
    # Защита от пустых данных — тихий баг без этого
    tag = (belief.get("tag") or "").lower()
    event_type = (new_event.get("type") or new_event.get("action_type") or "").lower()

    if not tag or not event_type:
        return dict(belief), {"changed": False, "reason": "empty_input", "delta": 0.0}

    # Cooldown — игнорируем спам событий
    last_tick = belief.get("last_update_tick", 0)
    if current_tick - last_tick < COOLDOWN_TICKS and last_tick > 0:
        return dict(belief), {"changed": False, "reason": "cooldown", "delta": 0.0}

    updated = dict(belief)
    confidence = float(belief.get("confidence", 0.5))
    intensity = float(new_event.get("intensity", 1.0))

    # Точное совпадение приоритетнее подстроки.
    # Противоречие и подтверждение взаимоисключают друг друга за один тик.
    contra = CONTRADICTIONS.get(tag, {})
    contra_delta = contra.get(event_type) or next(
        (d for k, d in contra.items() if k in event_type), None
    )

    confirm_delta = None
    if contra_delta is None:
        confirm = CONFIRMATIONS.get(tag, {})
        confirm_delta = confirm.get(event_type) or next(
            (d for k, d in confirm.items() if k in event_type), None
        )

    raw_delta = contra_delta if contra_delta is not None else confirm_delta
    scaled_delta = 0.0

    if raw_delta is not None:
        # Масштабирование на интенсивность события — основа калибровки R4.2
        scaled_delta = round(raw_delta * intensity, 4)
        confidence = _clamp(confidence + scaled_delta)

        if contra_delta is not None:
            updated["last_challenge"] = event_type
            reason = "contradiction"
        else:
            updated["last_confirmation"] = event_type
            reason = "confirmation"

        updated["last_update_tick"] = current_tick
    else:
        reason = "no_match"

    updated["confidence"] = round(confidence, 4)

    trace = {
        "changed": raw_delta is not None,
        "reason": reason,
        "delta": scaled_delta,
        "event_type": event_type,
        "tag": tag,
    }
    return updated, trace


def resolve_all(
    beliefs: list[Dict[str, Any]],
    new_event: Dict[str, Any],
    current_tick: int = 0,
) -> tuple[list[Dict[str, Any]], list[Dict[str, Any]]]:
    """
    Обновляет весь список beliefs одним событием.
    Возвращает (updated_beliefs, traces) — traces для калибровки R4.2.
    """
    results = [resolve(b, new_event, current_tick) for b in beliefs]
    updated = [r[0] for r in results]
    traces = [r[1] for r in results]
    return updated, traces
