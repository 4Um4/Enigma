# backend/app/services/npc/topic_extractor.py
"""
ФАЗА 4: TopicExtractor — извлечение темы для NPC вербализации.

По Уставу 3.2: topic заполняется ДО DecisionHub.
В текущем pipeline DecisionHub не производит CommunicationIntent,
поэтому TopicExtractor вызывается при сборке VerbalizationContext.

Принцип: простой Python-маппинг, не LLM.
event_type → базовая тема
scene_facts → уточнение через ключевые слова

path: /backend/app/services/npc/topic_extractor.py
Назначение: Извлечение темы из event_type + scene_facts для VerbalizationContext (Фаза 4 по Уставу)
Зависимости: typing
Основные сущности: extract_topic
"""

from typing import List, Optional

# Базовый маппинг event_type → topic
_EVENT_TOPIC_MAP: dict[str, str] = {
    "player_attacks": "нападение",
    "player_attack": "нападение",
    "combat": "бой",
    "player_interacts": "разговор",
    "dialogue": "разговор",
    "player_speaks": "разговор",
    "theft": "кража",
    "intimidation": "угроза",
    "player_threatens": "угроза",
    "player_insults": "оскорбление",
    "help": "помощь",
    "trade": "торговля",
    "capture": "задержание",
    "proximity_close": "встреча",
    "npc_interacts_npc": "встреча",
    "npc_proximity_close": "встреча",
    # world_tick не маппится — proactive topic формируется из STM + L2 (Устав 3.2)
}


# Ключевые слова → уточнение темы
_TOPIC_KEYWORDS: dict[str, str] = {
    "торговля": "торговля",
    "купить": "торговля",
    "продать": "торговля",
    "цена": "торговля",
    "монет": "торговля",
    "гильдия": "гильдия",
    "воры": "гильдия",
    "подвал": "подвал",
    "тайник": "тайник",
    "ход": "проход",
    "борко": "стража",
    "страж": "стража",
    "охран": "стража",
    "кузнец": "кузнец",
    "орм": "кузнец",
    "торнин": "таверна",
    "таверна": "таверна",
    "оружие": "оружие",
    "меч": "оружие",
    "лук": "оружие",
    "зелье": "зелья",
    "эликсир": "зелья",
    "квест": "задание",
    "работа": "задание",
    "доставка": "задание",
}


def extract_topic(
    event_type: str,
    scene_facts: Optional[List[str]] = None,
    raw_input: Optional[str] = None,
) -> str:
    """
    Извлечь тему из контекста события.

    Приоритет:
    1. Ключевые слова в raw_input/scene_facts (конкретнее)
    2. Базовый маппинг event_type
    3. Пустая строка (тема не определена)
    """
    # Склеиваем все текстовые источники для поиска ключевых слов
    _text_parts: list[str] = []
    if scene_facts:
        _text_parts.extend(scene_facts)
    if raw_input:
        _text_parts.append(raw_input)
    _combined = " ".join(_text_parts).lower()

    # Поиск по ключевым словам — приоритет над event_type
    for _word, _topic in _TOPIC_KEYWORDS.items():
        if _word in _combined:
            return _topic

    # Фоллбэк на event_type
    return _EVENT_TOPIC_MAP.get(event_type, "наблюдение")
