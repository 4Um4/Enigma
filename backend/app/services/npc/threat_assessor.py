# -*- coding: utf-8 -*-
"""
DEPRECATED: assess_threat() не вызывается из продакшн-кода.
apply_threat_to_npc() — мёртвый код (зависит от psyche_engine.apply_stress).

Угрозы теперь обрабатываются через:
  DecisionHub (intent scoring) → StateDeltas → StateApplicator
  CognitiveDistortionEngine (threat_bias из fear)

Этот файл будет удалён после проверки что sandbox/тесты не зависят от него.
"""
from __future__ import annotations
from typing import Dict, List


# Маркеры → угроза
MARKER_THREAT: Dict[str, int] = {
    "heavy_armor":      +20,
    "weapon_melee":     +20,
    "weapon_ranged":    +15,
    "drawn_weapon":     +25,
    "combat_stance":    +10,
    "blood_on_clothes": +15,
    "threatening_gesture": +20,
    "friendly_posture": -20,
    "hands_raised":     -15,
    "unarmed":          -10,
    "robes":            -5,
    "guild_badge":      +5,
    "slave_collar":     -15,
    "chains":           -10,
}

# Тип действия → угроза
ACTION_THREAT: Dict[str, int] = {
    "COMBAT":           +30,
    "INTIMIDATE":       +25,
    "CAPTURE":          +35,
    "BRIBERY":          -5,
    "PERSUASION":       -10,
    "DIPLOMACY":        -15,
    "ROMANCE":          -10,
    "SOCIAL":           -5,
    "EXPLORE":          0,
    "FLEE":             0,
    "UNKNOWN":          0,
}


def assess_threat(
    player_markers: List[str],
    action_type: str,
    player_reputation: Dict[str, int] = None,
) -> int:
    """
    Вычисляет уровень угрозы от игрока (0–100).
    Учитывает видимые маркеры, тип действия и репутацию.
    """
    score = 0

    # Маркеры
    for marker in player_markers:
        score += MARKER_THREAT.get(marker, 0)

    # Тип действия
    score += ACTION_THREAT.get(action_type, 0)

    # Репутация
    rep = player_reputation or {}
    if rep.get("cruel", 0) > 20:
        score += 10
    if rep.get("hero", 0) > 20:
        score -= 5
    if rep.get("betrayer", 0) > 10:
        score += 8

    return max(0, min(100, score))


def get_threat_category(score: int) -> str:
    """LOW | MEDIUM | HIGH | CRITICAL"""
    if score >= 70: return "CRITICAL"
    if score >= 45: return "HIGH"
    if score >= 20: return "MEDIUM"
    return "LOW"


def apply_threat_to_npc(npc: Dict, score: int, category: str) -> None:
    """
    Применяет угрозу к состоянию NPC — изменяет stress и fear.
    Вызывается из _run_python_engines после assess_threat.
    """
    from app.services.npc.psyche_engine import apply_stress

    if category == "CRITICAL":
        apply_stress(npc, random_int(40, 60))
        ss = npc.setdefault("social_stats", {})
        ss["fear_of_player"] = min(1.0, ss.get("fear_of_player", 0.1) + 0.3)

    elif category == "HIGH":
        apply_stress(npc, random_int(20, 40))
        ss = npc.setdefault("social_stats", {})
        ss["fear_of_player"] = min(1.0, ss.get("fear_of_player", 0.1) + 0.15)

    elif category == "MEDIUM":
        apply_stress(npc, random_int(5, 15))
        ss = npc.setdefault("social_stats", {})
        ss["fear_of_player"] = min(1.0, ss.get("fear_of_player", 0.1) + 0.07)


def random_int(a: int, b: int) -> int:
    import random
    return random.randint(a, b)
