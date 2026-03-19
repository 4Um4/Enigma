# ENIGMA — Фаза 3A: NPC Core Psychology
## Полный пошаговый маршрут реализации

---

## 📋 Что будет создано

```
backend/
├── app/services/npc/           ← папка не существует, создаём всё с нуля
│   ├── __init__.py
│   ├── npc_cognition.py        ← 3A.1: 4 драйва + build_npc_prompt
│   ├── psyche_engine.py        ← 3A.2: стресс, слом воли, состояния
│   ├── threat_assessor.py      ← 3A.3: оценка угрозы от игрока
│   └── perception_engine.py   ← 3A.4: как NPC видит игрока
├── data/npcs/                  ← папка не существует, создаём
│   ├── major_npcs.json         ← 3A.0: 5 полных NPC
│   └── mass_npc_templates.json ← 3A.0: 10 шаблонов
└── tests/
    ├── test_npc_cognition.py
    └── test_psyche_engine.py

Изменяем:
├── app/services/orchestrator.py   ← 3A.5: _run_python_engines + NPC блок
└── data/campaigns/demo-campaign/campaign_state.json  ← исправить location
```

**Время на реализацию:** 2 недели при ежедневной работе по 2–3 часа.

---

## 🔧 ШАГ 0 — Одноразовый фикс (5 минут)

Перед NPC-системой — исправить `current_location`, который до сих пор `"unknown"`.

**Файл:** `backend/data/campaigns/demo-campaign/campaign_state.json`

Найдите секцию `"metadata"` и замените:

```json
"metadata": {
  "current_location": "Таверна Серебряный Волк",
  "world_name": "Фандалин",
  "time_of_day": "вечер",
  "day": 1,
  "weather": "тихо, облачно",
  "season": "осень"
}
```

Это уберёт "unknown" из промптов навсегда.

---

## 📁 ШАГ 1 — Данные NPC (3A.0)

### 1.1 Создать папку

```
backend/data/npcs/
```

### 1.2 Создать `major_npcs.json`

Полный файл с 5 NPC. Каждый имеет все обязательные поля из схемы.

