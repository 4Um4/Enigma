# backend/app/services/action_classifier.py
"""
Action Classifier — мозг системы перед LLM.
Определяет тип действия игрока (0 ms) и какие агенты нужны.
Python считает — LLM только рассказывает.
"""

import re
import logging
from enum import Enum
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)


class ActionType(Enum):
    """Все возможные типы действий игрока (D&D 5e + sandbox)."""
    COMBAT = "COMBAT"                    # атака, бой
    SOCIAL = "SOCIAL"                    # разговор с одним NPC
    SOCIAL_MASS = "SOCIAL_MASS"          # обращение к толпе
    EXPLORE = "EXPLORE"                  # исследование, движение
    CRAFT_USE = "CRAFT_USE"              # использование предметов / заклинаний
    LORE_QUERY = "LORE_QUERY"            # вопросы по лору
    SANDBOX_MILD = "SANDBOX_MILD"        # безобидное нестандартное
    SANDBOX_SOCIAL = "SANDBOX_SOCIAL"    # социальное нарушение
    SANDBOX_PHYSICAL = "SANDBOX_PHYSICAL"# физическое нарушение
    ROMANCE = "ROMANCE"                  # романтика
    CAPTURE = "CAPTURE"                  # захват в плен
    FLEE = "FLEE"                        # побег
    LIFE_CHOICE = "LIFE_CHOICE"          # выбор жизни (фермер и т.п.)
    CHAR_CREATE = "CHAR_CREATE"          # создание персонажа
    UNKNOWN = "UNKNOWN"                  # fallback


class ActionClassifier:
    """Классификатор действий игрока по ключевым словам."""

    # Приоритет типов (если совпадает несколько — берём первый по этому списку)
    PRIORITY_ORDER: List[ActionType] = [
        ActionType.COMBAT,
        ActionType.CAPTURE,
        ActionType.SOCIAL_MASS,
        ActionType.SOCIAL,
        ActionType.EXPLORE,
        ActionType.FLEE,
        ActionType.ROMANCE,
        ActionType.LIFE_CHOICE,
        ActionType.SANDBOX_PHYSICAL,
        ActionType.SANDBOX_SOCIAL,
        ActionType.SANDBOX_MILD,
        ActionType.CRAFT_USE,
        ActionType.LORE_QUERY,
        ActionType.CHAR_CREATE,
        ActionType.UNKNOWN,
    ]

    # Словари ключевых слов и корней (русский + склонения)
    _KEYWORDS: Dict[ActionType, List[str]] = {
        ActionType.COMBAT: [
            "атак", "ударя", "бью", "режу", "стреля", "броса", "оружи", "меч", "лук",
            "убива", "убей", "рани", "драка", "ударил", "выстрел", "руби", "кидаю"
        ],
        ActionType.CAPTURE: [
            "плен", "связываю", "захват", "порабощ", "в плен", "арестов", "задерж"
        ],
        ActionType.SOCIAL_MASS: [
            "всем", "толпе", "горожан", "крич", "народ", "всем ", "крикну", "обращаюсь ко всем"
        ],
        ActionType.SOCIAL: [
            "говор", "скаж", "спрос", "убежд", "торг", "пуга", "соблазн", "привет",
            "здравствуй", "расскажи", "спроси", "ответь", "поговори"
        ],
        ActionType.EXPLORE: [
            "осматр", "ид", "исслед", "ищ", "открой", "вход", "посмотри", "вокруг",
            "обслед", "иду", "вхожу", "открываю"
        ],
        ActionType.FLEE: [
            "убега", "спасаюсь", "отступ", "бегу", "сдаюсь", "спасение", "побег"
        ],
        ActionType.ROMANCE: [
            "ухажива", "флирту", "влюбл", "провожу ночь", "сплю с", "целую", "обнима",
            "поцелуй", "роман", "ухаживаю"
        ],
        ActionType.LIFE_CHOICE: [
            "хочу стать", "покупаю дом", "строю", "женюсь", "фермер", "дом", "землю",
            "женитьба", "семья"
        ],
        ActionType.SANDBOX_PHYSICAL: [
            "мочусь", "расстёгиваю", "нужду", "пися", "срать", "дерусь грязно",
            "справляю нужду", "мочиться"
        ],
        ActionType.SANDBOX_SOCIAL: [
            "оскорб", "провоцир", "руга", "мат", "обзыва", "провокация"
        ],
        ActionType.SANDBOX_MILD: [
            "пою", "танцую", "сплю", "отдыха", "ем", "танец", "песня"
        ],
        ActionType.CRAFT_USE: [
            "использу", "созда", "применя", "достаю", "вытащ", "каст", "заклинание",
            "зелье", "применить", "использовать"
        ],
        ActionType.LORE_QUERY: [
            "что такое", "кто такой", "расскажи о", "объясни", "откуда", "кто это",
            "история", "кто такой"
        ],
        ActionType.CHAR_CREATE: [
            "созда", "персонаж", "кто я", "мой персонаж", "начало игры", "создать персонажа"
        ],
    }

    def classify(self, text: str) -> ActionType:
        """
        Определяет тип действия.
        Возвращает первый совпавший тип по приоритету.
        """
        if not text or not text.strip():
            return ActionType.UNKNOWN

        lower = text.lower().strip()

        for action_type in self.PRIORITY_ORDER:
            keywords = self._KEYWORDS.get(action_type, [])
            if any(kw in lower for kw in keywords):
                logger.debug(f"Action classified: {action_type.value} | text: {text[:60]}...")
                return action_type

        logger.debug(f"Action classified: UNKNOWN | text: {text[:60]}...")
        return ActionType.UNKNOWN

    def get_required_agents(self, action_type: ActionType, npc_present: bool = False) -> Tuple[List[str], Dict[str, bool]]:
        """
        Возвращает список нужных агентов + флаги.
        Формат: (["agent1", "agent2"], {"unconventional": True, "magic": False})
        """
        agents: List[str] = ["dm"]          # всегда нужен DM
        flags: Dict[str, bool] = {"unconventional": False, "magic": False}

        if action_type == ActionType.COMBAT:
            agents = ["rules", "dm"]

        elif action_type in (ActionType.SOCIAL, ActionType.ROMANCE):
            agents = ["npc_major", "dm"] if npc_present else ["dm"]

        elif action_type == ActionType.SOCIAL_MASS:
            agents = ["npc_mass", "dm"]

        elif action_type in (ActionType.EXPLORE, ActionType.LORE_QUERY, ActionType.CHAR_CREATE):
            agents = ["dm"]

        elif action_type == ActionType.CAPTURE:
            agents = ["npc_major", "dm"] if npc_present else ["npc_mass", "dm"]

        elif action_type == ActionType.CRAFT_USE:
            # TODO: в будущем можно добавить проверку на заклинания (magic=True)
            agents = ["rules", "dm"]
            flags["magic"] = "заклинание" in action_type.name.lower()  # заглушка

        elif action_type in (ActionType.SANDBOX_MILD, ActionType.SANDBOX_SOCIAL,
                             ActionType.SANDBOX_PHYSICAL, ActionType.FLEE,
                             ActionType.LIFE_CHOICE):
            agents = ["dm"]
            flags["unconventional"] = True

        logger.debug(f"Required agents for {action_type.value}: {agents} | flags: {flags}")
        return agents, flags


# Для удобного импорта в orchestrator.py и тестах
classifier = ActionClassifier()