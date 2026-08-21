# backend/app/domain/epistemology.py
"""
path: /project/backend/app/domain/epistemology.py
Назначение: Канонический контракт эпистемического слоя (Proposition Layer).
Зависимости: Нет
Основные сущности: Proposition, SpeechAct, ClaimEvent, EpistemicRecord

Железный инвариант S188:
> ClaimEvent никогда не является World Truth и никогда напрямую не мутирует RelationshipStore.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Predicate(Enum):
    """Действия/события, являющиеся предметом утверждения."""
    STOLE = "stole"
    ATTACKED = "attacked"
    HELPED = "helped"
    # S199: Second-Order ToM. Агент верит, что другой агент утверждает P.
    ASSERTS = "asserts"


class SpeechAct(Enum):
    """Тип коммуникативного акта."""
    ASSERT = "assert"
    DENY = "deny"
    QUESTION = "question"


@dataclass(frozen=True)
class Proposition:
    """
    Чистая семантика утверждения. Не содержит информации об истинности.
    S188 использует бинарный субъект–предикат–объект контракт как MVP-подмножество.
    """
    subject_id: str  # О ком утверждение
    predicate: Predicate  # Что произошло
    object_id: str  # С чем/кем взаимодействовали
    polarity: bool = True  # True: "B украл X". False: "B НЕ украл X".


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
class EpistemicRecord:
    """
    Субъективное убеждение агента. Это состояние сознания, а не факт мира.
    Хранит provenance (откуда агент это узнал).
    """
    agent_id: str
    proposition: Proposition
    confidence: float  # 0.0 - 1.0
    source_id: str  # От кого получено (speaker)
    source_claim_id: str  # ID исходного ClaimEvent
    first_observed_tick: int
    last_updated_tick: int

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