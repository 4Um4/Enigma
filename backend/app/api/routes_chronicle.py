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
from dataclasses import replace as _dc_replace
from typing import Any, Dict, Optional

from app.core.config import BASE_DIR
from app.domain.chronicle import (
    SCHEMA_VERSION,
    BeliefGrounding,
    CandidateStatus,
    CauseKind,
    CauseRef,
    ChronicleDocument,
    EntryProvenance,
    NpcCausalBelief,
    make_belief_id,
)
from app.services.chronicle.biography_decomposer import BiographyDecomposer
from app.services.chronicle.causal_linker import CausalLinker, LinkResult
from app.services.chronicle.chronicle_store import (
    ChronicleStore,
    document_from_dict,
    document_to_dict,
)
from app.services.chronicle.consistency_service import CanonicalRegistry, ConsistencyService
from fastapi import APIRouter, HTTPException, Request
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
    LLM_DRAFT-записи (канон не трогается — запрет 1). Мост «разбор → лампочка».
    COV-12, семантика повторного разбора фрагмента:
        • заменяются ВСЕ LLM_DRAFT-записи данного фрагмента (ordinal-диапазон
        [F*100, F*100+100)) — включая осиротевшие при сокращении числа items;
        • авторские записи (AUTHOR_CONFIRMED/AUTHOR_AUTHORED) не трогаются;
        если слот (F, idx) занят авторской записью, свежий черновик получает
        salted id и сосуществует с ней — автор сравнит при ревью.
    entry_id детерминирован: md5(chronicle[:salt]:фрагмент:порядковый)."""
    result = await _get_decomposer().decompose(req.npc_id, req.fragment_ord, req.fragment)
    if not result.ok:
        return {
            "status": "NOT_DECOMPOSED",
            "error": result.error,
            "age_anchors": result.age_anchors or [],
            "raw_response": result.raw_response,  # S371.0: для диагностики JSON-ошибок
        }
    # ── Merge в draft (S345: мост transient → persistent) ──────────────────
    from app.domain.chronicle import (
        ChronicleDocument,
        ChronicleEntry,
        EntityRef,
        EntityRefKind,
        EntryKind,
        EntryProvenance,
        make_entry_id,
    )
    from app.services.chronicle.decomposition_normalizer import (
        resolve_object_ref_from_roster,
    )
    from app.services.npc.npc_loader import get_display_names

    store = _get_store()
    doc = store.load_draft(req.campaign_id, req.npc_id)
    if doc is None:
        doc = ChronicleDocument(chronicle_id=req.npc_id, npc_ref=req.npc_id)
    # COV-10.4: roster для auto-resolution exact-match target_hint → object_id.
    # Тот же источник, что и в normalizer (_default_roster_provider → get_display_names).
    # Без этого exact-match записи оставались без object_id И без open_questions —
    # «застрявшая» запись, seeder skip'ает, resolver не может разрешить.
    _roster = get_display_names()
    # COV-12 (п.0): ordinal = fragment_ord*100 + idx → максимум 99 items на
    # фрагмент. Промпт-контракт — 1..6, но 7B контракт нарушает; молчаливое
    # переполнение разрушает диапазонную замену ниже — отказ явно.
    if len(result.items) >= 100:
        return {
            "status": "NOT_DECOMPOSED",
            "error": (
                f"too many items ({len(result.items)}): лимит 99 на фрагмент "
                "(ordinal = fragment_ord*100 + idx)"
            ),
            "age_anchors": result.age_anchors or [],
            "raw_response": result.raw_response,
        }
    # COV-12: диапазон заменяемых записей — все LLM_DRAFT данного фрагмента.
    _frag_lo = req.fragment_ord * 100
    _frag_hi = _frag_lo + 100
    # id слотов, занятых авторскими решениями (confirm сохраняет entry_id):
    # свежий черновик не может претендовать на тот же id — иначе повторный
    # разбор молча удалял бы подтверждённое автором.
    _author_ids = {
        e.entry_id
        for e in doc.entries
        if e.provenance is not EntryProvenance.LLM_DRAFT
    }
    new_entries = []
    for _idx, _it in enumerate(result.items):
        _eid = make_entry_id(doc.chronicle_id, req.fragment_ord, _idx)
        _salt = 0
        while _eid in _author_ids:
            _salt += 1
            _eid = make_entry_id(
                f"{doc.chronicle_id}:redraft{_salt}", req.fragment_ord, _idx
            )
        _age = _it.draft_payload.get("age", _it.draft_payload.get("historical_age"))
        # §1.1: однострочное «X if cond else None» = тихий отказ — развёрнуто
        _age_value = None
        if isinstance(_age, int):
            _age_value = _age

        # §S368: детерминированный fallback. Контракт (chronicle_decompose_system.txt:39)
        # требует age=атрибут СОБЫТИЯ. Если LLM не проставила age явно (регулярно
        # наблюдается в дампе s368_age_dump.txt при anchors=[8] и age=None в payload),
        # а препарсер извлёк ровно один якорь и в декомпозиции ровно одно EVENT —
        # якорь принадлежит этому событию (фраза «В N лет <событие>»).
        # Множественность якорей или событий → неопределённость, не выдумываем
        # (§ENIGMA-003). Не применяется к RELATIONSHIP/EFFECT (контракт: age только
        # для событий). Не использует day/строки — отдельная дыра, не S368.
        if (
            _age_value is None
            and _it.kind is EntryKind.EVENT
            and result.age_anchors
            and len(result.age_anchors) == 1
        ):
            _event_count = sum(1 for x in result.items if x.kind is EntryKind.EVENT)
            if _event_count == 1:
                _age_value = result.age_anchors[0]
        # COV-10.4: auto-resolve object_id для RELATIONSHIP/EFFECT с exact roster match.
        # Если normalizer создал ClarificationQuestion (non-match) — _it.question is not None,
        # и object_id остаётся None (автор разрешит через resolve_question).
        # Если exact match — question is None, и без этой резолюции запись осталась бы
        # без object_id и без open_questions («застрявшая» запись, seeder skip'ает).
        _object_id = None
        if _it.question is None and _it.kind in (EntryKind.RELATIONSHIP, EntryKind.EFFECT):
            _hint = _it.draft_payload.get("target_hint")
            if isinstance(_hint, str) and _hint.strip():
                _object_id = resolve_object_ref_from_roster(_hint, _roster)
        elif _it.question is not None and _it.kind in (EntryKind.RELATIONSHIP, EntryKind.EFFECT):
            # COV-12 (п.2b): placeholder EntityRef для non-match target_hint.
            # Без этого /resolve не находил EntityRef по _match (name_hint ==
            # target_span): object_id был None, _match искал по name_hint, а
            # name_hint у subject_id пустой → white spot создавался в
            # doc.white_spots, но запись на него не ссылалась (терялась при
            # канонизации). Placeholder NEW_NPC-name_hint=target_hint теперь
            # найдётся _match и перелинкуется на WHITE_SPOT/RESOLVED/UNKNOWN.
            _hint = _it.draft_payload.get("target_hint")
            if isinstance(_hint, str) and _hint.strip():
                _object_id = EntityRef(
                    ref_kind=EntityRefKind.NEW_NPC,
                    name_hint=_hint.strip(),
                )
        new_entries.append(
            ChronicleEntry(
                entry_id=_eid,
                kind=_it.kind,
                subject_id=EntityRef(ref_kind=EntityRefKind.RESOLVED, npc_id=req.npc_id),
                object_id=_object_id,
                historical_age=_age_value,
                payload=dict(_it.draft_payload),
                provenance=EntryProvenance.LLM_DRAFT,
                confidence=_it.confidence,
                open_questions=(_it.question,) if _it.question is not None else (),
                ordinal=req.fragment_ord * 100 + _idx,
            )
        )
    # COV-12: LLM_DRAFT-записи этого фрагмента заменяются ЦЕЛИКОМ (лечит
    # осиротевшие записи при сокращении items, напр. 4→3); авторские записи
    # в диапазоне сохраняются, прочие фрагменты не затрагиваются.
    _kept = [
        e
        for e in doc.entries
        if not (
            e.provenance is EntryProvenance.LLM_DRAFT
            and _frag_lo <= e.ordinal < _frag_hi
        )
    ]
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
        # COV-12 (п.1): coverage gate — пустой items теперь легален (право на
        # ноль), но автор должен видеть: 0 записей может быть как осознанным
        # (шапка), так и провалом LLM (молчание на критичной теме). Coverage
        # показывает контекст, не блокируя сохранение.
        "coverage": {
            "fragment_ord": req.fragment_ord,
            "items_count": len(result.items),
            "fragment_text_preview": req.fragment[:80],
            "critical_topic_warning": (
                # COV-12 (п.1): маркеры критичных тем. Подстрока, не морфология —
                # точности достаточно для warning (не для block). Список не
                # окончательный, расширяется по мере обнаружения слепых зон.
                "фрагмент содержит маркеры критичной темы (насилие/преступление/"
                "донос), но декомпозер не создал ни одной записи — проверить "
                "осознанно"
                if len(result.items) == 0
                and any(
                    m in req.fragment.lower()
                    for m in (
                        "насил", "изнасил", "шантаж", "донос", "предал",
                        "предательство", "убил", "убийств", "измен",
                        "преступл", "контрабанд",
                    )
                )
                else None
            ),
        },
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
    skipped_open_questions = 0
    skipped_low_confidence = 0
    for e in doc.entries:
        if e.provenance is EntryProvenance.LLM_DRAFT:
            # COV-12 (п.2a): разоружить confirm. Кнопка больше не переводит
            # в AUTHOR_CONFIRMED записи, требующие внимания автора:
            # - открытые вопросы (нужно /resolve);
            # - низкая уверенность LLM (<0.5) — требует ревью.
            # Раньше массово подтверждалось всё, включая мусор.
            if e.open_questions:
                skipped_open_questions += 1
                new_entries.append(e)
                continue
            if e.confidence is not None and e.confidence < 0.5:
                skipped_low_confidence += 1
                new_entries.append(e)
                continue
            e = _replace(e, provenance=EntryProvenance.AUTHOR_CONFIRMED, confidence=None)
            confirmed += 1
        new_entries.append(e)
    new_doc = _replace(doc, entries=tuple(new_entries))
    store.save_draft(new_doc, campaign_id)
    return {
        "status": "OK",
        "confirmed": confirmed,
        "skipped_open_questions": skipped_open_questions,
        "skipped_low_confidence": skipped_low_confidence,
    }


class CanonizeRequest(BaseModel):
    campaign_id: str = Field(..., min_length=1)

def _check_canonical_consistency(doc: ChronicleDocument) -> None:
    """CCH-7 Semantic Validation Gate (ADR-O-422, T-CCH-SV-01).

    Обязательный шаг семантической валидации перед save_canonical.
    Блокирует ТОЛЬКО CONTRADICTION canon-level (ссылка на несуществующего
    канонного NPC) — единственное нарушение, которое:
      - не ловится validate_document (только white_spot dangling блокируется
        store-уровнем; RESOLVED EntityRef на несуществующий npc_id — нет);
      - семантически означает «документ противоречит канону игры».

    Все остальные Finding.kind (MERGE_CANDIDATE, GAP, QUESTION, CANON_SYNC,
    INFO) — диагностические карточки автору (ADR-O-422), НЕ блокирующие
    канонизацию. Логируются как WARNING.

    Техническая ошибка сервиса (Exception) — НЕ маскируется под успех:
    пробрасывается как HTTP 500.
    """
    registry = _build_registry_for_canonize()
    report = ConsistencyService().check([doc], registry)
    contradictions = [
        f for f in report.findings
        if f.kind == "CONTRADICTION" and f.level == "canon"
    ]
    if contradictions:
        # Диагностируемый первый finding (детерминированно — по entry_id)
        c = contradictions[0]
        detail = (
            f"Semantic validation (CCH-7): {c.message} "
            f"[entry_id={c.doc_refs[0][1] if c.doc_refs else 'unknown'}]"
        )
        raise ValueError(detail)
    # Диагностические (не блокирующие) — логируем
    for f in report.findings:
        if f.kind != "CONTRADICTION":
            logger.info(
                "CCH-7 diagnostic (non-blocking): [%s/%s] %s",
                f.kind, f.level, f.message,
            )


def _build_registry_for_canonize() -> "CanonicalRegistry":
    """Точка для monkeypatch в тестах. Делегирует в прод-модуль registry_builder."""
    from app.services.chronicle.registry_builder import build_canonical_registry
    return build_canonical_registry()


@chronicle_router.post("/chronicle/{campaign_id}/{npc_id}/canonize")
async def canonize_chronicle(campaign_id: str, npc_id: str, req: CanonizeRequest) -> Dict[str, Any]:
    """FR-10.1/10.2 (CCH-3): перевод draft → канон. Единственный путь
    LLM_DRAFT → AUTHOR_CONFIRMED реализован фронтендом ДО вызова (UI обязан
    выставить provenance-флаги по каждому item); здесь — валидация store
    (запрет 1: LLM_DRAFT в каноне; «Save = Contract»: открытые вопросы)
    + CCH-7 Semantic Validation Gate (ADR-O-422, T-CCH-SV-01) + canonical_version++.
    Вытеснение старого канона — тихое (вердикт S336)."""
    store = _get_store()
    draft = store.load_draft(campaign_id, npc_id)
    if draft is None:
        raise HTTPException(status_code=404, detail=f"Черновик {npc_id} не найден в {campaign_id}")
    canonical = replace(
        draft,
        canonical=True,
        canonical_version=draft.canonical_version + 1,
    )
    # CCH-7: семантическая валидация (Contradiction canon-level) ДО save_canonical.
    # ValueError здесь → 422 с fix_hint (как у save_canonical ниже — единый контракт).
    # Техническая ошибка сервиса → проброс как 500 (не маскируется под успех).
    try:
        _check_canonical_consistency(canonical)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:
        # L4 fail-loud: техническая ошибка сервиса не должна пройти как успех.
        logger.error("CCH-7 ConsistencyService technical error: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"ConsistencyService internal error: {e}",
        ) from e
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

    S369: для каждой опции выполняет контрактуальную перелинковку EntityRef:
    - LEAVE_WHITE_SPOT → создать WhiteSpot (idempotent) + перелинк на WHITE_SPOT
    - SELECT_EXISTING_NPC → перелинк на RESOLVED с npc_id=selected_value
    - UNKNOWN_PERSON → перелинк на UNKNOWN_PERSON с name_hint=target_span
    - CREATE_NEW_NPC → перелинк на UNKNOWN_PERSON (placeholder, warning)
    История резолюции сохраняется в _resolved_questions (для аудита)."""
    from dataclasses import replace as _replace

    from app.domain.chronicle import (
        ClarificationOption,
        EntityRef,
        EntityRefKind,
        WhiteSpot,
        WhiteSpotResolutionState,
    )

    store = _get_store()
    doc = store.load_draft(campaign_id, npc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"Черновик {npc_id} не найден в {campaign_id}")

    # Валидация опции
    try:
        opt = ClarificationOption(req.selected_option)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Неизвестная опция: {req.selected_option}")

    # SELECT_EXISTING_NPC требует selected_value (npc_id)
    if opt is ClarificationOption.SELECT_EXISTING_NPC and not req.selected_value:
        raise HTTPException(
            status_code=422, detail="SELECT_EXISTING_NPC требует selected_value (npc_id)"
        )

    # Найти entry с этим question + сам question
    target_entry_idx: Optional[int] = None
    target_question = None
    for i, e in enumerate(doc.entries):
        for q in e.open_questions:
            if q.question_id == req.question_id:
                target_entry_idx = i
                target_question = q
                break
        if target_entry_idx is not None:
            break

    if target_entry_idx is None or target_question is None:
        raise HTTPException(status_code=404, detail=f"Вопрос {req.question_id} не найден в open_questions")
    assert target_entry_idx is not None

    target_span = target_question.target_span
    target_entry = doc.entries[target_entry_idx]

    # Найти какой EntityRef перелинковать (по name_hint == target_span)
    def _match(ref: Optional[EntityRef]) -> bool:
        return ref is not None and ref.name_hint == target_span and target_span != ""

    matches_subject = _match(target_entry.subject_id)
    matches_object = _match(target_entry.object_id)
    if matches_subject and matches_object:
        logger.warning(
            "resolve_question[%s]: target_span='%s' совпал и с subject_id, и с object_id "
            "в entry %s — выбираю subject_id",
            req.question_id, target_span, target_entry.entry_id,
        )

    # Создать WhiteSpot для LEAVE_WHITE_SPOT (idempotent — не дублировать)
    new_white_spots = list(doc.white_spots)
    if opt is ClarificationOption.LEAVE_WHITE_SPOT:
        if not any(ws.white_spot_id == req.question_id for ws in new_white_spots):
            new_ws = WhiteSpot(
                white_spot_id=req.question_id,
                label=target_span,
                context_hint=f"resolved via /resolve (entry={target_entry.entry_id})",
                resolution_state=WhiteSpotResolutionState.OPEN,
                created_from_entry=target_entry.entry_id,
            )
            new_white_spots.append(new_ws)

    # Перелинковка EntityRef под выбранную опцию
    def _relink(ref: EntityRef) -> EntityRef:
        if not _match(ref):
            return ref
        if opt is ClarificationOption.LEAVE_WHITE_SPOT:
            return EntityRef(
                ref_kind=EntityRefKind.WHITE_SPOT,
                white_spot_id=req.question_id,
                name_hint=ref.name_hint,
            )
        if opt is ClarificationOption.SELECT_EXISTING_NPC:
            return EntityRef(
                ref_kind=EntityRefKind.RESOLVED,
                npc_id=req.selected_value,
                name_hint=ref.name_hint,
            )
        if opt is ClarificationOption.UNKNOWN_PERSON:
            return EntityRef(
                ref_kind=EntityRefKind.UNKNOWN_PERSON,
                name_hint=ref.name_hint or target_span,
            )
        # CREATE_NEW_NPC — создание NPC вне скоупа /resolve; placeholder
        logger.warning(
            "resolve_question[%s]: CREATE_NEW_NPC selected_value='%s' — "
            "создание NPC вне скоупа, перелинковка на UNKNOWN_PERSON (placeholder)",
            req.question_id, req.selected_value,
        )
        return EntityRef(
            ref_kind=EntityRefKind.UNKNOWN_PERSON,
            name_hint=req.selected_value or ref.name_hint or target_span,
        )

    # Применить к target entry + убрать question + audit-запись
    new_entries = list(doc.entries)
    e = target_entry
    new_subject = _relink(e.subject_id) if (matches_subject and e.subject_id is not None) else e.subject_id
    new_object = _relink(e.object_id) if (matches_object and e.object_id is not None) else e.object_id

    _remaining = tuple(q for q in e.open_questions if q.question_id != req.question_id)
    _resolved_old = e.payload.get("_resolved_questions", [])
    _resolved_new = list(_resolved_old) + [{
        "question_id": req.question_id,
        "selected_option": req.selected_option,
        "selected_value": req.selected_value,
    }]
    _new_payload = {**e.payload, "_resolved_questions": _resolved_new}

    e = _replace(
        e,
        subject_id=new_subject,
        object_id=new_object,
        open_questions=_remaining,
        payload=_new_payload,
    )
    new_entries[target_entry_idx] = e

    new_doc = _replace(doc, entries=tuple(new_entries), white_spots=tuple(new_white_spots))
    store.save_draft(new_doc, campaign_id)
    return {
        "status": "OK",
        "resolved": req.question_id,
        "white_spots_count": len(new_white_spots),
        "selected_option": req.selected_option,
    }

