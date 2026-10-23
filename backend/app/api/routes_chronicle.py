"""
API Character Chronicle (ADR-O-420, CCH-2).

Файл: backend/app/api/routes_chronicle.py
Назначение: decompose/clarify/draft-цикл. Канонизация и UI — CCH-3.
Зависимости: app.services.chronicle.*, app.core.config
Основные сущности: chronicle_router

ГРАНИЦА: это внеигровой инструмент (layer 4 UI Doctrine). Эндпоинты НЕ входят
в тик-контур; NPCState/ядро не трогают (запрет 10 ADR-O-420).
"""
from __future__ import annotations

import logging
from dataclasses import replace
from typing import Any, Dict, Optional

from app.core.config import BASE_DIR
from app.domain.chronicle import SCHEMA_VERSION
from app.services.chronicle.biography_decomposer import BiographyDecomposer
from app.services.chronicle.chronicle_store import (
    ChronicleStore,
    document_from_dict,
    document_to_dict,
)
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

chronicle_router = APIRouter()

logger = logging.getLogger(__name__)

_store: Optional[ChronicleStore] = None
_decomposer: Optional[BiographyDecomposer] = None


def _get_store() -> ChronicleStore:
    global _store
    if _store is None:
        _store = ChronicleStore(
            canonical_dir=BASE_DIR / "config" / "npc" / "chronicles",
            drafts_root=BASE_DIR / "saves",
        )
    return _store


def _get_decomposer() -> BiographyDecomposer:
    global _decomposer
    if _decomposer is None:
        _decomposer = BiographyDecomposer()
    return _decomposer


class DecomposeRequest(BaseModel):
    campaign_id: str = Field(..., min_length=1)
    npc_id: str = Field(..., min_length=1)
    fragment_ord: int = Field(..., ge=0)
    fragment: str = Field(..., min_length=1)


class ClarifyRequest(BaseModel):
    campaign_id: str = Field(..., min_length=1)
    npc_id: str = Field(..., min_length=1)
    fragment_ord: int = Field(..., ge=0)
    question_id: str = Field(..., min_length=1)
    selected_option: str
    selected_value: Optional[str] = None


@chronicle_router.get("/chronicle/npcs")
async def list_chronicles() -> Dict[str, Any]:
    """Список NPC с хрониками (канон + черновики кампании определяются по файлам)."""
    store = _get_store()
    canon = sorted(p.stem for p in store._canonical_dir.glob("*.json"))
    return {"canonical": canon}


@chronicle_router.get("/chronicle/roster/{campaign_id}")
async def get_roster(campaign_id: str) -> Dict[str, Any]:
    """C0.5: полный ростер NPC со статусом хроники. Устранение второго
    источника истины (вердикт владельца): редактор берёт список ТОЛЬКО
    отсюда. Источник имён — list_individual_ids (единый читатель
    individuals); статус — по файлам store: canon > draft > none."""
    from app.services.npc.npc_loader import get_display_names, list_individual_ids

    store = _get_store()
    _names = get_display_names()
    roster = []
    for npc_id in list_individual_ids():
        if store.canonical_path(npc_id).exists():
            status = "canon"
        elif store.draft_path(campaign_id, npc_id).exists():
            status = "draft"
        else:
            status = "none"
        roster.append({"npc_id": npc_id, "chronicle": status, "name": _names.get(npc_id, npc_id)})
    return {"roster": roster}


@chronicle_router.get("/chronicle/{campaign_id}/beliefs-export")
async def beliefs_export(campaign_id: str, format: str = "md") -> Dict[str, Any]:
    """C2: сводка убеждений для «Сохранить как…». Каноны + черновики кампании
    → belief_export.collect (детерминированный); md|json — текст файла.
    Запись в выбранное место — фронт (сервер место не знает). Невалидный
    draft одного NPC — warning + пропуск (прецедент ростера), весь экспорт
    не роняется."""

    from app.services.chronicle import belief_export
    from app.services.npc.npc_loader import list_individual_ids

    if format not in ("md", "json"):
        raise HTTPException(status_code=422, detail="format: только md|json")
    store = _get_store()
    docs: Dict[str, Any] = {}
    for npc_id in list_individual_ids():
        canon = store.load_canonical(npc_id)
        if canon is not None:
            docs[npc_id] = canon
            continue
        try:
            draft = store.load_draft(campaign_id, npc_id)
        except ValueError as e:
            logger.warning(f"[CCH_EXPORT] {npc_id}: draft невалиден — пропущен: {e}")
            continue
        if draft is not None:
            docs[npc_id] = draft
    records = belief_export.collect_belief_seeds(docs)
    text = (
        belief_export.render_json(records, campaign_id)
        if format == "json"
        else belief_export.render_markdown(records, campaign_id)
    )
    return {"status": "OK", "format": format, "count": len(records), "text": text}


