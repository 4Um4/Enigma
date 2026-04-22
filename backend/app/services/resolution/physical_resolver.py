# backend/app/services/resolution/physical_resolver.py
"""
PhysicalResolver — чистый Python resolver физических действий.

Назначение: Чистый Python resolver — кубик + формула → PhysicalOutcome. НЕ LLM агент.
Зависимости: models/physical.py, random
Основные сущности: PhysicalResolver

Позиция в pipeline:
    Player Action (PHYSICAL) → PhysicalResolver → PhysicalOutcome → ReflexResolver → StateApplicator

АРХИТЕКТУРНОЕ РАЗДЕЛЕНИЕ от rules_agent:
    rules_agent      = LLM агент → текст для DM промпта ("успех/провал")
    PhysicalResolver = Python функция → стейт для StateApplicator (PhysicalOutcome)

Оба могут бросать кубик. Но выходы идут в РАЗНЫЕ каналы:
    rules_agent      → SceneOutcomeBuilder → DM промпт (текст)
    PhysicalResolver → StateApplicator → NPCState (числа)

ЗАПРЕЩЕНО:
  - Вызов LLM
  - Генерация текста
  - Доступ к NPCState (только входные числа)
"""

from __future__ import annotations

import random

from app.models.physical import DamageType, PhysicalOutcome, OutcomeResult


# ── Формулы D&D 5e (упрощённые) ──────────────────────────────────────────

_CRITICAL_THRESHOLD = 20
_NATURAL_1_FUMBLE = True  # Natural 1 = автоматический промах


def _roll_d20() -> int:
    """Бросок d20."""
    return random.randint(1, 20)


def _roll_damage(damage_formula: str, critical: bool = False) -> int:
    """
    Парсит формулу урона и бросает.
    Форматы: "1d6+2", "2d8", "1d10+3", "1d4"
    Critical = удваивает кубики (не бонус).
    """
    damage_formula = damage_formula.strip().lower()
    
    # Парсинг: "2d8+3" → (num_dice=2, dice_sides=8, flat_bonus=3)
    num_dice = 1
    dice_sides = 6
    flat_bonus = 0
    
    if "d" in damage_formula:
        parts = damage_formula.split("d", 1)
        num_dice = int(parts[0]) if parts[0] else 1
        
        remaining = parts[1]
        if "+" in remaining:
            dice_part, bonus_part = remaining.split("+", 1)
            dice_sides = int(dice_part)
            flat_bonus = int(bonus_part)
        elif "-" in remaining:
            dice_part, bonus_part = remaining.split("-", 1)
            dice_sides = int(dice_part)
            flat_bonus = -int(bonus_part)
        else:
            dice_sides = int(remaining)
    else:
        # Просто число без кубика
        return max(0, int(damage_formula))
    
    # Бросаем кубики
    actual_dice = num_dice * 2 if critical else num_dice
    total = sum(random.randint(1, dice_sides) for _ in range(actual_dice))
    total += flat_bonus
    
    return max(0, total)


class PhysicalResolver:
    """
    Резолвер физических действий. Чистый Python.
    НЕ имеет состояния. НЕ вызывает LLM.
    """
    
    def resolve_attack(
        self,
        attack_bonus: int = 0,
        target_ac: int = 10,
        damage_formula: str = "1d6",
        damage_type: DamageType = DamageType.BLUDGEONING,
        advantage: bool = False,
        disadvantage: bool = False,
        attacker_id: str = "",
    ) -> PhysicalOutcome:
        """
        Разрешает атаку: бросок попадания + бросок урона.
        
        Args:
            attack_bonus: Бонус атаки (ability + proficiency)
            target_ac: Класс брони цели
            damage_formula: Формула урона ("1d6+2")
            damage_type: Тип урона
            advantage/disadvantage: Модификаторы броска
            attacker_id: Кто атакует
            
        Returns:
            PhysicalOutcome с hit/miss/damage/critical
        """
        # Бросок попадания
        if advantage and disadvantage:
            # Нейтрализуют друг друга
            roll = _roll_d20()
        elif advantage:
            roll = max(_roll_d20(), _roll_d20())
        elif disadvantage:
            roll = min(_roll_d20(), _roll_d20())
        else:
            roll = _roll_d20()
        
        total_attack = roll + attack_bonus
        
        # Natural 1 = автоматический промах
        if _NATURAL_1_FUMBLE and roll == 1:
            return PhysicalOutcome(
                hit=False,
                damage=0,
                damage_type=damage_type,
                critical=False,
                attacker_id=attacker_id,
            )
        
        # Natural 20 = автоматическое попадание + крит
        critical = roll >= _CRITICAL_THRESHOLD
        hit = critical or (total_attack >= target_ac)
        
        # Бросок урона (только при попадании)
        damage = _roll_damage(damage_formula, critical) if hit else 0
        
        # Фаза R7: Градиентная боевка — OutcomeBand вместо бинарного hit/miss
        return OutcomeResult.from_physical(
            outcome=PhysicalOutcome(
                hit=hit,
                damage=damage,
                damage_type=damage_type,
                critical=critical,
                attacker_id=attacker_id,
            ),
            roll=roll,
            target_ac=target_ac,
        )


    def resolve_grapple(
        self,
        attacker_strength: int = 10,
        target_strength: int = 10,
        attacker_id: str = "",
    ) -> PhysicalOutcome:
        """
        Разрешает захват: contested check (STR vs STR).
        
        Returns:
            PhysicalOutcome с hit=успех захвата, damage=0
        """
        roll_attacker = _roll_d20() + _ability_modifier(attacker_strength)
        roll_target = _roll_d20() + _ability_modifier(target_strength)
        
        return PhysicalOutcome(
            hit=roll_attacker > roll_target,
            damage=0,
            damage_type=DamageType.BLUDGEONING,
            critical=False,
            attacker_id=attacker_id,
        )
    
    def resolve_item_damage(
        self,
        item_hp: int,
        damage: int,
    ) -> bool:
        """
        Проверяет повреждение предмета (щит, броня).
        Returns True если предмет сломан.
        """
        return item_hp - damage <= 0


def _ability_modifier(score: int) -> int:
    """D&D формула: (score - 10) // 2"""
    return (score - 10) // 2