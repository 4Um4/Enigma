from __future__ import annotations

# backend/app/domain/events.py
# Назначение: Единый язык событий. Все события в системе — экземпляры EventDTO.
# Зависимости: uuid.UUID, dataclasses, typing, time
# Основные сущности: EventDTO, MemoryPayload, PlayerActionPayload
import hashlib
from dataclasses import dataclass
from typing import Any, Dict, Literal, Optional, TypedDict
from uuid import UUID, uuid4

# ── Payload-типы (TypedDict — аннотации, не классы, не нарушают иерархию) ──


class MemoryPayload(TypedDict, total=False):
    """Что MemoryManager.apply() читает из payload.

    Все поля опциональные — apply() подставляет дефолты из NPCState.
    Caller не обязан заполнять всё.
    """

    npc_id: str
    target_id: str
    emotion_tag: str
    summary: str
    importance: Optional[float]
    npc_stress: float
    day: int
    scene_state: Dict[str, Any]
    contract_tag: str  # из domain.events: promise_given | promise_received | debt


class PlayerActionPayload(TypedDict, total=False):
    """Что game_loop кладёт в payload при действии игрока."""

    action_type: str
    content: str
    location: str
    player_name: str


# ── EventDTO ──


@dataclass(frozen=True)
class EventDTO:
    """Паспорт события. Неизменяем после создания.

    Проходит через EventBus → MemoryProcessor → Persistence.
    Никаких List[dict] больше нигде.
    """

    id: UUID
    type: str
    source: str  # player_name или npc_id
    timestamp: float
    payload: Dict[str, Any]
    visibility: Literal["public", "private", "whisper"]
    radius: float
    persistence_level: Literal["working", "session", "campaign"]

    @classmethod
    def create(
        cls,
        event_type: str,
        source: str,
        payload: Dict[str, Any],
        *,
        visibility: Literal["public", "private", "whisper"] = "public",
        radius: float = 999.0,
        persistence_level: Literal["working", "session", "campaign"] = "session",
        timestamp: float = 0.0,
        event_id: UUID | None = None,
    ) -> "EventDTO":
        """Фабричный метод — не нужно вручную передавать UUID и timestamp."""
        # BUG-FB-037 FIX: Детерминированный event_id и timestamp (убираем wall-clock).
        _final_ts = timestamp if timestamp != 0.0 else 0.0
        if event_id is None:
            _seed_str = f"{event_type}:{source}:{_final_ts}".encode("utf-8")
            event_id = UUID(hex=hashlib.md5(_seed_str).hexdigest())
        
        return cls(
            id=event_id,
            type=event_type,
            source=source,
            timestamp=_final_ts,
            payload=payload,
            visibility=visibility,
            radius=radius,
            persistence_level=persistence_level,
        )


# ── Теги контрактов и обязательств (Этап 6) ──
# Используются как теги в EventMemory для триггерного поиска и фильтрации.

CONTRACT_TAG_PROMISE_GIVEN: str = "promise_given"
CONTRACT_TAG_PROMISE_RECEIVED: str = "promise_received"
CONTRACT_TAG_DEBT: str = "debt"
CONTRACT_EVENT_FULFILLED: str = "promise_fulfilled"

CONTRACT_TAGS: frozenset[str] = frozenset(
    {
        CONTRACT_TAG_PROMISE_GIVEN,
        CONTRACT_TAG_PROMISE_RECEIVED,
        CONTRACT_TAG_DEBT,
    }
)
