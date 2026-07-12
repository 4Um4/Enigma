# -*- coding: utf-8 -*-
"""
Impact Propagation Engine (Мастер Тай: Violence Simulation).

Файл: backend/app/services/combat/impact_engine.py
Назначение: Вычисление каскадных физических последствий воздействия.
Зависимости: app.models.impact, app.models.idle_tick, app.models.state_delta
Основные сущности: resolve_physical_impact

Не "Combat System", а физическая причинность:
Force -> Tissue -> Pain -> Shock -> Functional Loss.

Правила:
1. Чистая функция: (Snapshots, Intent) -> List[StateDeltas]
2. НЕ пишет эмоции. Пишет PhysiologyPayload + shock_impulse.
3. HP — производная. Центр: Functional Capacity.
4. Контакт зависит от состояния (усталость, боль, готовность), а не от RNG "Hit Roll".

TODO:
- В будущем можно расширить ImpactIntentDTO, добавив поля для более сложных взаимодействий (например, area_of_effect для взрывов, или conditional_effects для эффектов, зависящих от состояния цели).
- ContactResult может быть расширен для включения более детальной информации о результатах воздействия,например, какие конкретные травмы были нанесены, или какие статусы были применены к цели. Это позволит нам более точно моделировать последствия физических воздействий и их влияние на NPC state.
- Важно, что эти контракты должны быть достаточно абстрактными, чтобы позволить гибкую реализацию механики насилия в будущем, включая возможность добавления новых типов воздействий, новых зон попадания, и более сложных взаимодействий между атакующими и защищающимися NPC. Это обеспечит нам широкие возможности для развития механики насилия в рамках нашей игры, не требуя постоянного изменения контрактов при добавлении новых фич.
"""

import random
from typing import List

from app.models.delta_payloads import InjuryDTO, PhysiologyPayload
from app.models.idle_tick import NPCStateSnapshot
from app.models.impact import ContactLevel, ImpactIntentDTO
from app.models.state_delta import DeltaDomain, StateDeltas

# Вероятности попадания по зонам (если не указана конкретная)
_ZONE_WEIGHTS = {
    "torso_chest": 35,
    "torso_gut": 25,
    "arm_l": 10,
    "arm_r": 10,
    "leg_l": 10,
    "leg_r": 10,
    "head_skull": 5,
    "head_face": 5,
}


def _resolve_contact(
    intent: ImpactIntentDTO, defender: NPCStateSnapshot, rng: random.Random
) -> ContactLevel:
    """Контактная модель: учитывает усталость, боль и готовность защищаться."""
    # Базовый шанс увернуться/блокировать (из способностей)
    _abilities = defender.get("base_abilities", {})
    _modifiers = defender.get("modifiers", {})
    dodge_chance = (
        _abilities.get("dexterity", 10.0) + _modifiers.get("dexterity", 0.0)
    ) / 100.0

    # Шок и боль снижают способность уклоняться (Functional Capacity)
    pain_penalty = defender.get("pain", 0.0) / 200.0
    fatigue_penalty = defender.get("fatigue", 0.0) / 200.0
    shock_penalty = defender.get("blood_loss", 0.0) / 2.0  # Кровопотеря = дезориентация

    effective_dodge = max(
        0.0, dodge_chance - pain_penalty - fatigue_penalty - shock_penalty
    )

    roll = rng.random()

    if roll < effective_dodge:
        return ContactLevel.MISS

    # Степень контакта (чем хуже уклонение, тем плотнее попадание)
    contact_roll = rng.random() - (effective_dodge * 0.5)
    if contact_roll > 0.8:
        return ContactLevel.PERFECT
    elif contact_roll > 0.5:
        return ContactLevel.SOLID
    elif contact_roll > 0.2:
        return ContactLevel.PARTIAL
    else:
        return ContactLevel.GLANCING


def _resolve_target_zone(intent: ImpactIntentDTO, rng: random.Random) -> str:
    """Определяет куда попало воздействие."""
    if intent.target_zone:
        return intent.target_zone

    zones = list(_ZONE_WEIGHTS.keys())
    weights = list(_ZONE_WEIGHTS.values())
    return rng.choices(zones, weights=weights, k=1)[0]


