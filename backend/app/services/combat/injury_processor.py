# -*- coding: utf-8 -*-
"""
path: backend/app/services/combat/injury_processor.py
Назначение: Мост между Injury и Physiology. Выводит эффекты из свойств раны, не из строковых флагов.
Зависимости: app.models.delta_payloads, app.models.state_delta, app.models.idle_tick
Основные сущности: InjuryProcessor

═══════════════════════════════════════════════════════════════
ПРИНЦИП: СВОЙСТВА ВМЕСТО ФЛАГОВ
═══════════════════════════════════════════════════════════════

Старый путь (запрещён):
    if "bleeding" in critical_effects:
        blood_loss_delta = severity * RATE

Новый путь:
    blood_loss_delta = severity * zone_rate * type_modifier

Разница:
    Флаг = инструкция («кровоточи»)
    Свойство = физическая реальность (зона, тип, глубина)

Физическая реальность раны ОПРЕДЕЛЯЕТ эффект.
Не строковый тег.

Артериальный порез ноги ≠ царапина на щече,
даже если structural_damage одинаковый.

═══════════════════════════════════════════════════════════════
НАПРАВЛЕНИЕ: INJURY → PROCESS → PHYSIOLOGY
═══════════════════════════════════════════════════════════════

Текущий InjuryProcessor — переходный слой.
Финальная архитектура:

    Injury
    ↓
    BleedingProcess(rate, source_injury)
    ↓
    blood_loss_delta каждый тик
    ↓
    Лечение останавливает Process, не blood_loss

Process — это причина с длительностью.
blood_loss — это симптом Process.

Лечение должно работать с причиной, не с симптомом.

Пока Process-системы нет, InjuryProcessor аппроксимирует её,
выводя эффекты из свойств травмы.
Когда Process появится, InjuryProcessor станет его фабрикой.

═══════════════════════════════════════════════════════════════
ДИНАМИКА С DECAYHANDLER (СВЁРТЫВАНИЕ)
═══════════════════════════════════════════════════════════════

InjuryProcessor:  +blood_loss_rate каждый тик (кровотечение)
DecayHandler:     -blood_loss * 0.01 каждый тик (свёртывание)

Равновесие:
    Артериальный порез (0.03/tick) >> свёртывание → смерть
    Поверхностный порез (0.005/tick) < свёртывание → восстановление
    Умеренный порез (0.015/tick) ≈ свёртывание → стабильная кровопотеря

Это создаёт фазовые переходы в организме БЕЗ порогов:
    лёгкая рана → самовосстановление
    средняя рана → стабильное ухудшение
    тяжёлая рана → смерть без вмешательства
"""

from __future__ import annotations

import logging
from typing import Dict, List

from app.models.delta_payloads import PhysiologyPayload
from app.models.idle_tick import NPCStateSnapshot
from app.models.state_delta import StateDeltas, DeltaDomain

logger = logging.getLogger(__name__)


# ── Зональные скорости кровопотери (л/тик на единицу structural_damage) ──
# Физическая реальность: разные зоны тела имеют разную васкуляризацию.
# Грудная клетка и пах — крупные сосуды. Конечности — средние.
# Череп — мало кровотечения (кость), лицо — много (мягкие ткани).

_ZONE_BLEEDING_RATE: Dict[str, float] = {
    "torso_chest":  0.025,   # Крупные сосуды, сердце, лёгкие
    "torso_gut":    0.020,   # Брыжеечные артерии
    "torso_groin":  0.030,   # Бедренная артерия — самая опасная зона
    "arm_l":        0.012,   # Лучевая/локтевая артерия
    "arm_r":        0.012,
    "leg_l":        0.015,   # Подколенная/берцовая артерия
    "leg_r":        0.015,
    "head_skull":   0.005,   # Кость — мало кровотечения
    "head_face":    0.015,   # Лицо — обильное кровоснабжение
    "head_eye_l":   0.003,   # Глаз — мало объёма, но критично
    "head_eye_r":   0.003,
    "head_neck":    0.035,   # Сонная артерия — летальная зона
}

