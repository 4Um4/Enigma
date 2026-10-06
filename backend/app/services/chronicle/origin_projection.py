"""
Проекция origin_events ↔ хроника (ADR-O-420, CCH-1).

Файл: backend/app/services/chronicle/origin_projection.py
Назначение: legacy origin_events читаются как ChronicleDocument-проекция
            (read-only миграция; roadmap CCH-1). Обратная запись — CCH-5.
Зависимости: app.domain.chronicle
Основные сущности: origin_events_to_chronicle / chronicle_to_origin_events.

КОНТРАКТ (археология _convert_origin_events, npc_loader):
- конвертер читает payload через .get с дефолтами и НЕ мутирует вход →
  deepcopy-payload гарантирует идентичный EventMemory-кортеж при повторном
  прогоне (T-CCH-01);
- day=-1000 (sentinel) живёт в payload как факт legacy-данных; точные
  датировки появятся только в новых авторских хрониках (вердикт Мастера S331);
- kind-семантика (EFFECT/BELIEF_SEED) НЕ выводится здесь — opaque payload,
  декомпозитор CCH-2 классифицирует новый авторский текст.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List

from app.domain.chronicle import (
    ChronicleDocument,
    ChronicleEntry,
    EntityRef,
    EntityRefKind,
    EntryKind,
    EntryProvenance,
    make_entry_id,
)

_PROJECTION_CHRONICLE_PREFIX = "chronicle_"


def origin_events_to_chronicle(
    npc_id: str, origin_list: List[Dict[str, Any]], *, author_text: str = ""
) -> ChronicleDocument:
    """Legacy origin_events → ChronicleDocument. payload хранится целиком (opaque)."""
    entries = tuple(
        ChronicleEntry(
            entry_id=make_entry_id(f"{_PROJECTION_CHRONICLE_PREFIX}{npc_id}", 0, ordinal),
            kind=EntryKind.EVENT,
            subject_id=EntityRef(ref_kind=EntityRefKind.RESOLVED, npc_id=npc_id),
            historical_age=None,  # legacy не несёт возраст; не выдумываем (§ENIGMA-003)
            payload=deepcopy(dict(raw)),
            provenance=EntryProvenance.AUTHOR_AUTHORED,  # legacy — рукопись автора
            ordinal=ordinal,
        )
        for ordinal, raw in enumerate(origin_list)
    )
    return ChronicleDocument(
        chronicle_id=f"{_PROJECTION_CHRONICLE_PREFIX}{npc_id}",
        npc_ref=npc_id,
        author_text=author_text,
        entries=entries,
    )


def chronicle_to_origin_events(doc: ChronicleDocument) -> List[Dict[str, Any]]:
    """Хроника-проекция → legacy-совместимый список (для _convert_origin_events).
    Только EVENT-записи с opaque payload; хроника-поля в экспорт не утекают."""
    out: List[Dict[str, Any]] = []
    for e in sorted(doc.entries, key=lambda x: x.ordinal):
        if e.kind is not EntryKind.EVENT:
            continue
        out.append(deepcopy(dict(e.payload)))
    return out