def _calculate_tissue_damage(
    force: float, contact: ContactLevel, damage_type: str
) -> float:
    """Вычисляет структурный урон в зависимости от контакта и типа."""
    contact_multiplier = {
        ContactLevel.MISS: 0.0,
        ContactLevel.GLANCING: 0.3,
        ContactLevel.PARTIAL: 0.6,
        ContactLevel.SOLID: 1.0,
        ContactLevel.PERFECT: 1.5,  # Уязвимые точки
    }.get(contact, 0.0)

    return force * contact_multiplier


def resolve_physical_impact(
    attacker: NPCStateSnapshot,
    defender: NPCStateSnapshot,
    intent: ImpactIntentDTO,
    rng_seed: int = 42,
) -> List[StateDeltas]:
    """Точка входа: вычисляет каскад физических последствий.

    Возвращает ТОЛЬКО Physiology-дельты.
    Эмоциональные/социальные последствия генерируются подписчиками на основе shock_impulse.
    """
    rng = random.Random(rng_seed)
    deltas = []

    # 1. Contact Resolution
    contact = _resolve_contact(intent, defender, rng)
    if contact == ContactLevel.MISS:
        # Промах — атакующий тратит энергию, защитник нет
        deltas.append(
            StateDeltas(
                npc_id=intent.actor_id,
                domain=DeltaDomain.PHYSIOLOGY,
                payload=PhysiologyPayload(fatigue_delta=2.0),
            )
        )
        return deltas

    # 2. Zone Resolution
    zone = _resolve_target_zone(intent, rng)

    # 3. Energy Transfer & Tissue Interaction
    structural_damage = _calculate_tissue_damage(
        intent.force, contact, intent.damage_type
    )

    # 4. Functional Consequences (Боль, Кровопотеря, Шок)
    # Зональные модификаторы (Мастер Тай: пах и голова = болевой шок)
    pain_multiplier = 1.0
    bleeding_multiplier = 1.0

    if zone.startswith("head"):
        pain_multiplier = 2.0
    elif zone == "torso_groin":
        pain_multiplier = 2.5
        bleeding_multiplier = 0.5  # Много боли, мало кровопотери
    elif zone.startswith("arm") or zone.startswith("leg"):
        bleeding_multiplier = 0.8

    if intent.damage_type == "slash":
        bleeding_multiplier *= 1.5
    elif intent.damage_type == "blunt":
        pain_multiplier *= 1.2
        bleeding_multiplier *= 0.5

    pain_delta = structural_damage * pain_multiplier
    blood_loss_delta = (structural_damage / 100.0) * bleeding_multiplier

    # Шоковый импульс (0-1.0) — сигнал для ReactionSubscriber
    shock_impulse = min(1.0, structural_damage / 50.0)

    # HP как макро-LOD производная
    hp_delta = -structural_damage

    # Травма (если урон существенный)
    injuries = ()
    functional_loss = 0.0
    if structural_damage > 20.0:
        functional_loss = structural_damage / 100.0
        injuries = (
            InjuryDTO(
                damage_type=intent.damage_type,
                target_zone=zone,
                structural_damage=structural_damage / 100.0,
                functional_loss=functional_loss,
                critical_effects=("bleeding",) if blood_loss_delta > 0.05 else (),
            ),
        )

    # Дельта для защищающегося
    deltas.append(
        StateDeltas(
            npc_id=intent.target_id,
            domain=DeltaDomain.PHYSIOLOGY,
            target=intent.actor_id,  # Источник давления (для трейсинга)
            payload=PhysiologyPayload(
                hp_delta=hp_delta,
                pain_delta=pain_delta,
                fatigue_delta=0.0,
                blood_loss_delta=blood_loss_delta,
                shock_impulse=shock_impulse,
                add_injuries=injuries,
                add_statuses=("unconscious",) if pain_delta > 90 else (),
            ),
            source="impact_resolution",
        )
    )

    # Дельта для атакующего (усталость от удара)
    deltas.append(
        StateDeltas(
            npc_id=intent.actor_id,
            domain=DeltaDomain.PHYSIOLOGY,
            payload=PhysiologyPayload(fatigue_delta=5.0 + (structural_damage * 0.1)),
            source="impact_resolution",
        )
    )

    return deltas