# ── CCH-5: экспорт-проекции канон-хроник ─────────────────────────────────────
# Артефакты аудита в config/npc/chronicles/_projections/. НЕ источник истины
# для рантайма (npc_loader/chronicle_seeder не читают проекции). Канон —
# единственный SSOT. Атомарная публикация через поколение + current.json (A3).
# EXPLICIT: секретность — только payload['is_secret'] is True на kind=EVENT.

@chronicle_router.get("/chronicle/{campaign_id}/{npc_id}/debug")
async def get_character_debug(campaign_id: str, npc_id: str, request: Request) -> Dict[str, Any]:
    """CCH-4 Character Debugger (FR-9.x, ADR-O-420): read-only окно Workbench layer 4.

    «СЕЙЧАС» — snapshot runtime NPCState: causal_ledger (последние 20),
    body_state, stress, will_state, life_project_state, intent, drives_base,
    behavior_mask, affective_load.
    «ИСТОЧНИКИ» — канон-entries (с subject/object/cause), white_spots,
    npc_beliefs, cause_candidates.

    4 состояния данных (дополнение Мастера 2026-10-25):
    - KNOWN — данные присутствуют и непусты
    - NOT_AUTHORED — поле есть в схеме, но в каноне отсутствует (автор не заполнил)
    - NOT_LOADED — runtime NPCState не найден (campaign/NPC не загружен)
    - INIT_ERROR — runtime NPCState повреждён (body_state=None и т.п.)

    Read-only: не мутирует состояние. Запрет 10 ADR-O-420.
    Изоляция от HUD: данные НЕ входят в WorldSnapshotDTO (запрет 7 ADR-O-420).
    """
    from app.services.game_loop_accessor import get_game_loop

    response: Dict[str, Any] = {
        "campaign_id": campaign_id,
        "npc_id": npc_id,
        "now": {},
        "sources": {},
        "states": {},
    }

    # ── СЕЙЧАС — runtime NPCState ───────────────────────────────────────────
    loop = None
    try:
        loop = get_game_loop(request)
    except RuntimeError:
        response["states"]["runtime"] = "NOT_LOADED"
        response["now"] = None
    else:
        all_npcs = loop._load_npcs_with_runtime(campaign_id)
        npc_dict: Optional[Dict[str, Any]] = None
        for n in all_npcs:
            if n.get("id") == npc_id or n.get("npc_id") == npc_id:
                npc_dict = n
                break

        if npc_dict is None:
            response["states"]["runtime"] = "NOT_LOADED"
            response["now"] = None
        else:
            body_state = npc_dict.get("body_state")
            if body_state is None or (isinstance(body_state, dict) and body_state.get("disabled")):
                runtime_state = "INIT_ERROR"
            else:
                runtime_state = "KNOWN"
            response["states"]["runtime"] = runtime_state

            psyche = npc_dict.get("psyche", {})
            ledger_raw = npc_dict.get("causal_ledger", [])
            # B1 (COV-11): runtime observability — populated memory/cache/imprints/beliefs.
            # Read-only: reads existing npc_dict fields; does NOT call seeder or materialize.
            # null = field absent in npc_dict (NOT_LOADED); 0/[] = field present but empty.
            _narrative_cache = npc_dict.get("narrative_cache")
            _relationship_cache = npc_dict.get("relationship_cache")
            _affective_imprints = npc_dict.get("affective_imprints")
            _psyche_beliefs = psyche.get("beliefs")
            response["now"] = {
                "npc_id": npc_id,
                "name": npc_dict.get("name", ""),
                "current_role": npc_dict.get("current_role", "unknown"),
                "stress": psyche.get("stress", 0.0),
                "will_state": psyche.get("state", "free"),
                "affective_load": psyche.get("affective_load", 0.0),
                "life_project_state": npc_dict.get("life_project_state", "ACTIVE"),
                "intent": npc_dict.get("intent"),
                "intent_target": npc_dict.get("intent_target"),
                "drives_base": psyche.get("drives_base", {}),
                "behavior_mask": npc_dict.get("behavior_mask", {}),
                "body_state": body_state,
                "causal_ledger_last_20": ledger_raw[-20:] if ledger_raw else [],
                "ledger_size": len(ledger_raw),
                # B1: runtime memory/cache/imprints/beliefs observability (COV-11).
                # null = field absent in npc_dict; counts/lists = field present.
                "episodic_memory_count": (
                    len(_narrative_cache) if _narrative_cache is not None else None
                ),
                "relationship_cache_targets": (
                    sorted(_relationship_cache.keys())
                    if isinstance(_relationship_cache, dict) else None
                ),
                "affective_imprints_count": (
                    len(_affective_imprints) if _affective_imprints is not None else None
                ),
                "psyche_beliefs_types": (
                    sorted(_psyche_beliefs.keys())
                    if isinstance(_psyche_beliefs, dict) else None
                ),
            }

    # ── ИСТОЧНИКИ — канон-хроника ──────────────────────────────────────────
    store = _get_store()
    canon_doc = store.load_canonical(npc_id)
    if canon_doc is None:
        response["states"]["chronicle"] = "NOT_AUTHORED"
        response["sources"] = None
        response["seed_summary"] = None
    else:
        response["states"]["chronicle"] = "KNOWN"
        response["sources"] = {
            "chronicle_id": canon_doc.chronicle_id,
            "canonical_version": canon_doc.canonical_version,
            "game_start_age": canon_doc.game_start_age,
            "entries": [
                {
                    "entry_id": e.entry_id,
                    "kind": e.kind.value,
                    "subject_id": (
                        {
                            "ref_kind": e.subject_id.ref_kind.value,
                            "npc_id": e.subject_id.npc_id,
                            "white_spot_id": e.subject_id.white_spot_id,
                            "name_hint": e.subject_id.name_hint,
                        } if e.subject_id else None
                    ),
                    "object_id": (
                        {
                            "ref_kind": e.object_id.ref_kind.value,
                            "npc_id": e.object_id.npc_id,
                            "white_spot_id": e.object_id.white_spot_id,
                            "name_hint": e.object_id.name_hint,
                        } if e.object_id else None
                    ),
                    "historical_age": e.historical_age,
                    "kind_value": e.kind.value,
                    "causes": [
                        {"cause_kind": c.cause_kind.value, "origin_ref": c.origin_ref}
                        for c in e.causes
                    ],
                    "provenance": e.provenance.value,
                }
                for e in canon_doc.entries
            ],
            "white_spots": [
                {
                    "white_spot_id": ws.white_spot_id,
                    "label": ws.label,
                    "resolution_state": ws.resolution_state.value,
                    "resolution_ref": ws.resolution_ref,
                    "created_from_entry": ws.created_from_entry,
                }
                for ws in canon_doc.white_spots
            ],
            "npc_beliefs_count": len(canon_doc.npc_beliefs),
            "cause_candidates_count": len(canon_doc.cause_candidates),
        }
        # CCH-8 P1: seed_summary — независимая диагностика, не статус загрузки.
        # KNOWN остаётся статусом. Не утверждает фактическое runtime-состояние
        # EventMemory в NpcState — только то, что seeder смог бы произвести
        # из текущего канона. Read-only: build_seed_report — pure function.
        from app.services.chronicle.chronicle_seeder import build_seed_report
        _sr = build_seed_report(npc_id)
        response["seed_summary"] = {
            "available": _sr is not None,
            "memories": _sr.memories_count if _sr else 0,
            "knowledge": _sr.knowledge_count if _sr else 0,
            "relationships": _sr.relationships_count if _sr else 0,
            "imprints": _sr.imprints_count if _sr else 0,
            "beliefs": _sr.beliefs_count if _sr else 0,
            "white_spots": _sr.white_spots_count if _sr else 0,
            "entries_total": _sr.entries_total if _sr else 0,
            "entries_author": _sr.entries_author if _sr else 0,
        }

    return response


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


