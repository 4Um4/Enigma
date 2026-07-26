from __future__ import annotations

# backend/app/services/action/dm_router.py
"""
path: backend/app/services/action/dm_router.py
Назначение: Этап 1 DM System — парсинг сырого текста в RawEvent (факты текста).
Зависимости: Нет (чистый парсер)
Основные сущности: DMRouter, RawEvent, RouterResult, RouterError

ПРИНЦИП: Router не знает мир. Router не знает NPC. Router не знает успех.
"""

import json
import logging
import re

logger = logging.getLogger(__name__)

# --- Инициализация данных на уровне модуля (Data-Driven) ---
import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List, Optional

_module_logger = logging.getLogger(__name__)

_INSULTS_PATH = Path(__file__).parent.parent.parent.parent / "data" / "insults_ru.json"
try:
    _INSULT_ROOTS: set[str] = set(json.loads(_INSULTS_PATH.read_text("utf-8-sig"))["roots"])
except Exception as _insult_err:
    # ИСПРАВЛЕНО: раньше empty set молча глотал ошибку → оскорбления
    # не распознавались без видимой причины. Теперь WARN в лог.
    _module_logger.warning(
        f"[DM_ROUTER] insults_ru.json not loaded ({_insult_err}). "
        f"Insult detection DISABLED. Path: {_INSULTS_PATH}"
    )
    _INSULT_ROOTS: set[str] = set()

_DIRECTED_AT_PATTERN = re.compile(
    r"(?i)\b(ты|тебя|тебе|вас|вам|твой|твоя|твоё|твои|вы)\b"
)

# Инициализация морфологии один раз (Optional Dependency: Degraded Mode if missing)
_MORPH = None
try:
    import pymorphy3 as pymorphy

    _MORPH = pymorphy.MorphAnalyzer()
except ImportError:
    _module_logger.warning(
        "[DM_ROUTER] pymorphy3 NOT INSTALLED. Lemmatization DISABLED (Degraded Mode). "
        "Intent extraction accuracy reduced. Run: pip install pymorphy3"
    )

# Леммы действий — pymorphy3 сведёт все формы к этим
_ACTION_LEMMAS: dict[str, frozenset[str]] = {
    "player_attacks": frozenset(
        {
            "атаковать",
            "ударить",
            "бить",
            "избить",
            "избивать",
            "резать",
            "стрелять",
            "кастовать",
            "колдовать",
            "убить",
            "убивать",
            "пнуть",
            "рассечь",
            "удушить",
            "задушить",
            "застрелить",
            "выстрелить",
        }
    ),
    "player_steals": frozenset(
        {
            "украсть",
            "свистнуть",
            "красть",
            "карманить",
            "забирать",
            "забрать",
            "выносить",
            "вынести",
        }
    ),
    "player_flees": frozenset(
        {
            "убежать",
            "сбежать",
            "бежать",
            "драпать",
            "отступать",
            "отступить",
            "прятаться",
            "спрятаться",
        }
    ),
    "player_threatens": frozenset(
        {
            "угрожать",
            "запугивать",
            "пугать",
            "приказывать",
            "требовать",
            "уставиться",
        }
    ),
}


# --- Сущности ---


class RouterError(Enum):
    EMPTY_INPUT = "EMPTY_INPUT"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class RawEvent:
    event_type: str
    actor_id: str
    raw_input: str
    base_intensity: float
    tick: int
    # R5: Разделение вербальных и физических действий
    action_mode: str = "VERBAL"  # VERBAL или PHYSICAL


@dataclass(frozen=True)
class RouterResult:
    is_valid: bool
    raw_event: Optional[RawEvent] = None
    error: Optional[RouterError] = None
    error_details: str = ""


# --- Router ---


