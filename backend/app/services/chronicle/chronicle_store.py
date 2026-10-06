"""
Хранилище Character Chronicle (ADR-O-420, CCH-1).

Файл: backend/app/services/chronicle/chronicle_store.py
Назначение: канон config/npc/chronicles/<npc_id>.json + черновики
            {drafts_root}/{campaign_id}/chronicle_drafts/<npc_id>.json.
Зависимости: app.domain.chronicle
Основные сущности: document_to_dict / document_from_dict (WARA-пара),
                   validate_document (fail-loud), ChronicleStore.

ЗАПРЕТЫ (ADR-O-420): canonical-файл не принимает LLM_DRAFT (запрет 1);
открытый вопрос в каноне обязан иметь selected_option («Save = Contract»);
KnowledgeLink-записи валидируются против события (инвариант двух времён,
запрет 4); dangling-ссылки white_spot/causes/entry_id — ошибки.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

from app.domain.chronicle import (
    KP_CERTAINTY,
    KP_CHANNEL,
    KP_EVENT_REF,
    KP_KNOWER,
    KP_LEARNED_AGE,
    KP_LEARNED_YEAR,
    SCHEMA_VERSION,
    CauseKind,
    CauseRef,
    ChronicleDocument,
    ChronicleEntry,
    ClarificationOption,
    ClarificationQuestion,
    EntityRef,
    EntityRefKind,
    EntryKind,
    EntryProvenance,
    KnowledgeChannel,
    KnowledgeLink,
    WhiteSpot,
    WhiteSpotResolutionState,
)

# ── Ключи — константы (§12.1) ────────────────────────────────────────────────
_KEY_SCHEMA_VERSION = "schema_version"
_KEY_CHRONICLE_ID = "chronicle_id"
_KEY_NPC_REF = "npc_ref"
_KEY_AUTHOR_TEXT = "author_text"
_KEY_ENTRIES = "entries"
_KEY_WHITE_SPOTS = "white_spots"
_KEY_CANONICAL = "canonical"
_KEY_CANONICAL_VERSION = "canonical_version"
_KEY_CREATED_BY = "created_by_tick_source"
_KEY_ENTRY_ID = "entry_id"
_KEY_KIND = "kind"
_KEY_HIST_AGE = "historical_age"
_KEY_HIST_YEAR = "historical_year"
_KEY_SUBJECT = "subject_id"
_KEY_OBJECT = "object_id"
_KEY_PAYLOAD = "payload"
_KEY_CAUSES = "causes"
_KEY_PROVENANCE = "provenance"
_KEY_CONFIDENCE = "confidence"
_KEY_OPEN_QUESTIONS = "open_questions"
_KEY_ORDINAL = "ordinal"
_KEY_REF_KIND = "ref_kind"
_KEY_NPC_ID = "npc_id"
_KEY_WS_ID = "white_spot_id"
_KEY_NAME_HINT = "name_hint"
_KEY_CAUSE_KIND = "cause_kind"
_KEY_ORIGIN_REF = "origin_ref"
_KEY_QUESTION_ID = "question_id"
_KEY_TARGET_SPAN = "target_span"
_KEY_OPTIONS = "options"
_KEY_SELECTED = "selected_option"
_KEY_SELECTED_VALUE = "selected_value"
_KEY_LABEL = "label"
_KEY_CONTEXT_HINT = "context_hint"
_KEY_RES_STATE = "resolution_state"
_KEY_RES_REF = "resolution_ref"
_KEY_CREATED_FROM = "created_from_entry"
# Схема payload kind=KNOWLEDGE_LINK — константы живут в домене (KP_*),
# единое определение для store и registry (§12.1).
_KEY_EVENT_REF = KP_EVENT_REF
_KEY_KNOWER = KP_KNOWER
_KEY_LEARNED_AGE = KP_LEARNED_AGE
_KEY_LEARNED_YEAR = KP_LEARNED_YEAR
_KEY_CHANNEL = KP_CHANNEL
_KEY_CERTAINTY = KP_CERTAINTY


def _enum(enum_cls: type, value: Any, ctx: str) -> Any:
    # Явная диспетчеризация без getattr-дефолта (§1.2): мусор → fail-loud с контекстом.
    if isinstance(value, enum_cls):
        return value
    try:
        return enum_cls(value)
    except ValueError:
        raise ValueError(f"{ctx}: неизвестное значение '{value}' для {enum_cls.__name__}") from None


def _entity_ref_from(data: Optional[Dict[str, Any]]) -> Optional[EntityRef]:
    if data is None:
        return None
    return EntityRef(
        ref_kind=_enum(EntityRefKind, data[_KEY_REF_KIND], _KEY_SUBJECT),
        npc_id=data.get(_KEY_NPC_ID),
        white_spot_id=data.get(_KEY_WS_ID),
        name_hint=data.get(_KEY_NAME_HINT, ""),
    )


def _entity_ref_required(data: Optional[Dict[str, Any]], ctx: str) -> EntityRef:
    """Обязательная ссылка: None в данных → fail-loud (§12.1, как _enum)."""
    ref = _entity_ref_from(data)
    if ref is None:
        raise ValueError(f"{ctx}: обязательная ссылка EntityRef отсутствует")
    return ref


def _entity_ref_to(ref: Optional[EntityRef]) -> Optional[Dict[str, Any]]:
    if ref is None:
        return None
    return {
        _KEY_REF_KIND: ref.ref_kind.value,
        _KEY_NPC_ID: ref.npc_id,
        _KEY_WS_ID: ref.white_spot_id,
        _KEY_NAME_HINT: ref.name_hint,
    }


def _cause_from(data: Dict[str, Any]) -> CauseRef:
    return CauseRef(
        cause_kind=_enum(CauseKind, data[_KEY_CAUSE_KIND], _KEY_CAUSES),
        origin_ref=data.get(_KEY_ORIGIN_REF),
    )


def _cause_to(cause: CauseRef) -> Dict[str, Any]:
    return {_KEY_CAUSE_KIND: cause.cause_kind.value, _KEY_ORIGIN_REF: cause.origin_ref}


def _question_from(data: Dict[str, Any]) -> ClarificationQuestion:
    # Явный if вместо тернарника (§1.1: запрещён паттерн `X if c else None`)
    _sel_raw = data.get(_KEY_SELECTED)
    if _sel_raw is not None:
        _sel = _enum(ClarificationOption, _sel_raw, _KEY_SELECTED)
    else:
        _sel = None
    return ClarificationQuestion(
        question_id=data[_KEY_QUESTION_ID],
        target_span=data.get(_KEY_TARGET_SPAN, ""),
        options=tuple(_enum(ClarificationOption, o, _KEY_OPTIONS) for o in data.get(_KEY_OPTIONS, ())),
        selected_option=_sel,
        selected_value=data.get(_KEY_SELECTED_VALUE),
    )


def _question_to(q: ClarificationQuestion) -> Dict[str, Any]:
    # Явный if вместо тернарника (§1.1)
    if q.selected_option is not None:
        _sel_value = q.selected_option.value
    else:
        _sel_value = None
    return {
        _KEY_QUESTION_ID: q.question_id,
        _KEY_TARGET_SPAN: q.target_span,
        _KEY_OPTIONS: [o.value for o in q.options],
        _KEY_SELECTED: _sel_value,
        _KEY_SELECTED_VALUE: q.selected_value,
    }


def _white_spot_from(data: Dict[str, Any]) -> WhiteSpot:
    return WhiteSpot(
        white_spot_id=data[_KEY_WS_ID],
        label=data.get(_KEY_LABEL, ""),
        context_hint=data.get(_KEY_CONTEXT_HINT, ""),
        resolution_state=_enum(WhiteSpotResolutionState, data.get(_KEY_RES_STATE, "OPEN"), _KEY_RES_STATE),
        resolution_ref=data.get(_KEY_RES_REF),
        created_from_entry=data.get(_KEY_CREATED_FROM),
    )


def _white_spot_to(ws: WhiteSpot) -> Dict[str, Any]:
    return {
        _KEY_WS_ID: ws.white_spot_id,
        _KEY_LABEL: ws.label,
        _KEY_CONTEXT_HINT: ws.context_hint,
        _KEY_RES_STATE: ws.resolution_state.value,
        _KEY_RES_REF: ws.resolution_ref,
        _KEY_CREATED_FROM: ws.created_from_entry,
    }


def _entry_from(data: Dict[str, Any]) -> ChronicleEntry:
    return ChronicleEntry(
        entry_id=data[_KEY_ENTRY_ID],
        kind=_enum(EntryKind, data[_KEY_KIND], _KEY_KIND),
        subject_id=_entity_ref_required(data[_KEY_SUBJECT], _KEY_SUBJECT),
        historical_age=data.get(_KEY_HIST_AGE),
        historical_year=data.get(_KEY_HIST_YEAR),
        object_id=_entity_ref_from(data.get(_KEY_OBJECT)),
        payload=dict(data.get(_KEY_PAYLOAD, {})),
        causes=tuple(_cause_from(c) for c in data.get(_KEY_CAUSES, ())),
        provenance=_enum(EntryProvenance, data.get(_KEY_PROVENANCE, "LLM_DRAFT"), _KEY_PROVENANCE),
        confidence=data.get(_KEY_CONFIDENCE),
        open_questions=tuple(_question_from(q) for q in data.get(_KEY_OPEN_QUESTIONS, ())),
        ordinal=data.get(_KEY_ORDINAL, 0),
    )


def _entry_to(e: ChronicleEntry) -> Dict[str, Any]:
    return {
        _KEY_ENTRY_ID: e.entry_id,
        _KEY_KIND: e.kind.value,
        _KEY_HIST_AGE: e.historical_age,
        _KEY_HIST_YEAR: e.historical_year,
        _KEY_SUBJECT: _entity_ref_to(e.subject_id),
        _KEY_OBJECT: _entity_ref_to(e.object_id),
        _KEY_PAYLOAD: e.payload,
        _KEY_CAUSES: [_cause_to(c) for c in e.causes],
        _KEY_PROVENANCE: e.provenance.value,
        _KEY_CONFIDENCE: e.confidence,
        _KEY_OPEN_QUESTIONS: [_question_to(q) for q in e.open_questions],
        _KEY_ORDINAL: e.ordinal,
    }


def document_to_dict(doc: ChronicleDocument) -> Dict[str, Any]:
    """WARA: пишет КАЖДОЕ поле, которое читает document_from_dict (§12.2)."""
    return {
        _KEY_SCHEMA_VERSION: doc.schema_version,
        _KEY_CHRONICLE_ID: doc.chronicle_id,
        _KEY_NPC_REF: doc.npc_ref,
        _KEY_AUTHOR_TEXT: doc.author_text,
        _KEY_ENTRIES: [_entry_to(e) for e in doc.entries],
        _KEY_WHITE_SPOTS: [_white_spot_to(ws) for ws in doc.white_spots],
        _KEY_CANONICAL: doc.canonical,
        _KEY_CANONICAL_VERSION: doc.canonical_version,
        _KEY_CREATED_BY: doc.created_by_tick_source,
    }


def document_from_dict(data: Dict[str, Any]) -> ChronicleDocument:
    """Обратная пара document_to_dict. Schema-version fail-loud (§12, прецедент truth_state_loader)."""
    if data.get(_KEY_SCHEMA_VERSION) != SCHEMA_VERSION:
        raise ValueError(f"Unsupported schema_version: {data.get(_KEY_SCHEMA_VERSION)} (ожидается {SCHEMA_VERSION})")
    return ChronicleDocument(
        chronicle_id=data[_KEY_CHRONICLE_ID],
        npc_ref=data[_KEY_NPC_REF],
        author_text=data.get(_KEY_AUTHOR_TEXT, ""),
        entries=tuple(_entry_from(e) for e in data.get(_KEY_ENTRIES, ())),
        white_spots=tuple(_white_spot_from(ws) for ws in data.get(_KEY_WHITE_SPOTS, ())),
        canonical=data.get(_KEY_CANONICAL, False),
        canonical_version=data.get(_KEY_CANONICAL_VERSION, 0),
        created_by_tick_source=data.get(_KEY_CREATED_BY),
    )


def validate_document(doc: ChronicleDocument, *, require_canonical_clean: bool) -> None:
    """Целостность документа (fail-loud; прецедент truth_state_loader.validate)."""
    entry_ids = {e.entry_id for e in doc.entries}
    if len(entry_ids) != len(doc.entries):
        raise ValueError(f"Хроника {doc.chronicle_id}: дубликат entry_id")
    ws_ids = {ws.white_spot_id for ws in doc.white_spots}

    for e in doc.entries:
        for ref in (e.subject_id, e.object_id):
            if ref is not None and ref.ref_kind.value == "WHITE_SPOT" and ref.white_spot_id not in ws_ids:
                raise ValueError(f"{e.entry_id}: dangling white_spot '{ref.white_spot_id}'")
        for c in e.causes:
            if c.origin_ref is not None and c.origin_ref not in entry_ids and c.origin_ref not in ws_ids:
                raise ValueError(f"{e.entry_id}: dangling cause origin_ref '{c.origin_ref}'")
        if require_canonical_clean:
            if e.provenance is EntryProvenance.LLM_DRAFT:
                raise ValueError(f"Запрет 1 (INV-LLM-NOT-SSOT): LLM_DRAFT '{e.entry_id}' в каноне {doc.chronicle_id}")
            for q in e.open_questions:
                if q.selected_option is None:
                    raise ValueError(f"Канон '{e.entry_id}': открытый вопрос '{q.question_id}' без резолюции автора")
        if e.kind is EntryKind.KNOWLEDGE_LINK:
            _validate_knowledge_entry(doc, e, entry_ids)


def _validate_knowledge_entry(doc: ChronicleDocument, entry: ChronicleEntry, entry_ids: set) -> None:
    p = entry.payload
    for key in (_KEY_EVENT_REF, _KEY_KNOWER, _KEY_CHANNEL, _KEY_CERTAINTY):
        if key not in p:
            raise ValueError(f"KNOWLEDGE_LINK '{entry.entry_id}': payload без '{key}'")
    if p[_KEY_EVENT_REF] not in entry_ids:
        raise ValueError(f"KNOWLEDGE_LINK '{entry.entry_id}': dangling event_ref '{p[_KEY_EVENT_REF]}'")
    link = KnowledgeLink(
        event_ref=p[_KEY_EVENT_REF],
        knower_id=_entity_ref_required(p[_KEY_KNOWER], _KEY_KNOWER),
        learned_age=p.get(_KEY_LEARNED_AGE),
        learned_year=p.get(_KEY_LEARNED_YEAR),
        channel=_enum(KnowledgeChannel, p[_KEY_CHANNEL], _KEY_CHANNEL),
        certainty=float(p[_KEY_CERTAINTY]),
    )
    event = next(e for e in doc.entries if e.entry_id == link.event_ref)
    KnowledgeLink.validate_against(event, link)


class ChronicleStore:
    """Файловое хранилище. Канон-запись — только через save_canonical (валидатор + флаг)."""

    def __init__(self, canonical_dir: Path, drafts_root: Path) -> None:
        self._canonical_dir = Path(canonical_dir)
        self._drafts_root = Path(drafts_root)

    def canonical_path(self, npc_id: str) -> Path:
        return self._canonical_dir / f"{npc_id}.json"

    def draft_path(self, campaign_id: str, npc_id: str) -> Path:
        return self._drafts_root / campaign_id / "chronicle_drafts" / f"{npc_id}.json"

    def has_canonical(self, npc_id: str) -> bool:
        return self.canonical_path(npc_id).is_file()

    def _read(self, path: Path) -> Optional[ChronicleDocument]:
        if not path.is_file():
            return None  # «нет хроники» — легальный Vacuum (legacy-путь)
        # utf-8-sig: терпит BOM (урок S317), не создаёт его.
        with open(path, "r", encoding="utf-8-sig") as f:
            return document_from_dict(json.load(f))

    def _write(self, path: Path, doc: ChronicleDocument) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(document_to_dict(doc), f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)  # атомарно на той же ФС
        return path

    def load_canonical(self, npc_id: str) -> Optional[ChronicleDocument]:
        return self._read(self.canonical_path(npc_id))

    def load_draft(self, campaign_id: str, npc_id: str) -> Optional[ChronicleDocument]:
        return self._read(self.draft_path(campaign_id, npc_id))

    def save_canonical(self, doc: ChronicleDocument) -> Path:
        if not doc.canonical:
            raise ValueError(f"save_canonical: документ {doc.chronicle_id} без флага canonical")
        validate_document(doc, require_canonical_clean=True)
        return self._write(self.canonical_path(doc.npc_ref), doc)

    def save_draft(self, doc: ChronicleDocument, campaign_id: str) -> Path:
        if doc.canonical:
            raise ValueError(f"save_draft: документ {doc.chronicle_id} помечен canonical")
        validate_document(doc, require_canonical_clean=False)
        return self._write(self.draft_path(campaign_id, doc.npc_ref), doc)
