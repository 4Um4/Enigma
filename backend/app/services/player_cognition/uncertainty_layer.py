"""
app/services/player_cognition/uncertainty_layer.py
Uncertainty Layer — финальная уверенность в каждом воспринятом элементе.

Объединяет: clarity × recognition × distortion × memory → final_confidence
UI использует final_confidence для принятия решений о отображении.

path: /backend/app/services/player_cognition/uncertainty_layer.py
Назначение: Вычисляет итоговую уверенность — объединяет clarity, recognition, distortion, memory в один final_confidence
Зависимости: types (PerceivedEntity)
Основные сущности: apply_uncertainty()
"""

from typing import List

from app.services.player_cognition.types import PerceivedEntity

# === Веса компонентов ===
_CLARITY_WEIGHT = 0.30
_RECOGNITION_WEIGHT = 0.20
_DISTORTION_PENALTY_WEIGHT = 0.25  # искажение УМЕНЬШАЕТ уверенность
_MEMORY_WEIGHT = 0.25


def _distortion_penalty(entity: PerceivedEntity) -> float:
    """
    Вычисляет штраф от когнитивного искажения.
    Чем выше bias — тем меньше доверия к восприятию.
    Возвращает 0.0 (нет штрафа) .. 1.0 (полное недоверие).
    """
    # Threat bias — игрок видит угрозу там где её нет
    threat_penalty = entity.threat_bias * 0.3
    # Trust bias — игрок не доверяет дружелюбным сигналам
    trust_penalty = abs(entity.trust_bias) * 0.4
    # Salience bias — фиксация сужает контекст
    salience_penalty = entity.salience_bias * 0.2

    total = threat_penalty + trust_penalty + salience_penalty
    return min(1.0, total)


def apply_uncertainty(entities: List[PerceivedEntity]) -> None:
    """
    Вычисляет final_confidence для каждой сущности.
    Вызывать ПОСЛЕ всех остальных слоёв.

    Мутирует entities in-place.
    """
    for entity in entities:
        if not entity.visible and not entity.audio_only:
            entity.final_confidence = 0.0
            continue

        # Базовые компоненты
        clarity = entity.clarity
        recognition = entity.recognition_confidence
        memory = entity.memory_decay

        # Штраф от искажения
        penalty = _distortion_penalty(entity)
        distortion_factor = 1.0 - penalty

        # Взвешенная сумма
        raw_confidence = (
            clarity * _CLARITY_WEIGHT
            + recognition * _RECOGNITION_WEIGHT
            + memory * _MEMORY_WEIGHT
        ) * distortion_factor

        # Audio-only — базовая неопределённость
        if entity.audio_only:
            raw_confidence *= 0.5

        entity.final_confidence = round(max(0.0, min(1.0, raw_confidence)), 3)