```json
[
  {
    "id": "tavern_keeper_tornin",
    "name": "Торнин Серебряная Луна",
    "tier": "major",
    "status_profile": {
      "freedom": 75, "wealth": 40, "power": 20,
      "title": "Хозяин таверны",
      "faction_rank": {"гильдия_воров": -1}
    },
    "visible_markers": ["apron", "keys", "heavy_build", "scar_on_cheek"],
    "hidden_truth": ["former_soldier", "owes_debt_to_thieves_guild"],
    "drives": {"control": 0.50, "significance": 0.25, "fear": 0.15, "desire": 0.10},
    "psyche": {
      "willpower": 65, "stress": 20, "breakpoint": 80,
      "loyalty_true": 60, "loyalty_fake": 60,
      "state": "free", "trauma_flags": []
    },
    "social_stats": {
      "trust": 0.60, "affection": 0.50,
      "fear_of_player": 0.05, "debt": 0
    },
    "relationships": {"player_default": 50, "guard_borko": 60},
    "routine": {
      "current": "cleaning_tables", "mood": "neutral", "interrupted": false,
      "next_task": "serve_customers",
      "schedule": {
        "06:00-22:00": "working",
        "22:00-06:00": "sleeping"
      }
    },
    "recent_events": [],
    "memory_trace": [],
    "flags": {
      "has_gold": true, "knows_secret": false,
      "is_enslaved": false, "planning_revenge": false, "is_dead": false
    },
    "location": "tavern_silver_wolf",
    "hp": 40, "max_hp": 40,
    "combat_stats": {"ac": 12, "attack_bonus": 3, "damage": "1d6+2"},
    "abilities": {
      "strength": 14, "dexterity": 10, "constitution": 13,
      "intelligence": 11, "wisdom": 12, "charisma": 13
    }
  },
  {
    "id": "guard_borko",
    "name": "Стражник Борко",
    "tier": "minor",
    "status_profile": {
      "freedom": 60, "wealth": 15, "power": 30,
      "title": "Стражник городских ворот",
      "faction_rank": {"стража_города": 2}
    },
    "visible_markers": ["city_guard_armor", "spear", "city_emblem"],
    "hidden_truth": ["takes_bribes", "lazy"],
    "drives": {"control": 0.40, "significance": 0.30, "fear": 0.20, "desire": 0.10},
    "psyche": {
      "willpower": 45, "stress": 25, "breakpoint": 65,
      "loyalty_true": 30, "loyalty_fake": 50,
      "state": "free", "trauma_flags": []
    },
    "social_stats": {
      "trust": 0.40, "affection": 0.30,
      "fear_of_player": 0.10, "debt": 0
    },
    "relationships": {"player_default": 40, "tavern_keeper_tornin": 60},
    "routine": {
      "current": "guarding_gate", "mood": "bored", "interrupted": false,
      "next_task": "patrol",
      "schedule": {
        "07:00-19:00": "guarding_gate",
        "19:00-07:00": "sleeping"
      }
    },
    "recent_events": [],
    "memory_trace": [],
    "flags": {
      "has_gold": false, "knows_secret": false,
      "is_enslaved": false, "planning_revenge": false, "is_dead": false
    },
    "location": "city_gate",
    "hp": 30, "max_hp": 30,
    "combat_stats": {"ac": 14, "attack_bonus": 4, "damage": "1d8+2"},
    "abilities": {
      "strength": 13, "dexterity": 12, "constitution": 12,
      "intelligence": 9, "wisdom": 11, "charisma": 10
    }
  },
  {
    "id": "maid_lusya",
    "name": "Люся",
    "tier": "minor",
    "status_profile": {
      "freedom": 50, "wealth": 5, "power": 5,
      "title": "Служанка таверны",
      "faction_rank": {}
    },
    "visible_markers": ["maid_dress", "tray", "tired_eyes"],
    "hidden_truth": ["spy_for_thieves_guild", "looking_for_escape"],
    "drives": {"control": 0.15, "significance": 0.20, "fear": 0.45, "desire": 0.20},
    "psyche": {
      "willpower": 35, "stress": 40, "breakpoint": 55,
      "loyalty_true": 20, "loyalty_fake": 55,
      "state": "coerced", "trauma_flags": ["threatened_in_past"]
    },
    "social_stats": {
      "trust": 0.35, "affection": 0.45,
      "fear_of_player": 0.20, "debt": 0
    },
    "relationships": {"player_default": 35, "tavern_keeper_tornin": 40},
    "routine": {
      "current": "serving_tables", "mood": "anxious", "interrupted": false,
      "next_task": "wash_dishes",
      "schedule": {
        "08:00-23:00": "serving_tables",
        "23:00-08:00": "sleeping"
      }
    },
    "recent_events": [],
    "memory_trace": [],
    "flags": {
      "has_gold": false, "knows_secret": true,
      "is_enslaved": false, "planning_revenge": false, "is_dead": false
    },
    "location": "tavern_silver_wolf",
    "hp": 15, "max_hp": 15,
    "combat_stats": {"ac": 10, "attack_bonus": 0, "damage": "1d4"},
    "abilities": {
      "strength": 8, "dexterity": 13, "constitution": 10,
      "intelligence": 12, "wisdom": 14, "charisma": 12
    }
  },
  {
    "id": "merchant_goran",
    "name": "Купец Горан",
    "tier": "minor",
    "status_profile": {
      "freedom": 80, "wealth": 70, "power": 35,
      "title": "Торговец тканями",
      "faction_rank": {"купеческая_гильдия": 3}
    },
    "visible_markers": ["merchant_robes", "coin_purse", "ledger"],
    "hidden_truth": ["smuggles_contraband", "owes_money_to_criminals"],
    "drives": {"control": 0.20, "significance": 0.25, "fear": 0.15, "desire": 0.40},
    "psyche": {
      "willpower": 50, "stress": 30, "breakpoint": 70,
      "loyalty_true": 45, "loyalty_fake": 45,
      "state": "free", "trauma_flags": []
    },
    "social_stats": {
      "trust": 0.50, "affection": 0.40,
      "fear_of_player": 0.05, "debt": 0
    },
    "relationships": {"player_default": 50},
    "routine": {
      "current": "haggling", "mood": "calculating", "interrupted": false,
      "next_task": "inspect_goods",
      "schedule": {
        "09:00-18:00": "market_trading",
        "18:00-21:00": "counting_money",
        "21:00-09:00": "sleeping"
      }
    },
    "recent_events": [],
    "memory_trace": [],
    "flags": {
      "has_gold": true, "knows_secret": true,
      "is_enslaved": false, "planning_revenge": false, "is_dead": false
    },
    "location": "market_square",
    "hp": 20, "max_hp": 20,
    "combat_stats": {"ac": 11, "attack_bonus": 1, "damage": "1d4"},
    "abilities": {
      "strength": 10, "dexterity": 12, "constitution": 11,
      "intelligence": 14, "wisdom": 13, "charisma": 15
    }
  },
  {
    "id": "thief_shadow",
    "name": "Тень",
    "tier": "major",
    "status_profile": {
      "freedom": 70, "wealth": 35, "power": 25,
      "title": "Вор",
      "faction_rank": {"гильдия_воров": 4}
    },
    "visible_markers": ["dark_cloak", "hood", "daggers"],
    "hidden_truth": ["guild_lieutenant", "looking_for_something"],
    "drives": {"control": 0.30, "significance": 0.20, "fear": 0.10, "desire": 0.40},
    "psyche": {
      "willpower": 70, "stress": 15, "breakpoint": 85,
      "loyalty_true": -20, "loyalty_fake": 50,
      "state": "deceptive", "trauma_flags": []
    },
    "social_stats": {
      "trust": 0.25, "affection": 0.20,
      "fear_of_player": 0.10, "debt": 0
    },
    "relationships": {"player_default": 25},
    "routine": {
      "current": "observing", "mood": "alert", "interrupted": false,
      "next_task": "contact_guild",
      "schedule": {
        "20:00-04:00": "active",
        "04:00-14:00": "sleeping",
        "14:00-20:00": "planning"
      }
    },
    "recent_events": [],
    "memory_trace": [],
    "flags": {
      "has_gold": false, "knows_secret": true,
      "is_enslaved": false, "planning_revenge": false, "is_dead": false
    },
    "location": "tavern_silver_wolf",
    "hp": 35, "max_hp": 35,
    "combat_stats": {"ac": 15, "attack_bonus": 5, "damage": "1d6+3"},
    "abilities": {
      "strength": 10, "dexterity": 17, "constitution": 12,
      "intelligence": 13, "wisdom": 14, "charisma": 11
    }
  }
]
```

