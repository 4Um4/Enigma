# backend/app/domain/communication.py
# Назначение: Доменные объекты коммуникации NPC. Уровень exposure, адресация, тема.
# Зависимости: typing.Literal
# Основные сущности: ExposureLevel, CommunicationIntent

from dataclasses import dataclass
from typing import Literal


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