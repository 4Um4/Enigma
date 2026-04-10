# backend/app/services/action/dm_router.py
"""
path: backend/app/services/action/dm_router.py
Назначение: Этап 1 DM System — парсинг сырого текста в RawEvent (факты текста).
Зависимости: Нет (чистый парсер)
Основные сущности: DMRouter, RawEvent, RouterResult, RouterError

ПРИНЦИП: Router не знает мир. Router не знает NPC. Router не знает успех.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional


class RouterError(Enum):
    """Типы ошибок валидации на этапе 1."""
    EMPTY_INPUT = "EMPTY_INPUT"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class RawEvent:
    """
    Чистый результат парсинга текста игрока.
    Не содержит никаких предположений о мире.
    Является входом для Scene Builder (Этап 2).
    """
    event_type: str
    actor_id: str
    raw_input: str
    base_intensity: float
    tick: int


@dataclass(frozen=True)
class RouterResult:
    """
    Результат работы DM Router.
    Содержит RawEvent или ошибку валидации.
    """
    is_valid: bool
    raw_event: Optional[RawEvent] = None
    error: Optional[RouterError] = None
    error_details: str = ""


class DMRouter:
    """
    Этап 1: Текст → RawEvent.
    
    Чистый Python (без LLM). Извлекает тип действия и базовую интенсивность.
    Не знает про сцену, расстояние, NPC, свидетелей.
    
    TODO: Будущая замена на data-driven парсер из services/input/patterns/*.yaml
    """

    # Базовые паттерны для определения типа события
    _PATTERNS: dict[str, re.Pattern] = {
        "player_attacks": re.compile(
            r"(?i)\b(атакую|удар|бью|режу|стреляю|каста|колдую|убью|убить)\b"
        ),
        "player_threatens": re.compile(
            r"(?i)\b(угрожаю|запугиваю|пугаю|приказываю|требую|уставился)\b"
        ),
        "player_flees": re.compile(
            r"(?i)\b(убегаю|прячусь|отступаю|отступить|бежать|сбежать)\b"
        ),
        "player_steals": re.compile(
            r"(?i)\b(краду|украсть|карман|сую|забираю|тихо беру)\b"
        ),
    }

    # Базовая интенсивность по типу (не из длины текста!)
    _BASE_INTENSITY: dict[str, float] = {
        "player_attacks": 1.0,
        "player_threatens": 0.7,
        "player_steals": 0.6,
        "player_flees": 0.5,
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
        """Парсит сырой текст и создаёт RawEvent."""
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

        return RouterResult(
            is_valid=True,
            raw_event=raw_event,
        )

    def _classify_action(self, text: str) -> str:
        """Определяет тип события по ключевым словам."""
        for event_type, pattern in self._PATTERNS.items():
            if pattern.search(text):
                return event_type
        return "player_interacts"