# ===== S366: Причинные кандидаты и NPC-убеждения =====
# ТРИ ЗАПРЕТА (вердикт Мастера §1):
# 1. TEMPORAL_ORDER — детекция, не проставление.
# 2. ACCEPT — НЕ создаёт NpcCausalBelief.
# 3. MISTAKEN — НЕ выводится из отсутствия CauseRef.


class LinkCausesResponse(BaseModel):
    status: str
    validation_errors: list
    new_candidates: list
    existing_candidates: list
    truncated: bool
    truncation_reason: str
    stats: dict


class ResolveCandidateRequest(BaseModel):
    candidate_id: str
    resolution: str  # "ACCEPT" | "REJECT_SILENT"


class RecordBeliefRequest(BaseModel):
    believer_id: str
    effect_entry_id: str
    alleged_cause_entry_id: str
    alleged_cause_kind: str  # CauseKind value
    grounding: str = "UNVERIFIED"  # BeliefGrounding value
    provenance: str = "LLM_DRAFT"  # EntryProvenance value
    confidence: float | None = None


@chronicle_router.post("/chronicle/{campaign_id}/{npc_id}/link-causes")
async def link_causes(campaign_id: str, npc_id: str) -> Dict[str, Any]:
    """S366: детекция причинных кандидатов + валидация существующих causes.
    НЕ проставляет causes. НЕ создаёт NpcCausalBelief. Idempotent.

    Возвращает:
    - validation_errors: список нарушений (INV-CANON-CAUSE-REF, VALIDATION_WARNING для white_spot_id).
    - new_candidates: новые CauseCandidate для рассмотрения автором (PENDING).
    - existing_candidates: уже существующие кандидаты в документе.
    - truncated: всегда False (лимит 5 на entry обрабатывается внутри detect_candidates).
    """
    store = _get_store()
    doc = store.load_canonical(npc_id) or store.load_draft(campaign_id, npc_id)
    if doc is None:
        return {"status": "NOT_FOUND", "error": f"chronicle {npc_id} not found"}

    linker = CausalLinker()
    result: LinkResult = linker.link(doc)

    # Сохраняем новых PENDING-кандидатов в документ (не в causes!)
    if result.new_candidates:
        updated_candidates = tuple(doc.cause_candidates) + result.new_candidates
        doc = _dc_replace(doc, cause_candidates=updated_candidates)
        store.save_canonical(doc) if doc.canonical else store.save_draft(doc, campaign_id)

    return {
        "status": "OK",
        "validation_errors": [
            {"entry_id": ve.entry_id, "error_code": ve.error_code, "message": ve.message}
            for ve in result.validation_errors
        ],
        "new_candidates": [
            {
                "candidate_id": c.candidate_id,
                "effect_entry_id": c.effect_entry_id,
                "candidate_entry_id": c.candidate_entry_id,
                "candidate_kind": c.candidate_kind.value,
                "basis": c.basis.value,
                "rationale": c.rationale,
                "status": c.status.value,
            }
            for c in result.new_candidates
        ],
        "existing_candidates": [
            {
                "candidate_id": c.candidate_id,
                "effect_entry_id": c.effect_entry_id,
                "candidate_entry_id": c.candidate_entry_id,
                "candidate_kind": c.candidate_kind.value,
                "basis": c.basis.value,
                "rationale": c.rationale,
                "status": c.status.value,
            }
            for c in result.existing_candidates
        ],
        "truncated": result.truncated,
        "truncation_reason": result.truncation_reason,
        "stats": result.stats,
    }


