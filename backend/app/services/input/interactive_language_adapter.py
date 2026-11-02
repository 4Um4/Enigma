"""
InteractiveLanguageAdapter — проектор IntentSemanticField → USLUnit (USL-1.3, ADR-O-437).

Назначение: проецирует уже разобранный смысл ввода игрока/NPC в общий словарь USL.
Не парсит raw_text — это работа IntentCompressor. Адаптер работает с уже
структурированными полями IntentSemanticField (вердикт Мастера Q3: «адаптеры
не парсеры»).

Контракты:
    - pure function: одинаковый IntentSemanticField → одинаковый USLUnit
    - read-only: не пишет в EpistemicStore/EventMemory/TruthState (USL-3)
    - transient: USLUnit не персистится
    - frozen: USLUnit immutable
    - provenance: source_span обязателен (USL-5)
    - DLG-L1 симметрия: PLAYER_ASSERTION / NPC_SPEECH различаются только
      source_kind, не глубиной разбора (roadmap §3.6:707)

Главный тест критерия Мастера: одинаковый смысл из биографии и из ввода даёт
совместимые events/temporal и различные epistemics. Время в input — открытая
задача USL-1.4 (Temporal Extractor), не угадывается.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from app.domain.epistemology import Predicate, Proposition, SpeechAct
from app.domain.intent_profile import IntentSemanticField
from app.domain.usl import (
    USLAnchorKind,
    USLContext,
    USLEntityRef,
    USLEpistemics,
    USLEvent,
    USLModality,
    USLModal,
    USLPredicate,
    USLSourceKind,
    USLSourceRef,
    USLTimeExpression,
    USLUnit,
    make_unit_id,
)


# ── 1. Mapping: Predicate → USLPredicate (общие 6 — тривиальный маппинг) ─────

_PREDICATE_TO_USL: Dict[Predicate, USLPredicate] = {
    Predicate.STOLE: USLPredicate.STOLE,
    Predicate.ATTACKED: USLPredicate.ATTACKED,
    Predicate.HELPED: USLPredicate.HELPED,
    Predicate.ASSERTS: USLPredicate.ASSERTS,
    Predicate.EXITS_TO: USLPredicate.EXITS_TO,
    Predicate.NAME: USLPredicate.NAME,
}


def predicate_to_usl(pred: Predicate) -> USLPredicate:
    """Тривиальный маппинг: 6 общих значений совпадают."""
    return _PREDICATE_TO_USL.get(pred, USLPredicate.ASSERTS)


# ── 2. semantic_acts[].type → USLPredicate (для ASSERT без proposition) ─────

_ACT_TYPE_TO_USL: Dict[str, USLPredicate] = {
    "ASSERT": USLPredicate.ASSERTS,
    "THREAT": USLPredicate.ATTACKED,
    "COMPLIMENT": USLPredicate.HELPED,
    "INSULT": USLPredicate.ATTACKED,
    "ACCUSATION": USLPredicate.STOLE,
}


def _act_type_to_usl_predicate(act_type: str) -> USLPredicate:
    """Маппинг типа акта в USLPredicate (conservative)."""
    return _ACT_TYPE_TO_USL.get(act_type.upper(), USLPredicate.ASSERTS)


# ── 3. semantic_acts per-act → USLModal ──────────────────────────────────────

_VALID_USL_MODALITIES = {"REALIS", "HYPOTHETICAL", "CONDITIONAL", "DESIRED"}


def _act_to_modal(act: Dict) -> USLModal:
    """Per-act контракт → USLModal (intent_compressor.py:238-266).

    None = недостаточная информация, НЕ False (правило Блока 1).
    """
    negated = act.get("negated")
    if not isinstance(negated, bool):
        negated = None

    modality_raw = act.get("modality")
    modality = None
    if isinstance(modality_raw, str) and modality_raw.upper() in _VALID_USL_MODALITIES:
        modality = USLModality(modality_raw.upper())

    condition = act.get("condition")
    if not isinstance(condition, str):
        condition = None

    quoted = act.get("quoted")
    if not isinstance(quoted, bool):
        quoted = None

    quoted_speaker = act.get("quoted_speaker_hint")
    if not isinstance(quoted_speaker, str):
        quoted_speaker = None

    return USLModal(
        negated=negated,
        modality=modality,
        condition=condition,
        quoted=quoted,
        quoted_speaker=quoted_speaker,
    )


# ── 4. Subject/object resolution → USLEntityRef ─────────────────────────────

def _actor_to_usl(field: IntentSemanticField) -> USLEntityRef:
    """Actor: resolved NPC или player (если actor=None)."""
    if field.actor and field.actor != "player":
        return USLEntityRef(
            kind="resolved",
            ref_id=field.actor,
            source_span="actor",
        )
    # Player или неразрешённый — это "self" (speaker)
    return USLEntityRef(kind="self", ref_id="player", source_span="self")


def _target_to_usl(field: IntentSemanticField) -> Optional[USLEntityRef]:
    """Target: resolved NPC или addressee (если None)."""
    if field.target:
        return USLEntityRef(
            kind="resolved",
            ref_id=field.target,
            source_span="target",
        )
    return None


def _addressee_to_usl(field: IntentSemanticField) -> Optional[USLEntityRef]:
    """Addressee (≠ target, доктрина телесной семантики §12-1)."""
    if field.addressee:
        return USLEntityRef(
            kind="addressee",
            ref_id=field.addressee,
            source_span="addressee",
        )
    return None


# ── 5. Proposition → USLEvent (главный путь: если proposition есть) ─────────

def _proposition_to_usl_event(prop: Proposition, field: IntentSemanticField) -> USLEvent:
    """Proposition → USLEvent (тривиальный маппинг для 6 общих предикатов)."""
    return USLEvent(
        predicate=predicate_to_usl(prop.predicate),
        subject=prop.subject_id,
        object=prop.object_id,
        polarity=prop.polarity,
        source_span=field.raw_text[:300],
    )


# ── 6. semantic_acts → список USLEvent (когда proposition=None) ──────────────

def _semantic_acts_to_usl_events(field: IntentSemanticField) -> Tuple[USLEvent, ...]:
    """Per-act контракт → USLEvent (для ASSERT/THREAT/COMPLIMENT без proposition).

    Conservative: act_type → USLPredicate (ASSERTS/ATTACKED/HELPED/STOLE).
    params.claim → object (для ASSERT). Все per-act модальности → первый акт
    в USLModal (главный акт — для обратной совместимости с IntentReadiness).
    """
    events: List[USLEvent] = []
    for act in field.semantic_acts or []:
        if not isinstance(act, dict):
            continue
        act_type = str(act.get("type") or "")
        if not act_type:
            continue
        params = act.get("params") or {}
        if not isinstance(params, dict):
            params = {}
        # subject — actor (resolved или player)
        actor_ref = _actor_to_usl(field).ref_id
        # object — params.claim (для ASSERT) или params.target
        object_ref = params.get("claim") or params.get("target") or "unknown"
        events.append(USLEvent(
            predicate=_act_type_to_usl_predicate(act_type),
            subject=actor_ref,
            object=str(object_ref)[:300],
            source_span=field.raw_text[:300],
        ))
    return tuple(events)


# ── 7. Главный проектор: IntentSemanticField → USLUnit ─────────────────────

def intent_to_usl_unit(
    field: IntentSemanticField,
    *,
    speaker_id: str = "player",
    tick: Optional[int] = None,
) -> USLUnit:
    """Проекция одного IntentSemanticField в USLUnit.

    speaker_id: "player" (для ввода игрока) или npc_id (для NPC_SPEECH, DLG-L1).
    tick: тик симуляции (для SPEECH_TIME якоря; опционален).

    Conservative:
        - Если proposition есть → USLEvent из proposition (главный путь)
        - Иначе semantic_acts → список USLEvent
        - Время: temporal=() (честный empty — в input нет временных полей,
          Шаг 2.C.7 подтвердил). USL-1.4 (Temporal Extractor) — future work.
        - Epistemics.source_kind: PLAYER_ASSERTION или NPC_SPEECH (по speaker_id)
    """
    # Источник (USL-5 span обязателен)
    text_span = field.raw_text[:300] if field.raw_text else ""
    source_kind = (
        USLSourceKind.PLAYER_ASSERTION if speaker_id == "player"
        else USLSourceKind.NPC_SPEECH
    )
    source_ref = USLSourceRef(
        source_kind=source_kind,
        document_ref=speaker_id,
        span=text_span,
        tick=tick,
    )

    # Сущности
    entities: List[USLEntityRef] = [_actor_to_usl(field)]
    target_usl = _target_to_usl(field)
    if target_usl:
        entities.append(target_usl)
    addressee_usl = _addressee_to_usl(field)
    if addressee_usl:
        entities.append(addressee_usl)

    # События (приоритет proposition, fallback — semantic_acts)
    events: Tuple[USLEvent, ...]
    if field.proposition is not None:
        events = (_proposition_to_usl_event(field.proposition, field),)
    else:
        events = _semantic_acts_to_usl_events(field)
        if not events:
            # Честный empty — comprehension_facts.llm_status мог быть UNAVAILABLE
            events = ()

    # Модальность (из первого semantic_act — главного)
    modality = USLModal()
    if field.semantic_acts:
        first_act = field.semantic_acts[0]
        if isinstance(first_act, dict):
            modality = _act_to_modal(first_act)

    # Время: честный empty (input не имеет временных полей — Шаг 2.C.7)
    temporal: Tuple[USLTimeExpression, ...] = ()
    # USL-1.4 (future): extract_temporal_from_text(field.raw_text) — но не сейчас

    # Контекст
    context = USLContext(
        references=tuple(field.references or ()),
        addressee=field.addressee,
        dialogue_thread=field.dialogue_thread,
        conversation_continuation=field.conversation_continuation,
    )

    # Epistemics (для ввода — без channel, certainty из comprehension_facts)
    certainty = None
    if field.comprehension_facts and isinstance(field.comprehension_facts, dict):
        # certainty — не в comprehension_facts; оставляем None (не угадываем)
        pass

    epistemics = USLEpistemics(
        source_kind=source_kind,
        channel=None,  # input не хранит канал — USL §2.3
        certainty=certainty,
    )

    return USLUnit(
        unit_id=make_unit_id(source_ref, text_span),
        source_ref=source_ref,
        text_span=text_span,
        entities=tuple(entities),
        events=events,
        temporal=temporal,
        relations=(),
        modality=modality,
        epistemics=epistemics,
        context=context,
        origin_kind="intent_field",
        origin_id=text_span or "input",
    )


# ── 8. Список полей → список USLUnit (для батча) ────────────────────────────

def intents_to_usl(
    fields: List[IntentSemanticField],
    *,
    speaker_id: str = "player",
    tick: Optional[int] = None,
) -> List[USLUnit]:
    """Проекция списка IntentSemanticField в список USLUnit.

    Pure function: одинаковый список → одинаковый результат (USL-6).
    """
    return [intent_to_usl_unit(f, speaker_id=speaker_id, tick=tick) for f in fields]