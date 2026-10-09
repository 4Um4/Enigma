"""path: backend/app/services/chronicle/chronicle_seeder.py
Назначение: CCH-4 / ADR-O-423 — сеялка хроники: чистый транслятор канона
            ChronicleDocument → seed стартового состояния ДО первого тика.
            НИЧЕГО не пишет сама: возвращает структуры; единственный
            применяющий — npc_loader (легален во всех цензусах —
            ADR-O-380 / NPCState._ALLOWED_WRITERS; расширений НЕ требуется).
            Гейт «новая игра» открывает загрузчик (L2 пуста везде).
Зависимости: app.core.config, app.domain.chronicle, app.services.chronicle
             .{age_math, chronicle_store}, app.models.npc_state,
             app.models.npc.beliefs (ленивые внутри функций), stdlib
Основные сущности: SeederError, canonical_chronicles, canonical_chronicle,
                   build_seed_memories, build_seed_knowledge,
                   build_seed_relationships, build_seed_imprints,
                   build_seed_beliefs, build_full_seed, SEED_* (CALIBRATION_CANDIDATE)"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set, Tuple, cast

from app.core.config import BASE_DIR
from app.domain.chronicle import (
    KP_CERTAINTY,
    KP_EVENT_REF,
    KP_KNOWER,
    KP_LEARNED_AGE,
    ChronicleDocument,
    ChronicleEntry,
    EntityRefKind,
    EntryKind,
    EntryProvenance,
)
from app.services.chronicle.age_math import (
    SENTINEL_DAY,
    day_offset,
    historical_event_seconds,
)

logger = logging.getLogger(__name__)

# ── Ключи payload-схем kind (§12.1: ключи — константы, не строки) ────────────

_PL_SUMMARY: str = "summary"
_PL_VALENCE: str = "valence"
_PL_EFFECT_KIND: str = "effect_kind"
_PL_TRIGGERS: str = "triggers"        # авторская пометка триггеров trauma (CCH-4)
_PL_BELIEF_TYPE: str = "belief_type"  # авторская пометка типа убеждения

# ── Seed-константы (CALIBRATION_CANDIDATE — ТЗ CCH-01 §11, риск №4) ─────────

SEED_EVENT_IMPORTANCE: float = 0.6         # ТЗ §7.4: «по умолчанию 0.6»
SEED_TRAUMA_EVENT_IMPORTANCE: float = 0.9  # ТЗ §7.4: «для травм ≥0.9»
SEED_DECAY_RATE: float = 0.001             # прецедент _convert_origin_events
SEED_TRUST_NEGATIVE: float = -40.0         # valence=negative (словарь nature
SEED_TRUST_POSITIVE: float = 30.0          #  НЕ закрыт — калибровка CCH-6)
SEED_TRAUMA_PAIN: float = 0.7
SEED_TRAUMA_FEAR: float = 0.5
SEED_TRAUMA_HUMILIATION: float = 0.3
SEED_TRAUMA_TRUST_SHIFT: float = -0.2
SEED_TRAUMA_REINFORCEMENT: float = 0.3
SEED_BELIEF_VALUE: float = 0.7
SEED_BELIEF_CONFIDENCE: float = 0.8


class SeederError(ValueError):
    """Fail-loud нарушение канона при посеве (запреты 3/4 ADR-O-420)."""


# ── Канон: чтение с mtime-кэшем (загрузчик зовётся несколько раз за тик) ─────

_cache: Dict[str, Any] = {"dir_mtime": None, "docs": {}}


def _canon_dir() -> Any:
    # Зеркало routes_chronicle._get_store (один путь, два читателя —
    # комментарий-парный якорь routes_chronicle:38; api→services запрещён).
    return BASE_DIR / "config" / "npc" / "chronicles"


def _store() -> Any:
    from app.services.chronicle.chronicle_store import ChronicleStore

    return ChronicleStore(canonical_dir=_canon_dir(), drafts_root=BASE_DIR / "saves")


def canonical_chronicles() -> Dict[str, ChronicleDocument]:
    """Все каноны. Кэш процесса с инвалидацией по mtime каталога: mtime НЕ
    входит в данные seed (T-CCH-05 не нарушен) — только решает, перечитать
    ли. Битый канон = fail-loud валидатора store (L4)."""
    try:
        mtime = _canon_dir().stat().st_mtime
    except OSError:
        # L4: отказ наблюдаем. Папки канона нет = канонов нет = legacy-путь
        # (легальная деградация, но не молчаливая). debug: idle зовёт
        # загрузчик несколько раз за тик — warning вечно спамил бы.
        logger.debug("[CCH_SEED] канон-папка отсутствует — seed выключен")
        return {}
    if _cache["dir_mtime"] != mtime or not _cache["docs"]:
        docs: Dict[str, ChronicleDocument] = {}
        for p in sorted(_canon_dir().glob("*.json")):
            doc = _store().load_canonical(p.stem)
            if doc is not None:
                docs[p.stem] = doc
        _cache["docs"] = docs
        _cache["dir_mtime"] = mtime
        logger.info(f"[CCH_SEED] канон перечитан: {len(docs)} хроник")
    return cast(Dict[str, ChronicleDocument], _cache["docs"])


def canonical_chronicle(npc_id: str) -> Optional[ChronicleDocument]:
    return canonical_chronicles().get(npc_id)


# ── Внутренние трансляции ────────────────────────────────────────────────────

_AUTHOR_OK = (EntryProvenance.AUTHOR_CONFIRMED, EntryProvenance.AUTHOR_AUTHORED)


def _author_entries(doc: ChronicleDocument) -> Tuple[ChronicleEntry, ...]:
    """Только канон-записи. LLM_DRAFT не сеется никогда (запрет 1)."""
    return tuple(e for e in doc.entries if e.provenance in _AUTHOR_OK)


def _day_from_age(
    age: Optional[int], start_age: Optional[int], label: str, *, strict: bool
) -> int:
    """Возраст → день от старта (чистая math age_math: birth_epoch
    сокращается → (age − start) × 365). strict=True — собственная хроника:
    якорь без game_start_age = отказ; событие в будущем = отказ (память о
    будущем = порча данных)."""
    if age is None:
        return SENTINEL_DAY
    if start_age is None:
        if strict:
            raise SeederError(f"{label}: возраст-якорь {age} без game_start_age")
        logger.warning(f"[CCH_SEED] {label}: возраст узнавания без game_start_age — {SENTINEL_DAY}")
        return SENTINEL_DAY
    day = day_offset(historical_event_seconds(age, 0), historical_event_seconds(start_age, 0))
    if day > 0:
        raise SeederError(f"{label}: событие в будущем ({age} лет > старт {start_age})")
    return day


def _resolved_npc_id(ref: Any) -> Optional[str]:
    if ref is not None and ref.ref_kind is EntityRefKind.RESOLVED:
        npc_id: Optional[str] = ref.npc_id
        return npc_id
    return None


def _trauma_linked_event_ids(doc: ChronicleDocument) -> Set[str]:
    """EVENT, на которые ссылается trauma-EFFECT → важность ≥0.9 (ТЗ §7.4)."""
    out: Set[str] = set()
    for e in _author_entries(doc):
        if e.kind is EntryKind.EFFECT and e.payload.get(_PL_EFFECT_KIND) == "trauma":
            out.update(c.origin_ref for c in e.causes if c.origin_ref)
    return out


# ── Публичные посевы ─────────────────────────────────────────────────────────


def build_seed_memories(npc_id: str, doc: ChronicleDocument) -> Tuple[Any, ...]:
    """EVENT канона → EventMemory(day<0). Происхождение — тег chronicle:<id>
    (запрет 3 закрыт конструктивно: каждый факт несёт ссылку на запись)."""
    from app.models.npc_state import EventMemory

    start = doc.game_start_age
    anchors = sum(1 for e in _author_entries(doc) if e.historical_age is not None)
    if anchors and start is None:
        raise SeederError(f"{doc.chronicle_id}: {anchors} возраст-якорей без game_start_age")
    trauma_ids = _trauma_linked_event_ids(doc)
    result = []
    for e in _author_entries(doc):
        if e.kind is not EntryKind.EVENT:
            continue
        day = _day_from_age(e.historical_age, start, f"{doc.chronicle_id}:{e.entry_id}", strict=True)
        result.append(
            EventMemory(
                event_type="origin",
                target_id=_resolved_npc_id(e.object_id) or "",
                emotion_tag="neutral",
                day=day,
                importance=(
                    SEED_TRAUMA_EVENT_IMPORTANCE
                    if e.entry_id in trauma_ids
                    else SEED_EVENT_IMPORTANCE
                ),
                clarity=1.0,
                confidence=1.0,
                decay_rate=SEED_DECAY_RATE,
                summary=str(e.payload.get(_PL_SUMMARY, "")),
                npc_id=npc_id,
                tags=(f"chronicle:{e.entry_id}",),
                is_secret=False,
                known_by=(),
                hidden_from=(),
                accessibility=1.0,
                secret_id=None,
            )
        )
    logger.info(f"[CCH_SEED] {npc_id}: memories={len(result)}")
    return tuple(result)


def build_seed_knowledge(
    npc_id: str, docs_by_npc: Dict[str, ChronicleDocument]
) -> Tuple[Any, ...]:
    """KNOWLEDGE_LINK (из ВСЕХ канонов, где knower == npc_id) → EventMemory,
    датированная возрастом УЗНАВАНИЯ (ось знания ≠ ось события — П4 ТЗ).
    Кого в знающих нет — записи не получает (изоляция, T-CCH-06).
    Секрет скрыт от игрока (hidden_from=('player',) — прецедент
    _seed_canon_secret_memories:616; запрет телепатии)."""
    from app.models.npc_state import EventMemory

    result = []
    for _src_id, doc in docs_by_npc.items():
        by_id = {e.entry_id: e for e in doc.entries}
        for e in _author_entries(doc):
            if e.kind is not EntryKind.KNOWLEDGE_LINK:
                continue
            knower = e.payload.get(KP_KNOWER)
            if not isinstance(knower, dict) or knower.get("ref_kind") != EntityRefKind.RESOLVED.value:
                continue  # массовка/пятно знание не сеют
            if knower.get("npc_id") != npc_id:
                continue
            ev = by_id.get(cast(str, e.payload.get(KP_EVENT_REF)))
            if ev is None or ev.provenance not in _AUTHOR_OK:
                logger.warning(f"[CCH_SEED] knowledge {e.entry_id}: источник не канон — пропущен")
                continue
            # Возраст узнавания — возраст ЗНАЮЩЕГО: конверсия относительно
            # ЕГО game_start_age (его хроника), НЕ владельца события.
            # Смешение чужих возрастов = порча оси времени (запрет 4).
            _k_doc = docs_by_npc.get(cast(str, knower.get("npc_id")))
            _k_start = None
            if _k_doc is not None:
                _k_start = _k_doc.game_start_age
            _k_day = _day_from_age(
                e.payload.get(KP_LEARNED_AGE), _k_start, f"{doc.chronicle_id}:{e.entry_id}", strict=False
            )
            if _k_day > 0:
                # Знание «из будущего» относительно знающего — странность
                # данных канона: не блокирует загрузку, но не сеется (L4).
                logger.warning(
                    f"[CCH_SEED] knowledge {e.entry_id}: learned_age в будущем знающего — пропущен"
                )
                continue
            result.append(
                EventMemory(
                    event_type="chronicle_knowledge",
                    target_id=_resolved_npc_id(ev.object_id) or "",
                    emotion_tag="neutral",
                    day=_k_day,
                    importance=SEED_EVENT_IMPORTANCE,
                    clarity=1.0,
                    confidence=float(e.payload.get(KP_CERTAINTY, 1.0)),
                    decay_rate=SEED_DECAY_RATE,
                    summary=f"Узнал(а): {ev.payload.get(_PL_SUMMARY, '')}",
                    npc_id=npc_id,
                    tags=(f"chronicle:{ev.entry_id}",),
                    is_secret=True,
                    known_by=(npc_id,),
                    hidden_from=("player",),
                    accessibility=1.0,
                    secret_id=None,
                )
            )
    if result:
        logger.info(f"[CCH_SEED] {npc_id}: knowledge={len(result)}")
    return tuple(result)


def build_seed_relationships(npc_id: str, doc: ChronicleDocument) -> Dict[str, Dict[str, Any]]:
    """RELATIONSHIP → enrichment-формат relationship_cache. Числа — только из
    знака valence (словарь nature не закрыт — CCH-6); chronicle_origin —
    происхождение скаляра (запрет 3; V2-подъёмник отфильтрует по
    _LEGACY_SCALARS — двойная защита). Неразрешённый адресат — громкий лог,
    не сеется, в каноне остаётся."""
    result: Dict[str, Dict[str, Any]] = {}
    for e in _author_entries(doc):
        if e.kind is not EntryKind.RELATIONSHIP:
            continue
        tgt = _resolved_npc_id(e.object_id)
        if tgt is None:
            logger.warning(f"[CCH_SEED] {npc_id}:{e.entry_id}: связь на неразрешённую сущность — не сеется")
            continue
        if tgt == npc_id:
            continue
        valence = e.payload.get(_PL_VALENCE)
        if valence == "negative":
            trust = SEED_TRUST_NEGATIVE
        elif valence == "positive":
            trust = SEED_TRUST_POSITIVE
        else:
            logger.warning(f"[CCH_SEED] {npc_id}:{e.entry_id}: valence='{valence}' без числа — не сеется")
            continue
        # Канон = актуальный снимок (вердикт S336): перезапись village-статика
        # на уровне загрузки осознанна; работающая кампания защищена
        # V2 existing-RAM-wins + sanitizer sync (кэш в дикте эфемерен,
        # P1 ARCH FIX npc_state:1264 «НЕ восстанавливаем из персистенса»).
        result[tgt] = {"trust": trust, "chronicle_origin": e.entry_id}
    if result:
        logger.info(f"[CCH_SEED] {npc_id}: relationships={sorted(result)}")
    return result


def build_seed_imprints(doc: ChronicleDocument) -> List[Dict[str, Any]]:
    """trauma-EFFECT → AffectiveImprint (decay_rate=0 — вечная, ТЗ FR-11.1)
    в ДИКТ-носитель (единственный, которым рантайм реально затухает:
    idle_services → decay_affective_imprints; второй носитель — известный
    долг CG-D-05, не расширяется). ТОЛЬКО поля AffectiveImprint: носитель
    восстанавливает объект как AffectiveImprint(**imp) — лишний ключ = краш.
    Происхождение травмы живёт в памяти-событии (тег chronicle:<id>) + лог.
    Триггеры — ТОЛЬКО авторская пометка payload['triggers']: нет пометки →
    импринт не создаётся, громкий лог (ничего не выдумываем)."""
    result: List[Dict[str, Any]] = []
    for e in _author_entries(doc):
        if e.kind is not EntryKind.EFFECT or e.payload.get(_PL_EFFECT_KIND) != "trauma":
            continue
        triggers = e.payload.get(_PL_TRIGGERS)
        if not triggers or not isinstance(triggers, (list, tuple)):
            logger.warning(
                f"[CCH_SEED] {doc.chronicle_id}:{e.entry_id}: trauma без triggers — импринт не создан"
            )
            continue
        result.append(
            {
                "source_entity_id": _resolved_npc_id(e.object_id) or "unknown",
                "trigger_tags": tuple(str(t) for t in triggers),
                "pain_signature": SEED_TRAUMA_PAIN,
                "fear_signature": SEED_TRAUMA_FEAR,
                "humiliation_signature": SEED_TRAUMA_HUMILIATION,
                "trust_shift": SEED_TRAUMA_TRUST_SHIFT,
                "reinforcement": SEED_TRAUMA_REINFORCEMENT,
                "decay_rate": 0.0,
                "created_at": 0,
                "last_triggered_at": 0,
            }
        )
    if result:
        logger.info(f"[CCH_SEED] {doc.npc_ref}: imprints={len(result)}")
    return result


def build_seed_beliefs(doc: ChronicleDocument) -> Dict[str, List[Any]]:
    """BELIEF_SEED → формат psyche['beliefs'] {type: [value, conf, src, tick]}.
    Только типы закрытого реестра BeliefType; без типа — остаётся в каноне
    (расширение — через сводку убеждений → вердикт владельца, не автоматически)."""
    from app.models.npc.beliefs import BeliefType

    registry = {t.value for t in BeliefType}
    result: Dict[str, List[Any]] = {}
    for e in _author_entries(doc):
        if e.kind is not EntryKind.BELIEF_SEED:
            continue
        btype = e.payload.get(_PL_BELIEF_TYPE)
        if btype not in registry:
            logger.warning(f"[CCH_SEED] {doc.chronicle_id}:{e.entry_id}: belief_type='{btype}' вне реестра — в каноне")
            continue
        result[str(btype)] = [SEED_BELIEF_VALUE, SEED_BELIEF_CONFIDENCE, "chronicle", 0]
    if result:
        logger.info(f"[CCH_SEED] {doc.npc_ref}: beliefs={sorted(result)}")
    return result


def build_full_seed(npc_id: str) -> Optional[Dict[str, Any]]:
    """Полная посылка посева. None = канона нет (legacy-путь нетронут).
    TRAIT_SEED сознательно отсутствует: черты ждут Character Calibration
    (отдельный ADR, вердикт владельца) — в каноне не теряются."""
    docs = canonical_chronicles()
    doc = docs.get(npc_id)
    if doc is None:
        return None
    return {
        "memories": build_seed_memories(npc_id, doc),
        "knowledge": build_seed_knowledge(npc_id, docs),
        "relationships": build_seed_relationships(npc_id, doc),
        "imprints": build_seed_imprints(doc),
        "beliefs": build_seed_beliefs(doc),
    }
