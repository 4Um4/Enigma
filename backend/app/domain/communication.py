# backend/app/domain/communication.py
# Назначение: Доменные объекты коммуникации NPC. Уровень exposure, адресация, тема.
# Зависимости: typing.Literal
# Основные сущности: ExposureLevel, CommunicationIntent

from dataclasses import dataclass
from typing import Literal, Optional

# ADR-O-311: Exposure Default Contract — радиус выводится из semantic.
_EXPOSURE_DEFAULT_RADIUS: dict[str, float] = {
    "secret": 1.5,  # собеседник рядом
    "whisper": 3.0,  # группа вплотную
    "normal": 5.0,  # обычная речь в комнате
    "shout": 15.0,  # публичное событие, бой
    "private": 0.0,  # внутренняя речь / солилоквий (не слышим)
}


@dataclass(frozen=True)
class ExposureLevel:
    """Семантический + физический уровень доступности речи.

    physical_radius выводится из semantic если не задан явно (None).
    Прямая передача radius допускается только для override (test/sandbox).
    """

    semantic: Literal["secret", "whisper", "normal", "shout", "private"]
    physical_radius: Optional[float] = None  # None = derive from semantic

    def __post_init__(self) -> None:
        if self.physical_radius is None:
            object.__setattr__(
                self,
                "physical_radius",
                _EXPOSURE_DEFAULT_RADIUS.get(self.semantic, 5.0),
            )

    @classmethod
    def from_semantic(
        cls, semantic: Literal["secret", "whisper", "normal", "shout", "private"]
    ) -> "ExposureLevel":
        """Единственный легальный способ создать ExposureLevel в прод-коде."""
        if semantic not in _EXPOSURE_DEFAULT_RADIUS:
            raise ValueError(
                f"Unknown exposure semantic: {semantic!r}. "
                f"Allowed: {list(_EXPOSURE_DEFAULT_RADIUS)}"
            )
        return cls(semantic=semantic)


@dataclass(frozen=True)
class DialogueRequest:
    """Доменный запрос на генерацию диалога.
    Execution Framework не знает про LLM, он знает только что нужно поговорить на эту тему."""

    topic: str
    target_id: str
    exposure: ExposureLevel
    intent_type: str = "talk"
    emotional_state: str = "нейтрально"
    # T-04: Строка с историей взаимодействий (npc_npc_context), сформированная в post_decision.
    npc_npc_context: str = ""


@dataclass(frozen=True)
class CommunicationIntent:
    """Единый источник истины для всей цепочки ответа NPC.

    Создаётся DecisionHub ПОСЛЕ TopicExtractor.
    Не допускается создание с пустым topic.
    """

    speaker: str  # npc_id
    audience: str  # 'player' | npc_id | 'all'
    topic: str  # 'торговля_мечом', 'угроза_бандитов' — из TopicExtractor
    intent_type: str  # 'диалог', 'приказ', 'ложь', 'вопрос'
    emotional_state: str  # 'злость', 'страх', 'любопытство'
    exposure_level: ExposureLevel
    semantic_action: Optional[str] = (
        None  # GAP8 FIX: Тип социального акта (MOVE, THREATEN, PERSUADE, GIVE)
    )
    target_id: Optional[str] = (
        None  # GAP8 FIX: ID цели директивы (для NPC-to-NPC Social Physics)
    )

    def __post_init__(self) -> None:
        # Устав 7.2: пустой topic = LLM плывёт по ассоциациям
        if not self.topic or not self.topic.strip():
            raise ValueError(
                f"CommunicationIntent.topic не может быть пустым (speaker={self.speaker!r})"
            )
