"""
Реестр белых пятен — writer-guard (ADR-O-420, CCH-1).

Файл: backend/app/services/chronicle/white_spot_registry.py
Назначение: единственный канал резолюции WhiteSpot. Запрет 2 ADR-O-420:
            ни декомпозитор, ни сеялка, ни сервис не меняют resolution_state
            вне авторского действия. Тест ТЗ: попытка из не-UI-модуля →
            ArchitecturalViolationError.
Зависимости: app.domain.chronicle; сериализация EntityRef-словарей —
             хелперы chronicle_store (единственное место литералов, §12.1).
Основные сущности: WhiteSpotRegistry.resolve (guard) / _resolve_impl (pure).

ЦЕНЗУС ПИСАТЕЛЕЙ (расширение = запись в IMPACT ADR-O-420, не молча):
- app.services.chronicle.white_spot_registry — собственный канал автора (CCH-1);
- CCH-3: routes_chronicle / UI-канал добавляется явно после ревизии.

Примечание: ArchitecturalViolationError сформулирован под NPCState-писателей
(прецедент relationship_state_store переиспользует его так же) — маркер класса
каноничен, текст сообщения косметически неточен.
"""
from __future__ import annotations

import sys
from dataclasses import replace
from typing import Any, Dict, Final, FrozenSet, Optional, Tuple

from app.domain.chronicle import (
    KP_KNOWER,
    ChronicleDocument,
    ChronicleEntry,
    EntityRef,
    EntityRefKind,
    EntryKind,
    WhiteSpot,
    WhiteSpotResolutionState,
)
from app.errors import ArchitecturalViolationError
from app.services.chronicle.chronicle_store import _entity_ref_from, _entity_ref_to

# ── Caller-guard: единственный writer-маршрут (прецедент ADR-O-370) ──────────
_ALLOWED_WRITER_MODULES: Final[FrozenSet[str]] = frozenset(
    {
        "app.services.chronicle.white_spot_registry",
    }
)


class WhiteSpotRegistry:
    """Операции над белыми пятнами. Резолюция — только через цензус писателей."""

    @staticmethod
    def find(doc: ChronicleDocument, white_spot_id: str) -> Optional[WhiteSpot]:
        for ws in doc.white_spots:
            if ws.white_spot_id == white_spot_id:
                return ws
        return None

    @staticmethod
    def all_open(doc: ChronicleDocument) -> Tuple[WhiteSpot, ...]:
        return tuple(
            ws for ws in doc.white_spots if ws.resolution_state is WhiteSpotResolutionState.OPEN
        )

    @staticmethod
    def resolve(doc: ChronicleDocument, white_spot_id: str, as_npc: Optional[str] = None) -> ChronicleDocument:
        """
        Авторская резолюция пятна. Guard ДО любой работы (прецедент ADR-O-370).
        as_npc → RESOLVED_AS_NPC + перелинковка на RESOLVED-EntityRef;
        as_npc=None → RESOLVED_AS_UNKNOWN + перелинковка на UNKNOWN_PERSON
        (массовка без тик-агента — вердикт Мастера S331, §12.5).
        Возвращает НОВЫЙ документ (frozen-домен); сохранение — через store.
        """
        caller = sys._getframe(1).f_globals.get("__name__", "")
        if caller not in _ALLOWED_WRITER_MODULES:
            raise ArchitecturalViolationError(f"WhiteSpot.resolve({white_spot_id})", caller)
        return WhiteSpotRegistry._resolve_impl(doc, white_spot_id, as_npc)

    @staticmethod
    def _resolve_impl(doc: ChronicleDocument, white_spot_id: str, as_npc: Optional[str] = None) -> ChronicleDocument:
        """Чистая перелинковка. Вызов только из guard-канала (цензус)."""
        target = WhiteSpotRegistry.find(doc, white_spot_id)
        if target is None:
            raise ValueError(f"WhiteSpot '{white_spot_id}' не найден в документе {doc.chronicle_id}")
        if target.resolution_state is not WhiteSpotResolutionState.OPEN:
            raise ValueError(
                f"WhiteSpot '{white_spot_id}' уже резолвлен ({target.resolution_state.value})"
            )

        new_state = (
            WhiteSpotResolutionState.RESOLVED_AS_NPC if as_npc else WhiteSpotResolutionState.RESOLVED_AS_UNKNOWN
        )
        new_spots = tuple(
            replace(
                ws,
                resolution_state=new_state if ws.white_spot_id == white_spot_id else ws.resolution_state,
                resolution_ref=(as_npc if ws.white_spot_id == white_spot_id and as_npc else ws.resolution_ref),
            )
            for ws in doc.white_spots
        )

        def _relink_ref(ref: Optional[EntityRef]) -> Optional[EntityRef]:
            if (
                ref is None
                or ref.ref_kind is not EntityRefKind.WHITE_SPOT
                or ref.white_spot_id != white_spot_id
            ):
                return ref
            if as_npc:
                return EntityRef(ref_kind=EntityRefKind.RESOLVED, npc_id=as_npc, name_hint=ref.name_hint or target.label)
            return EntityRef(ref_kind=EntityRefKind.UNKNOWN_PERSON, name_hint=ref.name_hint or target.label)

        def _relink_entry(e: ChronicleEntry) -> ChronicleEntry:
            new_subject = _relink_ref(e.subject_id)
            new_object = _relink_ref(e.object_id)
            new_payload: Dict[str, Any] = e.payload
            if e.kind is EntryKind.KNOWLEDGE_LINK:
                knower_raw = e.payload.get(KP_KNOWER)
                if isinstance(knower_raw, dict):
                    knower_ref = _entity_ref_from(knower_raw)  # мусор → fail-loud
                    relinked = _relink_ref(knower_ref)
                    if relinked is not knower_ref:
                        new_payload = {**e.payload, KP_KNOWER: _entity_ref_to(relinked)}
            if new_subject is e.subject_id and new_object is e.object_id and new_payload is e.payload:
                return e
            return replace(e, subject_id=new_subject, object_id=new_object, payload=new_payload)

        new_entries = tuple(_relink_entry(e) for e in doc.entries)
        return replace(doc, white_spots=new_spots, entries=new_entries)
