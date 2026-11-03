"""
USL — Universal Semantic Layer (Единый семантический слой).

Доменный тип: общий словарь смысла для биографического (CCH) и интерактивного
(AG1/DLG) языковых контуров.

Назначение (по вердикту Мастера ADR-O-437, USL-0):
    - transient DTO, не персистится (прецедент BiographyDecomposition);
    - не новый источник истины (инвариант USL-3 «USL не пишет мир»);
    - read-only проектор (не пишет в TruthState/канон/EventMemory/EpistemicStore);
    - frozen dataclasses, stdlib only (Закон 1.2 Устава);
    - ссылки на существующие типы domain-слоя, а не их копии.

Главный критерий успеха: одинаковый смысл одинаково понимается в биографии
NPC и в живом игровом диалоге. USL — не третья подсистема, а общий язык.

Контрактные инварианты USL-1…USL-6 (USL-документ §3.4):
    USL-1: одно представление смысла независимо от источника
    USL-2: источник ≠ истина (source_kind + epistemic_status)
    USL-3: не пишет мир (read-only проектор)
    USL-4: обратная совместимость (поверх существующих контрактов)
    USL-5: провенанс трассируем (source_span обязателен)
    USL-6: детерминизм (повторный прогон = идентичный USLUnit)
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Tuple

# Реюз существующих типов domain-слоя (не копии — ссылки).
# Закон 1.2 Устава: domain/ не импортирует services/models/api.
from app.domain.chronicle import KnowledgeChannel

# ── Источник USLUnit (USL-2: источник ≠ истина) ──────────────────────────────

class USLSourceKind(str, Enum):
    """Происхождение смысловой единицы.

    Определяет, ОТКУДА пришёл смысл. Не определяет истинность —
    за истинность отвечают существующие writer-каналы (canonize, BeliefRevisionEngine).
    PLAYER_ASSERTION никогда не становится AUTHOR_CANON (инвариант USL-2).
    """
    AUTHOR_CANON = "author_canon"           # канонизированная хроника (статус AUTHOR_*)
    AUTHOR_HYPOTHESIS = "author_hypothesis"  # LLM_DRAFT — гипотеза декомпозитора
    PLAYER_ASSERTION = "player_assertion"   # утверждение игрока (не становится каноном)
    NPC_SPEECH = "npc_speech"               # реплика NPC
    NPC_MEMORY = "npc_memory"               # воспоминание NPC
    WORLD_CHRONICLE = "world_chronicle"     # хроника мира (проекции CCH-5)
    RUMOR = "rumor"                         # слух
    INFERENCE = "inference"                 # вывод (BC-1 dormant; testimony — после BC-5)
    HYPOTHESIS = "hypothesis"               # модель-гипотеза (галлюцинация LLM, не разобрано)


@dataclass(frozen=True)
class USLSourceRef:
    """Источник единицы: КТО и ОТКУДА.

    span обязателен (USL-5: поле без происхождения запрещено).
    tick/ordinal — опциональны, зависят от источника.
    """
    source_kind: USLSourceKind
    document_ref: str = ""          # npc_id (биография) / npc_id+tick (ввод) / campaign_id
    span: str = ""                   # подстрока исходного текста (USL-5)
    tick: Optional[int] = None       # для игрового ввода (ClaimEvent.tick)
    ordinal: Optional[int] = None    # для биографического фрагмента (fragment_ord)


# ── Эпистемика (USL-3: не решает истинность) ─────────────────────────────────

@dataclass(frozen=True)
class USLEpistemics:
    """Источник и статус знания. НЕ равен вероятности истинности (USL-2).

    certainty — субъективная оценка уверенности источника, не вероятность
    истинности утверждения. disputed=True — противоречие уже известно в данных
    (прецедент BeliefGrounding.MISTAKEN).
    """
    source_kind: USLSourceKind
    channel: Optional[KnowledgeChannel] = None    # реюз chronicle.KnowledgeChannel
    certainty: Optional[float] = None              # 0..1, None = не оценено
    disputed: bool = False


# ── Сущности (тонкая ссылка, не копия EntityRef) ─────────────────────────────

@dataclass(frozen=True)
class USLEntityRef:
    """Ссылка на сущность в общем словаре USL.

    Не дублирует chronicle.EntityRef — это проекция. ref_id указывает на
    npc_id / white_spot_id / player / addressee / unknown. Для биографии
    строится из EntityRef; для ввода — из resolve_target_with_candidates.

    kind: "resolved" (npc_id) | "new_npc" | "white_spot" | "unknown_person"
          | "self" | "addressee" | "player" | "unknown"
    """
    kind: str
    ref_id: str = ""              # npc_id / white_spot_id / player / addressee / unknown
    name_hint: str = ""           # для unresolved — сырая NP-группа
    source_span: str = ""         # USL-5: подстрока, из которой возникла ссылка


# ── События (закрытый реестр USLPredicate) ───────────────────────────────────

class USLPredicate(str, Enum):
    """Закрытый реестр USL-предикатов (расширение = мини-ADR).

    Значения для общих 6 предикатов СОВПАДАЮТ с epistemology.Predicate.value —
    маппинг trivial: Predicate(uslpred.value) работает для общих. Это не
    дублирование онтологии — это общий словарь, из которого Predicate берёт
    подмножество для эпистемического транспорта, а USLPredicate — для смысла.

    Биографические расширения маппируются из EntryKind через явную таблицу
    (прецедент entry_kind_to_cause_kind, chronicle.py:114-123).
    """
    # Общие 6 (значения совпадают с Predicate.value)
    STOLE = "stole"
    ATTACKED = "attacked"
    HELPED = "helped"
    ASSERTS = "asserts"
    EXITS_TO = "exits_to"
    NAME = "name"
    # Биографические расширения (из EntryKind/payload)
    WORK_FOR = "work_for"           # EntryKind.RELATIONSHIP «работал на»
    KNOWS = "knows"                 # KNOWLEDGE_LINK «знал»
    BORN = "born"                   # EVENT «родился»
    DIED = "died"                   # EVENT «умер»
    LIVES_AT = "lives_at"           # LOCATION «живёт в»
    HAS_TRAIT = "has_trait"         # TRAIT_SEED
    HAS_EFFECT = "has_effect"       # EFFECT
    BELIEVES = "believes"           # BELIEF_SEED
    DESIRES = "desires"             # DESIRE_SEED


@dataclass(frozen=True)
class USLEvent:
    """Событие/действие как смысловая единица.

    subject/object — ref_id USLEntityRef (строка), не вложенный EntityRef.
    polarity — реюз Proposition.polarity (True = утверждение, False = отрицание).
    completed — завершённость («проработал пять лет» → True; «работаю» → False;
    None = не сказано).
    """
    predicate: USLPredicate
    subject: Optional[str] = None          # ref_id USLEntityRef
    object: Optional[str] = None
    polarity: bool = True
    completed: Optional[bool] = None
    negated: bool = False
    source_span: str = ""


# ── Время (6 форм по вердикту Мастера Q2) ─────────────────────────────────────

class USLTimeKind(str, Enum):
    """Форма времени (вердикт Мастера Q2: различать 6 форм).

    POINT — точка в прошлом/будущем («в 8 лет», «пять лет назад» с якорем)
    DURATION — длительность («пять лет», «десять лет службы»)
    INTERVAL — интервал между событиями («год прошёл после…»)
    ORDER — относительный порядок («до», «после», «за N лет до»)
    RELATIVE — относительное время («год назад», «вчера», «недавно»)
    UNKNOWN — неоднозначное или неопределённое время

    «Пять лет работал» — DURATION.
    «Пять лет назад работал» — RELATIVE (точка в прошлом относительно speech_time).
    Это разные семантические конструкции (поправка Мастера к Q2).
    """
    POINT = "point"
    DURATION = "duration"
    INTERVAL = "interval"
    ORDER = "order"
    RELATIVE = "relative"
    REPEAT = "repeat"  # CCH-15 P0: повторяемость («каждый год», «регулярно»)
    UNKNOWN = "unknown"


class USLAnchorKind(str, Enum):
    """Тип якоря времени (обобщение AgeAnchorKind, не расширение).

    AgeAnchorKind не трогаем (вердикт Q2). USLAnchorKind — отдельный реестр
    для общего слоя, включающий оси, которых в хронике нет (GAME_TICK, SPEECH_TIME).
    """
    AGE_N = "age_n"               # возраст (N лет) — реюз AgeAnchorKind.AGE_N
    YEARS_AGO = "years_ago"       # «N лет назад» — реюз AgeAnchorKind.YEARS_AGO
    WORLD_YEAR = "world_year"     # год мира (chronicle.py:339, потребитель пока 0)
    GAME_TICK = "game_tick"        # тик симуляции (ClaimEvent.tick)
    SPEECH_TIME = "speech_time"   # момент речи (для PLAYER_ASSERTION/NPC_SPEECH)
    EVENT_REF = "event_ref"       # ссылка на событие (relative_to)
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class USLTimeExpression:
    """Временная конструкция (USL §6.2).

    value — количество (лет/дней/тиков); семантика задаётся kind+anchor.
    relative_to — event_ref / unit_id, к которому относится INTERVAL/ORDER.
    source_span обязателен (USL-5).
    """
    kind: USLTimeKind
    anchor: Optional[USLAnchorKind] = None
    value: Optional[int] = None
    relative_to: Optional[str] = None
    source_span: str = ""


# ── Причинность (статус — за существующими слоями S366) ──────────────────────

class USLCausalRelation(str, Enum):
    """Реестр причинных связей (реюз TruthRelation).
    USL не создаёт новую причинность (USL §6.4).
    """
    CAUSES = "causes"
    ENABLES = "enables"
    EXPLAINS = "explains"
    CONTRADICTS = "contradicts"


@dataclass(frozen=True)
class USLCausalLink:
    """Заявленная в тексте причинная связь.

    asserted_by_text=True — текст прямо говорит («после смерти отца он унаследовал»).
    Статус истины решается существующими механизмами S366, не USL.
    Запрет: USLTimeExpression(ORDER) никогда не конвертируется в USLCausalLink
    автоматически (хронология ≠ причина).
    """
    relation: USLCausalRelation
    cause_ref: str
    effect_ref: str
    asserted_by_text: bool = True
    source_span: str = ""


# ── Отношения (без скаляров — USL §4.5) ──────────────────────────────────────

@dataclass(frozen=True)
class USLRelation:
    """Отношение между участниками.

    Скаляры (trust=0.8) запрещены в USL — «числа без происхождения запрещены»
    (chronicle.py:154-168). Скаляры вычисляются потребителями (сеялкой,
    RelationshipStore) из структуры. USL хранит только тип и valence.
    """
    relation_type: str             # "work_relation" / "kinship" / "alliance" / ...
    subject: str                   # ref_id USLEntityRef
    object: str
    valence: Optional[str] = None  # "positive" / "negative" / "neutral"
    source_span: str = ""


# ── Модальность (None = недостаточная информация, не False) ──────────────────

class USLModality(str, Enum):
    """Модальность акта (реюз _VALID_ACT_MODALITIES из intent_compressor)."""
    REALIS = "REALIS"
    HYPOTHETICAL = "HYPOTHETICAL"
    CONDITIONAL = "CONDITIONAL"
    DESIRED = "DESIRED"


@dataclass(frozen=True)
class USLModal:
    """Модальность, отрицание, условность.

    None = недостаточная информация, НЕ трактуется как False (правило Блока 1,
    intent_profile.py:53-55). Гейт потребителя (IntentReadiness) решает, что
    делать с None — USL лишь гарантирует, что модальность дошла до гейта.
    """
    negated: Optional[bool] = None
    modality: Optional[USLModality] = None
    condition: Optional[str] = None
    quoted: Optional[bool] = None
    quoted_speaker: Optional[str] = None


# ── Контекст разговора / фрагмента ───────────────────────────────────────────

@dataclass(frozen=True)
class USLContext:
    """Контекст, в котором возникла единица смысла.

    Собирает существующее из обоих контуров: references (анафора) из
    IntentSemanticField, addressee (≠ target, доктрина телесной семантики),
    dialogue_thread/conversation_continuation, place (scene location),
    fragment_ord (для биографии).
    """
    references: Tuple[str, ...] = ()
    addressee: Optional[str] = None
    dialogue_thread: Optional[str] = None
    conversation_continuation: Optional[str] = None
    place: Optional[str] = None
    fragment_ord: Optional[int] = None


# ── USLUnit — минимальная единица смысла ─────────────────────────────────────

@dataclass(frozen=True)
class USLUnit:
    """Минимальная единица смысла (USL §4.2).

    Transient DTO: не персистится нигде (прецедент BiographyDecomposition —
    «transient: не канон, не персистится как истина», chronicle.py:404-410).
    Frozen: прецедент IntentSemanticField.Config.frozen (Pure Reducer, ADR-TZ10-1).

    Не дублирует поля ChronicleEntry / IntentSemanticField — это проекция,
    собирающая общий смысл из обоих контуров. origin_kind/origin_id указывают
    на исходный объект для трассировки, не дублируя его.
    """
    unit_id: str                          # детерминированный (make_unit_id)
    source_ref: USLSourceRef
    text_span: str                        # USL-5: поле без происхождения запрещено

    entities: Tuple[USLEntityRef, ...] = ()
    events: Tuple[USLEvent, ...] = ()
    temporal: Tuple[USLTimeExpression, ...] = ()
    causal: Tuple[USLCausalLink, ...] = ()
    relations: Tuple[USLRelation, ...] = ()
    modality: USLModal = field(default_factory=USLModal)
    epistemics: USLEpistemics = field(
        default_factory=lambda: USLEpistemics(source_kind=USLSourceKind.HYPOTHESIS)
    )
    context: USLContext = field(default_factory=USLContext)

    # Трассировка к источнику (не дублирование)
    origin_kind: str = ""   # "chronicle_entry" / "intent_field" / "fragment"
    origin_id: str = ""     # entry_id / intent hash / fragment_ord


def make_unit_id(source_ref: USLSourceRef, text_span: str) -> str:
    """Детерминированный id USLUnit (USL-6: детерминизм).

    Прецедент: make_entry_id (chronicle.py), make_candidate_id (chronicle.py:318).
    Одинаковый source_ref + text_span → одинаковый id. Повторный прогон = идентичный USLUnit.
    """
    raw = f"{source_ref.source_kind.value}:{source_ref.document_ref}:{source_ref.span}:{text_span}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()