@chronicle_router.post("/chronicle/{campaign_id}/{npc_id}/resolve-cause-candidate")
async def resolve_cause_candidate(
    campaign_id: str, npc_id: str, req: ResolveCandidateRequest
) -> Dict[str, Any]:
    """S366: явное решение автора по кандидату.
    - ACCEPT → добавляет CauseRef(cause_kind, origin_ref=candidate_entry_id) в effect.causes.
    - REJECT_SILENT → кандидат → REJECTED, ничего больше.
    НЕ создаёт NpcCausalBelief (запрет 2, §1 Мастера).
    Idempotent: повторный вызов с тем же candidate_id и resolution — no-op.
    Ошибка 400 если кандидат уже разрешён с другим resolution.
    """
    if req.resolution not in ("ACCEPT", "REJECT_SILENT"):
        return {"status": "BAD_REQUEST", "error": f"resolution must be ACCEPT or REJECT_SILENT, got {req.resolution!r}"}

    store = _get_store()
    doc = store.load_canonical(npc_id) or store.load_draft(campaign_id, npc_id)
    if doc is None:
        return {"status": "NOT_FOUND", "error": f"chronicle {npc_id} not found"}

    # Найти кандидатa
    cand = None
    for c in doc.cause_candidates:
        if c.candidate_id == req.candidate_id:
            cand = c
            break
    if cand is None:
        return {"status": "NOT_FOUND", "error": f"candidate {req.candidate_id} not found"}

    # Idempotency: уже разрешён?
    if cand.status is CandidateStatus.ACCEPTED:
        if req.resolution == "ACCEPT":
            return {"status": "OK", "already": "ACCEPTED", "updated_entry_id": cand.effect_entry_id}
        else:
            return {"status": "BAD_REQUEST", "error": f"candidate {req.candidate_id} already ACCEPTED, cannot REJECT_SILENT"}
    if cand.status is CandidateStatus.REJECTED:
        if req.resolution == "REJECT_SILENT":
            return {"status": "OK", "already": "REJECTED"}
        else:
            return {"status": "BAD_REQUEST", "error": f"candidate {req.candidate_id} already REJECTED, cannot ACCEPT"}

    # Найти effect entry
    effect = None
    for e in doc.entries:
        if e.entry_id == cand.effect_entry_id:
            effect = e
            break
    if effect is None:
        return {"status": "BAD_REQUEST", "error": f"effect_entry_id {cand.effect_entry_id} not found in document"}

    if req.resolution == "ACCEPT":
        # Добавить CauseRef в effect.causes (без дублей)
        new_cause = CauseRef(cause_kind=cand.candidate_kind, origin_ref=cand.candidate_entry_id)
        existing_refs = {(c.cause_kind, c.origin_ref) for c in effect.causes}
        if (new_cause.cause_kind, new_cause.origin_ref) in existing_refs:
            # CauseRef уже есть (например, проставлен вручную) — просто пометить ACCEPTED
            new_causes = effect.causes
        else:
            new_causes = effect.causes + (new_cause,)
        # Заменить entry в документе
        new_entries = tuple(
            _dc_replace(e, causes=new_causes) if e.entry_id == effect.entry_id else e
            for e in doc.entries
        )
        # Пометить кандидатa ACCEPTED
        new_cands = tuple(
            _dc_replace(c, status=CandidateStatus.ACCEPTED) if c.candidate_id == cand.candidate_id else c
            for c in doc.cause_candidates
        )
        doc = _dc_replace(doc, entries=new_entries, cause_candidates=new_cands)
    else:  # REJECT_SILENT
        new_cands = tuple(
            _dc_replace(c, status=CandidateStatus.REJECTED) if c.candidate_id == cand.candidate_id else c
            for c in doc.cause_candidates
        )
        doc = _dc_replace(doc, cause_candidates=new_cands)

    # Сохранить
    store.save_canonical(doc) if doc.canonical else store.save_draft(doc, campaign_id)

    return {
        "status": "OK",
        "resolution": req.resolution,
        "candidate_id": req.candidate_id,
        "updated_entry_id": cand.effect_entry_id if req.resolution == "ACCEPT" else None,
    }


