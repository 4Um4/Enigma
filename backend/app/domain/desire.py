"""
path: /project/backend/app/domain/desire.py
Назначение: Living Activity — Desire (направленное желание) как персистентная
    runtime-сущность L2.8-класса: decay/обучение/множественная причинность (L-M1).
    Desire ≠ L3-драйв (эфемерная проекция EffectiveDrives): у Desire есть
    история (born_tick/last_fulfilled), вес и provenance-цепочка. Хранится
    в npc["desires"] как list[dict]; типизированный доступ — from_dict.
Зависимости: dataclasses, typing (чистый домен, никаких services)
Основные сущности: DesireSource, ProvenanceEntry, Desire
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Tuple

# §12.1: ключи — модульные константы, не inline-строки
_KEY_DESIRE_ID = "desire_id"
_KEY_SUBJECT = "subject_class"
_KEY_URGENCY = "urgency"
_KEY_TARGET_CLASS = "target_class"
_KEY_PROVENANCE = "provenance"
_KEY_BORN_TICK = "born_tick"
_KEY_LAST_FULFILLED = "last_fulfilled_tick"
_KEY_WEIGHT = "weight"
_KEY_LEARNED_FROM = "learned_from"

_KEY_PV_SOURCE = "source"
_KEY_PV_WEIGHT = "weight"
_KEY_PV_ORIGIN = "origin_ref"


class DesireSource(str, Enum):
    """Канонический реестр источников желания (три жизненных силы Мастера).

    I.  тело     → NEED
    II. личность → DRIVE (глубокие давления), VALUE (само-модель как линза),
                   RELATIONSHIP
    III. мир     → OBLIGATION (долг, служба, опека — imposed-позиции)
    + LEARNED — опыт (BC-1: SUCCEEDS_AT / FAILS_AT).

    Расширение реестра = мини-ADR (закрытый реестр, класс ADR-O-349).
    """

    NEED = "need"
    DRIVE = "drive"
    VALUE = "value"
    RELATIONSHIP = "relationship"
    OBLIGATION = "obligation"
    LEARNED = "learned"


def _clamp01(value: Any) -> float:
    """Кламп [0..1]: онтологические bounds — до коммита, не после (ADR-O-207)."""
    return max(0.0, min(1.0, float(value)))


@dataclass(frozen=True)
class ProvenanceEntry:
    """L-M1 (Multi-Cause Provenance): причинность множественная с рождения.

    weight — вклад источника; origin_ref — адресуемый источник (имя
    needs-ключа, id отношения, id imposed-позиции, id исхода).
    """

    source: DesireSource
    weight: float = 1.0
    origin_ref: str = ""

    def __post_init__(self) -> None:
        # Нормализация str → enum на рождении (закрытый реестр; прецедент
        # SemanticAction.__post_init__ — легальная запись в frozen).
        if not isinstance(self.source, DesireSource):
            object.__setattr__(self, "source", DesireSource(self.source))  # type: ignore[unreachable]
        object.__setattr__(self, "weight", _clamp01(self.weight))

    def to_dict(self) -> Dict[str, Any]:
        return {
            _KEY_PV_SOURCE: self.source.value,
            _KEY_PV_WEIGHT: round(self.weight, 4),
            _KEY_PV_ORIGIN: self.origin_ref,
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "ProvenanceEntry":
        return ProvenanceEntry(
            source=d.get(_KEY_PV_SOURCE, DesireSource.NEED.value),
            weight=d.get(_KEY_PV_WEIGHT, 1.0),
            origin_ref=d.get(_KEY_PV_ORIGIN, ""),
        )


@dataclass(frozen=True)
class Desire:
    """Направленное «хочу» с классом объекта и давлением.

    INVARIANT (L-M4 Causal Opacity): provenance описывает ФАКТИЧЕСКУЮ
    причинную структуру поведения; он НЕ гарантирует, что NPC «знает»
    причину собственного поведения. Само-модель — отдельный эпистемический
    слой (L-M3) и не читает этот контракт как истину о себе.

    Идентичность: desire_id стабилен по subject_class внутри набора NPC
    (idempotent upsert; детерминизм INV-REPLAY-DETERMINISM, uuid4 запрещён).
    """

    desire_id: str
    subject_class: str                       # food / money / safety / person / ...
    urgency: float                           # 0..1 — давление сейчас
    target_class: str                        # класс цели (не экземпляр)
    provenance: Tuple[ProvenanceEntry, ...]  # множественная (L-M1)
    born_tick: int
    last_fulfilled_tick: int = -1
    weight: float = 1.0                      # обучаемость: успех подкрепляет
    learned_from: Tuple[str, ...] = ()       # id исходов, append-only

    def __post_init__(self) -> None:
        object.__setattr__(self, "urgency", _clamp01(self.urgency))
        object.__setattr__(self, "weight", _clamp01(self.weight))
        # L4: молчаливые онтологические дыры запрещены — падаем громко
        if not self.subject_class:
            raise ValueError("Desire без subject_class — нарушение онтологии")
        if not self.desire_id:
            raise ValueError("Desire без desire_id — нарушение детерминизма")

    # ── Сериализация (§12: WARA — to_dict пишет всё, что from_dict читает) ──
    def to_dict(self) -> Dict[str, Any]:
        return {
            _KEY_DESIRE_ID: self.desire_id,
            _KEY_SUBJECT: self.subject_class,
            _KEY_URGENCY: round(self.urgency, 4),
            _KEY_TARGET_CLASS: self.target_class,
            _KEY_PROVENANCE: [p.to_dict() for p in self.provenance],
            _KEY_BORN_TICK: int(self.born_tick),
            _KEY_LAST_FULFILLED: int(self.last_fulfilled_tick),
            _KEY_WEIGHT: round(self.weight, 4),
            _KEY_LEARNED_FROM: list(self.learned_from),
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Desire":
        return Desire(
            desire_id=d.get(_KEY_DESIRE_ID, ""),
            subject_class=d.get(_KEY_SUBJECT, ""),
            urgency=d.get(_KEY_URGENCY, 0.0),
            target_class=d.get(_KEY_TARGET_CLASS, ""),
            provenance=tuple(
                ProvenanceEntry.from_dict(p) for p in d.get(_KEY_PROVENANCE, [])
            ),
            born_tick=int(d.get(_KEY_BORN_TICK, 0)),
            last_fulfilled_tick=int(d.get(_KEY_LAST_FULFILLED, -1)),
            weight=d.get(_KEY_WEIGHT, 1.0),
            learned_from=tuple(d.get(_KEY_LEARNED_FROM, [])),
        )

    @staticmethod
    def stable_id(subject_class: str) -> str:
        """Детерминированный id: один subject — одно желание на NPC."""
        return f"d:{subject_class}"

    @property
    def dominant_source(self) -> DesireSource:
        """Доминанта причинности (argmax веса). L-M1: остальное не исчезает."""
        if not self.provenance:
            return DesireSource.NEED
        return max(self.provenance, key=lambda p: p.weight).source
