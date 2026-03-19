# -*- coding: utf-8 -*-
"""
NPCCognition — 4 драйва личности + сборщик промпта
backend/app/services/npc/npc_cognition.py

Принцип: Python считает → LLM только говорит готовый текст.
"""
from __future__ import annotations
from typing import Dict, List, Optional


# ──────────────────────────────────────────────────────────────────────────────
# 1. Нормализация и анализ драйвов
# ──────────────────────────────────────────────────────────────────────────────

def normalize_drives(drives: Dict[str, float]) -> Dict[str, float]:
    """Нормализует драйвы к сумме 1.0."""
    total = sum(drives.values())
    if total <= 0:
        return {"control": 0.25, "significance": 0.25, "fear": 0.25, "desire": 0.25}
    return {k: round(v / total, 4) for k, v in drives.items()}


def get_dominant_drive(drives: Dict[str, float]) -> str:
    """Возвращает ключ с максимальным значением."""
    return max(drives, key=drives.get)


def get_speech_style(dominant_drive: str) -> str:
    """Строка-подсказка стиля речи для промпта NPC агента."""
    styles = {
        "control":      "Говорит структурированно и по делу. Предлагает план. Не терпит хаоса. Расставляет условия.",
        "significance": "Часто упоминает свой статус. Обижается на неуважение. Говорит с достоинством.",
        "fear":         "Осторожен. Задаёт уточняющие вопросы. Ищет выход. Говорит тихо или торопливо.",
        "desire":       "Энергичен. Интересуется выгодой. Готов рисковать. Любопытен. Торгуется.",
    }
    return styles.get(dominant_drive, "Говорит нейтрально, взвешивает слова.")


# ──────────────────────────────────────────────────────────────────────────────
# 2. Реакция на действие игрока — изменение trust и fear
# ──────────────────────────────────────────────────────────────────────────────

def process_player_action(
    npc: Dict,
    action_type: str,       # из ActionClassifier: COMBAT, SOCIAL, INTIMIDATE, BRIBERY...
    player: Dict,
    threat_level: int,      # 0–100 от ThreatAssessor
) -> Dict:
    """
    Обновляет trust и fear_of_player в social_stats NPC.
    Возвращает словарь изменений (дельты).
    """
    ss = npc.setdefault("social_stats", {
        "trust": 0.5, "affection": 0.4, "fear_of_player": 0.1, "debt": 0
    })

    delta_trust = 0.0
    delta_fear  = 0.0

    # Влияние типа действия
    action_effects = {
        "COMBAT":     (-0.20, +0.25),
        "INTIMIDATE": (-0.15, +0.20),
        "CAPTURE":    (-0.30, +0.35),
        "BRIBERY":    (+0.05, -0.05),
        "PERSUASION": (+0.08, -0.03),
        "DIPLOMACY":  (+0.10, -0.05),
        "ROMANCE":    (+0.05,  0.00),
        "SOCIAL":     (+0.03, -0.02),
        "EXPLORE":    (0.00,  0.00),
    }
    dt, df = action_effects.get(action_type, (0.0, 0.0))
    delta_trust += dt
    delta_fear  += df

    # Дополнительно от уровня угрозы
    if threat_level >= 70:
        delta_trust -= 0.10
        delta_fear  += 0.15
    elif threat_level >= 40:
        delta_trust -= 0.05
        delta_fear  += 0.07

    # Репутация игрока
    rep = player.get("reputation", {})
    if rep.get("hero", 0) > 30:
        delta_trust += 0.05
    if rep.get("cruel", 0) > 30:
        delta_fear  += 0.10
        delta_trust -= 0.05

    # Применяем изменения с ограничениями [0..1]
    ss["trust"]          = round(max(0.0, min(1.0, ss["trust"]          + delta_trust)), 4)
    ss["fear_of_player"] = round(max(0.0, min(1.0, ss["fear_of_player"] + delta_fear)), 4)

    return {"delta_trust": round(delta_trust, 4), "delta_fear": round(delta_fear, 4)}


# ──────────────────────────────────────────────────────────────────────────────
# 3. Сборка промпта для NPC LLM агента
# ──────────────────────────────────────────────────────────────────────────────

