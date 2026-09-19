# path: /project/backend/app/domain/disclosure.py
# Назначение: M1/P5.1 — «Disclosure is a directed social decision between
#   agents, not an NPC→Player mechanic» (Мастер). Каноническая формула:
#   KNOWER → RECIPIENT. V1: PERSON → PERSON. SocialTargetKind = PERSON
#   только (будущие GROUP/INSTITUTION/PUBLIC — через реальных потребителей,
#   не пустые обещания enum). Пороги — V1_CALIBRATION_DEFAULTS (не игровые
#   истины; Calibration Lab — будущий владелец).
# Зависимости: enum, dataclasses
# Основные сущности: SocialTargetKind, SocialTarget, DisclosureLevel,
#   InteractionPressure, DisclosureContext, DisclosureOutcome

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class SocialTargetKind(Enum):
    """Адресат социального взаимодействия. V1: только PERSON.
    GROUP/INSTITUTION/PUBLIC НЕ резервируются (Мастер: пустые enum-
    обещания = ложная онтологическая готовность; появятся вместе с
    реальными потребителями и механизмами)."""

    PERSON = "person"


@dataclass(frozen=True)
class SocialTarget:
    """Универсальный адресат. Player = SocialTarget(PERSON, "player") —
    обычный recipient, не специальный закон (PLAYER is special as INPUT
    DEVICE, not as SOCIAL LAW)."""

    kind: SocialTargetKind
    id: str


class DisclosureLevel(Enum):
    """Семантический контракт (не название реплики). P5 решает ЧТО;
    P7 вербализует КАК; LLM не решает. DENY = «не раскрываю», не «сообщаю
    ложь» (V1 без лжи — fabricate-структуры не существует)."""

    DENY = "deny"           # знание не передаётся
    REDIRECT = "redirect"   # знание не передаётся; разговор уходит в сторону
    HINT = "hint"           # информация о факте утекает; факт не идентифицирован
    PARTIAL = "partial"     # строгое подмножество; fraction ограничивает
    REVEAL = "reveal"       # знание передано


class InteractionPressure(Enum):
    """Тип социального давления (часть социальной онтологии; не строки)."""

    QUESTION = "question"
    ACCUSE = "accuse"
    PRESSURE = "pressure"


@dataclass(frozen=True)
class DisclosureContext:
    """Контекст взаимодействия. pressure_amount — накопленная интенсивность
    ДИАДИЧЕСКОГО давления (recipient → knower); float, не count
    (QUESTION+QUESTION+ACCUSE ≠ «3 вопроса» — аккумулятор смешивает типы)."""

    pressure: InteractionPressure
    pressure_amount: float  # накоплено recipient-давлением на knower


@dataclass(frozen=True)
class DisclosureOutcome:
    """P5-вердикт. БЕЗ stance (decision ≠ expression; stance — P7).
    Живёт в стеке вызова; передаётся как DTO-поле (НЕ prepared_prompt)."""

    level: DisclosureLevel
    secret_id: str
    fraction: float  # 0.0..1.0; для PARTIAL — доля канон-текста