@chronicle_router.post("/chronicle/{campaign_id}/{npc_id}/record-npc-belief")
async def record_npc_belief(
    campaign_id: str, npc_id: str, req: RecordBeliefRequest
) -> Dict[str, Any]:
    """S366: явная запись NPC-убеждения о причинной связи.
    НЕ мутирует ChronicleEntry.causes (СЛОЙ 1). Записывает в doc.npc_beliefs (СЛОЙ 2).
    MISTAKEN — только явное решение автора (запрет 3: не выводится автоматически из отсутствия CauseRef).

    Валидация:
    - believer_id не пустой.
    - effect_entry_id и alleged_cause_entry_id существуют в doc.entries.
    - alleged_cause_kind ∈ CauseKind.
    - grounding ∈ BeliefGrounding.
    - provenance/confidence — по контракту ChronicleEntry (LLM_DRAFT → confidence обязателен).
    """
    try:
        cause_kind = CauseKind(req.alleged_cause_kind)
        grounding = BeliefGrounding(req.grounding)
        provenance = EntryProvenance(req.provenance)
    except ValueError as e:
        logger.warning("[CCH_BELIEF] invalid enum value: %s", e)
        return {"status": "BAD_REQUEST", "error": f"invalid enum value: {e}"}

    store = _get_store()
    doc = store.load_canonical(npc_id) or store.load_draft(campaign_id, npc_id)
    if doc is None:
        return {"status": "NOT_FOUND", "error": f"chronicle {npc_id} not found"}

    entry_ids = {e.entry_id for e in doc.entries}
    if req.effect_entry_id not in entry_ids:
        return {"status": "BAD_REQUEST", "error": f"effect_entry_id {req.effect_entry_id} not in document"}
    if req.alleged_cause_entry_id not in entry_ids:
        return {"status": "BAD_REQUEST", "error": f"alleged_cause_entry_id {req.alleged_cause_entry_id} not in document"}

    # Минимальная believer-валидация: believer_id не пустой (full roster-check — за пределами S366)
    if not req.believer_id:
        return {"status": "BAD_REQUEST", "error": "believer_id must not be empty"}

    # Idempotency: если уже есть belief с тем же (believer, effect, alleged_cause) — обновляем
    belief_id = make_belief_id(req.believer_id, req.effect_entry_id, req.alleged_cause_entry_id)
    try:
        new_belief = NpcCausalBelief(
            believer_id=req.believer_id,
            effect_entry_id=req.effect_entry_id,
            alleged_cause_entry_id=req.alleged_cause_entry_id,
            alleged_cause_kind=cause_kind,
            grounding=grounding,
            provenance=provenance,
            confidence=req.confidence,
        )
    except ValueError as e:
        logger.warning("[CCH_BELIEF] belief validation failed: %s", e)
        return {"status": "BAD_REQUEST", "error": f"belief validation failed: {e}"}

    # Replace existing or append
    existing_beliefs = list(doc.npc_beliefs)
    replaced = False
    for i, b in enumerate(existing_beliefs):
        if (b.believer_id == req.believer_id
                and b.effect_entry_id == req.effect_entry_id
                and b.alleged_cause_entry_id == req.alleged_cause_entry_id):
            existing_beliefs[i] = new_belief
            replaced = True
            break
    if not replaced:
        existing_beliefs.append(new_belief)
    doc = _dc_replace(doc, npc_beliefs=tuple(existing_beliefs))

    store.save_canonical(doc) if doc.canonical else store.save_draft(doc, campaign_id)

    return {
        "status": "OK",
        "belief_id": belief_id,
        "action": "UPDATED" if replaced else "CREATED",
        "believer_id": req.believer_id,
        "effect_entry_id": req.effect_entry_id,
        "alleged_cause_entry_id": req.alleged_cause_entry_id,
        "grounding": grounding.value,
    }
