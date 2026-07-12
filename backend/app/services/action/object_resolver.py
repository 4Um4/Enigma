from __future__ import annotations
# backend/app/services/action/object_resolver.py
"""
ObjectResolver — поиск объекта сцены по тексту действия игрока.

Принцип:
  1. pymorphy2 приводит слова текста к нормальной форме (лемме)
  2. Леммы сравниваются с именами объектов в SceneState
  3. Возвращается конкретный instance_id или None

Никакого хардкода объектов — всё из SceneState.
Работает для любой локации и любого набора объектов.
"""

import logging
from typing import Optional
import pymorphy3 as pymorphy2
import re

logger = logging.getLogger(__name__)

# Синглтон анализатора — инициализация дорогая, делаем один раз
_morph: Optional[pymorphy2.MorphAnalyzer] = None


def _get_morph() -> pymorphy2.MorphAnalyzer:
    global _morph
    if _morph is None:
        _morph = pymorphy2.MorphAnalyzer()
    return _morph


def _lemmatize(text: str) -> set[str]:
    """
    Приводит все слова текста к нормальной форме.
    "переворачиваю стол" → {"переворачивать", "стол"}
    "к барной стойке" → {"к", "барный", "стойка"}
    """
    morph = _get_morph()
    words = text.lower().split()
    lemmas = set()
    for word in words:
        parsed = morph.parse(word)
        if parsed:
            lemmas.add(parsed[0].normal_form)
    return lemmas


def _lemmatize_phrase(phrase: str) -> set[str]:
    """Леммы для имени объекта из SceneState."""
    return _lemmatize(phrase)


def resolve_object(
    action_text: str,
    scene_state: Optional[dict],
) -> Optional[str]:
    """
    Ищет объект в SceneState который упоминается в тексте действия.

    Алгоритм:
      1. Лемматизируем текст действия
      2. Для каждого объекта в scene_state.objects:
         - берём его name (и instance_of если есть)
         - лемматизируем
         - если пересечение лемм непустое → матч
      3. Возвращаем первый найденный obj_id

    Примеры:
      "переворачиваю стол" + objects с "столы #1" → "tables_1"
      "разбиваю стакан" + objects с "барная стойка" → None
      "поджигаю свечу" + objects с "свечи" → "candles_main"

    Возвращает obj_id или None.
    """
    if not scene_state:
        return None

    objects = scene_state.get("objects", {})
    if not objects:
        return None

    action_lemmas = _lemmatize(action_text)

    best_match_id: Optional[str] = None
    best_score = 0

    for obj_id, obj_data in objects.items():
        # Собираем все варианты имени объекта
        name_variants: list[str] = []

        name = obj_data.get("name", "")
        if name:
            # Убираем суффикс "#N" у инстансов: "столы #3" → "столы"
            clean_name = name.split("#")[0].strip()
            name_variants.append(clean_name)

        # instance_of даёт нам базовый id: "tables_1" → "tables"
        instance_of = obj_data.get("instance_of", "")
        if instance_of:
            # "tables" → "стол" не напрямую, но лемма имени уже покрывает
            pass

        # Лемматизируем все варианты имени
        obj_lemmas: set[str] = set()
        for variant in name_variants:
            obj_lemmas |= _lemmatize_phrase(variant)

        # Пересечение лемм
        intersection = action_lemmas & obj_lemmas
        score = len(intersection)

        if score > best_score:
            best_score = score
            best_match_id = obj_id

    if best_match_id and best_score > 0:
        logger.debug(
            f"[OBJECT_RESOLVER] '{action_text[:40]}' → {best_match_id!r} "
            f"(score={best_score})"
        )
        return best_match_id

    return None


def resolve_object_group(
    action_text: str,
    scene_state: Optional[dict],
) -> list[str]:
    """
    Возвращает конкретный инстанс объекта с учётом номера из текста.
    "ломаю стол №5" → ["tables_5"]
    "ломаю стол" → ["tables_3"] (первый найденный)
    """
    if not scene_state:
        return []

    first_match = resolve_object(action_text, scene_state)
    if not first_match:
        return []

    objects = scene_state.get("objects", {})
    first_obj = objects.get(first_match, {})
    base_group = first_obj.get("instance_of", first_match)

    # Все инстансы группы
    group = [
        obj_id
        for obj_id, obj_data in objects.items()
        if obj_data.get("instance_of", obj_id) == base_group
    ]

    # Ищем явный номер в тексте: "№5", "#5", "номер 5", "пятый"
    number_match = re.search(r"[№#]\s*(\d+)|номер\s+(\d+)", action_text.lower())
    if number_match:
        n = int(number_match.group(1) or number_match.group(2))
        specific = f"{base_group}_{n}"
        if specific in objects:
            return [specific]

    return group[:1] if group else []
