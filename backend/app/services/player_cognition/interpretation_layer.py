"""
app/services/player_cognition/interpretation_layer.py
Interpretation Layer — выводы о значении наблюдений.

Tier 1 (Physical): "рука движется быстро" — из activity + markers
Tier 2 (Behavioral): "агрессия" — из комбинации Tier-1 выводов + контекста
Tier 3 (Narrative): только в DM-промпте, не здесь.

path: /backend/app/services/player_cognition/interpretation_layer.py
Назначение: Делает выводы о поведении на основе физических наблюдений — deterministic rules
Зависимости: types (Inference, InferenceTier, PerceivedEntity)
Основные сущности: apply_interpretation()
"""
from typing import List, Optional

from app.services.player_cognition.types import Inference, InferenceTier, PerceivedEntity


# === Tier 1: Physical inference ===
# activity → наблюдение + физический вывод
_TIER1_RULES: List[dict] = [
    {
        "activity": "fighting",
        "observation": "боевые действия",
        "inference_type": "combat",
        "confidence": 0.9,
    },
    {
        "activity": "fleeing",
        "observation": "быстрое перемещение прочь",
        "inference_type": "escape",
        "confidence": 0.85,
    },
    {
        "activity": "intimidating",
        "observation": "агрессивная поза/жесты",
        "inference_type": "possible_threat",
        "confidence": 0.75,
    },
    {
        "activity": "talking",
        "observation": "разговор",
        "inference_type": "communication",
        "confidence": 0.7,
    },
    {
        "activity": "helping",
        "observation": "оказывает помощь",
        "inference_type": "friendly_action",
        "confidence": 0.75,
    },
    {
        "activity": "observing",
        "observation": "наблюдает за окружением",
        "inference_type": "surveillance",
        "confidence": 0.5,
    },
    {
        "activity": "sleeping",
        "observation": "без сознания",
        "inference_type": "unconscious",
        "confidence": 0.95,
    },
    {
        "activity": "eating",
        "observation": "приём пищи",
        "inference_type": "routine_activity",
        "confidence": 0.8,
    },
    {
        "activity": "cleaning_tables",
        "observation": "убирает",
        "inference_type": "working",
        "confidence": 0.85,
    },
]

# visible_markers → физические наблюдения (без activity)
_MARKER_TIER1: List[dict] = [
    {
        "marker": "sword",
        "observation": "оружие в руках",
        "inference_type": "armed",
        "confidence": 0.95,
    },
    {
        "marker": "weapon",
        "observation": "оружие",
        "inference_type": "armed",
        "confidence": 0.9,
    },
    {
        "marker": "armor",
        "observation": "доспех",
        "inference_type": "armored",
        "confidence": 0.95,
    },
    {
        "marker": "helmet",
        "observation": "шлем",
        "inference_type": "armored",
        "confidence": 0.7,
    },
]


# === Tier 2: Behavioral inference ===
# Комбинации Tier-1 выводов → поведенческий вывод
_TIER2_RULES: List[dict] = [
    {
        "required_types": {"combat"},
        "inference_type": "active_aggression",
        "confidence": 0.85,
        "distance_modifier": {"<2.0": 0.10, "<5.0": 0.0, ">=5.0": -0.15},
    },
    {
        "required_types": {"possible_threat", "armed"},
        "any_of": True,  # хотя бы один из пары
        "inference_type": "potential_aggression",
        "confidence": 0.6,
        "distance_modifier": {"<2.0": 0.15, "<5.0": 0.05, ">=5.0": -0.10},
    },
    {
        "required_types": {"escape"},
        "inference_type": "retreat",
        "confidence": 0.8,
    },
    {
        "required_types": {"friendly_action", "communication"},
        "any_of": True,
        "inference_type": "peaceful_interaction",
        "confidence": 0.7,
    },
    {
        "required_types": {"surveillance"},
        "inference_type": "possible_ambush",
        "confidence": 0.3,
        "distance_modifier": {"<5.0": 0.15, ">=5.0": -0.10},
    },
    {
        "required_types": {"armed"},
        "missing_types": {"communication", "friendly_action", "working", "routine_activity"},
        "inference_type": "potentially_hostile",
        "confidence": 0.35,
    },
]


def _apply_tier1(entity: PerceivedEntity) -> List[Inference]:
    """Применяет Tier 1 правила к одной сущности"""
    inferences: List[Inference] = []
    raw = entity._raw_data
    observations: List[str] = []

    # По activity
    activity = raw.get("activity", "")
    for rule in _TIER1_RULES:
        if activity == rule["activity"]:
            observations.append(rule["observation"])
            inferences.append(Inference(
                inference_type=rule["inference_type"],
                tier=InferenceTier.PHYSICAL,
                confidence=rule["confidence"],
                source_observations=[rule["observation"]],
            ))
            break  # одно activity — одно правило

    # По visible_markers
    markers: List[str] = raw.get("visible_markers") or []
    for marker in markers:
        for rule in _MARKER_TIER1:
            if marker == rule["marker"]:
                observations.append(rule["observation"])
                inferences.append(Inference(
                    inference_type=rule["inference_type"],
                    tier=InferenceTier.PHYSICAL,
                    confidence=rule["confidence"],
                    source_observations=[rule["observation"]],
                ))

    entity.observations = observations
    return inferences


def _apply_tier2(
    entity: PerceivedEntity,
    tier1_types: set,
) -> List[Inference]:
    """Применяет Tier 2 behavioural правила"""
    inferences: List[Inference] = []

    for rule in _TIER2_RULES:
        required = rule.get("required_types", set())
        missing = rule.get("missing_types", set())
        any_of = rule.get("any_of", False)

        # Проверка обязательных типов
        if any_of:
            if not required.intersection(tier1_types):
                continue
        else:
            if not required.issubset(tier1_types):
                continue

        # Проверка отсутствующих типов
        if missing and missing.intersection(tier1_types):
            continue

        # Базовая confidence
        confidence = rule["confidence"]

        # Модификатор расстояния
        dist_mods = rule.get("distance_modifier", {})
        for threshold_str, modifier in dist_mods.items():
            op = threshold_str[:2]
            val = float(threshold_str[2:])
            if op == "<=" and entity.distance <= val:
                confidence += modifier
            elif op == ">=" and entity.distance >= val:
                confidence += modifier
            elif op == "< " and entity.distance < val:
                confidence += modifier

        confidence = max(0.0, min(1.0, confidence))

        # Собираем source_observations из Tier 1
        source = [inf.source_observations[0] for inf in entity.inferences if inf.tier == InferenceTier.PHYSICAL]

        inferences.append(Inference(
            inference_type=rule["inference_type"],
            tier=InferenceTier.BEHAVIORAL,
            confidence=confidence,
            source_observations=source,
        ))

    return inferences


def apply_interpretation(entities: List[PerceivedEntity]) -> None:
    """
    Применяет Interpretation Layer (Tier 1 + Tier 2) к сущностям.
    Только для видимых и в внимании.

    Мутирует entities in-place.
    """
    for entity in entities:
        if not entity.visible or not entity.in_attention:
            continue

        # Только NPC имеют поведение
        if entity.entity_type != "npc":
            continue

        # Tier 1: физические выводы
        tier1 = _apply_tier1(entity)
        entity.inferences.extend(tier1)

        # Tier 2: поведенческие выводы
        tier1_types = {inf.inference_type for inf in tier1}
        tier2 = _apply_tier2(entity, tier1_types)
        entity.inferences.extend(tier2)