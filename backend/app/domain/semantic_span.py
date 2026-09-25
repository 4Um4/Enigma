"""
path: /project/backend/app/domain/semantic_span.py
Назначение: SemanticSpan — инфраструктурный примитив привязки смысла к
    диапазону текста (Фаза 3, ADR-O-404-наследие). ДОЧЕРНИЙ идентификатор
    презентационного семантического объекта: НЕ event identity, НЕ
    эпистемическая сущность. Не имеет write-path в EpistemicStore/
    TruthState (модуль их не импортирует — структурная гарантия).
    Ladder: TEXT ≠ INTERPRETATION ≠ CLAIM ≠ BELIEF ≠ TRUTH.
Зависимости: dataclasses, hashlib (детерминизм span_id)
Основные сущности: SemanticSpan, SpanType, SpanCreator, SpanStatus,
    make_span_id
"""

from dataclasses import dataclass
from enum import Enum
from hashlib import md5


class SpanType(str, Enum):
    """Реализованные типы спанов. Первый срез — только SPEAKER_MENTION
    (детерминированный grounding). Остальные типы добавляются вместе с
    эмиттерами (мёртвых обработчиков не создаём — вердикт Мастера)."""

    SPEAKER_MENTION = "speaker_mention"


class SpanCreator(str, Enum):
    GROUNDING = "grounding"   # детерминированный код
    LLM = "llm"               # кандидат (Acceptance Gate — будущее)
    PLAYER = "player"         # ручная привязка (доска — будущее)


class SpanStatus(str, Enum):
    PROPOSED = "proposed"     # ожидает гейта приёмки
    ACCEPTED = "accepted"     # принят кодом (детерминированные — сразу)
    REJECTED = "rejected"     # отклонён гейтом (сохраняется с причиной)


def make_span_id(
    source_event_id: str, start: int, end: int, span_type: str
) -> str:
    """Детерминированный span_id (зеркало commitment_id-паттерна ADR-O-363).
    Дочерний идентичности: span_id НЕ является event identity; связь с
    событием — через source_event_id (одно событие → N спанов)."""
    _seed = f"{source_event_id}:{start}:{end}:{span_type}".encode("utf-8")
    return md5(_seed).hexdigest()


@dataclass(frozen=True)
class SemanticSpan:
    """Привязка диапазона текста к семантическому объекту.

    text_range — полуинтервал [start, end) по исходному тексту; исходный
    текст никогда не подменяется разметкой. confidence=1.0 легален только
    для детерминированного grounding; LLM-кандидаты получают < 1.0 и
    status=PROPOSED до Acceptance Gate (будущее).
    """

    span_id: str
    source_event_id: str          # сквозной event identity (ADR-O-404)
    start: int
    end: int
    span_type: SpanType
    semantic_id: str              # на что указывает (npc_id / ... )
    confidence: float
    creator: SpanCreator
    status: SpanStatus
