"""
ФАЗА 0: STM (кратковременная память диалога).
Хранится в RAM, не персистится. Ключ — campaign_id:npc_id:session.

path: /backend/app/services/memory/dialogue_session.py
Назначение: Кратковременная память диалога (STM) — буфер последних 5 реплик в RAM
Зависимости: нет (чистый dataclass)
Основные сущности: DialogueTurn, DialogueSession
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


@dataclass
class DialogueTurn:
    """Одна реплика в буфере STM."""

    speaker: str  # "player" или npc_id
    text: str


@dataclass
class DialogueSession:
    """
    Буфер текущего диалога. RAM only.
    LLM видит последние 5 реплик + текущую тему.
    """

    npc_id: str
    player_id: str = "player"
    buffer: list[DialogueTurn] = field(default_factory=list)
    max_size: int = 5

    # Текущая тема — определяется по ключевым словам, не LLM
    topic: Optional[str] = None

    # Pressure: счётчик повторных вопросов по теме + тип последнего давления (Этап 5)
    _pressure_by_topic: dict[str, int] = field(default_factory=dict)
    last_pressure_type: str = ""  # "physical", "threat", "intimidation", "question"

    # Эмоциональные маркеры для LLM-промпта
    emotional_markers: list[str] = field(default_factory=list)

    def add(self, speaker: str, text: str) -> None:
        """Добавить реплику в буфер. Старые вытесняются."""
        self.buffer.append(DialogueTurn(speaker=speaker, text=text))
        if len(self.buffer) > self.max_size:
            self.buffer.pop(0)
        # Простая детекция темы по ключевым словам
        self._detect_topic(text)

    def _detect_topic(self, text: str) -> None:
        """Детекция темы по ключевым словам. Не LLM — простой if."""
        _lower = text.lower()
        _keywords = {
            "подвал": "basement",
            "тайник": "basement",
            "ход": "basement",
            "гильдия": "guild",
            "воры": "guild",
            "торговля": "trade",
            "купить": "trade",
            "продать": "trade",
            "борко": "guard_borko",
            "страж": "guard",
            "торнин": "tavern_keeper",
            "кузнец": "blacksmith",
            "орм": "blacksmith",
        }
        for _word, _topic in _keywords.items():
            if _word in _lower:
                self.topic = _topic
                self._pressure_by_topic[_topic] = (
                    self._pressure_by_topic.get(_topic, 0) + 1
                )
                return

    def get_pressure(self, topic: str | None) -> int:
        """Давление по теме — сколько раз за сессию ковыряли."""
        if topic is None:
            return 0
        return self._pressure_by_topic.get(topic, 0)

    def to_prompt_block(self) -> str:
        """Текстуализация для LLM-промпта."""
        if not self.buffer:
            return ""
        _lines = []
        for _turn in self.buffer:
            _speaker_name = "Игрок" if _turn.speaker == "player" else self.npc_id
            _lines.append(f"{_speaker_name}: {_turn.text}")
        _result = "\n".join(_lines)
        if self.topic:
            _result += f"\n[Тема разговора: {self.topic}]"
        return _result

    def clear(self) -> None:
        """Очистить буфер (при завершении диалога)."""
        self.buffer.clear()
        self.topic = None
        self.emotional_markers.clear()
        self._pressure_by_topic.clear()
        self.last_pressure_type = ""

    @property
    def is_empty(self) -> bool:
        return len(self.buffer) == 0
