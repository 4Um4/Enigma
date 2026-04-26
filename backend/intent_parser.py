"""
backend/intent_parser.py
Парсер текстовых намерений перемещения.
Использует pymorphy3 для морфологического анализа — любые формы глаголов.
"подойду к Люсе", "подошёл к стражнику", "пойти на север" — всё работает.
"""
from typing import List, Optional, Tuple

from dataclasses import dataclass
from typing import List, Optional, Tuple

import unicodedata

import pymorphy3

from npc_name_resolver import npc_id_to_display

_morph = pymorphy3.MorphAnalyzer()


@dataclass
class MovementIntent:
    """Извлечённое намерение перемещения"""
    direction: Optional[str] = None
    target_npc_id: Optional[str] = None
    target_display_name: str = ""
    raw_text: str = ""


# === Глаголы перемещения — начальные формы ===
_MOVE_LEMMATA = {
    "идти", "подойти", "пойти", "направиться", "брести", "шагать",
    "бежать", "спешить", "подкрасться", "отойти", "отступить",
    "уйти", "пятиться", "подъехать", "приблизиться", "сойти",
    "проникнуть", "вернуться", "двинуться", "подползти",
    "проскочить", "миновать", "добраться",
}

# === Направления ===
_DIRECTION_PATTERNS: List[Tuple[list[str], str]] = [
    (["север", "на север", "вверх", "наверх", "north"], "north"),
    (["юг", "на юг", "вниз", "внизу", "south"], "south"),
    (["восток", "на восток", "направо", "right", "east"], "east"),
    (["запад", "на запад", "налево", "left", "west"], "west"),
    (["северо-восток", "на северо-восток", "northeast"], "northeast"),
    (["северо-запад", "на северо-запад", "northwest"], "northwest"),
    (["юго-восток", "на юго-восток", "southeast"], "southeast"),
    (["юго-запад", "на юго-запад", "southwest"], "southwest"),
]

_DIRECTION_VECTORS = {
    "north": (0.0, -1.0),
    "south": (0.0, 1.0),
    "east": (1.0, 0.0),
    "west": (-1.0, 0.0),
    "northeast": (0.707, -0.707),
    "northwest": (-0.707, -0.707),
    "southeast": (0.707, 0.707),
    "southwest": (-0.707, 0.707),
}


def _is_movement_verb(text: str) -> bool:
    """Проверяет содержит ли текст глагол перемещения через pymorphy3"""
    words = text.lower().split()
    for word in words:
        for parsed in _morph.parse(word):
            if parsed.tag.POS in ("VERB", "INFN"):
                if parsed.normal_form in _MOVE_LEMMATA:
                    return True
    return False


def _extract_direction(text: str) -> Optional[str]:
    """Извлекает направление из текста"""
    text_lower = text.lower()
    for patterns, direction in _DIRECTION_PATTERNS:
        for pattern in patterns:
            if pattern in text_lower:
                return direction
    return None


def _normalize(s: str) -> str:
    """Нормализует Unicode для надёжного сравнения кириллицы"""
    return unicodedata.normalize("NFC", s.lower())


def _find_npc_by_name(text: str, npc_ids: List[str]) -> Optional[str]:
    """Ищет NPC по имени через pymorphy3 — любые падежи: 'к Люсе', 'Люсю', 'Люсой'"""
    words = text.lower().split()
    # Лемматизируем все слова текста один раз
    text_lemmata: set[str] = set()
    for word in words:
        for parsed in _morph.parse(word):
            if parsed.tag.POS == "NOUN":
                text_lemmata.add(parsed.normal_form)

    print(f"[INTENT] text_lemmata: {text_lemmata}")

    candidates: List[Tuple[str, str, int]] = []

    for npc_id in npc_ids:
        display_name = npc_id_to_display(npc_id)
        # Лемматизируем каждое слово display_name
        # Разбиваем display_name на отдельные слова и лемматизируем каждое
        name_lemmata: set[str] = set()
        for word in display_name.lower().split():
            for parsed in _morph.parse(word):
                if parsed.tag.POS == "NOUN":
                    name_lemmata.add(parsed.normal_form)
        # Фоллбэк: прямое сравнение слов для имён собственных
        text_words = set(text.lower().split())
        name_words = set(display_name.lower().split())
        direct_match = text_words & name_words
        match = (text_lemmata & name_lemmata) | direct_match
        if match:
            candidates.append((npc_id, display_name, len(display_name)))

    if not candidates:
        return None

    candidates.sort(key=lambda x: x[2], reverse=True)
    return candidates[0][0]


def parse_movement_intent(
    text: str,
    available_npc_ids: List[str],
) -> Optional[MovementIntent]:
    """
    Парсит текст и извлекает намерение перемещения.
    Возвращает None если текст не выглядит как перемещение.
    """
    if not _is_movement_verb(text):
        return None

    direction = _extract_direction(text)
    npc_id = _find_npc_by_name(text, available_npc_ids)

    if direction is None and npc_id is None:
        return None

    display_name = ""
    if npc_id:
        display_name = npc_id_to_display(npc_id)

    return MovementIntent(
        direction=direction,
        target_npc_id=npc_id,
        target_display_name=display_name,
        raw_text=text,
    )


def get_direction_vector(direction: str) -> Tuple[float, float]:
    """Возвращает (dx, dy) для направления"""
    return _DIRECTION_VECTORS.get(direction, (0.0, 0.0))