### 1.3 Создать `mass_npc_templates.json`

```json
{
  "city_guard": {
    "archetype": "городской стражник",
    "drives": {"control": 0.45, "significance": 0.25, "fear": 0.20, "desire": 0.10},
    "stress_baseline": 25, "willpower_baseline": 50, "breakpoint_baseline": 65,
    "trust_baseline": 0.40, "fear_of_player_baseline": 0.10,
    "visible_markers": ["city_guard_armor", "spear"],
    "routine_template": {"07:00-19:00": "on_duty", "19:00-07:00": "off_duty"}
  },
  "tavern_drunk": {
    "archetype": "пьяный посетитель",
    "drives": {"control": 0.10, "significance": 0.30, "fear": 0.10, "desire": 0.50},
    "stress_baseline": 10, "willpower_baseline": 20, "breakpoint_baseline": 30,
    "trust_baseline": 0.60, "fear_of_player_baseline": 0.05,
    "visible_markers": ["ragged_clothes", "mug_of_ale"],
    "routine_template": {"12:00-24:00": "drinking", "00:00-12:00": "sleeping"}
  },
  "peasant": {
    "archetype": "крестьянин",
    "drives": {"control": 0.35, "significance": 0.15, "fear": 0.40, "desire": 0.10},
    "stress_baseline": 30, "willpower_baseline": 40, "breakpoint_baseline": 55,
    "trust_baseline": 0.45, "fear_of_player_baseline": 0.15,
    "visible_markers": ["tunic", "calloused_hands", "hoe"],
    "routine_template": {"06:00-18:00": "working_fields", "18:00-22:00": "home", "22:00-06:00": "sleeping"}
  },
  "merchant": {
    "archetype": "торговец",
    "drives": {"control": 0.25, "significance": 0.20, "fear": 0.15, "desire": 0.40},
    "stress_baseline": 20, "willpower_baseline": 55, "breakpoint_baseline": 70,
    "trust_baseline": 0.50, "fear_of_player_baseline": 0.05,
    "visible_markers": ["merchant_clothes", "coin_purse"],
    "routine_template": {"08:00-18:00": "trading", "18:00-08:00": "off_duty"}
  },
  "beggar": {
    "archetype": "нищий",
    "drives": {"control": 0.05, "significance": 0.10, "fear": 0.60, "desire": 0.25},
    "stress_baseline": 50, "willpower_baseline": 30, "breakpoint_baseline": 40,
    "trust_baseline": 0.25, "fear_of_player_baseline": 0.35,
    "visible_markers": ["rags", "begging_bowl"],
    "routine_template": {"08:00-20:00": "begging", "20:00-08:00": "sleeping"}
  },
  "monk": {
    "archetype": "монах",
    "drives": {"control": 0.20, "significance": 0.15, "fear": 0.15, "desire": 0.50},
    "stress_baseline": 10, "willpower_baseline": 75, "breakpoint_baseline": 90,
    "trust_baseline": 0.65, "fear_of_player_baseline": 0.02,
    "visible_markers": ["robes", "holy_symbol"],
    "routine_template": {"05:00-21:00": "duties", "21:00-05:00": "prayer_and_sleep"}
  },
  "soldier": {
    "archetype": "солдат",
    "drives": {"control": 0.40, "significance": 0.30, "fear": 0.10, "desire": 0.20},
    "stress_baseline": 30, "willpower_baseline": 65, "breakpoint_baseline": 80,
    "trust_baseline": 0.40, "fear_of_player_baseline": 0.05,
    "visible_markers": ["military_armor", "sword", "unit_emblem"],
    "routine_template": {"06:00-18:00": "training_patrol", "18:00-06:00": "barracks"}
  },
  "innkeeper_maid": {
    "archetype": "служанка",
    "drives": {"control": 0.20, "significance": 0.20, "fear": 0.35, "desire": 0.25},
    "stress_baseline": 35, "willpower_baseline": 35, "breakpoint_baseline": 50,
    "trust_baseline": 0.40, "fear_of_player_baseline": 0.20,
    "visible_markers": ["maid_dress", "tray"],
    "routine_template": {"07:00-22:00": "serving", "22:00-07:00": "sleeping"}
  },
  "child": {
    "archetype": "ребёнок",
    "drives": {"control": 0.10, "significance": 0.20, "fear": 0.30, "desire": 0.40},
    "stress_baseline": 15, "willpower_baseline": 20, "breakpoint_baseline": 30,
    "trust_baseline": 0.70, "fear_of_player_baseline": 0.10,
    "visible_markers": ["small_size", "simple_clothes"],
    "routine_template": {"08:00-20:00": "playing_chores", "20:00-08:00": "sleeping"}
  },
  "priest": {
    "archetype": "жрец",
    "drives": {"control": 0.20, "significance": 0.30, "fear": 0.10, "desire": 0.40},
    "stress_baseline": 10, "willpower_baseline": 70, "breakpoint_baseline": 85,
    "trust_baseline": 0.60, "fear_of_player_baseline": 0.03,
    "visible_markers": ["priest_robes", "temple_symbol"],
    "routine_template": {"06:00-20:00": "temple_duties", "20:00-06:00": "rest"}
  }
}
```

