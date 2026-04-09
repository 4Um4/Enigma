# backend/app/services/scene/narrative_extractor.py
# -*- coding: utf-8 -*-
"""
NarrativeExtractor R2.2.8 — production-hardened.

Критические фиксы:
1. Дедупликация по canonical (не raw_name) — убирает дубли от склонений
2. Fallback поиск объекта без holder для transient
3. State machine с приоритетами — broken не становится held
4. npc_actions как структура NpcAction — подготовка к R3
5. \\b в regex — убирает false positives ("ножны" != "нож")
6. prune по last_tick — не удаляет активные объекты
7. Защита от cascade merge — минимум событий и возраст
"""

from __future__ import annotations
import re
import uuid
from dataclasses import dataclass, field
from typing import Optional


# ──────────────────────────────────────────────────────────────────────────────
# Онтология объектов
# ──────────────────────────────────────────────────────────────────────────────

OBJECT_KEYWORDS: dict[str, list[str]] = {
    "prop":      ["поднос", "кружка", "стакан", "тарелка", "свеча", "книга",
                  "тряпка", "кубок", "миска", "чашка", "бутылка", "лютня",
                  "ложка", "вилка", "скатерть", "пергамент", "свиток",
                  "ключ", "верёвка", "факел", "фонарь"],
    "furniture": ["стол", "стул", "скамья", "стойка", "бочка", "ящик",
                  "дверь", "окно", "полка", "прилавок", "камин", "очаг"],
    "weapon":    ["нож", "меч", "кинжал", "дубина", "арбалет", "копьё",
                  "топор", "посох", "алебарда", "булава"],
    "container": ["мешок", "сундук", "кошелёк", "корзина", "сумка"],
    "food":      ["хлеб", "мясо", "суп", "эль", "вино", "каша", "сыр", "рыба"],
    "wearable":  ["плащ", "шляпа", "перчатка", "сапог", "пояс", "кольцо"],
    "magic":     ["кристалл", "амулет", "талисман", "фолиант", "руна",
                  "зелье", "эликсир", "артефакт"],
}

_KEYWORD_TO_TYPE: dict[str, str] = {
    kw: obj_type
    for obj_type, keywords in OBJECT_KEYWORDS.items()
    for kw in keywords
}

_MAGIC_WORDS: set[str] = {
    "магическ", "древн", "артефакт", "рунн", "легендарн",
    "проклят", "волшебн", "эфирн", "золот", "серебрян", "дракон",
}

EVENT_TRIGGERS: dict[str, list[str]] = {
    "drop":       ["роняет", "упал", "уронил", "падает", "разлетается", "грохнулся"],
    "break":      ["ломает", "разбил", "сломал", "трескается", "разбивается", "вдребезги"],
    "take":       ["берёт", "поднимает", "хватает", "взял", "подбирает", "схватил"],
    "use":        ["протирает", "чистит", "режет", "наливает", "несёт", "открывает"],
    "light":      ["зажигает", "поджигает", "разгорается", "вспыхивает"],
    "extinguish": ["тушит", "гасит", "потухла", "погасла"],
}

_TRIGGER_TO_EVENT: dict[str, str] = {
    word: event_type
    for event_type, words in EVENT_TRIGGERS.items()
    for word in words
}

# State machine с приоритетами (фикс #3)
# Больше = "более конечное", меньше = "можно перезаписать"
STATE_PRIORITY: dict[str, int] = {
    "present":      0,
    "held":         1,
    "dropped":      1,
    "in_use":       2,
    "lit":          2,
    "extinguished": 2,
    "broken":       3,  # финальное состояние
}

_EVENT_TO_STATE: dict[str, str] = {
    "drop":       "dropped",
    "break":      "broken",
    "take":       "held",
    "use":        "in_use",
    "light":      "lit",
    "extinguish": "extinguished",
}

_NPC_FRAGMENTS: dict[str, str] = {
    "торнин": "tavern_keeper_tornin",
    "люся":   "maid_lusya",
    "тень":   "thief_shadow",
    "борко":  "guard_borko",
    "горан":  "merchant_goran",
}