class DMRouter:
    """
    Этап 1: Текст → RawEvent.
    Чистый Python. Извлекает тип действия и базовую интенсивность.
    """

    # Паттерны ТОЛЬКО для сложных случаев, которые не покрываются лемматизацией:
    # - multi-word выражения ("на колени")
    # - составные условия (threatens_indirect)
    # Оскорбления обрабатываются через _INSULT_ROOTS + pymorphy3.
    _PATTERNS: dict[str, re.Pattern] = {
        "player_threatens": re.compile(r"(?i)на\s*колени|замолчи|молчи|сдохнешь"),
        "player_threatens_indirect": re.compile(
            r"(?i)(жена|дочь|сын|мать|отец|семья|ребёнок|дети).*"
            r"(видел|был[аи]?|спит|с[^а-яё]|незнаком|чужой|уходил[аи]?)"
            r"|"
            r"(видел|знаю|слышал).*"
            r"(жена|дочь|сын|мать|отец|семья|ребёнок|дети)"
        ),
        "player_insults": re.compile(
            r"(?i)\b(твою|тебя|тебе|вас|вам|твой|твоя|твоё|твои)\b.*"
            r"(дура|дурак|дебил|идиот|тупой|тупая|тупое|глупый|глупая|глупое|дерьмо|позор|подон|подона|мразь|мрази|шлюха|шлюхи|шлюхе|шлюхам|шлюхам)"
        ),
    }

    # R5: Физические действия требуют броска кубиков через rules_agent
    _PHYSICAL_ACTIONS: frozenset[str] = frozenset(
        {
            "player_attacks",
            "player_steals",
            # ИСПРАВЛЕНО: 'player_fleses' → 'player_flees'. Опечатка: 'e' и 's'
            # перепутаны местами. _classify_action возвращал "player_flees" (правильно),
            # но сравнение шло со сломанной строкой → побег классифицировался как VERBAL.
            "player_flees",
            "player_insults",
        }
    )

    # Интенсивность вынесена в domain/constants.py (ACTION_INTENSITY)

    def parse_and_validate(
        self,
        raw_input: str,
        player_data: dict,
        player_markers: List[str],
        target_npc_id: Optional[str],
        distance: float,
        location: str,
        current_tick: int,
    ) -> RouterResult:
        if not raw_input or not raw_input.strip():
            return RouterResult(
                is_valid=False,
                error=RouterError.EMPTY_INPUT,
                error_details="Пустой ввод от игрока",
            )

        event_type = self._classify_action(raw_input)
        from app.domain.constants import ACTION_INTENSITY

        base_intensity = ACTION_INTENSITY.get(event_type, 0.2)

        action_mode = "PHYSICAL" if event_type in self._PHYSICAL_ACTIONS else "VERBAL"
        raw_event = RawEvent(
            event_type=event_type,
            actor_id="player",
            raw_input=raw_input.strip(),
            base_intensity=base_intensity,
            tick=current_tick,
            action_mode=action_mode,
        )

        return RouterResult(is_valid=True, raw_event=raw_event)

    def get_rules_action_type(self, event_type: str) -> str:
        """
        Маппинг Router event_type → RulesAgent ActionType.
        Используется для передачи классификации в rules_agent.
        """
        _MAPPING: dict[str, str] = {
            "player_attacks": "COMBAT",
            "player_steals": "SANDBOX_PHYSICAL",
            "player_flees": "FLEE",
            "player_threatens": "SANDBOX_SOCIAL",
            "player_threatens_indirect": "SANDBOX_SOCIAL",
            "player_insults": "SANDBOX_SOCIAL",
            "player_interacts": "SANDBOX_MILD",
        }
        return _MAPPING.get(event_type, "UNKNOWN")

    def _classify_action(self, text: str) -> str:
        """Определяет тип события. Лемматизация для действий, regex для сложных случаев."""

        # 0. Знак вопроса = всегда player_interacts (вопросы не наносят урон!)
        if "?" in text:
            return "player_interacts"

        # 1. Лемматизация — один проход по всем словам, проверка всех категорий
        if _MORPH and _ACTION_LEMMAS:
            words = re.findall(r"[а-яёa-z]+", text.lower())
            for word in words:
                for parsed in _MORPH.parse(word):
                    lemma = parsed.normal_form
                    for event_type, lemmas in _ACTION_LEMMAS.items():
                        if lemma in lemmas:
                            return event_type

        # 2. Regex для сложных случаев (multi-word, составные условия)
        for event_type, pattern in self._PATTERNS.items():
            if pattern.search(text):
                return event_type

        # 3. Быстрая проверка междометий ("твою" и т.п.)
        if re.search(r"(?i)\bтвою\b", text):
            logger.debug("[DM_ROUTER] Exclamation insult detected: player_insults")
            return "player_insults"

        # 4. Сложная проверка оскорблений (лемматизация + контекст)
        if _INSULT_ROOTS and _MORPH:
            if self._is_directed_insult(text):
                logger.debug("[DM_ROUTER] Insult detected: player_insults")
                return "player_insults"

        return "player_interacts"

    def _is_directed_insult(self, text: str) -> bool:
        """Проверяет наличие направленного оскорбления с защитой от ложных срабатываний."""

        # Предварительно чистим текст от лишних символов для сплита
        words = re.findall(r"[а-яёa-z]+", text.lower())

        # Словарь отрицаний
        negations = {"не", "ни"}

        profanity_present = False  # мат найден (включая междометия)
        insult_confirmed = False  # немеждометное оскорбление подтверждено

        for i, word in enumerate(words):
            # 1. ЗАЩИТА ОТ ЗАЛИПАНИЯ КЛАВИШ: "идиооот" -> "идиот"
            clean_word = re.sub(r"(.)\1{2,}", r"\1", word)

            if not clean_word:
                continue

            parsed = _MORPH.parse(clean_word)[0]
            lemma = parsed.normal_form

            if lemma in _INSULT_ROOTS:
                # 3. ЗАЩИТА ОТ ОТРИЦАНИЙ: "ты не дурак", "он вовсе не идиот"
                # Проверяем 2 слова слева от найденного оскорбления
                window_start = max(0, i - 2)
                if any(prev_word in negations for prev_word in words[window_start:i]):
                    continue

                profanity_present = (
                    True  # запоминаем наличие мата (только если не отрицание)
                )

                # 2. ЗАЩИТА ОТ МЕЖДОМЕТИЙ: "Блядь, я забыл" (игнорируем как основное оскорбление)
                if "INTJ" in parsed.tag:
                    continue

                # Если мы здесь, значит оскорбление реальное (не междометие, не отрицание)
                insult_confirmed = True
                break

        # Если есть подтверждённое оскорбление (не междометие)
        if insult_confirmed:
            # 4. ПРОВЕРКА НАПРАВЛЕННОСТИ (Только прямое обращение!)
            # "Ты", "тебя", "Вы", "вас" и т.д.
            if _DIRECTED_AT_PATTERN.search(text):
                return True

            # 5. ЭВРИСТИКА КОРОТКИХ ФРАЗ
            # "Тупой ублюдок!" (2 слова) — явно сказано в лицо текущему NPC.
            # "Этот тупой ублюдок украл меч" (5 слов) — рассказ о третьем лице (НЕ оскорбляем NPC).
            if len(words) <= 4:
                return True

        # 6. ЭВРИСТИКА МАТА-МЕЖДОМЕТИЯ
        # Если мат-междометие + есть обращение "ты/вы" → оскорбление
        # "Пошёл ты нахуй" — 3 слова, но "ты" указывает направленность
        if profanity_present:
            if _DIRECTED_AT_PATTERN.search(text):
                return True
            # Очень короткие фразы без обращения — всё равно агрессия
            # "Нахуй иди!" — 2 слова
            # "Блядь, я забыл" — 3 слова, поэтому не попадает
            if len(words) <= 2:
                return True

        return False
