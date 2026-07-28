"""
ФАЗА 0: STM (кратковременная память диалога).
Хранится в RAM, не персистится. Ключ — campaign_id:npc_id:session.

path: /backend/app/services/memory/dialogue_session.py
Назначение: Кратковременная память диалога (STM) — буфер последних 5 реплик в RAM
Зависимости: нет (чистый dataclass)
Основные сущности: DialogueTurn, DialogueSession
"""

from dataclasses import dataclass, field
from typing import Optional, List, Tuple


@dataclass
class Claim:
    """Утверждение, сделанное в диалоге."""
    text: str
    speaker: str
    confidence: float
    timestamp_tick: int
    status: str = "open"  # "open" | "contested" | "confirmed" | "withdrawn"
    contested_by: Optional[str] = None


@dataclass
class OpenQuestion:
    """Вопрос, на который нет ответа."""
    text: str
    asked_by: str
    addressed_to: str
    timestamp_tick: int
    answered: bool = False
    answer_text: str = ""
    answered_by: Optional[str] = None
    answer_tick: Optional[int] = None


@dataclass
class DialogueTurn:
    """Расширенная реплика — с target/intent/tone/tick."""
    speaker: str
    text: str
    target_id: str = ""
    intent: str = ""
    tone: str = ""
    tick: int = 0


@dataclass
class DialogueSession:
    """Сессия диалога с structured thread memory."""
    npc_id: str
    partner_id: str = "player"
    thread_id: str = ""

    buffer: List[DialogueTurn] = field(default_factory=list)
    max_size: int = 8  # bump с 5 до 8

    topic: Optional[str] = None
    topic_confidence: float = 0.0
    topic_history: List[Tuple[str, int]] = field(default_factory=list)

    # Structured thread memory
    claims: List[Claim] = field(default_factory=list)
    open_questions: List[OpenQuestion] = field(default_factory=list)

    # Legacy / Этап 5
    _pressure_by_topic: dict = field(default_factory=dict)
    last_pressure_type: str = ""
    emotional_markers: List[str] = field(default_factory=list)

    # Lifecycle
    started_tick: int = 0
    last_activity_tick: int = 0
    ended: bool = False

    def add_turn(self, speaker: str, text: str, target_id: str = "",
                 intent: str = "", tone: str = "", tick: int = 0) -> None:
        """Добавляет реплику в буфер. Старые вытесняются."""
        self.buffer.append(DialogueTurn(
            speaker=speaker, text=text, target_id=target_id,
            intent=intent, tone=tone, tick=tick
        ))
        if len(self.buffer) > self.max_size:
            self.buffer.pop(0)
        self.last_activity_tick = tick
        self._detect_topic(text)

    def add(self, speaker: str, text: str) -> None:
        """Legacy-обёртка для совместимости со старым кодом."""
        self.add_turn(speaker=speaker, text=text)

    def _detect_topic(self, text: str) -> None:
        """Детекция темы по ключевым словам (временная, до LLM-экстрактора)."""
        _lower = text.lower()
        _keywords = {
            "подвал": "basement", "тайник": "basement", "ход": "basement",
            "гильдия": "guild", "воры": "guild",
            "торговля": "trade", "купить": "trade", "продать": "trade",
            "метель": "weather", "погода": "weather", "снег": "weather",
            "дождь": "weather", "ветер": "weather", "холод": "weather",
            "борко": "guard_borko", "страж": "guard",
            "торнин": "tavern_keeper", "кузнец": "blacksmith", "орм": "blacksmith",
        }
        for _word, _topic in _keywords.items():
            if _word in _lower:
                self.topic = _topic
                self.topic_confidence = 0.6  # Базовая уверенность для keyword-match
                self._pressure_by_topic[_topic] = (
                    self._pressure_by_topic.get(_topic, 0) + 1
                )
                return

    def get_pressure(self, topic: str | None) -> int:
        if topic is None:
            return 0
        return self._pressure_by_topic.get(topic, 0)

    def add_claim(self, text: str, speaker: str, confidence: float, tick: int) -> None:
        self.claims.append(Claim(
            text=text, speaker=speaker, confidence=confidence,
            timestamp_tick=tick
        ))
        open_claims = [c for c in self.claims if c.status == "open"]
        if len(open_claims) > 10:
            for c in open_claims[:-10]:
                c.status = "withdrawn"

    def add_open_question(self, text: str, asked_by: str, addressed_to: str, tick: int) -> None:
        self.open_questions.append(OpenQuestion(
            text=text, asked_by=asked_by, addressed_to=addressed_to,
            timestamp_tick=tick
        ))

    def answer_question(self, idx: int, answer_text: str, answered_by: str, tick: int) -> None:
        if 0 <= idx < len(self.open_questions):
            q = self.open_questions[idx]
            q.answered = True
            q.answer_text = answer_text
            q.answered_by = answered_by
            q.answer_tick = tick

    def to_prompt_block(self) -> str:
        """Текстуализация для LLM-промпта (расширенная)."""
        if not self.buffer:
            return ""
        lines = ["[Краткая память — текущий разговор]"]
        if self.partner_id:
            lines.append(f"Партнёр: {self.partner_id}")
        if self.topic:
            lines.append(f"Тема: {self.topic} (confidence: {self.topic_confidence:.2f})")
        lines.append("Последние реплики:")
        for turn in self.buffer[-5:]:
            target_marker = f" → {turn.target_id}" if turn.target_id else ""
            intent_marker = f" [{turn.intent}]" if turn.intent else ""
            speaker_name = "Игрок" if turn.speaker == "player" else self.npc_id
            lines.append(f"  {speaker_name}{target_marker}{intent_marker}: {turn.text}")
        if self.claims:
            open_claims = [c for c in self.claims if c.status == "open"][-5:]
            if open_claims:
                lines.append("Активные утверждения (claims):")
                for c in open_claims:
                    lines.append(f"  • {c.text} (от {c.speaker}, confidence {c.confidence:.2f})")
        if self.open_questions:
            unanswered = [q for q in self.open_questions if not q.answered][-3:]
            if unanswered:
                lines.append("Открытые вопросы:")
                for q in unanswered:
                    lines.append(f"  ? {q.text} (спросил {q.asked_by} → {q.addressed_to})")
        return "\n".join(lines)

    def consolidate_to_event_memory_summary(self) -> str:
        """Для EventMemory на завершении диалога."""
        summary_parts = [f"Диалог с {self.partner_id} ({len(self.buffer)} реплик)"]
        if self.topic:
            summary_parts.append(f"Тема: {self.topic}")
        if self.claims:
            open = [c for c in self.claims if c.status == "open"]
            if open:
                summary_parts.append("Утверждения: " + "; ".join(c.text for c in open[:3]))
        if self.open_questions:
            unanswered = [q for q in self.open_questions if not q.answered]
            if unanswered:
                summary_parts.append("Без ответа: " + "; ".join(q.text for q in unanswered[:2]))
        return ". ".join(summary_parts) + "."

    def clear(self) -> None:
        """Очистить буфер (при завершении диалога)."""
        self.buffer.clear()
        self.topic = None
        self.topic_confidence = 0.0
        self.emotional_markers.clear()
        self._pressure_by_topic.clear()
        self.last_pressure_type = ""
        self.claims.clear()
        self.open_questions.clear()
        self.topic_history.clear()

    @property
    def is_empty(self) -> bool:
        return len(self.buffer) == 0
