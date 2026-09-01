"""
Назначение: E1.0 контракта EMRL — единица интерпретации воспринятого события; вычисляемая проекция над EventMemory, не SSOT; provenance первого класса (source ≠ actor допустим для testimony)
Зависимости: dataclasses
Основные сущности: ExperienceTrace, TraceSource
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple


class TraceSource(str, Enum):
    """Происхождение опыта — определяет доверие и наследование."""
    PERCEPTION = "perception"      # NPC воспринял сам (услышал/увидел)
    TESTIMONY = "testimony"        # услышал от другого NPC (source_id обязателен)
    INTROSPECTION = "introspection"  # собственное действие/состояние


@dataclass(frozen=True)
class ExperienceTrace:
    """EMRL E1.0: интерпретация воспринятого события конкретным NPC.

    Не SSOT: первична EventMemory (content_reference); трейс — проекция
    интерпретации. Дельты потребители применяют сами, по своим клампам,
    гейтуясь relevance-полями (не суммируются, не являются 'валютой').

    provenance: actor — кто совершил событие; owner — кто пережил опыт;
    source — откуда owner знает (PERCEPTION: actor; TESTIMONY: рассказчик).
    """

    # Участники
    actor_id: str                    # кто совершил событие
    owner_id: str                    # чей опыт (интерпретатор)
    source_id: str                   # откуда owner знает (см. TraceSource)
    source_type: TraceSource

    # Ссылка на эпизод — идемпотентность по (content_reference, owner_id)
    content_reference: str           # EventMemory.id (mem_id)

    # Сигналы переживания — ПРОЕКЦИИ, заполняются резолвером E2.
    # E1: остаются дефолтами; diagnostic resolver может заполнять
    # с пометкой diagnostic=True (не production-контракт).
    meaning: Optional[str] = None
    valence: float = 0.0             # [-1, +1]
    arousal: float = 0.0             # [0, 1]
    novelty: float = 0.0             # [0, 1]

    # Релевантности по внутренним системам — гейты дельт, не суммы
    personal_relevance: float = 0.0
    social_relevance: float = 0.0
    identity_relevance: float = 0.0
    belief_relevance: float = 0.0

    # Доверие
    confidence: float = 0.5          # субъективная уверенность owner'а
    retrieval_strength: float = 0.5  # доступность (растёт от припоминаний,
    #                                 # НЕ от повторных припоминаний того же
    #                                 # источника — см. E1.2 замок)

    # Метаданные
    timestamp: int = 0
    diagnostic: bool = False         # True = заполнен диагност. резолвером

    # Аппликаторы дельт (idempotency): перечень уже применённых дельт
    applied_consumers: Tuple[str, ...] = ()

    def trace_id(self) -> str:
        """Идентичность трейса: эпизод + владелец (+ источник при testimony)."""
        base = f"{self.content_reference}:{self.owner_id}"
        if self.source_type == TraceSource.TESTIMONY:
            base += f":from:{self.source_id}"
        return base