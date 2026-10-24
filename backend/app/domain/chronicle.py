"""
Домен Character Chronicle — авторинг-компилятор ENIGMA (ADR-O-420).

Файл: backend/app/domain/chronicle.py
Назначение: DTO машинной хроники персонажа (Слой 0 канонического порядка):
            авторский текст → декомпозиция → хроника → seed стартового
            состояния ДО первого тика. Трек живёт ВНЕ тик-пайплайна.
Зависимости: stdlib only (Закон 1.2 Устава: domain не знает services/models).
Основные сущности: ChronicleDocument, ChronicleEntry, WhiteSpot,
                   KnowledgeLink, BiographyDecomposition, ClarificationQuestion.

КАУЗАЛЬНЫЕ ЗАПРЕТЫ (ADR-O-420 / DTO Registry §14):
- LLM_DRAFT не является каноном (INV-LLM-NOT-SSOT): единственный путь к
  AUTHOR_CONFIRMED — действие автора «Принять как канон» (UI).
- Два времени раздельны: historical_age (событие) и learned_age (знание);
  вычислять одно из другого запрещено (инвариант проверяется в KnowledgeLink).
- Writer-guard WhiteSpot живёт в services (registry), не здесь: домен
  хранит данные, авторитет записи — отдельный модуль с цензусом писателей.
- payload — dict по прецеденту EventDTO.payload: поверхностная иммутабельность
  frozen-dataclass; глубокая валидация схем kind — обязанность store (fail-loud).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Final, Optional, Tuple

# ── Константы ────────────────────────────────────────────────────────────────

SCHEMA_VERSION: Final[int] = 1  # ревизия схемы = ревизия ADR-O-420

_KIND_EVENT: Final[str] = "EVENT"
_KIND_RELATIONSHIP: Final[str] = "RELATIONSHIP"
_KIND_LOCATION: Final[str] = "LOCATION"
_KIND_EFFECT: Final[str] = "EFFECT"
_KIND_BELIEF_SEED: Final[str] = "BELIEF_SEED"
_KIND_OBSERVATION: Final[str] = "OBSERVATION"
_KIND_KNOWLEDGE_LINK: Final[str] = "KNOWLEDGE_LINK"
_KIND_TRAIT_SEED: Final[str] = "TRAIT_SEED"
_KIND_PORTRET: Final[str] = "PORTRET"  # вердикт владельца: авторский монолог-портрет
                                       # сохраняется целиком (оригинал > интерпретация)
_KIND_DESIRE_SEED: Final[str] = "DESIRE_SEED"  # вердикт владельца (п.11 Люси):
                                               # мечта/план — ещё не событие


class EntryKind(str, Enum):
    """Реестр типов записей хроники (закрытый; расширение = ревизия ADR-O-420)."""

    EVENT = _KIND_EVENT
    RELATIONSHIP = _KIND_RELATIONSHIP
    LOCATION = _KIND_LOCATION
    EFFECT = _KIND_EFFECT
    BELIEF_SEED = _KIND_BELIEF_SEED
    OBSERVATION = _KIND_OBSERVATION
    KNOWLEDGE_LINK = _KIND_KNOWLEDGE_LINK
    TRAIT_SEED = _KIND_TRAIT_SEED
    PORTRET = _KIND_PORTRET
    DESIRE_SEED = _KIND_DESIRE_SEED


class EntryProvenance(str, Enum):
    """Статус канона записи. LLM_DRAFT — гипотеза, не истина (П1 ТЗ)."""

    LLM_DRAFT = "LLM_DRAFT"
    AUTHOR_CONFIRMED = "AUTHOR_CONFIRMED"
    AUTHOR_AUTHORED = "AUTHOR_AUTHORED"


class KnowledgeChannel(str, Enum):
    """Как узнал: канал времени знания (seed → testimony/observation происхождение)."""

    WITNESSED = "WITNESSED"
    TOLD = "TOLD"
    OVERHEARD = "OVERHEARD"
    DEDUCED = "DEDUCED"
    UNKNOWN = "UNKNOWN"


class ClarificationOption(str, Enum):
    """Четыре опции резолюции неопознанной сущности (FR-3.1; «белое пятно» обязателен)."""

    SELECT_EXISTING_NPC = "SELECT_EXISTING_NPC"
    CREATE_NEW_NPC = "CREATE_NEW_NPC"
    UNKNOWN_PERSON = "UNKNOWN_PERSON"
    LEAVE_WHITE_SPOT = "LEAVE_WHITE_SPOT"


class WhiteSpotResolutionState(str, Enum):
    """Жизненный цикл белого пятна. Писатель — только действие автора (writer-guard)."""

    OPEN = "OPEN"
    RESOLVED_AS_NPC = "RESOLVED_AS_NPC"
    RESOLVED_AS_UNKNOWN = "RESOLVED_AS_UNKNOWN"
    RESERVED = "RESERVED"


class CauseKind(str, Enum):
    """Шесть типов авторских оснований (режим «Причины», FR-5.1)."""

    EVENT = "EVENT"
    RELATIONSHIP = "RELATIONSHIP"
    TRAIT = "TRAIT"
    NEED = "NEED"
    OBSERVATION = "OBSERVATION"
    UNKNOWN = "UNKNOWN"  # «причина не определена» — легальный ответ автора


# S366: явный детерминированный маппер EntryKind → CauseKind.
# Объявлен явно, не угадывается (вердикт Мастера по ADR v4 §3).
# 4 из 10 EntryKind имеют CauseKind. Остальные (LOCATION, EFFECT, BELIEF_SEED,
# KNOWLEDGE_LINK, PORTRET, DESIRE_SEED) не имеют прямого CauseKind — для них
# S366 не генерирует кандидата (зафиксировано как несовместимость контракта).
def entry_kind_to_cause_kind(entry_kind: "EntryKind") -> "Optional[CauseKind]":
    """Явное соответствие типа записи → типу основания (CauseRef.cause_kind).
    Возвращает None для EntryKind без соответствующего CauseKind.
    """
    return {
        EntryKind.EVENT: CauseKind.EVENT,
        EntryKind.RELATIONSHIP: CauseKind.RELATIONSHIP,
        EntryKind.TRAIT_SEED: CauseKind.TRAIT,
        EntryKind.OBSERVATION: CauseKind.OBSERVATION,
    }.get(entry_kind)


class EntityRefKind(str, Enum):
    """Онтология ссылки на сущность хроники (§13.1 roadmap)."""

    RESOLVED = "RESOLVED"          # существующий NPC (npc_id)
    NEW_NPC = "NEW_NPC"            # кандидат — создаётся только решением автора
    WHITE_SPOT = "WHITE_SPOT"      # намеренно неопределённая сущность
    UNKNOWN_PERSON = "UNKNOWN_PERSON"  # фоновая массовка без тик-агента


# ── Ссылки и причины ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class EntityRef:
    """Ссылка на сущность хроники. Валидация kind↔поля — fail-loud (L4)."""

    ref_kind: EntityRefKind
    npc_id: Optional[str] = None        # для RESOLVED
    white_spot_id: Optional[str] = None  # для WHITE_SPOT
    name_hint: str = ""                  # драфт имени для NEW_NPC / массовка

    def __post_init__(self) -> None:
        if self.ref_kind is EntityRefKind.RESOLVED and not self.npc_id:
            raise ValueError("EntityRef RESOLVED требует npc_id")
        if self.ref_kind is EntityRefKind.WHITE_SPOT and not self.white_spot_id:
            raise ValueError("EntityRef WHITE_SPOT требует white_spot_id")


@dataclass(frozen=True)
class CauseRef:
    """
    Авторское основание записи. Числа без происхождения запрещены (запрет 3):
    причина — это ссылка на запись/пятно, никогда не скаляр («Любовь = 0.8»).
    """

    cause_kind: CauseKind
    origin_ref: Optional[str] = None  # entry_id | white_spot_id | id authored-фразы

    def __post_init__(self) -> None:
        if self.cause_kind is not CauseKind.UNKNOWN and not self.origin_ref:
            raise ValueError(f"CauseRef {self.cause_kind.value} требует origin_ref")
        if self.cause_kind is CauseKind.UNKNOWN and self.origin_ref:
            raise ValueError("CauseRef UNKNOWN — «причина не определена», origin_ref не задаётся")


# ── Схема payload kind=KNOWLEDGE_LINK (единые ключи сериализации, §12.1) ─────

KP_EVENT_REF: Final[str] = "event_ref"
KP_KNOWER: Final[str] = "knower"
KP_LEARNED_AGE: Final[str] = "learned_age"
KP_LEARNED_YEAR: Final[str] = "learned_year"
KP_CHANNEL: Final[str] = "channel"
KP_CERTAINTY: Final[str] = "certainty"


def make_entry_id(chronicle_id: str, fragment_ord: int, ordinal: int) -> str:
    """Детерминированный id записи (replay-safe; прецедент EventDTO md5)."""
    raw = f"{chronicle_id}:{fragment_ord}:{ordinal}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


# ── Вопросы и белые пятна ────────────────────────────────────────────────────


@dataclass(frozen=True)
class ClarificationQuestion:
    """
    Вопрос автору. Канонизация фрагмента с открытым вопросом блокируется,
    если автор не выбрал «оставить белым пятном» («Save = Contract», FR-10.x).
    """

    question_id: str
    target_span: str  # на какой кусок текста
    options: Tuple[ClarificationOption, ...] = ()
    selected_option: Optional[ClarificationOption] = None
    selected_value: Optional[str] = None  # id выбранного NPC / имя нового / и т.п.

    def __post_init__(self) -> None:
        if ClarificationOption.LEAVE_WHITE_SPOT not in self.options:
            raise ValueError("ClarificationQuestion обязан предлагать LEAVE_WHITE_SPOT (П3)")


@dataclass(frozen=True)
class WhiteSpot:
    """
    Намеренно неопределённая сущность. Существует в данных и проекциях;
    до резолюции не становится тик-агентом (запрет преждевременного заполнения).
    """

    white_spot_id: str
    label: str                      # «стражник»
    context_hint: str = ""          # из какого фрагмента возникла
    resolution_state: WhiteSpotResolutionState = WhiteSpotResolutionState.OPEN
    resolution_ref: Optional[str] = None  # npc_id после RESOLVED_AS_NPC
    created_from_entry: Optional[str] = None


# ===== S366: Причинные кандидаты и NPC-убеждения =====
# АРХИТЕКТУРНОЕ РАЗДЕЛЕНИЕ (мини-ADR v6, вердикт Мастера):
# СЛОЙ 1 — объективная причинность: ChronicleEntry.causes (существующий)
# СЛОЙ 2 — субъективное убеждение NPC: ChronicleDocument.npc_beliefs (новое)
# СЛОЙ 3 — кандидат-вопрос автору: ChronicleDocument.cause_candidates (новое)
# СЛОЙ 4 — действие автора: отдельные endpoint'ы (link-causes, resolve, record-belief)
#
# ТРИ ЗАПРЕТА (вердикт Мастера §1):
# 1. хронологический порядок → причинность — запрещён (TEMPORAL_ORDER только детекция)
# 2. автор подтвердил факт → NPC об этом знает — запрещён (ACCEPT не создаёт belief)
# 3. факт не записан → убеждение NPC ошибочно — запрещён (MISTAKEN не выводится автоматически)


class BeliefGrounding(str, Enum):
    """Обоснованность NPC-убеждения о причинной связи (СЛОЙ 2).
    MISTAKEN — только явное решение автора при наличии основания;
    НЕ выводится автоматически из отсутствия CauseRef в effect.causes."""
    GROUNDED = "GROUNDED"      # совпадает с объективной причиной (есть CauseRef в effect.causes)
    MISTAKEN = "MISTAKEN"      # противоречит известным фактам (явное решение автора)
    UNVERIFIED = "UNVERIFIED"  # факт не подтверждён, но и не противоречит


class CandidateBasis(str, Enum):
    """Детерминированные признаки детекции кандидатов (СЛОЙ 3).
    НИ ОДИН из них НЕ доказывает причинность — только основание для вопроса автору.

    SPAN_OVERLAP — не реализован: нет CauseKind.PORTRET (зафиксировано как
    несовместимость контракта — ver. 1)."""
    TEMPORAL_ORDER = "TEMPORAL_ORDER"        # EVENT M<N (хронология — НЕ причина)
    TARGET_HINT_MATCH = "TARGET_HINT_MATCH"  # EFFECT.target_hint == RELATIONSHIP.target_hint


class CandidateStatus(str, Enum):
    """Жизненный цикл кандидата. Переходы: PENDING → ACCEPTED | REJECTED."""
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class NpcCausalBelief:
    """СЛОЙ 2: NPC считает entry → entry причинной связью. Может быть ошибочным.

    Не мутирует ChronicleEntry.causes (СЛОЙ 1). Записывается отдельным действием автора
    (POST /record-npc-belief), НЕ выводится автоматически из ACCEPT причинного кандидата.

    Применяет ТЕ ЖЕ правила provenance/confidence, что и ChronicleEntry
    (валидатор :227-231): LLM_DRAFT обязан нести confidence; AUTHOR_* не хранят.
    """
    believer_id: str                            # NPC, держащий убеждение
    effect_entry_id: str                        # entry_id следствия (в текущем документе)
    alleged_cause_entry_id: str                 # entry_id предполагаемой причины (в текущем документе)
    alleged_cause_kind: CauseKind               # из существующего enum, без расширения
    grounding: BeliefGrounding = BeliefGrounding.UNVERIFIED
    provenance: EntryProvenance = EntryProvenance.LLM_DRAFT
    confidence: Optional[float] = None

    def __post_init__(self) -> None:
        if not self.believer_id:
            raise ValueError("NpcCausalBelief: believer_id пуст")
        if self.effect_entry_id == self.alleged_cause_entry_id:
            raise ValueError("NpcCausalBelief: effect и alleged_cause — одна запись")
        if self.provenance is EntryProvenance.LLM_DRAFT and self.confidence is None:
            raise ValueError("NpcCausalBelief LLM_DRAFT обязан нести confidence (гипотеза)")
        if self.provenance in (EntryProvenance.AUTHOR_CONFIRMED, EntryProvenance.AUTHOR_AUTHORED):
            if self.confidence is not None:
                raise ValueError("NpcCausalBelief AUTHOR_* не хранит confidence — канон не гипотеза")
        if self.confidence is not None and not (0.0 <= self.confidence <= 1.0):
            raise ValueError("NpcCausalBelief confidence вне [0, 1]")


@dataclass(frozen=True)
class CauseCandidate:
    """СЛОЙ 3: детекция возможной причинной связи. НЕ проставляет causes. Ждёт явного решения автора.

    Idempotency: candidate_id детерминирован (effect+candidate+basis), повторная детекция
    не создаёт дубликат. REJECTED не возобновляется без изменения данных.
    """
    candidate_id: str
    effect_entry_id: str                        # entry, в causes[] которого идёт запись (при ACCEPT)
    candidate_entry_id: str                     # существующая запись-кандидат (основание)
    candidate_kind: CauseKind                   # из существующего enum, без расширения
    basis: CandidateBasis
    rationale: str                              # объяснение для автора (детерминированное)
    status: CandidateStatus = CandidateStatus.PENDING

    def __post_init__(self) -> None:
        if not self.candidate_id:
            raise ValueError("CauseCandidate: candidate_id пуст")
        if self.effect_entry_id == self.candidate_entry_id:
            raise ValueError("CauseCandidate: effect и candidate — одна запись")
        if not self.rationale:
            raise ValueError("CauseCandidate: rationale пуст")


def make_candidate_id(effect_entry_id: str, candidate_entry_id: str, basis: CandidateBasis) -> str:
    """Детерминированный id кандидата → idempotency: повторная детекция не создаёт дубль."""
    return f"{effect_entry_id}#cand-{basis.value}-{candidate_entry_id}"


def make_belief_id(believer_id: str, effect_entry_id: str, alleged_cause_entry_id: str) -> str:
    """Детерминированный id NPC-убеждения → idempotency при повторной записи."""
    return f"{believer_id}#belief-{effect_entry_id}-{alleged_cause_entry_id}"


# ── Машинная хроника ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ChronicleEntry:
    """Единица машинной хроники (результат декомпозиции одного фрагмента)."""

    entry_id: str
    kind: EntryKind
    subject_id: EntityRef
    historical_age: Optional[int] = None   # ось 1: историческое время
    historical_year: Optional[int] = None  # альтернативный якорь (год мира)
    object_id: Optional[EntityRef] = None
    payload: Dict[str, Any] = field(default_factory=dict)  # схема по kind — store
    causes: Tuple[CauseRef, ...] = ()
    provenance: EntryProvenance = EntryProvenance.LLM_DRAFT
    confidence: Optional[float] = None     # только для гипотезы LLM
    open_questions: Tuple[ClarificationQuestion, ...] = ()
    ordinal: int = 0                       # порядок в ленте документа

    def __post_init__(self) -> None:
        if self.provenance is EntryProvenance.LLM_DRAFT and self.confidence is None:
            raise ValueError("LLM_DRAFT обязан нести confidence (гипотеза, П1)")
        if self.provenance in (EntryProvenance.AUTHOR_CONFIRMED, EntryProvenance.AUTHOR_AUTHORED):
            if self.confidence is not None:
                raise ValueError("AUTHOR_* не хранит confidence — канон не гипотеза")
        if self.confidence is not None and not (0.0 <= self.confidence <= 1.0):
            raise ValueError("confidence вне [0, 1]")


@dataclass(frozen=True)
class KnowledgeLink:
    """Время знания: кто и когда узнал о событии. Ось независима от historical."""

    event_ref: str  # entry_id события
    knower_id: EntityRef
    learned_age: Optional[int] = None
    learned_year: Optional[int] = None
    channel: KnowledgeChannel = KnowledgeChannel.UNKNOWN
    certainty: float = 1.0

    def __post_init__(self) -> None:
        if not (0.0 <= self.certainty <= 1.0):
            raise ValueError("certainty вне [0, 1]")

    @staticmethod
    def validate_against(event: "ChronicleEntry", link: "KnowledgeLink") -> None:
        """Инвариант «learned ≥ historical» (запрет 4). Fail-loud, вызывается store."""
        if link.event_ref != event.entry_id:
            raise ValueError("KnowledgeLink ссылается на чужой event_ref")
        if link.learned_age is not None and event.historical_age is not None:
            if link.learned_age < event.historical_age:
                raise ValueError(
                    f"Два времени смешаны: learned_age({link.learned_age}) < "
                    f"historical_age({event.historical_age})"
                )


# ── Декомпозиция (transient) ─────────────────────────────────────────────────


@dataclass(frozen=True)
class DecompositionItem:
    """Кандидат декомпозитора. Гипотеза до «Принять как канон» (INV-LLM-NOT-SSOT)."""

    kind: EntryKind
    draft_payload: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    needs_confirmation: bool = False
    question: Optional[ClarificationQuestion] = None

    def __post_init__(self) -> None:
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError("confidence вне [0, 1]")


@dataclass(frozen=True)
class BiographyDecomposition:
    """Результат разбора фрагмента. Transient: не канон, не персистится как истина."""

    chronicle_id: str
    fragment_ord: int
    items: Tuple[DecompositionItem, ...] = ()


# ── Документ ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ChronicleDocument:
    """
    Документ хроники одного персонажа. author_text append-only по абзацам:
    декомпозиция обратима и перепроводима без потери авторского слова (FR-1.5).
    """

    chronicle_id: str
    npc_ref: str  # npc_id или якорь white-spotp/services/chronicle/chronicle_store.py
    author_text: str = ""
    entries: Tuple[ChronicleEntry, ...] = ()
    white_spots: Tuple[WhiteSpot, ...] = ()
    canonical: bool = False
    canonical_version: int = 0
    schema_version: int = SCHEMA_VERSION
    created_by_tick_source: Optional[str] = None  # прологепистический якорь
    # ADR-O-422: возраст персонажа на момент игры (для меж-NPC возрастной
    # математики сверщика). None = не задан (Vacuum, §ENIGMA-003).
    game_start_age: Optional[int] = None
    # ADR-O-422: группы склеенных событий — кортежи entry_id, подтверждённые
    # автором карточкой «это одно событие». Пусто = склеек нет.
    event_groups: Tuple[Tuple[str, ...], ...] = ()
    # S366: субъективные причинные убеждения NPC (СЛОЙ 2). Не мутирует causes.
    # Пусто по умолчанию → backward compat со старыми документами без этого поля.
    npc_beliefs: Tuple["NpcCausalBelief", ...] = ()
    # S366: причинные кандидаты для проверки автором (СЛОЙ 3). Не проставляет causes.
    # PENDING → ACCEPTED | REJECTED через POST /resolve-cause-candidate.
    cause_candidates: Tuple["CauseCandidate", ...] = ()