@chronicle_router.get("/chronicle/{campaign_id}/trait-gaps")
async def trait_gaps_export(campaign_id: str, format: str = "md") -> Dict[str, Any]:
    """Детектор-лампочка (вердикт Мастера): слова-характеристики всех NPC
    (записи + Портреты + Мечты) против словаря онтологии. Частоты, соседи,
    статусы. md|json. Файл пишет фронт."""
    from app.services.chronicle import trait_gap_detector

    if format not in ("md", "json"):
        raise HTTPException(status_code=422, detail="format: только md|json")
    store = _get_store()
    from app.services.npc.npc_loader import list_individual_ids

    docs: Dict[str, Any] = {}
    for npc_id in list_individual_ids():
        canon = store.load_canonical(npc_id)
        if canon is not None:
            docs[npc_id] = canon
            continue
        try:
            draft = store.load_draft(campaign_id, npc_id)
        except ValueError as e:
            logger.warning(f"[CCH_GAPS] {npc_id}: draft невалиден — пропущен: {e}")
            continue
        if draft is not None:
            docs[npc_id] = draft
    rep = trait_gap_detector.build_report(docs, campaign_id)
    text = (
        trait_gap_detector.render_json(rep)
        if format == "json"
        else trait_gap_detector.render_markdown(rep)
    )
    return {"status": "OK", "format": format, "count": rep["total"], "text": text}

# ── CCH-4.5: отчёт понимания «поняла / не поняла» по каждому пункту ────────
router = chronicle_router

@router.get("/chronicle/{campaign}/understanding")
def get_understanding(campaign: str, source: str = "drafts",
                      format: str = "md") -> dict:
    """Каждый пункт author_text -> поняла/частично/не поняла.

    Конверт как у trait-gaps/beliefs-export: status/text/count.
    Полный отчёт — в поле report (per_npc records с matched — вердикты
    по пунктам; пригодится панели ИСТОРИЯ). source=drafts — LLM-черновики
    сейва; source=canon — то, что реально увидит сеялка после F9.
    """
    from app.core.config import BASE_DIR
    from app.services.chronicle.understanding_report import (
        build_report,
        docs_from_dir,
        render_json,
        render_markdown,
    )

    if source == "canon":
        base = BASE_DIR / "config" / "npc" / "chronicles"
    else:
        base = BASE_DIR / "saves" / campaign / "chronicle_drafts"
    docs, problems = docs_from_dir(base)
    if not docs:
        return {
            "status": "EMPTY",
            "campaign": campaign,
            "source": source,
            "problems": problems,
            "empty_reason": (
                "Канон пуст: сеялке пока нечего грузить — пункты ещё "
                "не приняты в канон (F9)."
                if source == "canon"
                else "Черновики не найдены: сохрани авторский текст и "
                "прогони разбор (Ctrl+G) хотя бы для одного NPC."
            ),
        }
    rep = build_report(docs, campaign)
    if problems:
        rep["problems"] = problems
    rep["source"] = source
    text = render_markdown(rep) if format != "json" else render_json(rep)
    return {
        "status": "OK",
        "text": text,
        "count": rep["totals"]["items"],
        "report": rep,
    }


