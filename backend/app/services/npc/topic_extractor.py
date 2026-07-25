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

from typing import Any, List, Optional

# T-01: Маппинги для генерации тем из состояния NPC
_DRIVE_TO_TOPIC: dict[str, str] = {
    "control": "власть",
    "significance": "статус",
    "fear": "безопасность",
    "desire": "желания",
}
_LIFE_PROJECT_TO_TOPIC: dict[str, str] = {
    "family_builder": "семья",
    "wealth_creator": "деньги",
    "warrior": "бой",
    "knowledge_seeker": "знания",
    "ruler": "власть",
    "isolation": "одиночество",
    "revenge": "месть",
    "survival": "выживание",
    "hermit": "покой",
}
_ROLE_TO_TOPIC: dict[str, str] = {
    "tavern_keeper": "таверна",
    "maid": "работа",
    "guard": "стража",
    "thief": "наблюдение",
    "blacksmith": "кузница",
    "merchant": "торговля",
}

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


# T-07: Маппинг фраз → тема (приоритет над одиночными ключевыми словами)
_PHRASE_TO_TOPIC: dict[str, str] = {
    "как дела": "самочувствие",
    "как ты": "самочувствие",
    "что нового": "новости",
    "расскажи о себе": "биография",
    "кто ты": "биография",
    "что знаешь": "слухи",
    "помоги": "помощь",
    "где": "место",
    "кто": "человек",
    "почему": "причина",
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
    npc_state: Optional[Any] = None,
) -> str:
    """
    Извлечь тему из контекста события.

    Приоритет:
    0. Если нет текстовых источников — тема из состояния NPC (drives, life_project, role)
    1. Ключевые слова в raw_input/scene_facts (конкретнее)
    2. Базовый маппинг event_type
    3. Пустая строка (тема не определена)
    """
    # T-01: Для idle-тиков приоритет у структурного состояния NPC (автономная тематическая жизнь).
    # STM не должно конкурировать с внутренним состоянием, если нет реального события.
    if event_type in ("idle", "world_tick") and npc_state is not None:
        _npc_dict = npc_state if isinstance(npc_state, dict) else {}
        # Приоритет: drives > life_project (core_orientation) > role
        _drives = _npc_dict.get("drives", {})
        if _drives:
            try:
                _dominant_drive = max(_drives.items(), key=lambda x: float(x[1]))[0]
                _topic = _DRIVE_TO_TOPIC.get(_dominant_drive)
                if _topic:
                    return _topic
            except (ValueError, TypeError):
                pass

        _life_project = _npc_dict.get("core_orientation", "")
        if _life_project:
            _topic = _LIFE_PROJECT_TO_TOPIC.get(_life_project)
            if _topic:
                return _topic

        _role = _npc_dict.get("_archetype", "")
        if _role:
            _topic = _ROLE_TO_TOPIC.get(_role)
            if _topic:
                return _topic

    # Склеиваем все текстовые источники для поиска ключевых слов
    _text_parts: list[str] = []
    if scene_facts:
        _text_parts.extend(scene_facts)
    if raw_input:
        _text_parts.append(raw_input)
    _combined = " ".join(_text_parts).lower()

    # T-07: Поиск по фразам (приоритет над одиночными ключевыми словами)
    for _phrase, _topic in _PHRASE_TO_TOPIC.items():
        if _phrase in _combined:
            return _topic

    # Поиск по ключевым словам — приоритет над event_type
    for _word, _topic in _TOPIC_KEYWORDS.items():
        if _word in _combined:
            return _topic

    # Фоллбэк на event_type
    return _EVENT_TOPIC_MAP.get(event_type, "наблюдение")
