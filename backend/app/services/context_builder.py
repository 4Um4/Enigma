"""
Dynamic Context Builder - умный сборщик контекста для LLM.
Берёт горячую память + релевантные факты из CampaignState.
"""
import re
from typing import Any, Optional

from app.services.campaign_state_service import get_campaign_state_service
from app.services.prompt_loader import load_system_prompt
from app.core.config import settings


# Глобальная переменная для кэширования системного промпта
_system_prompt_cache: Optional[str] = None


def get_system_prompt() -> str:
    """Получить системный промпт из файла с кэшированием."""
    global _system_prompt_cache
    if _system_prompt_cache is None:
        try:
            _system_prompt_cache = load_system_prompt(settings.system_prompt_file)
        except (FileNotFoundError, ValueError):
            # Fallback - используем встроенный промт
            _system_prompt_cache = _get_fallback_system_prompt()
    return _system_prompt_cache


def _get_fallback_system_prompt() -> str:
    """Встроенный промт на случай если файл не найден."""
    return """Ты — Опытный Dungeon Master (D&D 5e). Твой стиль — живой, литературный, без канцеляризмов.

ПРАВИЛА БРОСКОВ:
1. Запрещено требовать броски для рутинных действий (купить эль, выпить, войти в дверь).
2. Бросок d20 требуется только если есть реальный риск провала (подкуп, взлом, бой).
3. Если игрок просто говорит "Я пью эль" — опиши вкус и атмосферу. Без кубиков.

СТИЛЬ РЕЧИ:
- Не используй фразы типа "Куда вы хотели получить...", "Оформите заказ...".
- Говори как рассказчик: "Торбин наливает вам пенный эль...".
- Никогда не пиши за игрока.
- Никогда не выводи теги <system> в ответе."""


def extract_keywords(text: str) -> list[str]:
    """
    Простое извлечение ключевых слов из текста.
    Удаляет стоп-слова и возвращает список значимых слов.
    """
    # Стоп-слова для русского языка
    stop_words = {
        'в', 'на', 'с', 'со', 'по', 'к', 'за', 'из', 'от', 'до', 'для', 'о', 'об', 'у', 'при', 'над', 'под',
        'и', 'а', 'но', 'или', 'да', 'же', 'ли', 'бы', 'не', 'что', 'как', 'так', 'это', 'тот', 'этот',
        'я', 'ты', 'он', 'она', 'оно', 'мы', 'вы', 'они', 'его', 'её', 'их', 'его', 'ее',
        'быть', 'был', 'была', 'было', 'были', 'есть', 'будет', 'будут',
        'мой', 'твой', 'наш', 'ваш', 'свой',
        'который', 'какой', 'что', 'кто', 'где', 'когда', 'почему', 'зачем',
        'хочу', 'хотим', 'хотите', 'можем', 'можете', 'может', 'могут',
        'идти', 'идем', 'идете', 'идут', 'пойти', 'пошли',
        'вижу', 'видим', 'видите', 'видят', 'посмотреть', 'смотреть',
        'говорить', 'говорю', 'говорим', 'сказать', 'скажу', 'скажи',
        'сделать', 'делать', 'сделаю', 'делаю', 'сделаем',
        'нужно', 'надо', 'можн', 'необходим',
        'выйти', 'войти', 'выйдем', 'войдем',
        'начать', 'начинать', 'начали', 'начинаем',
        'встать', 'вставать', 'сесть', 'садиться',
        'быстрый', 'быстро', 'медленный', 'медленно',
        'большой', 'маленький', 'хороший', 'плохой',
        'один', 'два', 'три', 'четыре', 'пять',
        'первый', 'второй', 'третий',
        'весь', 'все', 'всё', 'каждый', 'любой',
        'только', 'уже', 'еще', 'ещё', 'тоже', 'также',
        'сегодня', 'завтра', 'вчера', 'сейчас', 'потом', 'потому',
        'если', 'когда', 'пока', 'дождёмся', 'ждать',
        'мастер', 'пожалуйста', 'спасибо', 'здравствуй', 'привет', 'прощай', 'пока',
    }
    
    # Очищаем текст и разбиваем на слова
    text_lower = text.lower()
    # Удаляем знаки препинания
    text_clean = re.sub(r'[^\w\s]', ' ', text_lower)
    words = text_clean.split()
    
    # Фильтруем стоп-слова и короткие слова
    keywords = [w for w in words if w not in stop_words and len(w) > 2]
    
    return keywords


