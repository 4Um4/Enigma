# backend/app/domain/communication.py
# Назначение: Доменные объекты коммуникации NPC. Уровень exposure, адресация, тема.
# Зависимости: typing.Literal
# Основные сущности: ExposureLevel, CommunicationIntent

from dataclasses import dataclass
from typing import Literal, Optional


@dataclass(frozen=True)
class ExposureLevel:
    """Семантический + физический уровень доступности речи."""
    semantic: Literal["secret", "whisper", "normal", "shout", "private"]
    physical_radius: float


@dataclass(frozen=True)
class CommunicationIntent:
    """Единый источник истины для всей цепочки ответа NPC.
    
    Создаётся DecisionHub ПОСЛЕ TopicExtractor.
    Не допускается создание с пустым topic.
    """
    speaker: str           # npc_id
    audience: str          # 'player' | npc_id | 'all'
    topic: str             # 'торговля_мечом', 'угроза_бандитов' — из TopicExtractor
    intent_type: str       # 'диалог', 'приказ', 'ложь', 'вопрос'
    emotional_state: str   # 'злость', 'страх', 'любопытство'
    exposure_level: ExposureLevel
    semantic_action: Optional[str] = None   # GAP8 FIX: Тип социального акта (MOVE, THREATEN, PERSUADE, GIVE)
    target_id: Optional[str] = None         # GAP8 FIX: ID цели директивы (для NPC-to-NPC Social Physics)

    def __post_init__(self) -> None:
        # Устав 7.2: пустой topic = LLM плывёт по ассоциациям
        if not self.topic or not self.topic.strip():
            raise ValueError(f"CommunicationIntent.topic не может быть пустым (speaker={self.speaker!r})")