# backend/app/domain/epistemology.py
"""
path: /project/backend/app/domain/epistemology.py
Назначение: Канонический контракт эпистемического слоя (Proposition Layer).
Зависимости: Нет
Основные сущности: Proposition, SpeechAct, ClaimEvent, EpistemicRecord, AttributedBelief

Железный инвариант S188:
> ClaimEvent никогда не является World Truth и никогда напрямую не мутирует RelationshipStore.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional, Union


class Predicate(Enum):
    """Действия/события, являющиеся предметом утверждения."""

    STOLE = "stole"
    ATTACKED = "attacked"
    HELPED = "helped"
    # S199: Second-Order ToM. Агент верит, что другой агент утверждает P.
    ASSERTS = "asserts"
    # SPATIAL-KNOWLEDGE-01 (mini-ADR, мандат «способность узнавать мир»):
    # «subject_id прошёл через boundary-узел subject в направлении object_id».
    # Субъект — наблюдаемый актор, объект — целевая локация. Единственный
    # spatial-предикат реестра; расширение — отдельной ревизией.
    EXITS_TO = "exits_to"
    # Шаг 4 (вердикт Мастера, 1α): «subject_id представился как object_id».
    # Детерминированная канонизация SELF_INTRODUCTION: subject — актор,
    # object — заявленное имя. CLAIM ≠ BELIEF ≠ TRUTH: запись о факте
    # утверждения, не об истинности имени. Расширение — отдельной ревизией.
    NAME = "name"
    # COGNITIVE-CONTINUITY-01: subject оскорбил object.
    # subject — оскорбитель, object — жертва. Расширение реестра (по образцу
    # NAME: запись о факте оскорбления, не об истинности слов).
    INSULTED = "insulted"


class SpeechAct(Enum):
    """Тип коммуникативного акта (Searle's Speech Act Theory, адаптировано под ENIGMA)."""

    ASSERT = "assert"  # утверждение
    QUESTION = "question"  # вопрос
    REQUEST = "request"  # просьба
    ORDER = "order"  # приказ
    OFFER = "offer"  # предложение
    PROMISE = "promise"  # обещание
    THREAT = "threat"  # угроза
    APOLOGY = "apology"  # извинение
    COMPLIMENT = "compliment"  # комплимент
    INSULT = "insult"  # оскорбление
    ACCUSATION = "accusation"  # обвинение
    GREETING = "greeting"  # приветствие
    FAREWELL = "farewell"  # прощание
    CONTINUE = "continue"  # «продолжай», «ну?», «и?»
    CLARIFY = "clarify"  # «не это я имел в виду»
    REJECT = "reject"  # отказ
    ACCEPT = "accept"  # согласие
    # Legacy / MVP aliases (для обратной совместимости со старым кодом)
    DENY = "reject"


class SocialIntent(Enum):
    """Каузальная цель социального действия (не путать с лингвистической формой SpeechAct)."""

    OBTAIN_INFORMATION = "obtain_information"
    OBTAIN_COOPERATION = "obtain_cooperation"
    OBTAIN_COMPLIANCE = "obtain_compliance"  # через угрозу
    REPAIR_RELATIONSHIP = "repair_relationship"
    BUILD_RAPPORT = "build_rapport"
    INTIMIDATE = "intimidate"
    FLIRT = "flirt"
    COMFORT = "comfort"
    DECEIVE = "deceive"
    CONFESS = "confess"
    PROVOKE = "provoke"
    DEFEND = "defend"
    NEUTRAL = "neutral"  # бытовая коммуникация


@dataclass(frozen=True)
class Proposition:
    """
    Чистая семантика утверждения. Не содержит информации об истинности.
    S188 использует бинарный субъект–предикат–объект контракт как MVP-подмножество.
    """

    subject_id: str  # О ком утверждение
    predicate: Predicate  # Что произошло
    object_id: str
    is_attributed: bool = False  # EPISTEMIC-005: True если это модель чужого убеждения  # С чем/кем взаимодействовали
    polarity: bool = True  # True: "B украл X". False: "B НЕ украл X".

    def to_dict(self) -> dict[str, Any]:
        """Э6: JSON-сериализация (§12 WARA)."""
        return {
            "subject_id": self.subject_id,
            "predicate": self.predicate.value,
            "object_id": self.object_id,
            "polarity": self.polarity,
        }

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "Proposition":
        from app.domain.epistemology import Predicate  # forward-ref safe

        return Proposition(
            subject_id=d["subject_id"],
            predicate=Predicate(d["predicate"]),
            object_id=d["object_id"],
            polarity=d.get("polarity", True),
        )


@dataclass(frozen=True)
class ClaimEvent:
    """
    Контекст передачи информации. Объективное событие в мире (кто-то что-то сказал).
    Один Claim (по claim_id) может передаваться через множество событий.
    """

    event_id: str
    claim_id: str
    speaker_id: str
    listener_id: str
    proposition: Proposition
    speech_act: SpeechAct = SpeechAct.ASSERT
    tick: int = 0


@dataclass(frozen=True)
class AttributedBelief:
    """
    Рекурсивная структура атрибуции убеждения (EPISTEMIC-005).

    Семантика: holder_id верит, что content истинно.
    content может быть:
    - Proposition (атомарное утверждение) — базовый случай
    - AttributedBelief (следующий уровень атрибуции) — рекурсия

    Пример:
    AttributedBelief(
        holder_id="B",
        content=AttributedBelief(
            holder_id="C",
            content=Proposition(subject_id="X", predicate=Predicate.STOLE, object_id="Y")
        )
    )
    означает: "B верит, что C верит, что X украл Y"
    """
    holder_id: str
    content: Union[Proposition, "AttributedBelief"]

    def __post_init__(self) -> None:
        # Валидация: content должен быть Proposition или AttributedBelief
        if not isinstance(self.content, (Proposition, AttributedBelief)):
            raise TypeError(
                f"AttributedBelief.content must be Proposition or AttributedBelief, "
                f"got {type(self.content).__name__}"
            )


@dataclass(frozen=True)
class EpistemicRecord:
    """
    Субъективное убеждение агента. Это состояние сознания, а не факт мира.
    Хранит provenance (откуда агент это узнал).

    Семантика полей:
    - agent_id: корневой наблюдатель, владелец этой записи
    - proposition: атомарное содержание записи (о чём речь)
    - attribution_chain: если None — собственное убеждение agent_id;
                         если не None — приписанное убеждение (agent_id моделирует,
                         что цепочка holder_id верит в proposition)

    Инвариант: если attribution_chain существует, атомарное содержание на её конце
    обязано совпадать с proposition.
    """

    agent_id: str
    proposition: Proposition
    confidence: float  # 0.0 - 1.0
    source_id: str  # От кого получено (speaker)
    source_claim_id: str  # ID исходного ClaimEvent
    first_observed_tick: int
    last_updated_tick: int
    # COGNITIVE-CONTINUITY-01: provenance chain. source_type различает
    # непосредственное наблюдение ("direct_observation") и свидетельство
    # ("testimony"). original_source_id сохраняет первоисточник цепочки
    # при ретрансляции (не перезаписывается свежим спикером).
    source_type: str = ""
    original_source_id: str = ""
    # A19.5: История обработанных claim_id для идемпотентности.
    # Предотвращает искусственный рост confidence при повторной доставке одного и того же утверждения.
    # ОГРАНИЧЕНИЕ: История растёт неограниченно в рамках одной записи. Для долгоживущих NPC
    # это может привести к увеличению размера сохранений. Будущее улучшение: отдельный индекс
    # обработанных утверждений в EpistemicStore с TTL или LRU-вытеснением.
    seen_claim_ids: tuple[str, ...] = ()
    # EPISTEMIC-005: Рекурсивная атрибуция убеждения.
    # None = собственное убеждение агента в proposition.
    # Не None = агент верит, что цепочка holder_id верит в proposition.
    attribution_chain: Optional[AttributedBelief] = None

    def __post_init__(self) -> None:
        # Проверка согласованности proposition и attribution_chain
        if self.attribution_chain is not None:
            # Извлекаем атомарное содержание с конца цепочки
            atomic_content = self._get_atomic_content(self.attribution_chain)
            if atomic_content != self.proposition:
                raise ValueError(
                    f"EpistemicRecord invariant violation: attribution_chain atomic content "
                    f"({atomic_content}) does not match proposition ({self.proposition})"
                )

    @staticmethod
    def _get_atomic_content(chain: AttributedBelief) -> Proposition:
        """Итеративно извлекает атомарное содержание с конца цепочки атрибуции."""
        current: Union[Proposition, AttributedBelief] = chain
        visited = set()  # Защита от структурных циклов

        while isinstance(current, AttributedBelief):
            obj_id = id(current)
            if obj_id in visited:
                raise ValueError("Structural cycle detected in attribution_chain")
            visited.add(obj_id)
            current = current.content

        # content по контракту — Proposition | AttributedBelief; цикл вы 제거л
        # все AttributedBelief, поэтому current гарантированно Proposition.
        return current

    def to_dict(self) -> dict[str, Any]:
        """Итеративная сериализация без рекурсии."""
        result = {
            "agent_id": self.agent_id,
            "proposition": self.proposition.to_dict(),
            "confidence": self.confidence,
            "source_id": self.source_id,
            "source_claim_id": self.source_claim_id,
            "first_observed_tick": self.first_observed_tick,
            "last_updated_tick": self.last_updated_tick,
            "source_type": self.source_type,
            "original_source_id": self.original_source_id,
            "seen_claim_ids": list(self.seen_claim_ids),
        }

        if self.attribution_chain is not None:
            # Итеративная сериализация цепочки holder_id
            chain_data = []
            current: Union[Proposition, AttributedBelief] = self.attribution_chain
            visited = set()

            while isinstance(current, AttributedBelief):
                obj_id = id(current)
                if obj_id in visited:
                    raise ValueError("Structural cycle detected during serialization")
                visited.add(obj_id)
                chain_data.append(current.holder_id)
                current = current.content

            result["attribution_chain"] = chain_data

        return result

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "EpistemicRecord":
        """Десериализация с обратной совместимостью."""
        from app.domain.epistemology import Predicate  # forward-ref safe

        prop_data = d["proposition"]
        proposition = Proposition(
            subject_id=prop_data["subject_id"],
            predicate=Predicate(prop_data["predicate"]),
            object_id=prop_data["object_id"],
            polarity=prop_data.get("polarity", True)
        )

        attribution_chain: Optional[AttributedBelief] = None
        chain_data = d.get("attribution_chain")
        if chain_data:
            # Итеративная десериализация: строим цепочку снизу вверх
            # chain_data — это список holder_id от внешнего к внутреннему уровню
            # Последний holder_id верит в proposition
            current_content: Optional[AttributedBelief] = None
            for holder_id in reversed(chain_data):
                current_content = AttributedBelief(
                    holder_id=holder_id,
                    content=current_content if current_content is not None else proposition,
                )
            attribution_chain = current_content

        return EpistemicRecord(
            agent_id=d["agent_id"],
            proposition=proposition,
            confidence=d["confidence"],
            source_id=d["source_id"],
            source_claim_id=d["source_claim_id"],
            first_observed_tick=d["first_observed_tick"],
            last_updated_tick=d["last_updated_tick"],
            source_type=d.get("source_type", ""),
            original_source_id=d.get("original_source_id", ""),
            seen_claim_ids=tuple(d.get("seen_claim_ids", [])),
            attribution_chain=attribution_chain
        )


@dataclass(frozen=True)
class BeliefSummary:
    """A19.5 Step 2: Лёгкая проекция убеждения для DecisionHub.
    Содержит минимальную семантику для оценки действий без копирования всего EpistemicRecord.
    """

    proposition: Proposition
    confidence: float
    source_id: str
    subject_id: str
    object_id: str
    is_attributed: bool = False  # EPISTEMIC-005: True если это модель чужого убеждения


@dataclass(frozen=True)
class EpistemicContext:
    """
    Проекция убеждений агента в когнитивно-релевантное состояние.
    Это НЕ EpistemicRecord. Это результат интерпретации убеждений.
    DecisionHub читает этот контекст, а не EpistemicStore.
    """

    agent_id: str
    perceived_threats: tuple[str, ...] = ()
    perceived_allies: tuple[str, ...] = ()
    perceived_violations: int = 0
    max_confidence: float = 0.0
    # S197: Causal Provenance. Утверждение, породившее max_confidence.
    # DecisionHub пробрасывает его в CommunicationIntent, чтобы избежать угадывания (causal break) в post_decision.
    trigger_proposition: Optional[Proposition] = None
    trigger_source_id: Optional[str] = None  # R4: Автор trigger_proposition (для целеполагания)
    # GC-RELEVANCE-01 (R1): клеймы, адресованные самому агенту (subject == agent).
    # Обвинение в свой адрес — не новость о третьем лице и не угроза в собственном
    # лице (проб S258: perceived_threats содержал самого агента). Отдельный канал
    # самореферентности, развязанный с threat/violation/trigger-путём.
    claims_about_self: tuple[Proposition, ...] = ()
    claim_source_id: Optional[str] = None  # R4: Автор топ-claim_about_self (для целеполагания)
    max_self_confidence: float = 0.0
    # COGNITIVE-CONTINUITY-01: report-канал. Знание об оскорблении третьего
    # лица — отдельный канал от threat (trigger) и self-relevance
    # (claims_about_self). NPC может решить сообщить жертве.
    # Заполняется EpistemicContextResolver для Predicate.INSULTED (и будущих
    # REPORT_PREDICATES) при conf >= REPORT_CONFIDENCE_THRESHOLD.
    report_proposition: Optional[Proposition] = None
    # A19.5 Step 2: Топ-3 наиболее уверенных убеждения агента для target-aware scoring.
    recent_beliefs: tuple[BeliefSummary, ...] = ()
    # EPISTEMIC-005: Отдельное хранение атрибутированных убеждений (Theory of Mind).
    # Не вытесняют прямые убеждения и не влияют на прямой scoring.
    attributed_beliefs: tuple[BeliefSummary, ...] = ()