---

## 📁 ШАГ 2 — Создать папку NPC движков

```
backend/app/services/npc/
```

Создайте файл `__init__.py` (пустой):

```python
# -*- coding: utf-8 -*-
"""NPC Psychology Engines — Enigma Fase 3A"""
```

---

## 📁 ШАГ 3 — NPCCognition (3A.1)

**Файл:** `backend/app/services/npc/npc_cognition.py`

```python
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
```

---

## 📁 ШАГ 4 — PsycheEngine (3A.2)

**Файл:** `backend/app/services/npc/psyche_engine.py`

```python
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
```

---

## 📁 ШАГ 5 — ThreatAssessor (3A.3)

**Файл:** `backend/app/services/npc/threat_assessor.py`

```python
# -*- coding: utf-8 -*-
"""
ThreatAssessor — оценка угрозы от игрока
backend/app/services/npc/threat_assessor.py

Работает < 10ms. Не использует LLM.
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
```

---

## 📁 ШАГ 6 — PerceptionEngine (3A.4)

**Файл:** `backend/app/services/npc/perception_engine.py`

```python
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
```

---

## 📁 ШАГ 7 — Интеграция в Orchestrator (3A.5)

**Файл:** `backend/app/services/orchestrator.py`

Найдите метод `_run_python_engines` и добавьте в него NPC-блок.