@chronicle_router.post("/chronicle/{campaign_id}/{npc_id}/decompose")
async def decompose_fragment(campaign_id: str, npc_id: str, req: DecomposeRequest) -> Dict[str, Any]:
    """FR-2.x: фрагмент → декомпозиция. Результат merge-ится в ЧЕРНОВИК как
    LLM_DRAFT-записи (канон не трогается — запрет 1; повторный разбор того же
    фрагмента ЗАМЕНЯЕТ записи: entry_id детерминирован (chronicle:фрагмент:
    порядковый), дубли невозможны по построению). Мост «разбор → лампочка»."""
    result = await _get_decomposer().decompose(req.npc_id, req.fragment_ord, req.fragment)
    if not result.ok:
        return {"status": "NOT_DECOMPOSED", "error": result.error, "age_anchors": result.age_anchors or []}
    # ── Merge в draft (S345: мост transient → persistent) ──────────────────
    from app.domain.chronicle import (
        ChronicleDocument,
        ChronicleEntry,
        EntityRef,
        EntityRefKind,
        EntryProvenance,
        make_entry_id,
    )
    store = _get_store()
    doc = store.load_draft(req.campaign_id, req.npc_id)
    if doc is None:
        doc = ChronicleDocument(chronicle_id=req.npc_id, npc_ref=req.npc_id)
    new_ids = set()
    new_entries = []
    for _idx, _it in enumerate(result.items):
        _eid = make_entry_id(doc.chronicle_id, req.fragment_ord, _idx)
        new_ids.add(_eid)
        _age = _it.draft_payload.get("age", _it.draft_payload.get("historical_age"))
        # §1.1: однострочное «X if cond else None» = тихий отказ — развёрнуто
        _age_value = None
        if isinstance(_age, int):
            _age_value = _age
        new_entries.append(
            ChronicleEntry(
                entry_id=_eid,
                kind=_it.kind,
                subject_id=EntityRef(ref_kind=EntityRefKind.RESOLVED, npc_id=req.npc_id),
                historical_age=_age_value,
                payload=dict(_it.draft_payload),
                provenance=EntryProvenance.LLM_DRAFT,
                confidence=_it.confidence,
                open_questions=(_it.question,) if _it.question is not None else (),
                ordinal=req.fragment_ord * 100 + _idx,
            )
        )
    _kept = [e for e in doc.entries if e.entry_id not in new_ids]
    _merged = tuple(sorted(_kept + new_entries, key=lambda e: e.ordinal))
    store.save_draft(replace(doc, entries=_merged), req.campaign_id)
    return {
        "status": "OK",
        "age_anchors": result.age_anchors,
        "items": [
            {
                "kind": i.kind.value,
                "draft_payload": i.draft_payload,
                "confidence": i.confidence,
                "needs_confirmation": i.needs_confirmation,
                "question": None if i.question is None else {
                    "question_id": i.question.question_id,
                    "target_span": i.question.target_span,
                    "options": [o.value for o in i.question.options],
                },
            }
            for i in result.items
        ],
    }


@chronicle_router.get("/chronicle/{campaign_id}/{npc_id}/draft")
async def get_draft(campaign_id: str, npc_id: str) -> Dict[str, Any]:
    doc = _get_store().load_draft(campaign_id, npc_id)
    if doc is None:
        return {"status": "EMPTY"}
    return {"status": "OK", "document": document_to_dict(doc)}


@chronicle_router.put("/chronicle/{campaign_id}/{npc_id}/draft")
async def put_draft(campaign_id: str, npc_id: str, body: Dict[str, Any]) -> Dict[str, Any]:
    """Сохранение черновика (UI конструирует document-dict; валидация store)."""
    doc = document_from_dict({**body, "schema_version": body.get("schema_version", SCHEMA_VERSION)})
    if doc.npc_ref != npc_id:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="npc_ref не совпадает с {npc_id}")
    path = _get_store().save_draft(doc, campaign_id)
    return {"status": "OK", "path": str(path)}


@chronicle_router.post("/chronicle/{campaign_id}/{npc_id}/confirm-author-entries")
async def confirm_author_entries(campaign_id: str, npc_id: str) -> Dict[str, Any]:
    """S365: LLM_DRAFT -> AUTHOR_CONFIRMED для всех записей draft.
    Вызывается фронтом ДО canonize (T-CCH-04). Без него канон-валидатор
    падает с запретом 1 (LLM_DRAFT в каноне)."""
    from dataclasses import replace as _replace
    from app.domain.chronicle import EntryProvenance
    store = _get_store()
    doc = store.load_draft(campaign_id, npc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"Черновик {npc_id} не найден в {campaign_id}")
    new_entries = []
    confirmed = 0
    for e in doc.entries:
        if e.provenance is EntryProvenance.LLM_DRAFT:
            e = _replace(e, provenance=EntryProvenance.AUTHOR_CONFIRMED, confidence=None)
            confirmed += 1
        new_entries.append(e)
    new_doc = _replace(doc, entries=tuple(new_entries))
    store.save_draft(new_doc, campaign_id)
    return {"status": "OK", "confirmed": confirmed}


class CanonizeRequest(BaseModel):
    campaign_id: str = Field(..., min_length=1)

