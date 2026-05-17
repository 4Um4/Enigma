# -*- coding: utf-8 -*-
"""
PerceptionEngine — как NPC воспринимает статус игрока
backend/app/services/npc/perception_engine.py

Работает < 15ms. Не использует LLM.
"""
from __future__ import annotations
from typing import Dict, List


# Маркеры → статус (сумма = воспринимаемый статус)
MARKER_STATUS: Dict[str, int] = {
    "royal_crown":      +50,
    "noble_clothes":    +30,
    "fine_armor":       +20,
    "guild_badge":      +20,
    "heavy_armor":      +10,
    "military_emblem":  +15,
    "merchant_clothes": +10,
    "tunic":            0,
    "rags":             -30,
    "slave_collar":     -60,
    "chains":           -50,
    "blood_on_clothes": -10,
    "begging_bowl":     -40,
}


def assess_status(visible_markers: List[str]) -> int:
    """Вычисляет воспринимаемый статус игрока (0–100)."""
    score = 50  # базовый нейтральный
    for marker in visible_markers:
        score += MARKER_STATUS.get(marker, 0)
    return max(0, min(100, score))


def get_status_label(score: int) -> str:
    """Текстовый ярлык статуса."""
    if score >= 85: return "правитель"
    if score >= 65: return "благородный"
    if score >= 45: return "уважаемый"
    if score >= 25: return "простолюдин"
    return "нищий / изгой"


def get_social_permissions(
    player_markers: List[str],
    npc: Dict,
) -> List[str]:
    """
    Список разрешённых социальных действий.
    Зависит от статуса игрока и свободы NPC.
    """
    player_status = assess_status(player_markers)
    npc_freedom   = npc.get("status_profile", {}).get("freedom", 50)

    permissions = []

    # Базовые — всегда
    permissions.extend(["greet", "talk", "ask"])

    # По статусу игрока
    if player_status >= 65:
        permissions.extend(["demand", "order", "threaten"])
    if player_status >= 45:
        permissions.extend(["negotiate", "trade"])
    if player_status < 20:
        permissions.append("beg")

    # По свободе NPC
    if npc_freedom < 20:
        # Раб — не может требовать
        for p in ["demand", "order"]:
            if p in permissions:
                permissions.remove(p)

    # Всегда доступно
    permissions.extend(["charm", "bribe", "deceive"])

    return list(set(permissions))  # уникальные