**Сначала добавьте импорты в начало файла** (после существующих):

```python
from app.services.npc.npc_cognition   import (process_player_action, build_npc_prompt,
                                                get_inner_thought, normalize_drives)
from app.services.npc.psyche_engine   import apply_stress, get_behavior_hint
from app.services.npc.threat_assessor import assess_threat, get_threat_category, apply_threat_to_npc
from app.services.npc.perception_engine import assess_status, get_status_label, get_social_permissions
```

**Добавьте метод загрузки NPC** (после `__init__`):

```python
_npc_cache: dict | None = None  # кэш в RAM

def _load_npcs(self) -> list:
    """Загружает NPC из JSON. Кэширует в RAM."""
    global _npc_cache
    if _npc_cache is not None:
        return _npc_cache
    npc_path = self.data_dir / "npcs" / "major_npcs.json"
    if npc_path.exists():
        import json
        with open(npc_path, "r", encoding="utf-8") as f:
            _npc_cache = json.load(f)
    else:
        _npc_cache = []
    return _npc_cache

def _save_npcs(self, npcs: list) -> None:
    """Сохраняет обновлённые NPC обратно в JSON."""
    import json
    npc_path = self.data_dir / "npcs" / "major_npcs.json"
    npc_path.parent.mkdir(parents=True, exist_ok=True)
    with open(npc_path, "w", encoding="utf-8") as f:
        json.dump(npcs, f, ensure_ascii=False, indent=2)
    global _npc_cache
    _npc_cache = npcs  # обновляем кэш

def _get_npcs_in_location(self, location: str) -> list:
    """Возвращает NPC которые сейчас в данной локации."""
    return [npc for npc in self._load_npcs() if npc.get("location") == location]
```

**Расширьте `_run_python_engines`** — добавьте NPC-блок перед `return`:

```python
# ── NPC Psychology блок ───────────────────────────────────────────────────────
action_type = shared_context.get("action_type", "EXPLORE")
player_data = {}
if req.actions:
    player_name = req.actions[0].player_name
    chars = self.character_service.list_characters(req.campaign_id)
    player_data = next(
        (c.model_dump() for c in chars if c.name == player_name), {}
    )

npcs_in_location = self._get_npcs_in_location(req.location)
npc_contexts = []

for npc in npcs_in_location:
    # 1. Threat
    player_markers = player_data.get("visible_markers", [])
    threat_score   = assess_threat(
        player_markers, action_type,
        player_data.get("reputation", {})
    )
    threat_cat = get_threat_category(threat_score)
    apply_threat_to_npc(npc, threat_score, threat_cat)

    # 2. Perception
    status_score  = assess_status(player_markers)
    status_label  = get_status_label(status_score)
    permissions   = get_social_permissions(player_markers, npc)

    # 3. NPCCognition — trust/fear
    action_deltas = process_player_action(npc, action_type, player_data, threat_score)

    # 4. PsycheEngine — behavior hint
    behavior_hint = get_behavior_hint(npc)

    # 5. Промпт для NPC агента
    npc_system_prompt = build_npc_prompt(
        npc, player_data, shared_context,
        behavior_hint=behavior_hint,
        perceived_status=status_label,
        threat_category=threat_cat,
    )

    # 6. Inner thought для Debug Mode
    inner_thought = get_inner_thought(npc, shared_context)

    npc_contexts.append({
        "npc_id":          npc["id"],
        "npc_name":        npc["name"],
        "threat_score":    threat_score,
        "threat_category": threat_cat,
        "perceived_status": status_label,
        "behavior_hint":   behavior_hint,
        "system_prompt":   npc_system_prompt,
        "inner_thought":   inner_thought,
        "permissions":     permissions,
        "action_deltas":   action_deltas,
    })

# Сохраняем обновлённые состояния NPC
if npcs_in_location:
    all_npcs = self._load_npcs()
    for updated_npc in npcs_in_location:
        for i, n in enumerate(all_npcs):
            if n["id"] == updated_npc["id"]:
                all_npcs[i] = updated_npc
                break
    self._save_npcs(all_npcs)

# Добавляем к результатам
results["npc_contexts"] = npc_contexts
# ── Конец NPC блока ────────────────────────────────────────────────────────────
```

---

## 📁 ШАГ 8 — Тесты

### `backend/tests/test_npc_cognition.py`