@chronicle_router.post("/chronicle/{campaign_id}/{npc_id}/canonize")
async def canonize_chronicle(campaign_id: str, npc_id: str, req: CanonizeRequest) -> Dict[str, Any]:
    """FR-10.1/10.2 (CCH-3): перевод draft → канон. Единственный путь
    LLM_DRAFT → AUTHOR_CONFIRMED реализован фронтендом ДО вызова (UI обязан
    выставить provenance-флаги по каждому item); здесь — валидация store
    (запрет 1: LLM_DRAFT в каноне; «Save = Contract»: открытые вопросы)
    + canonical_version++. Вытеснение старого канона — тихое (вердикт S336)."""
    store = _get_store()
    draft = store.load_draft(campaign_id, npc_id)
    if draft is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Черновик {npc_id} не найден в {campaign_id}")
    canonical = replace(
        draft,
        canonical=True,
        canonical_version=draft.canonical_version + 1,
    )
    try:
        path = store.save_canonical(canonical)
    except ValueError as e:
        # «Save = Contract»: LLM_DRAFT / открытые вопросы / dangling — блок с fix_hint
        raise HTTPException(status_code=422, detail=str(e)) from e
    return {"status": "OK", "path": str(path), "canonical_version": canonical.canonical_version}


class ResolveRequest(BaseModel):
    campaign_id: str = Field(..., min_length=1)
    npc_id: str = Field(..., min_length=1)
    question_id: str = Field(..., min_length=1)
    selected_option: str
    selected_value: Optional[str] = None


@chronicle_router.post("/chronicle/{campaign_id}/{npc_id}/resolve")
async def resolve_question(campaign_id: str, npc_id: str, req: ResolveRequest) -> Dict[str, Any]:
    """FR-3.1: резолюция открытого вопроса в draft. Убирает вопрос из
    open_questions записи (иначе _next_open_question найдёт его снова).
    История резолюции сохраняется в _resolved_questions (для аудита)."""
    from dataclasses import replace as _replace
    store = _get_store()
    doc = store.load_draft(campaign_id, npc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"Черновик {npc_id} не найден в {campaign_id}")
    new_entries = []
    changed = False
    for e in doc.entries:
        if any(q.question_id == req.question_id for q in e.open_questions):
            _remaining = tuple(q for q in e.open_questions if q.question_id != req.question_id)
            _resolved_old = e.payload.get("_resolved_questions", [])
            _resolved_new = list(_resolved_old) + [{
                "question_id": req.question_id,
                "selected_option": req.selected_option,
                "selected_value": req.selected_value,
            }]
            _new_payload = {**e.payload, "_resolved_questions": _resolved_new}
            e = _replace(e, open_questions=_remaining, payload=_new_payload)
            changed = True
        new_entries.append(e)
    if not changed:
        raise HTTPException(status_code=404, detail=f"Вопрос {req.question_id} не найден в open_questions")
    new_doc = _replace(doc, entries=tuple(new_entries))
    store.save_draft(new_doc, campaign_id)
    return {"status": "OK", "resolved": req.question_id}

# ── CCH-5: экспорт-проекции канон-хроник ─────────────────────────────────────
# Артефакты аудита в config/npc/chronicles/_projections/. НЕ источник истины
# для рантайма (npc_loader/chronicle_seeder не читают проекции). Канон —
# единственный SSOT. Атомарная публикация через поколение + current.json (A3).
# EXPLICIT: секретность — только payload['is_secret'] is True на kind=EVENT.

@chronicle_router.post("/chronicle/{campaign_id}/export-projections")
async def export_projections(campaign_id: str) -> Dict[str, Any]:
    """CCH-5 (ADR-O-420): публикация трёх проекций канон-хроник в форматы
    старых систем: origin_events / village_relations / truth_state.

    Возвращает:
      - status: OK | EMPTY | BLOCKED
      - generation_id: ID нового поколения (None при EMPTY/BLOCKED)
      - files: какие файлы опубликованы
      - truth_state_status: OK | EMPTY
      - diagnostics: счётчики и списки пропусков/блокировок
      - errors: структурно повреждённые ссылки (при BLOCKED)

    BLOCKED — структурно повреждённые ссылки (dangling origin_ref, unknown
    participants); поколение не публикуется, старый current.json действующий.
    EMPTY — нет канонов вообще или нет секретных EVENT (truth_state-файл
    не создаётся).
    """
    from app.services.chronicle.chronicle_projections import export_all_projections
    return export_all_projections(campaign_id)


@chronicle_router.get("/chronicle/projections/current")
async def get_current_projection() -> Dict[str, Any]:
    """Текущее активное поколение проекций (для аудита/тестов). None если
    никогда не публиковалось. Read-only — не запускает публикацию."""
    from app.services.chronicle.chronicle_projections import (
        list_generations,
        read_current_pointer,
    )
    current = read_current_pointer()
    return {
        "current": current,
        "generations": list_generations(),
    }
