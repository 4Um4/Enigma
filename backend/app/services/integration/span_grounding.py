"""
path: /project/backend/app/services/integration/span_grounding.py
Назначение: Детерминированный grounding SPEAKER_MENTION над journal-записью.
    Единственный эмиттер спанов первого среза. Без LLM, confidence=1.0,
    status=ACCEPTED (детерминированный grounding в гейте не нуждается).
    Граница (вердикт Мастера): speaker-метадата НЕ равна substring текста —
    span создаётся только при фактическом нахождении имени в тексте;
    не найдено → spans = [] (§ENIGMA-003: отсутствие проекции ≠ ноль).
Зависимости: app.domain.semantic_span
Основные сущности: ground_speaker_mention
"""

from app.domain.semantic_span import (
    SemanticSpan,
    SpanCreator,
    SpanStatus,
    SpanType,
    make_span_id,
)


def ground_speaker_mention(
    source_event_id: str, speaker: str, text: str
) -> list[SemanticSpan]:
    """Ищет speaker-имя в тексте записи; возвращает 0 или 1 спан.

    Детерминизм: первое вхождение, точные границы. Пустое имя или имя,
    отсутствующее в тексте → [] (никаких искусственных спанов).
    """
    if not source_event_id or not speaker or not text:
        return []
    _idx = text.find(speaker)
    if _idx < 0:
        return []
    _end = _idx + len(speaker)
    return [
        SemanticSpan(
            span_id=make_span_id(source_event_id, _idx, _end, SpanType.SPEAKER_MENTION.value),
            source_event_id=source_event_id,
            start=_idx,
            end=_end,
            span_type=SpanType.SPEAKER_MENTION,
            semantic_id=speaker,
            confidence=1.0,
            creator=SpanCreator.GROUNDING,
            status=SpanStatus.ACCEPTED,
        )
    ]