_DEFAULT_ZONE_RATE: float = 0.010  # Для неизвестных зон


# ── Модификаторы типа повреждения ──
# Физическая реальность: порезы кровоточат, ушибы — нет, ожоги прижигают.

_DAMAGE_TYPE_BLEEDING: Dict[str, float] = {
    "slash":   1.5,    # Разрез — обильное наружное кровотечение
    "puncture": 1.0,   # Колющее — внутреннее кровотечение
    "blunt":    0.15,  # Ушиб — минимальное кровотечение (гематома)
    "burn":     0.05,  # Ожог — прижигает сосуды
    "crush":    0.3,   # Раздавливание — умеренное внутреннее
    "disease":  0.0,   # Болезнь не кровоточит (пока)
}

_DEFAULT_DAMAGE_RATE: float = 0.5


# ── Зональные модификаторы боли (плотность нервных окончаний / чувствительность) ──
_ZONE_PAIN_RATE: Dict[str, float] = {
    "torso_chest":  1.5,   # Множество нервных окончаний, дыхание
    "torso_gut":    1.2,   # Висцеральная боль
    "torso_groin":  2.5,   # Экстремальная чувствительность
    "arm_l":        1.0,   # Стандартная мышечная/костная боль
    "arm_r":        1.0,
    "leg_l":        1.0,
    "leg_r":        1.0,
    "head_skull":   0.8,   # В основном кость (если не лицо)
    "head_face":    2.0,   # Обилие нервов
    "head_eye_l":   2.0,   # Экстремальная чувствительность
    "head_eye_r":   2.0,
    "head_neck":    2.5,   # Горло, сонная артерия
}

_DEFAULT_ZONE_PAIN: float = 1.0

# ── Модификаторы типа боли ──
_DAMAGE_TYPE_PAIN: Dict[str, float] = {
    "slash":   1.5,    # Острая режущая боль
    "puncture": 1.5,   # Глубокая колющая
    "blunt":    0.8,   # Тупая ноющая
    "burn":     3.0,   # Интенсивная жгучая (самая сильная хроническая)
    "crush":    2.0,   # Пульсирующая давящая
    "disease":  1.0,   # Ломота
}

_DEFAULT_TYPE_PAIN: float = 1.0

_BASE_CHRONIC_PAIN_RATE: float = 2.0  # Базовая инъекция боли за тик (компенсирует PAIN_DECAY_LAMBDA=0.05)


def _compute_pain_rate(injury: dict) -> float:
    """Выводит скорость хронической боли из физических свойств раны.
    
    Формула:
        pain_rate = structural_damage * BASE_CHRONIC_PAIN_RATE * zone_modifier * type_modifier
        
    Взаимодействие с Decay:
        Decay: -pain * 0.05
        Injury: +pain_rate
        Равновесие: pain = pain_rate / 0.05
        
    Примеры:
        Порез груди (0.5 structural): 0.5 * 2.0 * 1.5 * 1.5 = 2.25/tick → равновесие pain=45 (дрожь, морщится)
        Ушиб руки (0.2 structural): 0.2 * 2.0 * 1.0 * 0.8 = 0.32/tick → равновесие pain=6.4 (не проявляется)
        Ожог лица (0.8 structural): 0.8 * 2.0 * 2.0 * 3.0 = 9.6/tick → равновесие pain=100 (агония)
    """
    zone = injury.get("target_zone", "")
    damage_type = injury.get("damage_type", "blunt")
    severity = float(injury.get("structural_damage", 0.0))
    
    zone_mod = _ZONE_PAIN_RATE.get(zone, _DEFAULT_ZONE_PAIN)
    type_mod = _DAMAGE_TYPE_PAIN.get(damage_type, _DEFAULT_TYPE_PAIN)
    
    return severity * _BASE_CHRONIC_PAIN_RATE * zone_mod * type_mod


