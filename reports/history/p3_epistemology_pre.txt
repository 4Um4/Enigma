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
    """Тип коммуникативного акта (Searle's Speech Act Theory, адаптировано под ENIGMA)."""
    ASSERT       = "assert"        # утверждение
    QUESTION     = "question"      # вопрос
    REQUEST      = "request"       # просьба
    ORDER        = "order"         # приказ
    OFFER        = "offer"         # предложение
    PROMISE      = "promise"       # обещание
    THREAT       = "threat"        # угроза
    APOLOGY      = "apology"       # извинение
    COMPLIMENT   = "compliment"    # комплимент
    INSULT       = "insult"        # оскорбление
    ACCUSATION   = "accusation"    # обвинение
    GREETING     = "greeting"      # приветствие
    FAREWELL     = "farewell"      # прощание
    CONTINUE     = "continue"      # «продолжай», «ну?», «и?»
    CLARIFY      = "clarify"       # «не это я имел в виду»
    REJECT       = "reject"        # отказ
    ACCEPT       = "accept"        # согласие
    # Legacy / MVP aliases (для обратной совместимости со старым кодом)
    DENY         = "reject"

class SocialIntent(Enum):
    """Каузальная цель социального действия (не путать с лингвистической формой SpeechAct)."""
    OBTAIN_INFORMATION   = "obtain_information"
    OBTAIN_COOPERATION   = "obtain_cooperation"
    OBTAIN_COMPLIANCE    = "obtain_compliance"     # через угрозу
    REPAIR_RELATIONSHIP  = "repair_relationship"
    BUILD_RAPPORT        = "build_rapport"
    INTIMIDATE           = "intimidate"
    FLIRT                = "flirt"
    COMFORT              = "comfort"
    DECEIVE              = "deceive"
    CONFESS              = "confess"
    PROVOKE              = "provoke"
    DEFEND               = "defend"
    NEUTRAL              = "neutral"               # бытовая коммуникация


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

    def to_dict(self) -> dict:
        """Э6: JSON-сериализация (§12 WARA)."""
        return {
            "subject_id": self.subject_id,
            "predicate": self.predicate.value,
            "object_id": self.object_id,
            "polarity": self.polarity,
        }

    @staticmethod
    def from_dict(d: dict) -> "Proposition":
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