```python
# -*- coding: utf-8 -*-
"""Тесты NPCCognition"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.services.npc.npc_cognition import (
    normalize_drives, get_dominant_drive, get_speech_style,
    process_player_action, build_npc_prompt, get_inner_thought,
)

def make_npc():
    return {
        "id": "test_npc",
        "name": "Тестовый NPC",
        "tier": "minor",
        "status_profile": {"freedom": 50, "wealth": 20, "power": 10, "title": "Стражник"},
        "visible_markers": ["armor"],
        "drives": {"control": 0.6, "significance": 0.2, "fear": 0.15, "desire": 0.05},
        "psyche": {"willpower": 60, "stress": 20, "breakpoint": 80,
                   "loyalty_true": 50, "loyalty_fake": 50, "state": "free", "trauma_flags": []},
        "social_stats": {"trust": 0.5, "affection": 0.4, "fear_of_player": 0.1, "debt": 0},
        "memory_trace": [],
        "location": "city_gate",
        "abilities": {"strength": 12, "dexterity": 10, "constitution": 11,
                      "intelligence": 9, "wisdom": 10, "charisma": 9},
    }

def test_normalize():
    d = {"control": 3, "significance": 1, "fear": 0, "desire": 0}
    n = normalize_drives(d)
    assert abs(sum(n.values()) - 1.0) < 0.001, "Сумма должна быть 1.0"
    print("✅ normalize_drives")

def test_dominant():
    d = {"control": 0.6, "significance": 0.2, "fear": 0.1, "desire": 0.1}
    assert get_dominant_drive(d) == "control"
    print("✅ get_dominant_drive")

def test_speech_style():
    s = get_speech_style("control")
    assert len(s) > 10
    print("✅ get_speech_style")

def test_process_action_combat():
    npc = make_npc()
    before_trust = npc["social_stats"]["trust"]
    result = process_player_action(npc, "COMBAT", {}, 80)
    assert npc["social_stats"]["trust"] < before_trust, "COMBAT должен снизить доверие"
    assert result["delta_trust"] < 0
    print("✅ process_player_action (COMBAT снижает trust)")

def test_process_action_bribery():
    npc = make_npc()
    before_trust = npc["social_stats"]["trust"]
    result = process_player_action(npc, "BRIBERY", {}, 5)
    assert npc["social_stats"]["trust"] > before_trust, "BRIBERY должен повысить доверие"
    print("✅ process_player_action (BRIBERY повышает trust)")

def test_build_prompt():
    npc = make_npc()
    prompt = build_npc_prompt(npc, {}, {})
    assert "Тестовый NPC" in prompt
    assert "control" in prompt
    print("✅ build_npc_prompt (содержит имя и драйв)")

def test_inner_thought():
    npc = make_npc()
    thought = get_inner_thought(npc)
    assert "Тестовый NPC" in thought
    assert "control" in thought
    print("✅ get_inner_thought")

if __name__ == "__main__":
    test_normalize()
    test_dominant()
    test_speech_style()
    test_process_action_combat()
    test_process_action_bribery()
    test_build_prompt()
    test_inner_thought()
    print("\n✅✅✅ Все тесты NPCCognition прошли!")
```

### `backend/tests/test_psyche_engine.py`