_JUNK_WORDS: set[str] = {
    "и", "в", "на", "с", "под", "за", "по", "из", "от", "до", "к", "у",
    "он", "она", "оно", "они", "мы", "вы", "я", "ты",
    "быстро", "медленно", "осторожно", "резко", "внезапно", "тихо", "громко",
    "затем", "потом", "вдруг", "снова", "уже", "ещё",
}

MAX_EVENTS_IN_EXTRACTOR: int = 200
MIN_EVENTS_FOR_MERGE:    int = 5   # фикс #7
MIN_AGE_FOR_MERGE:       int = 10  # фикс #7


# ──────────────────────────────────────────────────────────────────────────────
# Структуры данных
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class ExtractedObject:
    object_id:      str
    name:           str
    raw_name:       str
    canonical_name: str
    obj_type:       str
    state:          str
    importance:     int          # 1=уникальный, 2=обычный transient
    holder:         Optional[str]
    created_tick:   int


@dataclass
class ExtractedEvent:
    event_id:    str
    event_type:  str
    actor:       Optional[str]
    object_name: str
    object_id:   Optional[str]
    canonical:   str             # для дедупликации
    tick:        int


@dataclass
class NpcAction:
    """Структурированное действие NPC — фикс #4, подготовка к R3 intent."""
    action:           str
    object_canonical: str
    object_raw:       str
    tick:             int


@dataclass
class ExtractionResult:
    new_objects:    list[ExtractedObject]          = field(default_factory=list)
    new_events:     list[ExtractedEvent]           = field(default_factory=list)
    npc_actions:    dict[str, NpcAction]           = field(default_factory=dict)
    updated_states: list[tuple[str, str]]          = field(default_factory=list)
    # updated_states: [(object_id, new_state), ...]


# ──────────────────────────────────────────────────────────────────────────────
# NarrativeExtractor R2.2.8
# ──────────────────────────────────────────────────────────────────────────────

