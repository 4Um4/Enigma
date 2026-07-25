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
    attacker: NPCStateSnapshot, intent: ImpactIntentDTO, defender: NPCStateSnapshot, rng: random.Random
) -> ContactLevel:
    """Контактная модель: D&D 5e attack_roll → ContactLevel mapping (TZ §4.3)."""
    from app.services.game.combat_math import ability_modifier, attack_roll

    # Адаптер NPCStateSnapshot → combat_math dict
    # combat_math ожидает "abilities", а snapshot содержит "base_abilities".
    # Также поддерживаем legacy-формат с "abilities" для обратной совместимости.
    attacker_dict = {
        "abilities": attacker.get("base_abilities", attacker.get("abilities", {})),
        "level": attacker.get("level", 1),
        "equipped_weapon": attacker.get("equipped_weapon", {}),
    }

    # Вычисляем AC защитника: 10 + Dex mod + Armor mod
    # Если в snapshot нет ac, вычисляем его из dexterity
    defender_dict = {}
    if "ac" in defender:
        defender_dict["ac"] = defender["ac"]
    else:
        defender_abilities = defender.get("base_abilities", defender.get("abilities", {}))
        dex_score = defender_abilities.get("dexterity", 10.0)
        dex_mod = ability_modifier(dex_score)
        armor_mod = defender.get("modifiers", {}).get("ac", 0.0)
        # S123: High pain reduces dodge (AC). -1 AC for every 10 pain.
        pain = defender.get("pain", 0.0)
        pain_penalty = int(pain // 10.0)
        defender_dict["ac"] = 10 + dex_mod + armor_mod - pain_penalty

    # S118: Используем D&D 5e бросок атаки. combat_math берет статы из словарей.
    # ADR-O-301: Пробрасываем rng для детерминированности броска d20.
    result = attack_roll(attacker_dict, defender_dict, rng=rng)

    if not result.hit:
        return ContactLevel.MISS

    if result.critical:
        return ContactLevel.PERFECT

    # Определяем плотность контакта по перевыполению AC
    margin = result.attack_total - result.target_ac
    if margin >= 5:
        return ContactLevel.SOLID
    elif margin >= 2:
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
    contact = _resolve_contact(attacker, intent, defender, rng)
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
    if structural_damage > 15.0:
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