```python
# -*- coding: utf-8 -*-
"""Тесты PsycheEngine"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.services.npc.psyche_engine import (
    apply_stress, recover_stress, resolve_coercion,
    check_loyalty_break, get_behavior_hint
)

def make_npc(willpower=60, stress=20, breakpoint=80, state="free"):
    return {
        "name": "Тест",
        "drives": {"control": 0.4, "significance": 0.2, "fear": 0.3, "desire": 0.1},
        "psyche": {
            "willpower": willpower, "stress": stress, "breakpoint": breakpoint,
            "loyalty_true": 50, "loyalty_fake": 50,
            "state": state, "trauma_flags": []
        },
        "social_stats": {"trust": 0.5, "fear_of_player": 0.1},
        "routine": {"current": "working"},
    }

def test_stress_normal():
    npc = make_npc(stress=20)
    r = apply_stress(npc, 30)
    assert npc["psyche"]["stress"] == 50
    assert r["state_changed"] == False
    print("✅ apply_stress (нормальный стресс)")

def test_stress_breaks_will():
    npc = make_npc(willpower=60, stress=70, breakpoint=80)
    r = apply_stress(npc, 20)  # 70+20=90 > 80
    assert npc["psyche"]["state"] == "broken"
    assert r["state_changed"] == True
    print("✅ apply_stress (breakpoint → state=broken)")

def test_stress_capped_at_100():
    npc = make_npc(stress=90)
    apply_stress(npc, 50)
    assert npc["psyche"]["stress"] == 100
    print("✅ apply_stress (capped at 100)")

def test_recover_stress():
    npc = make_npc(stress=80)
    recover_stress(npc, ticks_safe=2)
    assert npc["psyche"]["stress"] <= 70
    print("✅ recover_stress")

def test_coercion_threat_submit():
    npc = make_npc(willpower=30, stress=50)
    r = resolve_coercion(npc, "threat", intensity=60)
    assert r["outcome"] in ("submit", "broken")
    print(f"✅ resolve_coercion (threat) → {r['outcome']}")

def test_coercion_resist():
    npc = make_npc(willpower=90, stress=5)
    r = resolve_coercion(npc, "threat", intensity=20)
    assert r["outcome"] == "resist"
    print("✅ resolve_coercion (высокая воля → resist)")

def test_loyalty_break():
    npc = make_npc(state="broken")
    npc["psyche"]["loyalty_true"] = -70
    # Запускаем несколько раз — вероятностная функция
    results = [check_loyalty_break(npc) for _ in range(20)]
    assert any(results), "При loyalty_true=-70 должно быть хоть одно предательство из 20"
    print("✅ check_loyalty_break (низкая лояльность → вероятность предательства)")

def test_behavior_hint_broken():
    npc = make_npc(state="broken", stress=90)
    hint = get_behavior_hint(npc)
    assert len(hint) > 5
    print(f"✅ get_behavior_hint (broken): {hint}")

if __name__ == "__main__":
    test_stress_normal()
    test_stress_breaks_will()
    test_stress_capped_at_100()
    test_recover_stress()
    test_coercion_threat_submit()
    test_coercion_resist()
    test_loyalty_break()
    test_behavior_hint_broken()
    print("\n✅✅✅ Все тесты PsycheEngine прошли!")
```

---

## 🗺️ Итоговая последовательность действий

| # | Действие | Файл | Время |
|---|----------|------|-------|
| 1 | Исправить `current_location` | `campaign_state.json` | 5 мин |
| 2 | Создать папку `data/npcs/` | — | 1 мин |
| 3 | Создать `major_npcs.json` | 5 NPC (см. выше) | 15 мин |
| 4 | Создать `mass_npc_templates.json` | 10 шаблонов | 10 мин |
| 5 | Создать `npc/__init__.py` | пустой | 1 мин |
| 6 | Создать `npc_cognition.py` | 3A.1 | 20 мин |
| 7 | Создать `psyche_engine.py` | 3A.2 | 20 мин |
| 8 | Создать `threat_assessor.py` | 3A.3 | 15 мин |
| 9 | Создать `perception_engine.py` | 3A.4 | 15 мин |
| 10 | Запустить тесты | `test_npc_cognition.py` | 5 мин |
| 11 | Запустить тесты | `test_psyche_engine.py` | 5 мин |
| 12 | Добавить импорты в `orchestrator.py` | 3A.5 | 5 мин |
| 13 | Добавить методы загрузки NPC | orchestrator | 15 мин |
| 14 | Расширить `_run_python_engines` | orchestrator | 20 мин |
| 15 | Запустить игру, проверить что NPC видны в ответах | — | 10 мин |

**Итого:** ~2–3 часа работы за один вечер.

---

## ✅ Критерии готовности 3A

После выполнения всех шагов:

```
✅ backend/app/services/npc/ существует (4 файла + __init__)
✅ backend/data/npcs/major_npcs.json — 5 NPC с полными данными
✅ backend/data/npcs/mass_npc_templates.json — 10 шаблонов
✅ test_npc_cognition.py — все 7 тестов зелёные
✅ test_psyche_engine.py — все 8 тестов зелёные
✅ В логах игры видно: threat_score, behavior_hint, npc_name
✅ DM агент получает "- Торнин: поведение: предлагает порядок..." в контексте
✅ campaign_state.json — current_location не "unknown"
```

После этого — переходите к **3B** (LifeEngine + KarmaEngine).
