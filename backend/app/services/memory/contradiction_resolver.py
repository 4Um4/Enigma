# backend/app/services/memory/contradiction_resolver.py
"""
R1.5 — Contradiction Resolver.
Если новое событие противоречит belief NPC — обновляем confidence.
Чистая Python-логика, без LLM.
"""

from __future__ import annotations
from typing import Any, Dict

# Какие типы событий подрывают какие beliefs
CONTRADICTIONS: Dict[str, Dict[str, float]] = {
    "hero": {
        "combat_ally":    -0.25,
        "theft":          -0.20,
        "vandalism":      -0.15,
        "intimidation":   -0.10,
    },
    "threat": {
        "help":           -0.20,
        "dialogue_key":   -0.10,
        "quest":          -0.15,
    },
    "friendly": {
        "combat":         -0.30,
        "intimidation":   -0.20,
        "theft":          -0.25,
    },
    "trustworthy": {
        "theft":          -0.35,
        "deception":      -0.30,
        "vandalism":      -0.15,
    },
}

# Какие события усиливают belief
CONFIRMATIONS: Dict[str, Dict[str, float]] = {
    "hero": {
        "quest":          +0.15,
        "help":           +0.20,
        "dialogue_key":   +0.05,
    },
    "threat": {
        "combat":         +0.20,
        "intimidation":   +0.25,
        "vandalism":      +0.15,
    },
    "friendly": {
        "help":           +0.20,
        "dialogue_casual": +0.10,
        "quest":          +0.10,
    },
    "trustworthy": {
        "quest":          +0.15,
        "help":           +0.20,
        "dialogue_key":   +0.10,
    },
}


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def resolve(belief: Dict[str, Any], new_event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Обновляет confidence belief на основе нового события.

    belief = {"statement": "игрок герой", "tag": "hero", "confidence": 0.7}
    event  = {"type": "theft"}
    →      {"statement": "игрок герой", "tag": "hero", "confidence": 0.50}

    Возвращает обновлённый belief (оригинал не мутируется).
    """
    updated = dict(belief)
    tag = belief.get("tag", "").lower()
    event_type = (
        new_event.get("type") or new_event.get("action_type") or ""
    ).lower()
    confidence = float(belief.get("confidence", 0.5))

    # Проверяем противоречия
    contra = CONTRADICTIONS.get(tag, {})
    for key, delta in contra.items():
        if key in event_type:
            confidence = _clamp(confidence + delta)
            updated["last_challenge"] = event_type
            break

    # Проверяем подтверждения
    confirm = CONFIRMATIONS.get(tag, {})
    for key, delta in confirm.items():
        if key in event_type:
            confidence = _clamp(confidence + delta)
            updated["last_confirmation"] = event_type
            break

    updated["confidence"] = round(confidence, 4)
    return updated


def resolve_all(
    beliefs: list[Dict[str, Any]],
    new_event: Dict[str, Any],
) -> list[Dict[str, Any]]:
    """Обновляет весь список beliefs одним событием."""
    return [resolve(b, new_event) for b in beliefs]