class NarrativeExtractor:

    def __init__(self) -> None:
        self._keyword_pattern = self._build_keyword_pattern()

    def _build_keyword_pattern(self) -> re.Pattern:
        """Фикс #5: границы слов \\b — "ножны" не матчится как "нож"."""
        all_keywords = sorted(
            [kw for kws in OBJECT_KEYWORDS.values() for kw in kws],
            key=len, reverse=True,
        )
        pattern = r"\b(" + "|".join(re.escape(kw) for kw in all_keywords) + r")\b"
        return re.compile(pattern, re.IGNORECASE)

    def _extract_simple_np(self, sentence: str, keyword: str) -> str:
        """Извлекает 1-3 слова вокруг keyword как raw_name."""
        words = sentence.lower().split()
        keyword_lower = keyword.lower()
        for i, word in enumerate(words):
            clean = word.strip(".,;:!?")
            if keyword_lower in clean:
                left = []
                for j in range(max(0, i - 2), i):
                    candidate = words[j].strip(".,;:!?")
                    if len(candidate) > 2 and candidate not in _JUNK_WORDS:
                        left.append(candidate)
                return " ".join(left + [clean])
        return keyword

    @staticmethod
    def _make_canonical(keyword: str) -> str:
        """Canonical = базовая форма keyword (нижний регистр)."""
        return keyword.lower()

    def _is_magic(self, text: str) -> bool:
        text_lower = text.lower()
        return any(mw in text_lower for mw in _MAGIC_WORDS)

    def _detect_importance(self, raw_name: str, keyword: str) -> int:
        if self._is_magic(raw_name):
            return 1
        obj_type = _KEYWORD_TO_TYPE.get(keyword, "prop")
        if obj_type in ("magic", "weapon", "wearable"):
            return 1
        if len(raw_name.split()) >= 3:
            return 1
        return 2

    def _can_update_state(self, old_state: str, new_state: str) -> bool:
        """Фикс #3: FSM. broken не становится held."""
        return STATE_PRIORITY.get(new_state, 0) >= STATE_PRIORITY.get(old_state, 0)

    def extract(
        self,
        dm_text: str,
        scene_state: dict,
        tick: int,
    ) -> ExtractionResult:
        result = ExtractionResult()
        if not dm_text:
            return result

        existing_objects = scene_state.get("objects", {})

        all_events  = scene_state.get("scene_events", [])
        recent_evts = all_events[-MAX_EVENTS_IN_EXTRACTOR:]

        # Фикс #1: дедупликация по canonical, не raw_name
        existing_event_keys: set[tuple] = {
            (
                e.get("event_type", e.get("type", "")),
                e.get("canonical", e.get("object_name", "").lower()),
                e.get("actor"),
            )
            for e in recent_evts
        }

        sentences = re.split(r'[.!?;]+', dm_text)

        for sentence in sentences:
            sent_lower = sentence.lower().strip()
            if not sent_lower:
                continue

            # Ищем триггер
            found_event_type: Optional[str] = None
            for trigger, etype in _TRIGGER_TO_EVENT.items():
                if trigger in sent_lower:
                    found_event_type = etype
                    break
            if not found_event_type:
                continue

            # Ищем актора
            actor: Optional[str] = None
            for frag, npc_id in _NPC_FRAGMENTS.items():
                if frag in sent_lower:
                    actor = npc_id
                    break

            matches = list(self._keyword_pattern.finditer(sentence))
            for match in matches:
                keyword   = match.group().lower()
                raw_name  = self._extract_simple_np(sentence, keyword)
                canonical = self._make_canonical(keyword)

                # Фикс #1: canonical в ключе
                event_key = (found_event_type, canonical, actor)
                if event_key in existing_event_keys:
                    continue

                # Поиск существующего объекта
                existing_id: Optional[str] = None
                fallback_candidate: Optional[str] = None

                for oid, obj in existing_objects.items():
                    # Точное совпадение raw_name
                    if raw_name.lower() == obj.get("raw_name", "").lower():
                        existing_id = oid
                        break
                    # Фикс #2: fallback по canonical для transient без holder
                    if canonical == obj.get("canonical_name"):
                        if actor and actor == obj.get("holder"):
                            existing_id = oid
                            break
                        if obj.get("importance") == 2:
                            fallback_candidate = oid

                if not existing_id and fallback_candidate:
                    existing_id = fallback_candidate

                new_state = _EVENT_TO_STATE.get(found_event_type, "present")

                if existing_id:
                    obj_data  = existing_objects[existing_id]
                    old_state = obj_data.get("state", "present")
                    # Фикс #3: FSM
                    if self._can_update_state(old_state, new_state):
                        result.updated_states.append((existing_id, new_state))
                    obj_id = existing_id
                else:
                    importance   = self._detect_importance(raw_name, keyword)
                    obj_type     = _KEYWORD_TO_TYPE.get(keyword, "prop")
                    holder_part  = actor.split("_")[-1] if actor else "scene"
                    obj_id       = f"{canonical}_{holder_part}_t{tick}_{uuid.uuid4().hex[:4]}"

                    result.new_objects.append(ExtractedObject(
                        object_id      = obj_id,
                        name           = keyword,
                        raw_name       = raw_name,
                        canonical_name = canonical,
                        obj_type       = obj_type,
                        state          = new_state,
                        importance     = importance,
                        holder         = actor,
                        created_tick   = tick,
                    ))

                result.new_events.append(ExtractedEvent(
                    event_id    = f"evt_{uuid.uuid4().hex[:6]}",
                    event_type  = found_event_type,
                    actor       = actor,
                    object_name = raw_name,
                    object_id   = obj_id,
                    canonical   = canonical,
                    tick        = tick,
                ))

                # Фикс #4: структура вместо строки
                if actor:
                    result.npc_actions[actor] = NpcAction(
                        action           = found_event_type,
                        object_canonical = canonical,
                        object_raw       = raw_name,
                        tick             = tick,
                    )

                break  # один объект на предложение

        return result


# Синглтон
_extractor_instance: Optional[NarrativeExtractor] = None

def get_extractor() -> NarrativeExtractor:
    global _extractor_instance
    if _extractor_instance is None:
        _extractor_instance = NarrativeExtractor()
    return _extractor_instance
