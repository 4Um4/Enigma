# -*- coding: utf-8 -*-
"""
PsycheEngine — стресс, слом воли, психологические состояния
backend/app/services/npc/psyche_engine.py
"""
from __future__ import annotations
from typing import Dict, Tuple


# ──────────────────────────────────────────────────────────────────────────────
# Стресс
# ──────────────────────────────────────────────────────────────────────────────

def apply_stress(npc: Dict, amount: int) -> Dict:
    """
    Добавляет стресс. Если stress > breakpoint → state = 'broken'.
    Возвращает словарь с изменениями.
    """
    psyche = npc.setdefault("psyche", {
        "willpower": 50, "stress": 0, "breakpoint": 80,
        "loyalty_true": 50, "loyalty_fake": 50, "state": "free", "trauma_flags": []
    })

    stress_before = psyche.get("stress", 0)
    psyche["stress"] = min(100, stress_before + amount)

    state_changed = False
    if psyche["stress"] > psyche.get("breakpoint", 80) and psyche.get("state") == "free":
        psyche["state"] = "broken"
        psyche["loyalty_true"] = min(psyche.get("loyalty_true", 50),
                                      psyche.get("loyalty_true", 50) - 30)
        psyche.setdefault("trauma_flags", []).append("will_broken")
        state_changed = True

    return {
        "stress_before": stress_before,
        "stress_after":  psyche["stress"],
        "state":         psyche["state"],
        "state_changed": state_changed,
    }


def recover_stress(npc: Dict, ticks_safe: int = 1) -> None:
    """Снижает стресс при нахождении в безопасности."""
    psyche = npc.get("psyche", {})
    current = psyche.get("stress", 0)
    activity = npc.get("routine", {}).get("current", "")
    recovery = 15 if "sleeping" in activity else 5
    psyche["stress"] = max(0, current - recovery * ticks_safe)


# ──────────────────────────────────────────────────────────────────────────────
# Принуждение
# ──────────────────────────────────────────────────────────────────────────────

def resolve_coercion(
    npc: Dict,
    action_type: str,   # "threat" | "bribe" | "charm" | "torture" | "isolation"
    intensity: int,     # 1–100
) -> Dict:
    """
    Разрешает попытку принуждения NPC.
    Возвращает outcome и изменения состояния.
    """
    psyche = npc.get("psyche", {})
    willpower = psyche.get("willpower", 50)
    stress    = psyche.get("stress", 0)
    state     = psyche.get("state", "free")

    # Стресс снижает сопротивление
    effective_resistance = max(0, willpower - stress // 2)

    # Интенсивность действия vs сопротивление
    outcomes = {
        "threat":    {"threshold": 40, "stress_gain": intensity // 2},
        "bribe":     {"threshold": 30, "stress_gain": 0},
        "charm":     {"threshold": 25, "stress_gain": 0},
        "torture":   {"threshold": 60, "stress_gain": intensity},
        "isolation": {"threshold": 50, "stress_gain": intensity // 3},
    }
    params = outcomes.get(action_type, {"threshold": 40, "stress_gain": 10})

    # Применить стресс
    if params["stress_gain"] > 0:
        apply_stress(npc, params["stress_gain"])

    # Определить исход
    if state == "broken":
        outcome = "submit"
    elif intensity >= effective_resistance + params["threshold"]:
        if action_type == "bribe":
            outcome = "accept_bribe"
        else:
            outcome = "broken"
            psyche["state"] = "broken"
            psyche["loyalty_true"] = psyche.get("loyalty_true", 50) - 40
    elif intensity >= effective_resistance:
        outcome = "submit"
        if state == "free":
            psyche["state"] = "coerced"
    else:
        outcome = "resist"

    return {
        "outcome":    outcome,
        "state":      psyche.get("state"),
        "stress":     psyche.get("stress"),
        "resistance": effective_resistance,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Проверка предательства
# ──────────────────────────────────────────────────────────────────────────────

def check_loyalty_break(npc: Dict) -> bool:
    """
    Проверяет готово ли сломленное NPC к предательству.
    Вероятность = (|loyalty_true| - 50) / 50 если state=broken и loyalty_true < -50
    """
    import random
    psyche = npc.get("psyche", {})
    if psyche.get("state") != "broken":
        return False
    lt = psyche.get("loyalty_true", 0)
    if lt >= -50:
        return False
    chance = (abs(lt) - 50) / 50.0
    if random.random() < chance:
        psyche["state"] = "deceptive"
        npc.setdefault("flags", {})["planning_revenge"] = True
        return True
    return False


# ──────────────────────────────────────────────────────────────────────────────
# Подсказка поведения для промпта
# ──────────────────────────────────────────────────────────────────────────────

def get_behavior_hint(npc: Dict) -> str:
    """
    Краткая строка для промпта — как именно NPC ведёт себя.
    Учитывает state + стресс + доминирующий драйв.
    """
    from app.services.npc.npc_cognition import get_dominant_drive, normalize_drives

    psyche  = npc.get("psyche", {})
    state   = psyche.get("state", "free")
    stress  = psyche.get("stress", 0)
    drives  = normalize_drives(npc.get("drives", {}))
    dominant = get_dominant_drive(drives)

    # Матрица state × stress × drive
    if state == "broken":
        if stress >= 85:
            return "говорит дрожащим голосом, отвечает на всё немедленно, избегает взгляда"
        return "подчиняется из страха, слова короткие и осторожные"

    if state == "deceptive":
        if dominant == "control":
            return "внешне спокоен и деловит, внутри ждёт момента для предательства"
        return "улыбается, соглашается, но глаза говорят другое"

    if state == "coerced":
        return "делает что говорят, но с плохо скрытой ненавистью"

    if state == "loyal":
        if dominant == "significance":
            return "горд что служит, упоминает это в речи"
        return "искренне помогает, может пожертвовать собой"

    # state == "free"
    stress_mod = (
        "говорит быстро, перебивает себя"      if stress >= 70 else
        "немного напряжён, выбирает слова"      if stress >= 40 else
        ""
    )
    drive_mod = {
        "control":      "предлагает порядок и условия",
        "significance": "упоминает своё положение",
        "fear":         "задаёт уточняющие вопросы, медленно решает",
        "desire":       "открыт, торгуется, любопытен",
    }.get(dominant, "")

    parts = [p for p in [stress_mod, drive_mod] if p]
    return ", ".join(parts) if parts else "ведёт себя нейтрально"