def find_relevant_facts(
    campaign_id: str,
    user_query: str,
    max_facts: int = 5
) -> list[dict[str, Any]]:
    """
    Умный поиск фактов с весами и семантическими связями.
    """
    campaign_service = get_campaign_state_service()
    all_facts = campaign_service.get_world_facts(campaign_id)
    
    if not all_facts:
        return []

    keywords = extract_keywords(user_query)
    if not keywords:
        # Возвращаем последние факты если нет ключевых слов
        return [
            {"text": f.text, "category": f.category, "tags": f.tags}
            for f in all_facts[-max_facts:]
        ]

    # Семантические связи - если игрок ищет X, могут быть важны факты про Y
    semantic_links = {
        'леч': ['клирик', 'зелье', 'храм', 'аптекарь', 'целитель', 'магия', 'исцел'],
        'торг': ['купец', 'лавка', 'рынок', 'золото', 'цена', 'покупк', 'продаж'],
        'враг': ['монстр', 'злодей', 'босс', 'враг', 'противник', 'нежить', 'дракон'],
        'дом': ['жилище', 'квартир', 'убежище', 'таверн', 'гостинниц'],
        'квест': ['задание', 'поручение', 'миссия', 'цель', 'награда'],
        'оружи': ['меч', 'щит', 'лук', 'посох', 'оружие', 'броня'],
        'маг': ['заклинани', 'волшебник', 'магия', 'руна'],
        'бой': ['атака', 'защита', 'урон', 'бросок', 'кубик'],
    }

    scored_facts = []
    for fact in all_facts:
        score = 0
        fact_text_lower = fact.text.lower()
        fact_tags = " ".join(fact.tags).lower()
        fact_combined = f"{fact_text_lower} {fact_tags}"

        # 1. Прямое совпадение ключевых слов (высокий вес)
        for kw in keywords:
            if kw in fact_combined:
                score += 5

        # 2. Семантические связи (средний вес)
        for kw in keywords:
            for trigger, associates in semantic_links.items():
                if trigger in kw:  # Если ключевое слово содержит корень
                    for assoc in associates:
                        if assoc in fact_combined:
                            score += 3
                            break

        # 3. Вес по категории
        if 'npc' in fact.category and any(k in keywords for k in ['кто', 'имя', 'звать', 'встрет']):
            score += 2
        if 'location' in fact.category and any(k in keywords for k in ['идти', 'найти', 'где', 'дорог']):
            score += 2

        if score > 0:
            scored_facts.append({
                "fact": fact,
                "score": score,
                "text": fact.text,
                "category": fact.category,
                "tags": fact.tags
            })

    # Сортировка и отбор
    scored_facts.sort(key=lambda x: x["score"], reverse=True)
    
    return [
        {
            "text": item["text"],
            "category": item["category"],
            "tags": item["tags"]
        }
        for item in scored_facts[:max_facts]
    ]


def build_dynamic_context(
    session_history: list[dict[str, Any]],
    campaign_id: str,
    user_query: str,
    world_canon: Optional[list[dict[str, Any]]] = None,
    max_facts: int = 3,
    max_recent_messages: int = 5
) -> str:
    """
    Собирает умный контекст: канон + релевантные факты + сессия.
    """
    campaign_service = get_campaign_state_service()
    
    # 1. Горячая память (последние сообщения)
    recent_messages = session_history[-max_recent_messages:] if session_history else []
    recent_block = ""
    if recent_messages:
        recent_lines = []
        for msg in recent_messages:
            if "player_text" in msg:
                recent_lines.append(f"Игрок: {msg['player_text']}")
            if "dm_response" in msg:
                # Обрезаем длинные ответы
                resp = msg["dm_response"]
                if len(resp) > 300:
                    resp = resp[:300] + "..."
                recent_lines.append(f"Мастер: {resp}")
        recent_block = "\n".join(recent_lines)
    
    # 2. Поиск релевантных фактов
    relevant_facts = find_relevant_facts(campaign_id, user_query, max_facts)
    
    if relevant_facts:
        facts_lines = [
            f"• [{f['category'].upper()}] {f['text']}"
            for f in relevant_facts
        ]
        facts_block = "\n".join(facts_lines)
    else:
        facts_block = "• (нет сохранённых фактов о мире)"
    
    # 3. Канон мира (если передан)
    world_block = ""
    if world_canon:
        # Берем последние записи из канона
        recent_canon = world_canon[-2:] if len(world_canon) > 2 else world_canon
        canon_lines = []
        for entry in recent_canon:
            text = entry.get("text", str(entry))
            if len(text) > 200:
                text = text[:200] + "..."
            source = entry.get("source_file", "источник неизвестен")
            canon_lines.append(f"• [{source}] {text}")
        if canon_lines:
            world_block = "\n📜 КАНОН МИРА:\n" + "\n".join(canon_lines)
    
    # 4. Получаем системный промпт из файла
    system_prompt = get_system_prompt()
    
    # 5. Собираем финальный промпт с системным промптом из файла
    prompt = f"""<system>
{system_prompt}

### РЕЛЕВАНТНЫЕ ФАКТЫ КАМПАНИИ:
{facts_block}
{world_block}

### ПОСЛЕДНИЕ СОБЫТИЯ:
{recent_block if recent_block else '(нет предыдущих сообщений)'}

Текущий запрос игрока: {user_query}

Ответ мастера:</system>"""

    return prompt


def build_simple_context(
    user_query: str,
    campaign_id: str,
    world_canon: Optional[list[dict[str, Any]]] = None,
    max_facts: int = 4
) -> str:
    """
    Упрощённая версия build_dynamic_context для случая без истории сессии.
    """
    return build_dynamic_context(
        session_history=[],
        campaign_id=campaign_id,
        user_query=user_query,
        world_canon=world_canon,
        max_facts=max_facts,
        max_recent_messages=0
    )

