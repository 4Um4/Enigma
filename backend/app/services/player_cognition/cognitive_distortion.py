"""
app/services/player_cognition/cognitive_distortion.py
Cognitive Distortion для игрока — искажение восприятия на основе состояния.

Те же 3 оси что у NPC (threat_bias, trust_bias, salience_bias),
но источники другие: stress, hp, fatigue — не relationship_cache.

path: /backend/app/services/player_cognition/cognitive_distortion.py
Назначение: Искажает восприятие игрока на основе его состояния (stress, hp, fatigue) — те же 3 оси что у NPC, другие источники
Зависимости: types (PerceivedEntity), math
Основные сущности: PlayerDistortionInputs, apply_cognitive_distortion()
"""

from dataclasses import dataclass
from typing import List

from app.services.player_cognition.types import PerceivedEntity


@dataclass
class PlayerDistortionInputs:
    """
    Входные параметры искажения — абстрактный контракт.
    Не привязан к NPCState напрямую — вызывающий код извлекает числа.
    """

    stress: float = 0.0  # 0-100
    effective_hp: int = 100
    effective_max_hp: int = 100
    fatigue: float = 0.0  # 0-100, TODO: будет добавлено в NPCState позже


# === Множители искажения ===
_THREAT_AMPLIFICATION = 0.008  # стресс → усиление угрозы
_STRESS_TUNNEL = 0.006  # стресс → фиксация на угрозах
_LOW_HP_THREAT = 0.15  # низкое HP → базовый бонус угрозы
_LOW_HP_THRESHOLD = 0.4  # ниже 40% HP — искажение включается
_FATIGUE_BLUR = 0.003  # усталость → общее снижение чёткости
_MAX_DISTORTION = 0.6  # governor: суммарное искажение не превышает


def _compute_bias(inputs: PlayerDistortionInputs) -> tuple[float, float, float]:
    """
    Вычисляет 3 оси искажения из состояния игрока.

    Returns:
        (threat_bias, trust_bias, salience_bias)
        threat_bias:  0.0 .. +1.0 (усиление воспринимаемой угрозы)
        trust_bias:   -1.0 .. 0.0 (снижение доверия — игрок параноит)
        salience_bias: 0.0 .. +1.0 (фиксация на угрозах)
    """
    threat_bias = 0.0
    trust_bias = 0.0
    salience_bias = 0.0

    # 1. Stress → threat amplification
    if inputs.stress > 30.0:
        threat_bias += (inputs.stress - 30.0) * _THREAT_AMPLIFICATION

    # 2. Stress → tunnel vision (salience)
    if inputs.stress > 50.0:
        salience_bias += (inputs.stress - 50.0) * _STRESS_TUNNEL

    # 3. Low HP → threat (инстинкт самосохранения)
    if inputs.effective_max_hp > 0:
        hp_ratio = inputs.effective_hp / inputs.effective_max_hp
    else:
        hp_ratio = 1.0

    if hp_ratio < _LOW_HP_THRESHOLD:
        deficit = _LOW_HP_THRESHOLD - hp_ratio
        threat_bias += deficit * _LOW_HP_THREAT
        trust_bias -= deficit * 0.2  # раненый меньше доверяет

    # 4. Fatigue → общее снижение (через trust — меньше доверия к оценкам)
    if inputs.fatigue > 40.0:
        trust_bias -= (inputs.fatigue - 40.0) * _FATIGUE_BLUR

    # Governor
    total = abs(threat_bias) + abs(trust_bias) + abs(salience_bias)
    if total > _MAX_DISTORTION:
        scale = _MAX_DISTORTION / total
        threat_bias *= scale
        trust_bias *= scale
        salience_bias *= scale

    # Капы
    threat_bias = max(0.0, min(1.0, threat_bias))
    trust_bias = max(-1.0, min(0.0, trust_bias))
    salience_bias = max(0.0, min(1.0, salience_bias))

    return (
        round(threat_bias, 3),
        round(trust_bias, 3),
        round(salience_bias, 3),
    )


def apply_cognitive_distortion(
    entities: List[PerceivedEntity],
    inputs: PlayerDistortionInputs,
) -> None:
    """
    Применяет когнитивное искажение к воспринимаемым сущностям.
    Записывает bias в каждую сущность — Uncertainty Layer использует их позже.

    Мутирует entities in-place.
    """
    threat_bias, trust_bias, salience_bias = _compute_bias(inputs)

    for entity in entities:
        entity.threat_bias = threat_bias
        entity.trust_bias = trust_bias
        entity.salience_bias = salience_bias

        # Усиление угрозы: inference типа "armed" усиливается при high threat_bias
        if threat_bias > 0.1:
            for inf in entity.inferences:
                if inf.inference_type in (
                    "armed",
                    "possible_threat",
                    "potential_aggression",
                ):
                    inf.confidence = min(1.0, inf.confidence + threat_bias * 0.2)

        # Снижение доверия: "friendly_action" и "communication" ослабляются
        if trust_bias < -0.1:
            for inf in entity.inferences:
                if inf.inference_type in (
                    "friendly_action",
                    "communication",
                    "peaceful_interaction",
                ):
                    inf.confidence = max(0.0, inf.confidence + trust_bias * 0.3)
