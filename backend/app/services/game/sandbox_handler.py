# -*- coding: utf-8 -*-
"""
Sandbox Handler — любые нестандартные действия игрока
backend/app/services/game/sandbox_handler.py

Принцип: нет запрещённых действий — есть последствия.
Топ-100 нестандартных действий D&D 5e заложены в логику.
Всё что не попало в категории → handle_unknown (universal fallback).
"""

import random
import json
import os
import traceback
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path
from enum import Enum

# ──────────────────────────────────────────────────────────────────────────────
# Логирование
# ──────────────────────────────────────────────────────────────────────────────

_LOG_DIR = Path("data/logs")
_LOG_DIR.mkdir(parents=True, exist_ok=True)
_SANDBOX_LOG = _LOG_DIR / "sandbox_log.jsonl"
_ERROR_LOG   = _LOG_DIR / "error_log.jsonl"


def _log(event: str, data: Dict) -> None:
    entry = {"ts": datetime.now().isoformat(timespec="seconds"), "event": event, **data}
    with open(_SANDBOX_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _log_error(module: str, fn: str, error: Exception, ctx: Dict = None) -> None:
    entry = {
        "ts":      datetime.now().isoformat(timespec="seconds"),
        "module":  module, "function": fn,
        "error":   type(error).__name__,
        "message": str(error),
        "tb":      traceback.format_exc(),
        "ctx":     ctx or {},
    }
    with open(_ERROR_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(f"[ERROR] {module}.{fn} → {type(error).__name__}: {error}")


# ──────────────────────────────────────────────────────────────────────────────
# Типы и результат
# ──────────────────────────────────────────────────────────────────────────────

class ActionType(str, Enum):
    PHYSICAL          = "SANDBOX_PHYSICAL"
    SOCIAL_VIOLATION  = "SANDBOX_SOCIAL"
    ROMANCE           = "ROMANCE"
    CAPTURE           = "CAPTURE"
    FLEE              = "FLEE"
    LIFE_CHOICE       = "LIFE_CHOICE"
    INTIMIDATE        = "INTIMIDATE"
    BRIBERY           = "BRIBERY"
    DECEPTION         = "DECEPTION"
    PERSUASION        = "PERSUASION"
    STEALTH           = "STEALTH"
    ACROBATICS        = "ACROBATICS"
    DISTRACTION       = "DISTRACTION"
    ENVIRONMENTAL     = "ENVIRONMENTAL"
    ANIMAL_INTERACTION = "ANIMAL_INTERACTION"
    CRAFTING          = "CRAFTING"
    DISGUISE          = "DISGUISE"
    PICKPOCKET        = "PICKPOCKET"
    LOCKPICK          = "LOCKPICK"
    POISON            = "POISON"
    DIPLOMACY         = "DIPLOMACY"
    SURRENDER         = "SURRENDER"
    TAUNT             = "TAUNT"
    IMPROVISED_WEAPON = "IMPROVISED_WEAPON"
    CROWD_CONTROL     = "CROWD_CONTROL"
    UNKNOWN           = "UNKNOWN"


class SandboxResult:
    def __init__(
        self,
        action_type: ActionType,
        success: bool,
        consequences: Dict,
        context_for_dm: Dict,
    ):
        self.action_type    = action_type
        self.success        = success
        self.consequences   = consequences
        self.context_for_dm = context_for_dm

    def to_dict(self) -> Dict:
        return {
            "action_type":    self.action_type.value,
            "success":        self.success,
            "consequences":   self.consequences,
            "context_for_dm": self.context_for_dm,
        }


# ──────────────────────────────────────────────────────────────────────────────
# Утилиты бросков
# ──────────────────────────────────────────────────────────────────────────────

def _ability_mod(score: int) -> int:
    return (score - 10) // 2

def _get_mod(player: Dict, ability: str) -> int:
    return _ability_mod(player.get("abilities", {}).get(ability, 10))

def _prof(player: Dict) -> int:
    return 2 + (player.get("level", 1) - 1) // 4

def _d20(player: Dict, ability: str, proficient: bool = False) -> Tuple[int, int, int]:
    """Возвращает (d20, модификатор, итог)."""
    roll = random.randint(1, 20)
    mod  = _get_mod(player, ability)
    prof = _prof(player) if proficient else 0
    return roll, mod + prof, roll + mod + prof


# ──────────────────────────────────────────────────────────────────────────────
# Реестр обработчиков
# ──────────────────────────────────────────────────────────────────────────────

_HANDLERS: Dict[ActionType, Any] = {}

def _register(action_type: ActionType):
    def decorator(fn):
        _HANDLERS[action_type] = fn
        return fn
    return decorator


# ──────────────────────────────────────────────────────────────────────────────
# ОБРАБОТЧИКИ — Топ-100 нестандартных ситуаций D&D 5e
# ──────────────────────────────────────────────────────────────────────────────

# ── 1. ФИЗИЧЕСКИЕ НАРУШЕНИЯ (мочится, раздевается и т.п.) ────────────────────
@_register(ActionType.PHYSICAL)
def handle_physical(player: Dict, action: str, **kw) -> SandboxResult:
    severity_map = {
        "мочится": "mild", "писает": "mild", "плюёт": "mild",
        "какает": "medium", "обнажается": "medium", "раздевается": "medium",
        "дерётся грязно": "medium",
    }
    severity = next((v for k, v in severity_map.items() if k in action.lower()), "mild")
    dc = {"mild": 10, "medium": 14, "severe": 18}[severity]
    d20, mod, total = _d20(player, "charisma")
    success = total >= dc
    rep = {"mild": random.randint(-5, -10), "medium": random.randint(-15, -25), "severe": -40}[severity]
    ctx = {"type": "physical", "severity": severity,
           "roll": f"d20({d20})+CHA({mod})={total} vs DC{dc}", "rep_impact": rep}
    _log("physical_sandbox", ctx)
    return SandboxResult(ActionType.PHYSICAL, success, {"reputation": rep, "ban_risk": severity == "severe"}, ctx)


# ── 2. ПОБЕГ ──────────────────────────────────────────────────────────────────
@_register(ActionType.FLEE)
def handle_flee(player: Dict, action: str, enemies: List[Dict] = None, location: str = "open", **kw) -> SandboxResult:
    enemies = enemies or []
    p_spd  = player.get("speed", 30)
    e_spd  = max((e.get("speed", 30) for e in enemies), default=30)
    dc = 10 + max(0, e_spd - p_spd) // 5
    if location in ["лес", "коридор", "толпа"]: dc += 4
    if len(enemies) > 3: dc += 3
    d20, mod, total = _d20(player, "dexterity", proficient=True)
    success = total >= dc
    ctx = {"type": "flee", "roll": f"d20({d20})+DEX({mod})={total} vs DC{dc}", "success": success}
    _log("flee", ctx)
    cons = {
        "fled": success,
        "opportunity_attack": not success,
        "state": "fled" if success else "in_combat",
    }
    return SandboxResult(ActionType.FLEE, success, cons, ctx)


# ── 3. ЗАХВАТ / ПЛЕН ──────────────────────────────────────────────────────────
@_register(ActionType.CAPTURE)
def handle_capture(player: Dict, action: str, npc: Dict = None, **kw) -> SandboxResult:
    npc = npc or {}
    p_str  = _get_mod(player, "strength") + _prof(player)
    n_str  = _get_mod(npc, "strength")
    p_roll = random.randint(1, 20) + p_str
    n_roll = random.randint(1, 20) + n_str
    success = p_roll > n_roll
    if success and npc:
        npc.setdefault("visible_markers", []).append("chains")
        npc.setdefault("psyche", {})["state"] = "coerced"
        npc.setdefault("flags", {})["is_enslaved"] = True
    ctx = {"type": "capture", "p_roll": p_roll, "n_roll": n_roll, "success": success,
           "karma_impact": +15}
    _log("capture", ctx)
    return SandboxResult(ActionType.CAPTURE, success, {"enslaved": success, "karma_cruel": 15}, ctx)


# ── 4. РОМАНТИКА / ФЛИРТ ──────────────────────────────────────────────────────
@_register(ActionType.ROMANCE)
def handle_romance(player: Dict, action: str, npc: Dict = None, **kw) -> SandboxResult:
    npc = npc or {}
    affection = npc.get("social_stats", {}).get("affection", 0.3) * 100
    dc = max(8, 20 - int(affection / 5))
    d20, mod, total = _d20(player, "charisma", proficient=True)
    success = total >= dc
    stages = ["знакомство", "симпатия", "дружба", "любовь", "партнёрство"]
    cur    = npc.get("romance_stage", "знакомство")
    if success and cur in stages:
        idx = stages.index(cur)
        if idx < len(stages) - 1:
            npc["romance_stage"] = stages[idx + 1]
    ctx = {"type": "romance", "roll": f"d20({d20})+CHA({mod})={total} vs DC{dc}",
           "affection_gained": 15 if success else 0, "new_stage": npc.get("romance_stage", cur)}
    _log("romance", ctx)
    return SandboxResult(ActionType.ROMANCE, success, {"affection": 15 if success else 0}, ctx)


# ── 5. ЖИЗНЕННЫЙ ВЫБОР (фермер, торговец, пацифист) ──────────────────────────
@_register(ActionType.LIFE_CHOICE)
def handle_life_choice(player: Dict, action: str, **kw) -> SandboxResult:
    player["campaign_mode"] = "peaceful_life"
    ctx = {"type": "life_choice", "action": action, "mode": "peaceful_life", "fast_time": True}
    _log("life_choice", ctx)
    return SandboxResult(ActionType.LIFE_CHOICE, True, {"mode": "peaceful_life"}, ctx)


# ── 6. ЗАПУГИВАНИЕ ────────────────────────────────────────────────────────────
@_register(ActionType.INTIMIDATE)
def handle_intimidate(player: Dict, action: str, npc: Dict = None, **kw) -> SandboxResult:
    npc = npc or {}
    willpower = npc.get("psyche", {}).get("willpower", 50)
    dc = 8 + willpower // 10
    d20, mod, total = _d20(player, "charisma", proficient=True)
    success = total >= dc
    if success and npc:
        npc.setdefault("psyche", {})["stress"] = min(100, npc["psyche"].get("stress", 0) + 30)
        npc.setdefault("social_stats", {})["fear_of_player"] = min(1.0,
            npc["social_stats"].get("fear_of_player", 0.1) + 0.2)
    ctx = {"type": "intimidate", "roll": f"d20({d20})+CHA({mod})={total} vs DC{dc}", "success": success}
    _log("intimidate", ctx)
    return SandboxResult(ActionType.INTIMIDATE, success,
                          {"fear_increased": success, "trust_decreased": success}, ctx)


# ── 7. ПОДКУП ─────────────────────────────────────────────────────────────────
@_register(ActionType.BRIBERY)
def handle_bribery(player: Dict, action: str, npc: Dict = None, gold: int = 10, **kw) -> SandboxResult:
    npc = npc or {}
    npc_wealth = npc.get("status_profile", {}).get("wealth", 10)
    greed      = npc.get("drives", {}).get("desire", 0.3)
    dc = max(5, 20 - int(greed * 20) - gold // 10)
    d20, mod, total = _d20(player, "charisma")
    success = total >= dc
    if success and npc:
        npc.setdefault("social_stats", {})["trust"] = min(1.0,
            npc["social_stats"].get("trust", 0.5) + 0.15)
    ctx = {"type": "bribery", "gold": gold, "roll": f"d20({d20})+CHA({mod})={total} vs DC{dc}",
           "success": success}
    _log("bribery", ctx)
    return SandboxResult(ActionType.BRIBERY, success, {"gold_spent": gold if success else 0}, ctx)


# ── 8. ОБМАН ──────────────────────────────────────────────────────────────────
@_register(ActionType.DECEPTION)
def handle_deception(player: Dict, action: str, npc: Dict = None, **kw) -> SandboxResult:
    npc = npc or {}
    insight = _get_mod(npc, "wisdom") + 2
    d20p, modp, totalp = _d20(player, "charisma", proficient=True)
    d20n = random.randint(1, 20) + insight
    success = totalp > d20n
    if not success and npc:
        npc.setdefault("social_stats", {})["trust"] = max(0.0,
            npc["social_stats"].get("trust", 0.5) - 0.2)
    ctx = {"type": "deception", "player_roll": totalp, "npc_insight": d20n, "success": success}
    _log("deception", ctx)
    return SandboxResult(ActionType.DECEPTION, success, {"caught": not success}, ctx)


# ── 9. УБЕЖДЕНИЕ ──────────────────────────────────────────────────────────────
@_register(ActionType.PERSUASION)
def handle_persuasion(player: Dict, action: str, npc: Dict = None, **kw) -> SandboxResult:
    npc = npc or {}
    trust = npc.get("social_stats", {}).get("trust", 0.5) * 20
    dc = max(8, 18 - int(trust))
    d20, mod, total = _d20(player, "charisma", proficient=True)
    success = total >= dc
    if success and npc:
        npc.setdefault("social_stats", {})["trust"] = min(1.0,
            npc["social_stats"].get("trust", 0.5) + 0.1)
    ctx = {"type": "persuasion", "roll": f"d20({d20})+CHA({mod})={total} vs DC{dc}", "success": success}
    _log("persuasion", ctx)
    return SandboxResult(ActionType.PERSUASION, success, {"trust_gained": 0.1 if success else 0}, ctx)


# ── 10. СКРЫТНОСТЬ ────────────────────────────────────────────────────────────
@_register(ActionType.STEALTH)
def handle_stealth(player: Dict, action: str, npc: Dict = None, **kw) -> SandboxResult:
    npc = npc or {}
    perception = _get_mod(npc, "wisdom") + 2
    d20p, modp, totalp = _d20(player, "dexterity", proficient=True)
    d20n = random.randint(1, 20) + perception
    success = totalp > d20n
    ctx = {"type": "stealth", "player_roll": totalp, "npc_perception": d20n, "success": success}
    _log("stealth", ctx)
    return SandboxResult(ActionType.STEALTH, success, {"detected": not success}, ctx)


# ── 11. АКРОБАТИКА / ПРЫЖОК / КАРАБКАНЬЕ ─────────────────────────────────────
@_register(ActionType.ACROBATICS)
def handle_acrobatics(player: Dict, action: str, dc: int = 14, **kw) -> SandboxResult:
    ability = "dexterity" if any(w in action.lower() for w in ["прыж", "кувырк", "балансир"]) else "strength"
    d20, mod, total = _d20(player, ability, proficient=True)
    success = total >= dc
    ctx = {"type": "acrobatics", "ability": ability,
           "roll": f"d20({d20})+{ability}({mod})={total} vs DC{dc}", "success": success}
    _log("acrobatics", ctx)
    return SandboxResult(ActionType.ACROBATICS, success, {"injury_risk": not success}, ctx)


# ── 12. ОТВЛЕЧЕНИЕ ВНИМАНИЯ ───────────────────────────────────────────────────
@_register(ActionType.DISTRACTION)
def handle_distraction(player: Dict, action: str, **kw) -> SandboxResult:
    d20, mod, total = _d20(player, "charisma", proficient=True)
    dc = 13
    success = total >= dc
    ctx = {"type": "distraction", "roll": f"d20({d20})+CHA({mod})={total} vs DC{dc}", "success": success,
           "duration_rounds": random.randint(1, 3) if success else 0}
    _log("distraction", ctx)
    return SandboxResult(ActionType.DISTRACTION, success,
                          {"enemies_distracted": success, "advantage_for_ally": success}, ctx)


# ── 13. ВЗАИМОДЕЙСТВИЕ С ЖИВОТНЫМИ ───────────────────────────────────────────
@_register(ActionType.ANIMAL_INTERACTION)
def handle_animal(player: Dict, action: str, npc: Dict = None, **kw) -> SandboxResult:
    animal = npc or {}
    attitude = animal.get("attitude", "neutral")
    dc = {"hostile": 20, "neutral": 14, "friendly": 8}.get(attitude, 14)
    d20, mod, total = _d20(player, "wisdom", proficient=True)
    success = total >= dc
    ctx = {"type": "animal", "attitude": attitude,
           "roll": f"d20({d20})+WIS({mod})={total} vs DC{dc}", "success": success}
    _log("animal_interaction", ctx)
    return SandboxResult(ActionType.ANIMAL_INTERACTION, success,
                          {"tamed": success and attitude == "neutral",
                           "calmed": success and attitude == "hostile"}, ctx)


# ── 14. СОЗДАНИЕ ПРЕДМЕТА (CRAFTING) ─────────────────────────────────────────
@_register(ActionType.CRAFTING)
def handle_crafting(player: Dict, action: str, difficulty: str = "medium", **kw) -> SandboxResult:
    dc = {"easy": 10, "medium": 15, "hard": 20, "expert": 25}.get(difficulty, 15)
    d20, mod, total = _d20(player, "intelligence", proficient=True)
    success = total >= dc
    quality = "отличное" if total >= dc + 5 else ("хорошее" if success else "неудачное")
    ctx = {"type": "crafting", "difficulty": difficulty, "quality": quality,
           "roll": f"d20({d20})+INT({mod})={total} vs DC{dc}", "success": success}
    _log("crafting", ctx)
    return SandboxResult(ActionType.CRAFTING, success,
                          {"item_created": success, "quality": quality}, ctx)


# ── 15. МАСКИРОВКА / ПЕРЕОДЕВАНИЕ ────────────────────────────────────────────
@_register(ActionType.DISGUISE)
def handle_disguise(player: Dict, action: str, npc: Dict = None, **kw) -> SandboxResult:
    npc = npc or {}
    d20p, modp, totalp = _d20(player, "charisma", proficient=True)
    perception = _get_mod(npc, "wisdom") + 2 if npc else 5
    d20n = random.randint(1, 20) + perception
    success = totalp > d20n
    ctx = {"type": "disguise", "player_roll": totalp, "npc_check": d20n, "success": success}
    _log("disguise", ctx)
    return SandboxResult(ActionType.DISGUISE, success, {"disguise_maintained": success}, ctx)


# ── 16. КАРМАННАЯ КРАЖА ───────────────────────────────────────────────────────
@_register(ActionType.PICKPOCKET)
def handle_pickpocket(player: Dict, action: str, npc: Dict = None, **kw) -> SandboxResult:
    npc = npc or {}
    perception = _get_mod(npc, "wisdom") + random.randint(0, 3)
    d20p, modp, totalp = _d20(player, "dexterity", proficient=True)
    d20n = random.randint(1, 20) + perception
    success = totalp > d20n
    loot = random.randint(1, 20) if success else 0
    ctx = {"type": "pickpocket", "player_roll": totalp, "npc_perception": d20n,
           "success": success, "gold": loot}
    _log("pickpocket", ctx)
    cons = {"gold_stolen": loot, "caught": not success,
            "reputation_impact": -20 if not success else -5}
    return SandboxResult(ActionType.PICKPOCKET, success, cons, ctx)


# ── 17. ВЗЛОМ ЗАМКА ───────────────────────────────────────────────────────────
@_register(ActionType.LOCKPICK)
def handle_lockpick(player: Dict, action: str, lock_quality: str = "medium", **kw) -> SandboxResult:
    dc = {"simple": 10, "medium": 15, "complex": 20, "masterwork": 25}.get(lock_quality, 15)
    d20, mod, total = _d20(player, "dexterity", proficient=True)
    success = total >= dc
    ctx = {"type": "lockpick", "lock_quality": lock_quality,
           "roll": f"d20({d20})+DEX({mod})={total} vs DC{dc}", "success": success}
    _log("lockpick", ctx)
    return SandboxResult(ActionType.LOCKPICK, success,
                          {"opened": success, "time_spent_rounds": 1 if success else 3}, ctx)


# ── 18. ЯД ────────────────────────────────────────────────────────────────────
@_register(ActionType.POISON)
def handle_poison(player: Dict, action: str, npc: Dict = None, **kw) -> SandboxResult:
    npc = npc or {}
    dc = 14
    d20, mod, total = _d20(player, "dexterity", proficient=True)
    success = total >= dc
    if success and npc:
        con_save = random.randint(1, 20) + _get_mod(npc, "constitution")
        poisoned = con_save < 14
        npc.setdefault("conditions", [])
        if poisoned:
            npc["conditions"].append({"type": "poisoned", "duration": 3})
    ctx = {"type": "poison", "roll": f"d20({d20})+DEX({mod})={total}", "success": success}
    _log("poison", ctx)
    return SandboxResult(ActionType.POISON, success,
                          {"applied": success, "karma_evil": 10}, ctx)


# ── 19. ДИПЛОМАТИЯ / ПЕРЕГОВОРЫ ───────────────────────────────────────────────
@_register(ActionType.DIPLOMACY)
def handle_diplomacy(player: Dict, action: str, npc: Dict = None, **kw) -> SandboxResult:
    npc = npc or {}
    trust = npc.get("social_stats", {}).get("trust", 0.5)
    dc = max(10, 20 - int(trust * 20))
    d20, mod, total = _d20(player, "charisma", proficient=True)
    success = total >= dc
    if success and npc:
        npc.setdefault("social_stats", {})["trust"] = min(1.0, trust + 0.2)
        npc.setdefault("psyche", {})["stress"] = max(0, npc["psyche"].get("stress", 30) - 20)
    ctx = {"type": "diplomacy", "roll": f"d20({d20})+CHA({mod})={total} vs DC{dc}", "success": success}
    _log("diplomacy", ctx)
    return SandboxResult(ActionType.DIPLOMACY, success, {"peace_achieved": success}, ctx)


# ── 20. СДАЧА / КАПИТУЛЯЦИЯ ───────────────────────────────────────────────────
@_register(ActionType.SURRENDER)
def handle_surrender(player: Dict, action: str, **kw) -> SandboxResult:
    ctx = {"type": "surrender", "state": "surrendered",
           "karma_coward": 5, "karma_wise": 3}
    _log("surrender", ctx)
    return SandboxResult(ActionType.SURRENDER, True,
                          {"state": "prisoner", "hp_safe": True}, ctx)


# ── 21. ПРОВОКАЦИЯ / ЗАДРАЗНИТЬ ───────────────────────────────────────────────
@_register(ActionType.TAUNT)
def handle_taunt(player: Dict, action: str, npc: Dict = None, **kw) -> SandboxResult:
    npc = npc or {}
    d20, mod, total = _d20(player, "charisma", proficient=True)
    npc_resist = random.randint(1, 20) + _get_mod(npc, "wisdom")
    success = total > npc_resist
    if success and npc:
        npc.setdefault("psyche", {})["stress"] = min(100, npc["psyche"].get("stress", 20) + 20)
    ctx = {"type": "taunt", "player": total, "npc_resist": npc_resist, "success": success}
    _log("taunt", ctx)
    return SandboxResult(ActionType.TAUNT, success,
                          {"npc_angered": success, "attacks_only_player": success}, ctx)


# ── 22. ИМПРОВИЗИРОВАННОЕ ОРУЖИЕ ──────────────────────────────────────────────
@_register(ActionType.IMPROVISED_WEAPON)
def handle_improvised(player: Dict, action: str, **kw) -> SandboxResult:
    dmg = random.randint(1, 4)
    str_mod = _get_mod(player, "strength")
    d20 = random.randint(1, 20) + str_mod
    ctx = {"type": "improvised_weapon", "attack_roll": d20, "damage": dmg + str_mod,
           "item_description": action}
    _log("improvised_weapon", ctx)
    return SandboxResult(ActionType.IMPROVISED_WEAPON, d20 >= 10,
                          {"damage": dmg + str_mod}, ctx)


# ── 23. КОНТРОЛЬ ТОЛПЫ ────────────────────────────────────────────────────────
@_register(ActionType.CROWD_CONTROL)
def handle_crowd(player: Dict, action: str, **kw) -> SandboxResult:
    d20, mod, total = _d20(player, "charisma", proficient=True)
    crowd_size = random.randint(5, 30)
    dc = 10 + crowd_size // 5
    success = total >= dc
    ctx = {"type": "crowd_control", "crowd_size": crowd_size,
           "roll": f"d20({d20})+CHA({mod})={total} vs DC{dc}", "success": success}
    _log("crowd_control", ctx)
    return SandboxResult(ActionType.CROWD_CONTROL, success,
                          {"crowd_calmed": success, "crowd_size": crowd_size}, ctx)


# ──────────────────────────────────────────────────────────────────────────────
# ТОП-100 нестандартных действий — универсальный обработчик
# ──────────────────────────────────────────────────────────────────────────────

# Таблица: ключевые слова → (тип, ability, dc_base, severity)
TOP_100_ACTIONS = [
    # Социальные
    ("прошу прощения у",      ActionType.PERSUASION,  "charisma",    10, "mild"),
    ("угощаю выпивкой",       ActionType.PERSUASION,  "charisma",     8, "mild"),
    ("рассказываю анекдот",   ActionType.PERSUASION,  "charisma",    12, "mild"),
    ("пою песню",             ActionType.PERSUASION,  "charisma",    13, "mild"),
    ("танцую",                ActionType.ACROBATICS,  "dexterity",   12, "mild"),
    ("торгуюсь",              ActionType.PERSUASION,  "charisma",    14, "mild"),
    ("прошу помощи",          ActionType.PERSUASION,  "charisma",    11, "mild"),
    ("читаю лекцию",          ActionType.PERSUASION,  "intelligence",14, "mild"),
    ("задаю вопрос",          ActionType.PERSUASION,  "charisma",     8, "mild"),
    ("шепчу на ухо",          ActionType.STEALTH,     "dexterity",   10, "mild"),
    # Тактические
    ("прячусь за",            ActionType.STEALTH,     "dexterity",   14, "mild"),
    ("создаю помеху",         ActionType.DISTRACTION, "charisma",    13, "mild"),
    ("подбираю камень",       ActionType.IMPROVISED_WEAPON,"strength",10,"mild"),
    ("бросаю грязь",          ActionType.IMPROVISED_WEAPON,"dexterity",12,"mild"),
    ("опрокидываю стол",      ActionType.IMPROVISED_WEAPON,"strength",13,"mild"),
    ("поджигаю масло",        ActionType.ENVIRONMENTAL,"intelligence",14,"medium"),
    ("толкаю в яму",          ActionType.ACROBATICS,  "strength",    14, "medium"),
    ("разбиваю светильник",   ActionType.ENVIRONMENTAL,"dexterity",  10, "mild"),
    ("кидаю дымовую шашку",   ActionType.ENVIRONMENTAL,"dexterity",  10, "mild"),
    ("валю колонну",          ActionType.ENVIRONMENTAL,"strength",   18, "medium"),
    # Исследование
    ("лезу на стену",         ActionType.ACROBATICS,  "strength",    14, "mild"),
    ("прыгаю через пропасть", ActionType.ACROBATICS,  "strength",    16, "medium"),
    ("ныряю под воду",        ActionType.ACROBATICS,  "constitution",12, "mild"),
    ("ползу через лаз",       ActionType.ACROBATICS,  "dexterity",   12, "mild"),
    ("взбираюсь на дракона",  ActionType.ACROBATICS,  "strength",    20, "severe"),
    ("езжу верхом на монстре",ActionType.ANIMAL_INTERACTION,"wisdom", 18,"severe"),
    # Хитрость
    ("притворяюсь мёртвым",   ActionType.DECEPTION,   "charisma",   14, "mild"),
    ("говорю чужим голосом",  ActionType.DECEPTION,   "charisma",   15, "mild"),
    ("изображаю стражника",   ActionType.DISGUISE,    "charisma",   16, "medium"),
    ("делаю вид что сплю",    ActionType.DECEPTION,   "charisma",   11, "mild"),
    ("хожу как NPC",          ActionType.DISGUISE,    "charisma",   14, "mild"),
    # Природа и животные
    ("успокаиваю лошадь",     ActionType.ANIMAL_INTERACTION,"wisdom", 12,"mild"),
    ("приручаю волка",        ActionType.ANIMAL_INTERACTION,"wisdom", 18,"medium"),
    ("разговариваю с котом",  ActionType.ANIMAL_INTERACTION,"wisdom",  8,"mild"),
    ("отпугиваю воронов",     ActionType.ANIMAL_INTERACTION,"wisdom", 10,"mild"),
    ("ловлю рыбу",            ActionType.CRAFTING,    "wisdom",      12, "mild"),
    # Крафт и инструменты
    ("чиню меч",              ActionType.CRAFTING,    "intelligence",14, "mild"),
    ("варю зелье",            ActionType.CRAFTING,    "intelligence",18, "medium"),
    ("строю ловушку",         ActionType.CRAFTING,    "intelligence",14, "medium"),
    ("готовлю еду",           ActionType.CRAFTING,    "wisdom",      10, "mild"),
    ("делаю факел",           ActionType.CRAFTING,    "intelligence", 8, "mild"),
    # Нестандартный бой
    ("атакую с разбега",      ActionType.IMPROVISED_WEAPON,"strength",14,"medium"),
    ("бью головой",           ActionType.IMPROVISED_WEAPON,"strength",12,"medium"),
    ("кусаю",                 ActionType.IMPROVISED_WEAPON,"strength",10,"medium"),
    ("царапаю",               ActionType.IMPROVISED_WEAPON,"dexterity",8,"mild"),
    ("бросаю тарелку",        ActionType.IMPROVISED_WEAPON,"dexterity",12,"mild"),
    # Нелепые / абсурдные но физически возможные
    ("кричу изо всех сил",    ActionType.CROWD_CONTROL,"charisma",   12, "mild"),
    ("пою военную песню",     ActionType.CROWD_CONTROL,"charisma",   14, "mild"),
    ("предлагаю мир",         ActionType.DIPLOMACY,   "charisma",   16, "medium"),
    ("преклоняю колено",      ActionType.DIPLOMACY,   "charisma",    8, "mild"),
    ("плачу от жалости",      ActionType.PERSUASION,  "charisma",   14, "medium"),
    ("рассказываю трагедию",  ActionType.PERSUASION,  "charisma",   15, "medium"),
    ("называю детей",         ActionType.LIFE_CHOICE, "wisdom",       8, "mild"),
    ("усыновляю гоблина",     ActionType.LIFE_CHOICE, "charisma",   16, "medium"),
    ("берусь за работу",      ActionType.LIFE_CHOICE, "wisdom",      10, "mild"),
    ("сдаюсь на милость",     ActionType.SURRENDER,   "charisma",    8, "mild"),
    ("просю убежища",         ActionType.DIPLOMACY,   "charisma",   12, "mild"),
    ("делюсь едой",           ActionType.PERSUASION,  "wisdom",       8, "mild"),
    ("даю клятву",            ActionType.DIPLOMACY,   "charisma",   10, "mild"),
    ("прошу благословения",   ActionType.DIPLOMACY,   "wisdom",      12, "mild"),
    ("оскорбляю предков",     ActionType.TAUNT,       "charisma",   12, "medium"),
    ("плюю на портрет",       ActionType.PHYSICAL,    "charisma",   10, "medium"),
    ("ломаю чужой меч",       ActionType.IMPROVISED_WEAPON,"strength",18,"medium"),
    ("режу верёвку",          ActionType.IMPROVISED_WEAPON,"dexterity",10,"mild"),
    ("толкаю в реку",         ActionType.ENVIRONMENTAL,"strength",   14, "medium"),
    ("тушу огонь плащом",     ActionType.ENVIRONMENTAL,"dexterity",  12, "mild"),
    ("открываю окно",         ActionType.ACROBATICS,  "dexterity",   10, "mild"),
    ("залезаю в мешок",       ActionType.STEALTH,     "dexterity",   14, "mild"),
    ("кувырком к цели",       ActionType.ACROBATICS,  "dexterity",   14, "mild"),
    ("прячу предмет",         ActionType.STEALTH,     "dexterity",   12, "mild"),
    ("пью яд намеренно",      ActionType.UNKNOWN,     "constitution",20, "severe"),
    ("ем чужую еду",          ActionType.PHYSICAL,    "constitution", 8, "mild"),
    ("воет на луну",          ActionType.CROWD_CONTROL,"charisma",   14, "mild"),
    ("читает стихи врагу",    ActionType.TAUNT,       "charisma",   12, "mild"),
    ("гипнотизирует взглядом",ActionType.DECEPTION,   "charisma",   16, "medium"),
    ("разыгрывает сумасшествие",ActionType.DECEPTION, "charisma",   15, "medium"),
    ("просит о дуэли",        ActionType.DIPLOMACY,   "charisma",   14, "medium"),
    ("бросает перчатку",      ActionType.TAUNT,       "charisma",   10, "mild"),
    ("свистит союзнику",      ActionType.DISTRACTION, "dexterity",   10, "mild"),
    ("издаёт звук животного", ActionType.DISTRACTION, "charisma",    12, "mild"),
    ("делает финт",           ActionType.DECEPTION,   "charisma",   13, "mild"),
    ("прячется в толпе",      ActionType.STEALTH,     "dexterity",   14, "medium"),
    ("ловит стрелу",          ActionType.ACROBATICS,  "dexterity",   20, "severe"),
    ("читает по губам",       ActionType.UNKNOWN,     "wisdom",      16, "medium"),
    ("ищет слабое место",     ActionType.UNKNOWN,     "intelligence",15, "mild"),
    ("замечает засаду",       ActionType.UNKNOWN,     "wisdom",      14, "mild"),
    ("считает деньги врага",  ActionType.UNKNOWN,     "intelligence",12, "mild"),
    ("запоминает лицо",       ActionType.UNKNOWN,     "wisdom",       8, "mild"),
    ("рисует карту",          ActionType.CRAFTING,    "intelligence",12, "mild"),
    ("пишет записку",         ActionType.CRAFTING,    "intelligence", 8, "mild"),
    ("поднимает флаг",        ActionType.CROWD_CONTROL,"charisma",   12, "mild"),
    ("зажигает сигнальный огонь",ActionType.ENVIRONMENTAL,"intelligence",10,"mild"),
    ("стучит в дверь",        ActionType.PERSUASION,  "charisma",    8, "mild"),
    ("проверяет на яд",       ActionType.UNKNOWN,     "wisdom",      14, "mild"),
    ("прощается с другом",    ActionType.PERSUASION,  "wisdom",       8, "mild"),
    ("просит напоследок",     ActionType.PERSUASION,  "charisma",   14, "medium"),
    ("ищет выход",            ActionType.UNKNOWN,     "intelligence",12, "mild"),
    ("ждёт удобного момента", ActionType.STEALTH,     "wisdom",      12, "mild"),
    ("читает надпись",        ActionType.UNKNOWN,     "intelligence", 8, "mild"),
    ("нюхает воздух",         ActionType.UNKNOWN,     "wisdom",      10, "mild"),
    ("прикасается к артефакту",ActionType.UNKNOWN,    "wisdom",      14, "medium"),
]


@_register(ActionType.UNKNOWN)
def handle_unknown(player: Dict, action: str, **kw) -> SandboxResult:
    """
    Универсальный обработчик для Топ-100 и всего остального.
    Ищет совпадение в таблице, если нет — случайный результат.
    """
    lower = action.lower()

    # Ищем совпадение в TOP_100
    matched = None
    for kw_phrase, a_type, ability, dc, severity in TOP_100_ACTIONS:
        if kw_phrase in lower:
            matched = (a_type, ability, dc, severity)
            break

    if matched:
        a_type, ability, dc, severity = matched
        d20, mod, total = _d20(player, ability)
        success = total >= dc
    else:
        # Совсем неизвестное — случайный DC и характеристика
        ability  = random.choice(["strength", "dexterity", "intelligence", "wisdom", "charisma"])
        dc       = random.choice([10, 12, 14, 15])
        severity = random.choice(["mild", "medium"])
        d20, mod, total = _d20(player, ability)
        success  = total >= dc
        a_type   = ActionType.UNKNOWN

    cons_table = {
        "mild":   ["репутация -5",  "NPC удивлён",      "забавный момент"],
        "medium": ["репутация -15", "стража замечает",  "NPC возмущён"],
        "severe": ["репутация -30", "вендетта фракции", "объявлен вне закона"],
    }
    consequence = random.choice(cons_table[severity])
    rep = {"mild": -5, "medium": -15, "severe": -30}[severity]

    ctx = {
        "type":        a_type.value,
        "action":      action,
        "severity":    severity,
        "roll":        f"d20({d20})+{ability}({mod})={total} vs DC{dc}",
        "success":     success,
        "consequence": consequence,
    }
    _log("unknown_sandbox", ctx)
    return SandboxResult(a_type, success, {"reputation": rep, "consequence": consequence}, ctx)


# ──────────────────────────────────────────────────────────────────────────────
# Классификатор типа действия
# ──────────────────────────────────────────────────────────────────────────────

_KEYWORD_MAP: List[Tuple[List[str], ActionType]] = [
    (["бегу", "убегаю", "сбегаю", "отступаю", "ретируюсь"],   ActionType.FLEE),
    (["захватываю", "беру в плен", "связываю", "пленю"],       ActionType.CAPTURE),
    (["женюсь", "влюбляюсь", "флиртую", "целую", "ухаживаю",
      "признаюсь в любви", "приглашаю на свидание"],           ActionType.ROMANCE),
    (["становлюсь фермером", "бросаю приключения", "живу спокойно",
      "покупаю дом", "строю ферму", "женюсь и остаюсь"],       ActionType.LIFE_CHOICE),
    (["пугаю", "угрожаю", "запугиваю", "рычу", "нависаю"],    ActionType.INTIMIDATE),
    (["подкупаю", "даю золото", "предлагаю монеты",
      "плачу за", "взятка"],                                   ActionType.BRIBERY),
    (["обманываю", "лгу", "вру", "говорю неправду",
      "притворяюсь"],                                          ActionType.DECEPTION),
    (["убеждаю", "уговариваю", "прошу", "умоляю"],             ActionType.PERSUASION),
    (["прячусь", "крадусь", "скрываюсь", "иду тихо"],          ActionType.STEALTH),
    (["прыгаю", "кувырком", "карабкаюсь", "балансирую",
      "ныряю", "лезу"],                                        ActionType.ACROBATICS),
    (["отвлекаю", "создаю шум", "бросаю камень в сторону"],    ActionType.DISTRACTION),
    (["говорю с животным", "успокаиваю зверя", "приручаю",
      "кормлю зверя"],                                         ActionType.ANIMAL_INTERACTION),
    (["создаю", "чиню", "строю ловушку", "варю зелье",
      "готовлю", "кузнец"],                                    ActionType.CRAFTING),
    (["переодеваюсь", "надеваю маску", "меняю облик"],         ActionType.DISGUISE),
    (["краду кошелёк", "вытаскиваю из кармана",
      "ворую незаметно"],                                      ActionType.PICKPOCKET),
    (["вскрываю замок", "отмычка", "взламываю дверь"],         ActionType.LOCKPICK),
    (["отравляю", "добавляю яд", "подсыпаю зелье"],            ActionType.POISON),
    (["веду переговоры", "предлагаю мир", "прошу перемирия"],  ActionType.DIPLOMACY),
    (["сдаюсь", "капитулирую", "поднимаю руки"],               ActionType.SURRENDER),
    (["дразню", "провоцирую", "оскорбляю", "насмехаюсь"],      ActionType.TAUNT),
    (["бью стулом", "кидаю бутылку", "использую факел как дубину",
      "хватаю первое попавшееся"],                             ActionType.IMPROVISED_WEAPON),
    (["кричу толпе", "обращаюсь к толпе", "призываю людей",
      "веду за собой"],                                        ActionType.CROWD_CONTROL),
    (["мочусь", "писаю", "справляю нужду", "раздеваюсь",
      "обнажаюсь", "плюю на", "какаю"],                       ActionType.PHYSICAL),
]


def _classify(action: str) -> ActionType:
    lower = action.lower()
    for keywords, a_type in _KEYWORD_MAP:
        if any(kw in lower for kw in keywords):
            return a_type
    return ActionType.UNKNOWN


# ──────────────────────────────────────────────────────────────────────────────
# Главная точка входа
# ──────────────────────────────────────────────────────────────────────────────

def process_sandbox_action(
    player:        Dict,
    action_desc:   str,
    target:        Optional[Dict] = None,
    enemies:       Optional[List[Dict]] = None,
    location_type: str = "open",
    gold:          int = 0,
    dc_override:   Optional[int] = None,
) -> SandboxResult:
    """
    Единая точка входа для всех нестандартных действий.

    Аргументы:
        player       — словарь персонажа из characters.json
        action_desc  — текст действия от игрока
        target       — NPC цель (если есть)
        enemies      — список врагов (для flee)
        location_type — тип местности ("open", "лес", "коридор", ...)
        gold         — сумма для взятки
        dc_override  — принудительный DC (для тестов)
    """
    try:
        action_type = _classify(action_desc)
        handler     = _HANDLERS.get(action_type, _HANDLERS[ActionType.UNKNOWN])

        result = handler(
            player,
            action_desc,
            npc=target,
            enemies=enemies or [],
            location=location_type,
            gold=gold,
            dc=dc_override or 0,
        )

        # Постобработка: вызовы внешних движков (заглушки — заменить на реальные)
        # PsycheEngine.update(target, result) ← Фаза 3
        # KarmaEngine.apply(player, result)   ← Фаза 3
        # LifeEngine.schedule(result)         ← Фаза 9

        return result

    except Exception as e:
        _log_error("sandbox_handler", "process_sandbox_action", e,
                   {"player": player.get("name"), "action": action_desc})
        return SandboxResult(
            ActionType.UNKNOWN, False, {},
            {"error": True, "message": "Внутренняя ошибка — действие обработано безопасно"},
        )
