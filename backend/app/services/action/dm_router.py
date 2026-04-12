# backend/app/services/action/dm_router.py
"""
path: backend/app/services/action/dm_router.py
Назначение: Этап 1 DM System — парсинг сырого текста в RawEvent (факты текста).
Зависимости: Нет (чистый парсер)
Основные сущности: DMRouter, RawEvent, RouterResult, RouterError

ПРИНЦИП: Router не знает мир. Router не знает NPC. Router не знает успех.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List, Optional


# --- Инициализация данных на уровне модуля (Data-Driven) ---

_INSULTS_PATH = Path(__file__).parent.parent.parent.parent / "data" / "insults_ru.json"
try:
    _INSULT_ROOTS: set[str] = set(json.loads(_INSULTS_PATH.read_text("utf-8"))["roots"])
except Exception:
    _INSULT_ROOTS: set[str] = set()

_DIRECTED_AT_PATTERN = re.compile(r"(?i)\b(ты|тебя|тебе|вас|вам|твой|твоя|твоё|твои|вы)\b")

# Инициализация морфологии один раз
_MORPH = None
try:
    import pymorphy3 as pymorphy
    _MORPH = pymorphy.MorphAnalyzer()
except Exception:
    pass


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

    # Паттерны ТОЛЬКО для простых, однозначных физических действий.
    # Оскорблений здесь нет! Они обрабатываются сложной логикой ниже.
    _PATTERNS: dict[str, re.Pattern] = {
        "player_attacks": re.compile(
            r"(?i)\b(атакую|удар|бью|режу|стреляю|каста|колдую|убью|убить)\b"
        ),
        "player_threatens": re.compile(
            r"(?i)\b(угрожаю|запугиваю|пугаю|приказываю|требую|уставился"
            r"|на\s*колени|замолчи|молчи|сдохнешь|убью|задушу|выбью)"
        ),
        # Косвенные угрозы: упоминание близких + негативный контекст
        "player_threatens_indirect": re.compile(
            r"(?i)(жена|дочь|сын|мать|отец|семья|ребёнок|дети).*"
            r"(видел|был[аи]?|спит|с[^а-яё]|незнаком|чужой|уходил[аи]?)"
            r"|"
            r"(видел|знаю|слышал).*"
            r"(жена|дочь|сын|мать|отец|семья|ребёнок|дети)"
        ),
        "player_flees": re.compile(
            r"(?i)\b(убегаю|прячусь|отступаю|отступить|бежать|сбежать)\b"
        ),
        "player_steals": re.compile(
            r"(?i)\b(краду|украсть|карман|сую|забираю|тихо беру)\b"
        ),
    }

    _BASE_INTENSITY: dict[str, float] = {
        "player_attacks": 1.0,
        "player_threatens": 0.7,
        "player_threatens_indirect": 0.6,  # ниже чем прямая угроза, выше чем болтовня
        "player_steals": 0.6,
        "player_flees": 0.5,
        "player_insults": 0.65,
        "player_interacts": 0.2,
    }

    def parse_and_validate(
        self,
        raw_input: str,
        player_data: dict,
        player_markers: List[str],
        target_npc_id: Optional[str],
        distance: float,
        location: str,
        current_day: int,
        current_tick: int,
    ) -> RouterResult:
        if not raw_input or not raw_input.strip():
            return RouterResult(
                is_valid=False,
                error=RouterError.EMPTY_INPUT,
                error_details="Пустой ввод от игрока"
            )

        event_type = self._classify_action(raw_input)
        base_intensity = self._BASE_INTENSITY.get(event_type, 0.2)

        raw_event = RawEvent(
            event_type=event_type,
            actor_id="player",
            raw_input=raw_input.strip(),
            base_intensity=base_intensity,
            tick=current_tick,
        )

        return RouterResult(is_valid=True, raw_event=raw_event)

    def _classify_action(self, text: str) -> str:
        """Определяет тип события. Физические действия -> Регексы. Оскорбления -> Морфология."""
        
        # 1. Быстрая проверка физических действий
        for event_type, pattern in self._PATTERNS.items():
            if pattern.search(text):
                return event_type

        # 2. Быстрая проверка междометий которые не попадают в морфологию ("твою" и т.п.)
        if re.search(r"(?i)\bтвою\b", text):
            print(f"[DM_ROUTER] Exclamation insult detected: player_insults")
            return "player_insults"

        # 3. Сложная проверка оскорблений (только если морфология доступна и словарь загружен)
        if _INSULT_ROOTS and _MORPH:
            if self._is_directed_insult(text):
                print(f"[DM_ROUTER] Insult detected: player_insults")
                return "player_insults"

        return "player_interacts"

    def _is_directed_insult(self, text: str) -> bool:
        """Проверяет наличие направленного оскорбления с защитой от ложных срабатываний."""
        
        # Предварительно чистим текст от лишних символов для сплита
        words = re.findall(r'[а-яёa-z]+', text.lower())
        
        # Словарь отрицаний
        negations = {"не", "ни"}

        profanity_present = False  # мат найден (включая междометия)
        insult_confirmed = False   # немеждометное оскорбление подтверждено

        for i, word in enumerate(words):
            # 1. ЗАЩИТА ОТ ЗАЛИПАНИЯ КЛАВИШ: "идиооот" -> "идиот"
            clean_word = re.sub(r'(.)\1{2,}', r'\1', word)
            
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

                profanity_present = True  # запоминаем наличие мата (только если не отрицание)
                
                # 2. ЗАЩИТА ОТ МЕЖДОМЕТИЙ: "Блядь, я забыл" (игнорируем как основное оскорбление)
                if 'INTJ' in parsed.tag:
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