"""
path: /project/backend/app/services/integration/journal_presentation.py
Назначение: PresentationProjection журнала игрока (Фаза 2 вертикального
    среза): journal-записи → клиенто-независимый presentation-блок.
    ЧИСТАЯ ФУНКЦИЯ над projection-данными: не хранит, не пишет, не
    резолвит семантику (границы ADR-O-404 / PRE-CODE контрактов D).
Зависимости: typing
Основные сущности: project_journal
"""

from typing import Any, Dict, List

from app.domain.semantic_span import SemanticSpan
from app.services.integration.span_grounding import ground_speaker_mention

_KEY_EVENT_ID = "event_id"
_KEY_TICK = "tick"


def project_journal(journal: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Разворачивает записи журнала в presentation-блоки.

    provenance_complete: происхождение прослеживается до шинного события
    (event_id непуст). narrative/self без события — легально False
    (§ENIGMA-003: отсутствие проекции ≠ ноль; не выдумываем identity).
    Клиент (Pygame/Web/что угодно) рисует по полям, не интерпретируя.
    """
    out: List[Dict[str, Any]] = []
    for entry in journal or []:
        _event_id = entry.get(_KEY_EVENT_ID, "")
        _text = entry.get("text", "")
        _speaker = entry.get("speaker", "")
        # Фаза 3: детерминированный grounding спанов. Только для записей
        # с identity (без event_id привязывать не к чему); speaker-имя
        # ищется в тексте фактически — нет имени в тексте → spans=[].
        _spans: List[SemanticSpan] = []
        if _event_id:
            _spans = ground_speaker_mention(_event_id, _speaker, _text)
        out.append(
            {
                "speaker": _speaker,
                "text": _text,
                "channel": entry.get("channel", "narrative"),
                "event_id": _event_id,
                "tick": entry.get(_KEY_TICK, 0),
                "provenance_complete": bool(_event_id),
                "spans": [
                    {
                        "span_id": s.span_id,
                        "source_event_id": s.source_event_id,
                        "start": s.start,
                        "end": s.end,
                        "span_type": s.span_type.value,
                        "semantic_id": s.semantic_id,
                        "confidence": s.confidence,
                        "creator": s.creator.value,
                        "status": s.status.value,
                    }
                    for s in _spans
                ],
            }
        )
    return out


def project_claims(claims: List[Any]) -> List[Dict[str, Any]]:
    """PresentationProjection STM-claims (Claim Bridge, R3): чистая
    функция, ничего не пишет. ПОКАЗЫВАЕТ утверждение и его provenance,
    не решая истинности. ephemeral=true всегда (STM Claim эфемерен —
    мост НЕ меняет lifecycle, STOP-критерий Мастера)."""
    out: List[Dict[str, Any]] = []
    for c in claims or []:
        out.append(
            {
                "text": getattr(c, "text", ""),
                "speaker": getattr(c, "speaker", ""),
                "confidence": getattr(c, "confidence", 0.0),
                "status": getattr(c, "status", "open"),
                "event_id": getattr(c, "event_id", ""),
                "tick": getattr(c, "timestamp_tick", 0),
                "ephemeral": True,
                "provenance_complete": bool(getattr(c, "event_id", "")),
            }
        )
    return out