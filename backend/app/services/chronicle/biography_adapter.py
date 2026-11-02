"""
BiographyAdapter — проектор ChronicleEntry → USLUnit (USL-1.2, ADR-O-437).

Назначение: проецирует уже разобранный канон хроники в общий словарь смысла USL.
Не парсит author_text — это работа BiographyDecomposer. Адаптер работает с
уже структурированными полями ChronicleEntry (вердикт Мастера Q3: «адаптеры
не парсеры»).

Контракты:
    - pure function: одинаковый ChronicleDocument → одинаковый List[USLUnit]
    - read-only: не пишет в канон/EventMemory/EpistemicStore (USL-3)
    - transient: USLUnit не персистится (прецедент BiographyDecomposition)
    - frozen: USLUnit и все вложенные immutable
    - provenance: source_span обязателен (USL-5)

Conservative mapping: EVENT → ASSERTS (без специализации BORN/DIED — future work,
не угадываем). RELATIONSHIP → ASSERTS + USLRelation (тип из payload.nature).
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from app.domain.chronicle import (
    ChronicleDocument,
    ChronicleEntry,
    EntityRef,
    EntityRefKind,
    EntryKind,
    EntryProvenance,
    KP_CHANNEL,
    KP_CERTAINTY,
    KP_EVENT_REF,
    KP_KNOWER,
    KP_LEARNED_AGE,
    KP_LEARNED_YEAR,
    KnowledgeChannel,
)
from app.domain.usl import (
    USLAnchorKind,
    USLContext,
    USLEntityRef,
    USLEpistemics,
    USLEvent,
    USLModal,
    USLPredicate,
    USLRelation,
    USLSourceKind,
    USLSourceRef,
    USLTimeExpression,
    USLTimeKind,
    USLUnit,
    make_unit_id,
)


# ── 1. Mapping: EntryKind → USLPredicate ──────────────────────────────────────
# Прецедент: entry_kind_to_cause_kind (chronicle.py:114-123).
# Conservative mapping — без угадывания BORN/DIED для EVENT (future work).
_ENTRY_KIND_TO_USL_PREDICATE: Dict[EntryKind, USLPredicate] = {
    EntryKind.EVENT: USLPredicate.ASSERTS,           # общий предикат события
    EntryKind.RELATIONSHIP: USLPredicate.ASSERTS,    # + USLRelation(relation_type=nature)
    EntryKind.LOCATION: USLPredicate.LIVES_AT,
    EntryKind.EFFECT: USLPredicate.HAS_EFFECT,
    EntryKind.BELIEF_SEED: USLPredicate.BELIEVES,
    EntryKind.KNOWLEDGE_LINK: USLPredicate.KNOWS,
    EntryKind.TRAIT_SEED: USLPredicate.HAS_TRAIT,
    EntryKind.PORTRET: USLPredicate.HAS_TRAIT,        # агрегация traits[]
    EntryKind.OBSERVATION: USLPredicate.ASSERTS,
    EntryKind.DESIRE_SEED: USLPredicate.DESIRES,
}


def entry_kind_to_usl_predicate(entry_kind: EntryKind) -> Optional[USLPredicate]:
    """Явное соответствие EntryKind → USLPredicate (прецедент entry_kind_to_cause_kind).

    Возвращает None для неизвестных (на данный момент — все 10 покрыты).
    Расширение = мини-ADR (закрытый реестр USLPredicate).
    """
    return _ENTRY_KIND_TO_USL_PREDICATE.get(entry_kind)


# ── 2. EntityRef → USLEntityRef (тонкая проекция, не копия) ───────────────────

def _entityref_to_usl(ref: Optional[EntityRef]) -> Optional[USLEntityRef]:
    """Проекция chronicle.EntityRef → USLEntityRef.

    Не дублирует поля — ref_id указывает на тот же npc_id/white_spot_id.
    kind хранится строкой (USLEntityRef.kind: str) — USL реестр шире chronicle
    (добавляет "self"/"addressee"/"player"/"unknown" для ввода).
    """
    if ref is None:
        return None
    kind_map = {
        EntityRefKind.RESOLVED: "resolved",
        EntityRefKind.NEW_NPC: "new_npc",
        EntityRefKind.WHITE_SPOT: "white_spot",
        EntityRefKind.UNKNOWN_PERSON: "unknown_person",
    }
    usl_kind = kind_map.get(ref.ref_kind, "unknown")
    ref_id = ref.npc_id or ref.white_spot_id or ""
    return USLEntityRef(
        kind=usl_kind,
        ref_id=ref_id,
        name_hint=ref.name_hint,
        source_span=ref.name_hint,  # name_hint — лучшее приближение span для биографии
    )


# ── 3. Provenance → USLSourceKind ────────────────────────────────────────────

_PROVENANCE_TO_USL_SOURCE: Dict[EntryProvenance, USLSourceKind] = {
    EntryProvenance.AUTHOR_CONFIRMED: USLSourceKind.AUTHOR_CANON,
    EntryProvenance.AUTHOR_AUTHORED: USLSourceKind.AUTHOR_CANON,
    EntryProvenance.LLM_DRAFT: USLSourceKind.AUTHOR_HYPOTHESIS,
}


def _provenance_to_usl_source(provenance: EntryProvenance) -> USLSourceKind:
    return _PROVENANCE_TO_USL_SOURCE.get(provenance, USLSourceKind.HYPOTHESIS)


# ── 4. Время из готовых полей (не парсинг) ─────────────────────────────────────

def _extract_temporal(entry: ChronicleEntry) -> Tuple[USLTimeExpression, ...]:
    """Извлекает временные конструкции из уже структурированных полей.

    Не парсит author_text (вердикт Мастера Q3). Использует:
        - entry.historical_age → POINT(AGE_N)
        - entry.historical_year → POINT(WORLD_YEAR)
        - payload.day → POINT(GAME_TICK)
        - payload.duration_years → DURATION
        - KNOWLEDGE_LINK.payload.learned_age → POINT(AGE_N, "learned_age")
    Если ничего нет → пустой кортеж (честный empty, §ENIGMA-003).
    """
    temporal: List[USLTimeExpression] = []

    if entry.historical_age is not None:
        temporal.append(USLTimeExpression(
            kind=USLTimeKind.POINT,
            anchor=USLAnchorKind.AGE_N,
            value=entry.historical_age,
            source_span=f"historical_age={entry.historical_age}",
        ))

    if entry.historical_year is not None:
        temporal.append(USLTimeExpression(
            kind=USLTimeKind.POINT,
            anchor=USLAnchorKind.WORLD_YEAR,
            value=entry.historical_year,
            source_span=f"historical_year={entry.historical_year}",
        ))

    payload = entry.payload or {}
    if isinstance(payload, dict):
        day = payload.get("day")
        if day is not None and isinstance(day, (int, float)):
            temporal.append(USLTimeExpression(
                kind=USLTimeKind.POINT,
                anchor=USLAnchorKind.GAME_TICK,
                value=int(day),
                source_span=f"day={day}",
            ))

        duration_years = payload.get("duration_years")
        if duration_years is not None and isinstance(duration_years, (int, float)):
            temporal.append(USLTimeExpression(
                kind=USLTimeKind.DURATION,
                value=int(duration_years),
                source_span=f"duration_years={duration_years}",
            ))

        # KNOWLEDGE_LINK: learned_age — отдельная ось (время знания, не события)
        learned_age = payload.get(KP_LEARNED_AGE)
        if learned_age is not None and isinstance(learned_age, (int, float)):
            temporal.append(USLTimeExpression(
                kind=USLTimeKind.POINT,
                anchor=USLAnchorKind.AGE_N,
                value=int(learned_age),
                source_span=f"learned_age={learned_age}",
            ))

    return tuple(temporal)


# ── 5. Payload → USLRelation (для RELATIONSHIP) ─────────────────────────────

def _payload_to_relation(
    payload: Dict, subject_id: str, object_id: Optional[str]
) -> Optional[USLRelation]:
    """Извлекает USLRelation из RELATIONSHIP.payload (если есть nature/valence)."""
    if not payload:
        return None
    nature = payload.get("nature")
    valence_raw = payload.get("valence")
    if not nature and not valence_raw:
        return None
    valence = None
    if isinstance(valence_raw, str):
        v = valence_raw.lower()
        if v in ("positive", "negative", "neutral"):
            valence = v
    return USLRelation(
        relation_type=str(nature or "relationship"),
        subject=subject_id,
        object=object_id or "unknown",
        valence=valence,
        source_span=str(payload.get("summary", ""))[:200],
    )


# ── 6. Главный проектор: ChronicleEntry → USLUnit ────────────────────────────

def entry_to_usl_unit(entry: ChronicleEntry, doc: ChronicleDocument) -> USLUnit:
    """Проекция одной записи хроники в USLUnit.

    Conservative: сохраняет смысл без догадок. EVENT → ASSERTS (без BORN/DIED
    специализации). Время — только из структурированных полей (не парсинг).
    """
    # Источник: USL-5 span обязателен
    text_span = _extract_text_span(entry)
    source_kind = _provenance_to_usl_source(entry.provenance)
    source_ref = USLSourceRef(
        source_kind=source_kind,
        document_ref=doc.npc_ref,
        span=text_span,
        ordinal=entry.ordinal,
    )

    # Сущности
    entities: List[USLEntityRef] = []
    subject_usl = _entityref_to_usl(entry.subject_id)
    if subject_usl:
        entities.append(subject_usl)
    object_usl = _entityref_to_usl(entry.object_id)
    if object_usl:
        entities.append(object_usl)

    subject_ref = subject_usl.ref_id if subject_usl else "unknown"
    object_ref = object_usl.ref_id if object_usl else None

    # Событие
    predicate = entry_kind_to_usl_predicate(entry.kind) or USLPredicate.ASSERTS
    event = USLEvent(
        predicate=predicate,
        subject=subject_ref,
        object=object_ref,
        source_span=text_span,
    )

    # Время
    temporal = _extract_temporal(entry)

    # Отношения (для RELATIONSHIP)
    relations: Tuple[USLRelation, ...] = ()
    if entry.kind is EntryKind.RELATIONSHIP:
        rel = _payload_to_relation(entry.payload or {}, subject_ref, object_ref)
        if rel:
            relations = (rel,)

    # Эпистемика (для KNOWLEDGE_LINK — channel из payload)
    channel = None
    certainty = None
    if entry.kind is EntryKind.KNOWLEDGE_LINK and isinstance(entry.payload, dict):
        ch_raw = entry.payload.get(KP_CHANNEL)
        if isinstance(ch_raw, str):
            try:
                channel = KnowledgeChannel(ch_raw)
            except ValueError:
                channel = None
        cert_raw = entry.payload.get(KP_CERTAINTY)
        if isinstance(cert_raw, (int, float)) and 0.0 <= cert_raw <= 1.0:
            certainty = float(cert_raw)

    epistemics = USLEpistemics(
        source_kind=source_kind,
        channel=channel,
        certainty=certainty if certainty is not None else entry.confidence,
    )

    # Контекст
    context = USLContext(
        fragment_ord=entry.ordinal,
    )

    return USLUnit(
        unit_id=make_unit_id(source_ref, text_span),
        source_ref=source_ref,
        text_span=text_span,
        entities=tuple(entities),
        events=(event,),
        temporal=temporal,
        relations=relations,
        modality=USLModal(),
        epistemics=epistemics,
        context=context,
        origin_kind="chronicle_entry",
        origin_id=entry.entry_id,
    )


def _extract_text_span(entry: ChronicleEntry) -> str:
    """Извлекает текстовый span из entry (для USL-5 provenance).

    Приоритет: payload.summary → payload.statement → payload.trait → entry_id.
    Если payload пустой — fallback на entry_id (гарантированно непустой).
    """
    payload = entry.payload or {}
    if isinstance(payload, dict):
        for key in ("summary", "statement", "trait", "effect_kind"):
            val = payload.get(key)
            if isinstance(val, str) and val.strip():
                return val[:300]
    return entry.entry_id


# ── 7. Документ → список USLUnit ──────────────────────────────────────────────

def biography_to_usl(doc: ChronicleDocument) -> List[USLUnit]:
    """Проекция всего документа хроники в список USLUnit.

    Pure function: одинаковый doc → одинаковый список (USL-6 детерминизм).
    Один entry → один USLUnit (1:1 mapping; future: агрегация PORTRET traits).
    """
    return [entry_to_usl_unit(entry, doc) for entry in doc.entries]