def build_npc_prompt(
    npc: Dict,
    player: Dict,
    context: Dict,
    behavior_hint: str = "",      # из PsycheEngine
    perceived_status: str = "",   # из PerceptionEngine
    threat_category: str = "LOW", # из ThreatAssessor
) -> str:
    """
    Строит system prompt для NPC LLM агента.
    LLM получает уже посчитанные числа и только озвучивает их.
    """
    drives     = normalize_drives(npc.get("drives", {}))
    dominant   = get_dominant_drive(drives)
    speech     = get_speech_style(dominant)
    ss         = npc.get("social_stats", {})
    psyche     = npc.get("psyche", {})
    state      = psyche.get("state", "free")
    stress     = psyche.get("stress", 0)
    trust      = ss.get("trust", 0.5)
    fear       = ss.get("fear_of_player", 0.1)

    # Последние 3 воспоминания об игроке
    memories = npc.get("memory_trace", [])[-3:]
    mem_str = ""
    if memories:
        mem_str = "\nПомнит об игроке:\n" + "\n".join(
            f"  — {m.get('event', '?')} (давно: {m.get('tick_added', '?')})"
            for m in memories
        )

    # Состояние стресса
    stress_desc = (
        "в панике, на грани срыва" if stress >= 85 else
        "взволнован, нервничает"   if stress >= 60 else
        "напряжён"                  if stress >= 35 else
        "спокоен"
    )

    prompt = f"""Ты — {npc['name']}. {npc.get('status_profile', {}).get('title', '')}.

ПСИХОЛОГИЯ ПРЯМО СЕЙЧАС:
Доминирующий драйв: {dominant} ({drives.get(dominant, 0):.0%})
Стиль речи: {speech}
Стресс: {stress}/100 ({stress_desc})
Состояние воли: {state}
Доверие к игроку: {trust:.0%}
Страх перед игроком: {fear:.0%}
Воспринимает игрока как: {perceived_status or 'незнакомца'}
Угроза от игрока: {threat_category}
{('Поведение: ' + behavior_hint) if behavior_hint else ''}
{mem_str}

ИНСТРУКЦИЯ:
Отвечай ТОЛЬКО от первого лица, как {npc['name']}.
Используй стиль речи своего доминирующего драйва.
НЕ описывай свои действия от третьего лица.
Отвечай на русском языке. 1–3 предложения.
Если состояние "broken" — ты подчиняешься из страха.
Если состояние "deceptive" — внешне согласен, внутри враждебен.
Если состояние "loyal" — искренне помогаешь.

Ответь в JSON:
{{"speech": "что говоришь вслух", "action": "что делаешь физически (кратко)", "trust_change": число от -10 до +10, "stress_change": число от -10 до +10}}"""

    return prompt


# ──────────────────────────────────────────────────────────────────────────────
# 4. Внутренняя мысль (для Debug Mode F12)
# ──────────────────────────────────────────────────────────────────────────────

def get_inner_thought(npc: Dict, context: Dict = None) -> str:
    """
    Строка для Debug Mode (F12). Игрок НЕ видит это.
    Показывает реальное психологическое состояние NPC.
    """
    drives  = normalize_drives(npc.get("drives", {}))
    dominant = get_dominant_drive(drives)
    psyche  = npc.get("psyche", {})
    ss      = npc.get("social_stats", {})
    state   = psyche.get("state", "free")
    stress  = psyche.get("stress", 0)
    lt      = psyche.get("loyalty_true", 50)
    lf      = psyche.get("loyalty_fake", 50)

    plan = {
        "broken":    "подчиняться и ждать шанса сбежать",
        "deceptive": "притворяться лояльным, готовить предательство",
        "coerced":   "терпеть и сопротивляться где возможно",
        "loyal":     "искренне помогать",
        "free":      "действовать по собственным интересам",
    }.get(state, "действовать по ситуации")

    return (
        f"[Внутренняя мысль: {npc['name']}]\n"
        f"Драйв: {dominant} ({drives.get(dominant, 0):.0%})\n"
        f"Стресс: {stress}/100  Состояние: {state}\n"
        f"Лояльность (реальная): {lt}  (показная): {lf}\n"
        f"Доверие: {ss.get('trust', 0.5):.0%}  "
        f"Страх: {ss.get('fear_of_player', 0.1):.0%}\n"
        f"План: {plan}"
    )