def _compute_bleeding_rate(injury: dict) -> float:
    """Выводит скорость кровопотери из физических свойств раны.
    
    Не читает строковые флаги.
    Свойства раны (зона, тип, глубина) определяют эффект.
    
    Формула:
        bleeding_rate = structural_damage * zone_rate * type_modifier
    
    Примеры:
        Порез груди (slash, torso_chest, severity=0.5):
            0.5 * 0.025 * 1.5 = 0.019 за тик
            Без лечения через 47 тиков: blood_loss = 0.9 → DEAD
            
        Ушиб руки (blunt, arm_r, severity=0.5):
            0.5 * 0.012 * 0.15 = 0.0009 за тик
            Свёртывание побеждает → самовосстановление
            
        Порез шеи (slash, head_neck, severity=0.3):
            0.3 * 0.035 * 1.5 = 0.016 за тик
            Критическое кровотечение из сонной артерии
    """
    zone = injury.get("target_zone", "")
    damage_type = injury.get("damage_type", "blunt")
    severity = float(injury.get("structural_damage", 0.0))
    
    zone_rate = _ZONE_BLEEDING_RATE.get(zone, _DEFAULT_ZONE_RATE)
    type_modifier = _DAMAGE_TYPE_BLEEDING.get(damage_type, _DEFAULT_DAMAGE_RATE)
    
    return severity * zone_rate * type_modifier


class InjuryProcessor:
    """Phase 0.5: Injury → Physiology bridge.
    
    Чистая функция: читает injuries из снапшота,
    выводит физиологические эффекты из свойств ран.
    
    Следует протоколу IdleTickHandler.
    
    TODO: Когда появится Process-система,
    InjuryProcessor станет фабрикой процессов:
        Injury → InjuryProcessor.spawn_processes()
        Process → каждую фазу 0.5: generate_physiology_delta()
        Treatment → Process.deactivate()
    """
    
    name: str = "injury_processor"
    
    def handle(
        self,
        npcs: List[NPCStateSnapshot],
        campaign_id: str,
        current_tick: int,
    ) -> List[StateDeltas]:
        """Чистая функция: Injury properties → Physiology deltas."""
        results: List[StateDeltas] = []
        
        for npc in npcs:
            npc_id = npc.get("npc_id", "")
            if not npc_id:
                continue
            
            injuries_by_zone = npc.get("injuries_by_zone", {})
            if not injuries_by_zone:
                logger.warning(f"[INJURY_PROC] npc={npc_id} NO injuries_by_zone")
                continue
            
            logger.warning(f"[INJURY_PROC] npc={npc_id} zones={list(injuries_by_zone.keys())} wounds={sum(len(v) for v in injuries_by_zone.values())}")
            
            total_blood_loss_delta = 0.0
            total_pain_delta = 0.0
            wound_count = 0
            
            for zone, zone_injuries in injuries_by_zone.items():
                for inj in zone_injuries:
                    bleed_rate = _compute_bleeding_rate(inj)
                    if bleed_rate > 0.0:
                        total_blood_loss_delta += bleed_rate
                        wound_count += 1
                    
                    # ADR-141: Хроническая боль от открытых ран
                    pain_rate = _compute_pain_rate(inj)
                    if pain_rate > 0.0:
                        total_pain_delta += pain_rate
                        wound_count += 1
            
            if wound_count > 0 and (total_blood_loss_delta > 0 or total_pain_delta > 0):
                results.append(StateDeltas(
                    npc_id=npc_id,
                    domain=DeltaDomain.PHYSIOLOGY,
                    payload=PhysiologyPayload(
                        blood_loss_delta=round(total_blood_loss_delta, 4),
                        pain_delta=round(total_pain_delta, 4),
                    ),
                    source="injury_effects",
                ))
                
                logger.debug(
                    f"[INJURY_PROCESS] npc={npc_id} "
                    f"wounds={wound_count} "
                    f"blood_loss_delta=+{total_blood_loss_delta:.4f} "
                    f"pain_delta=+{total_pain_delta:.4f}"
                )
        
        return results