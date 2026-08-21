# -*- coding: utf-8 -*-
"""
Combat Math Engine — D&D 5e / 2024
backend/app/services/game/combat_math.py

Принцип: Python считает → LLM рассказывает.
Все броски логируются (честность системы).
LLM получает build_combat_context() и только нарративит.
"""

import json
import random
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from app.core.clock import get_clock

# ──────────────────────────────────────────────────────────────────────────────
# Логирование
# ──────────────────────────────────────────────────────────────────────────────

_LOG_DIR = Path("data/logs")
_LOG_DIR.mkdir(parents=True, exist_ok=True)
_COMBAT_LOG = _LOG_DIR / "combat_log.jsonl"


def _log_roll(description: str, rolls: Any, total: int, context: Dict = None) -> None:
    entry = {
        "ts": get_clock().now().isoformat(timespec="seconds"),
        "event": "roll",
        "desc": description,
        "rolls": rolls if isinstance(rolls, list) else [rolls],
        "total": total,
        **(context or {}),
    }
    with open(_COMBAT_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _log_event(event: str, data: Dict) -> None:
    entry = {"ts": get_clock().now().isoformat(timespec="seconds"), "event": event, **data}
    with open(_COMBAT_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


# ──────────────────────────────────────────────────────────────────────────────
# 1. Броски кубиков
# ──────────────────────────────────────────────────────────────────────────────


def roll(n: int, sides: int, rng: Optional[random.Random] = None) -> Tuple[List[int], int]:
    """Бросить NdM. Возвращает (список бросков, сумма)."""
    _rng = rng or random
    results = [_rng.randint(1, sides) for _ in range(n)]
    total = sum(results)
    _log_roll(f"{n}d{sides}", results, total)
    return results, total


def roll_advantage(sides: int = 20, rng: Optional[random.Random] = None) -> Tuple[int, int, int]:
    """Бросок с преимуществом. Возвращает (r1, r2, max)."""
    _rng = rng or random
    r1, r2 = _rng.randint(1, sides), _rng.randint(1, sides)
    result = max(r1, r2)
    _log_roll(f"advantage d{sides}", [r1, r2], result)
    return r1, r2, result


def roll_disadvantage(sides: int = 20, rng: Optional[random.Random] = None) -> Tuple[int, int, int]:
    """Бросок с помехой. Возвращает (r1, r2, min)."""
    _rng = rng or random
    r1, r2 = _rng.randint(1, sides), _rng.randint(1, sides)
    result = min(r1, r2)
    _log_roll(f"disadvantage d{sides}", [r1, r2], result)
    return r1, r2, result


def parse_dice(dice_str: str) -> Tuple[int, int, int]:
    """Парсит строку '2d6+3' → (кол-во, грани, бонус)."""
    s = dice_str.replace(" ", "").lower()
    bonus = 0
    if "+" in s:
        parts = s.split("+", 1)
        s = parts[0]
        bonus = int(parts[1])
    elif "-" in s and "d" in s:
        idx = s.rindex("-")
        bonus = -int(s[idx + 1 :])
        s = s[:idx]
    if "d" in s:
        n, sides = map(int, s.split("d"))
    else:
        n, sides = 0, 0
    return n, sides, bonus


# ──────────────────────────────────────────────────────────────────────────────
# 2. Модификаторы характеристик
# ──────────────────────────────────────────────────────────────────────────────


def ability_modifier(score: int) -> int:
    return (score - 10) // 2


def proficiency_bonus(level: int) -> int:
    return 2 + (level - 1) // 4


# ──────────────────────────────────────────────────────────────────────────────
# 3. Условия боя (environment)
# ──────────────────────────────────────────────────────────────────────────────

ENVIRONMENT_MODIFIERS: Dict[str, int] = {
    # Освещение
    "темнота": -5,  # disadvantage на атаки
    "тусклый_свет": -2,
    "яркий_свет": 0,
    # Местность
    "возвышение": +2,  # атакующий выше цели
    "скользкий_пол": -2,
    "тесное_пространство": -3,
    # Стихии
    "огонь_рядом": -1,
    "ливень": -2,
    "сильный_ветер": -3,  # дальнобойное
    # Тактика
    "фланг": +2,  # союзник с другой стороны
    "укрытие_половинное": -2,
    "укрытие_трёхчетвертное": -5,
}


def get_environment_bonus(conditions: List[str]) -> int:
    """Суммирует модификаторы от условий окружения."""
    total = 0
    for c in conditions:
        total += ENVIRONMENT_MODIFIERS.get(c.lower(), 0)
    return total


# ──────────────────────────────────────────────────────────────────────────────
# 4. Результат атаки
# ──────────────────────────────────────────────────────────────────────────────


class AttackResult:
    def __init__(
        self,
        d20: int,
        attack_total: int,
        hit: bool,
        critical: bool,
        fumble: bool,
        damage: int,
        breakdown: str,
        target_ac: int,
    ):
        self.d20 = d20
        self.attack_total = attack_total
        self.hit = hit
        self.critical = critical
        self.fumble = fumble  # d20=1
        self.damage = damage
        self.breakdown = breakdown
        self.target_ac = target_ac

    def to_dict(self) -> Dict:
        return {
            "d20": self.d20,
            "attack_total": self.attack_total,
            "hit": self.hit,
            "critical": self.critical,
            "fumble": self.fumble,
            "damage": self.damage,
            "breakdown": self.breakdown,
            "target_ac": self.target_ac,
        }


def attack_roll(
    attacker: Dict,
    target: Dict,
    advantage: bool = False,
    disadvantage: bool = False,
    env_conditions: List[str] = None,
    rng: Optional[random.Random] = None,
) -> AttackResult:
    """
    Полный бросок атаки D&D 5e/2024.

    attacker и target — словари из characters.json / major_npcs.json.
    """
    _rng = rng or random
    weapon = attacker.get("equipped_weapon", {})
    ability = weapon.get("ability", "strength")
    abilities = attacker.get("abilities", {})
    mod = ability_modifier(abilities.get(ability, 10))
    level = attacker.get("level", 1)
    prof = proficiency_bonus(level) if weapon.get("proficient", True) else 0
    env_bonus = get_environment_bonus(env_conditions or [])

    # Бросок d20
    if advantage and not disadvantage:
        r1, r2, d20 = roll_advantage(rng=_rng)
        roll_desc = f"adv({r1},{r2})→{d20}"
    elif disadvantage and not advantage:
        r1, r2, d20 = roll_disadvantage(rng=_rng)
        roll_desc = f"dis({r1},{r2})→{d20}"
    else:
        d20 = _rng.randint(1, 20)
        roll_desc = str(d20)
        _log_roll("attack d20", [d20], d20)

    total_attack = d20 + mod + prof + env_bonus
    ac = target.get("ac", 10)

    fumble = d20 == 1
    critical = d20 == 20
    hit = (not fumble) and (critical or total_attack >= ac)

    # Урон
    damage = 0
    dmg_breakdown = "промах"
    if hit:
        dmg_dice = weapon.get("damage", "1d6")
        dmg_data = damage_roll(dmg_dice, mod, critical=critical, rng=_rng)
        damage = max(0, dmg_data["total"])
        dmg_breakdown = dmg_data["breakdown"]

    breakdown = (
        f"d20={roll_desc} + {ability}({mod:+}) + prof({prof:+}) + env({env_bonus:+}) "
        f"= {total_attack} vs AC{ac} → {'КРИТ!' if critical else ('ПРОВАЛ!' if fumble else ('попадание' if hit else 'промах'))} | "
        f"урон: {dmg_breakdown}"
    )

    result = AttackResult(
        d20, total_attack, hit, critical, fumble, damage, breakdown, ac
    )
    _log_event("attack", result.to_dict())
    return result


# ──────────────────────────────────────────────────────────────────────────────
# 5. Урон
# ──────────────────────────────────────────────────────────────────────────────


def damage_roll(weapon_dice: str, ability_mod: int, critical: bool = False, rng: Optional[random.Random] = None) -> Dict:
    """
    Бросок урона.
    При критическом — удваиваются кубики (не бонус).
    """
    num, sides, bonus = parse_dice(weapon_dice)
    dice_count = num * 2 if critical else num
    results, dice_total = roll(dice_count, sides, rng=rng) if dice_count > 0 else ([], 0)
    total = dice_total + ability_mod + bonus

    breakdown = (
        f"{'КРИТ! ' if critical else ''}"
        f"{dice_count}d{sides}={results} + mod({ability_mod:+}) + bonus({bonus:+}) = {total}"
    )
    return {
        "total": total,
        "breakdown": breakdown,
        "critical": critical,
        "rolls": results,
    }


# ──────────────────────────────────────────────────────────────────────────────
# 6. Инициатива
# ──────────────────────────────────────────────────────────────────────────────


def roll_initiative(character: Dict, rng: Optional[random.Random] = None) -> int:
    _rng = rng or random
    dex_mod = ability_modifier(character.get("abilities", {}).get("dexterity", 10))
    d20 = _rng.randint(1, 20)
    total = d20 + dex_mod
    _log_roll("initiative", [d20], total, {"character": character.get("name", "?")})
    return total


def sort_initiative(combatants: List[Dict], rng: Optional[random.Random] = None) -> List[Dict]:
    """Сортировка по инициативе. Игроки идут раньше при равенстве."""
    for c in combatants:
        if "initiative" not in c:
            c["initiative"] = roll_initiative(c, rng=rng)
    return sorted(
        combatants,
        key=lambda c: (-c["initiative"], 0 if c.get("type") == "player" else 1),
    )


# ──────────────────────────────────────────────────────────────────────────────
# 7. HP и состояния
# ──────────────────────────────────────────────────────────────────────────────


def apply_damage(target: Dict, damage: int) -> Dict:
    """Применяет урон. Возвращает изменения."""
    # BUG-PERC-005 FIX: Пишем HP в body_state["current_hp"] (SSOT, ADR-HP-UNIFICATION)
    body = target.setdefault("body_state", {})
    before = body.get("current_hp", target.get("hp", 0))  # Fallback на legacy hp для старых сейвов
    body["current_hp"] = max(0, before - damage)
    
    if body["current_hp"] <= 0:
        # ADR-123: life_status — единственный источник истины о смерти
        body["life_status"] = "DEAD"
        target["status"] = (
            "dead" if target.get("tier") in ("minor", "mass") else "incapacitated"
        )
        
    _log_event(
        "damage_applied",
        {
            "target": target.get("name", "?"),
            "damage": damage,
            "hp_before": before,
            "hp_after": body["current_hp"],
            "status": target.get("status", "alive"),
        },
    )
    return {
        "hp_before": before,
        "hp_after": body["current_hp"],
        "status": target.get("status", "alive"),
    }


def apply_healing(target: Dict, amount: int) -> Dict:
    # BUG-PERC-006 FIX: Запрет воскрешения мёртвых (DEAD → ALIVE запрещён, ADR-127)
    body = target.setdefault("body_state", {})
    if body.get("life_status") == "DEAD":
        import logging
        logging.getLogger(__name__).warning(
            f"[COMBAT] apply_healing skipped for DEAD npc={target.get('id', target.get('name', '?'))}"
        )
        return {"hp_before": body.get("current_hp", 0), "hp_after": body.get("current_hp", 0)}
        
    max_hp = body.get("max_hp", target.get("max_hp", body.get("current_hp", 0)))
    before = body.get("current_hp", target.get("hp", 0))
    body["current_hp"] = min(max_hp, before + amount)
    
    if body["current_hp"] > 0:
        target["status"] = "alive"
        
    _log_event(
        "healing_applied",
        {
            "target": target.get("name", "?"),
            "healed": amount,
            "hp_before": before,
            "hp_after": body["current_hp"],
        },
    )
    return {"hp_before": before, "hp_after": body["current_hp"]}


# ──────────────────────────────────────────────────────────────────────────────
# 8. Спасброски и проверки навыков
# ──────────────────────────────────────────────────────────────────────────────

SKILL_TO_ABILITY: Dict[str, str] = {
    "атлетика": "strength",
    "акробатика": "dexterity",
    "ловкость_рук": "dexterity",
    "скрытность": "dexterity",
    "магия": "intelligence",
    "история": "intelligence",
    "природа": "intelligence",
    "религия": "intelligence",
    "расследование": "intelligence",
    "проницательность": "wisdom",
    "медицина": "wisdom",
    "выживание": "wisdom",
    "восприятие": "wisdom",
    "уход_за_животными": "wisdom",
    "убеждение": "charisma",
    "обман": "charisma",
    "запугивание": "charisma",
    "выступление": "charisma",
}


def skill_check(character: Dict, skill: str, dc: int, rng: Optional[random.Random] = None) -> Dict:
    """Проверка навыка. Возвращает результат."""
    _rng = rng or random
    ability = SKILL_TO_ABILITY.get(skill.lower(), "strength")
    mod = ability_modifier(character.get("abilities", {}).get(ability, 10))
    has_proficiency = skill.lower() in [
        s.lower() for s in character.get("proficiencies", [])
    ]
    prof = proficiency_bonus(character.get("level", 1)) if has_proficiency else 0

    d20 = _rng.randint(1, 20)
    total = d20 + mod + prof
    success = total >= dc
    _log_roll(f"skill_check {skill} DC{dc}", [d20], total)

    return {
        "skill": skill,
        "ability": ability,
        "d20": d20,
        "mod": mod,
        "prof": prof,
        "total": total,
        "dc": dc,
        "success": success,
        "breakdown": f"d20({d20}) + {ability}({mod:+}) + prof({prof:+}) = {total} vs DC{dc}",
    }


def saving_throw(character: Dict, ability: str, dc: int, rng: Optional[random.Random] = None) -> Dict:
    """Спасбросок по характеристике."""
    _rng = rng or random
    mod = ability_modifier(character.get("abilities", {}).get(ability, 10))
    save_prof = ability in character.get("saving_throw_proficiencies", [])
    prof = proficiency_bonus(character.get("level", 1)) if save_prof else 0

    d20 = _rng.randint(1, 20)
    total = d20 + mod + prof
    success = total >= dc
    _log_roll(f"saving_throw {ability} DC{dc}", [d20], total)

    return {
        "ability": ability,
        "d20": d20,
        "total": total,
        "dc": dc,
        "success": success,
        "breakdown": f"d20({d20}) + {ability}({mod:+}) + prof({prof:+}) = {total} vs DC{dc}",
    }


# ──────────────────────────────────────────────────────────────────────────────
# 9. Смерть и спасброски от смерти
# ──────────────────────────────────────────────────────────────────────────────


def death_saving_throw(character: Dict, rng: Optional[random.Random] = None) -> Dict:
    """
    Спасбросок от смерти (D&D 5e).
    3 успеха → стабилизация. 3 провала → смерть. 20 → 1 HP.
    """
    _rng = rng or random
    d20 = _rng.randint(1, 20)
    _log_roll("death_save", [d20], d20)

    if d20 == 20:
        return {"d20": d20, "result": "miracle", "hp": 1, "note": "Чудо! Встаёт с 1 HP"}
    elif d20 == 1:
        return {"d20": d20, "result": "double_failure", "failures": 2}
    elif d20 >= 10:
        return {"d20": d20, "result": "success"}
    else:
        return {"d20": d20, "result": "failure"}


# ──────────────────────────────────────────────────────────────────────────────
# 10. Боевая сетка (позиции)
# ──────────────────────────────────────────────────────────────────────────────


class CombatGrid:
    """
    Простая 2D сетка для боя.
    Позволяет DM говорить 'гоблин зашёл тебе за спину'.
    """

    def __init__(self):
        self.positions: Dict[str, Tuple[int, int]] = {}

    def place(self, name: str, x: int, y: int) -> None:
        self.positions[name] = (x, y)

    def distance(self, a: str, b: str) -> float:
        """Расстояние в клетках (1 клетка = 5 футов)."""
        if a not in self.positions or b not in self.positions:
            return 999.0
        ax, ay = self.positions[a]
        bx, by = self.positions[b]
        return max(abs(ax - bx), abs(ay - by))  # Chebyshev distance (D&D правило)

    def is_flanking(self, attacker: str, ally: str, target: str) -> bool:
        """Фланкирование: союзник с противоположной стороны от атакующего."""
        if not all(k in self.positions for k in [attacker, ally, target]):
            return False
        tx, ty = self.positions[target]
        ax, ay = self.positions[attacker]
        lx, ly = self.positions[ally]
        # Оппозиционный: сумма векторов ≈ 0
        return (ax + lx - 2 * tx) ** 2 + (ay + ly - 2 * ty) ** 2 < 4

    def is_adjacent(self, a: str, b: str) -> bool:
        return self.distance(a, b) <= 1

    def get_neighbors(self, target: str, radius: int = 1) -> List[str]:
        """Все существа в радиусе клеток."""
        return [
            name
            for name in self.positions
            if name != target and self.distance(target, name) <= radius
        ]

    def to_dict(self) -> Dict:
        return {name: {"x": x, "y": y} for name, (x, y) in self.positions.items()}


# ──────────────────────────────────────────────────────────────────────────────
# 11. Контекст для DM агента
# ──────────────────────────────────────────────────────────────────────────────


def build_combat_context(
    attack: AttackResult,
    target: Dict,
    grid: CombatGrid = None,
    conditions: List[str] = None,
) -> Dict:
    """
    Готовый контекст — DM агент получает это и только нарративит.
    Никаких вычислений в LLM.
    """
    return {
        "attack_roll": attack.attack_total,
        "d20": attack.d20,
        "hit": attack.hit,
        "critical": attack.critical,
        "fumble": attack.fumble,
        "damage": attack.damage,
        "target_hp_before": target.get("hp", 0) + attack.damage,
        "target_hp_after": target.get("hp", 0),
        "target_status": target.get("status", "alive"),
        "breakdown": attack.breakdown,
        "env_conditions": conditions or [],
        "grid": grid.to_dict() if grid else {},
    }
