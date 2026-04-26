# backend/app/domain/events.py
# Назначение: Единый язык событий. Все события в системе — экземпляры EventDTO.
# Зависимости: uuid.UUID, dataclasses, typing
# Основные сущности: EventDTO

from dataclasses import dataclass
from typing import Literal
from uuid import UUID


@dataclass(frozen=True)
class EventDTO:
    """Паспорт события. Неизменяем после создания.
    
    Проходит через EventBus → MemoryProcessor → Persistence.
    Никаких List[dict] больше нигде.
    """
    id: UUID
    type: str
    source: str            # player_name или npc_id
    timestamp: float
    payload: dict
    visibility: Literal["public", "private", "whisper"]
    radius: float
    persistence_level: Literal["working", "session", "campaign"]