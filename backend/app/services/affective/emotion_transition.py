"""
Emotion Transition: Конвертация накопленного аффективного давления в эмоциональный переход.
ADR-049: Восприятие → Накопление → Фазовый переход (Эмоция).

- Проверять при каждом тике, если affective_load пересекает пороги.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from app.models.delta_payloads import EmotionPayload

# Пороги аффективного коллапса
THRESHOLD_ANXIOUS = 0.3
THRESHOLD_FEARFUL = 0.6
THRESHOLD_PANIC = 0.85


def resolve_emotion_transition(
    affective_load: float, prev_load: float, psyche: Dict[str, Any]
) -> Optional[EmotionPayload]:
    """
    Проверяет пересечение порогов аффективного давления.
    Если давление превысило порог (фазовый переход), генерирует EmotionPayload.
    Трусость снижает порог паники, воля — повышает.
    """
    fear_drive = psyche.get("fear", 0.5)
    willpower = psyche.get("willpower", 0.5)

    # Динамические пороги личности (S72: все три порога персонализированы)
    panic_threshold = THRESHOLD_PANIC - (fear_drive * 0.15) + (willpower * 0.05)
    fear_threshold = THRESHOLD_FEARFUL - (fear_drive * 0.1) + (willpower * 0.05)
    anxious_threshold = THRESHOLD_ANXIOUS - (fear_drive * 0.05) + (willpower * 0.03)

    _stress_delta = 0.0
    _emotion_tag = None
    _fear_delta = 0.0

    # Фазовый коллапс: Паника
    if affective_load > panic_threshold and prev_load <= panic_threshold:
        _emotion_tag = "panic"
        _stress_delta = affective_load * 30.0
        _fear_delta = affective_load * 20.0
    # Фазовый коллапс: Страх
    elif affective_load > fear_threshold and prev_load <= fear_threshold:
        _emotion_tag = "fear"
        _stress_delta = affective_load * 15.0
        _fear_delta = affective_load * 10.0
    # Нарастание: Тревога (S72: порог персонализирован)
    elif affective_load > anxious_threshold and prev_load <= anxious_threshold:
        _emotion_tag = "anxious"
        _stress_delta = affective_load * 8.0

    if _stress_delta > 0:
        return EmotionPayload(
            stress_delta=_stress_delta,
            emotion_delta=_fear_delta,
            emotion_tag=_emotion_tag,
        )

    return None
