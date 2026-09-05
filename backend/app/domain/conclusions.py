# backend/app/domain/conclusions.py
"""
Назначение: BC-1/ADR-O-381 — доменные контракты Conclusion-слоя: закрытый
    predicate-реестр, ConclusionProposal (сырьё вывода, НЕ команда) и
    ConclusionRecord (SSOT-запись триплета). Машино-пригодные выводы, не
    фразы. Семантически НЕ наследует MemoryCrystal (memory-домен E1.2):
    заимствуются только структурные дисциплины (frozen-контракт,
    tuple-evidence, кламп confidence, идентичность = триплет + происхождение).
Зависимости: dataclasses, enum, typing (domain-purity: только stdlib).
Основные сущности: ConclusionPredicate, ConclusionProposal, ConclusionRecord.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Tuple


class ConclusionPredicate(Enum):
    """ADR-O-381: ЗАКРЫТЫЙ predicate-реестр.

    Старт — ОДИН предикат IS_DANGEROUS: минимальный вертикальный срез
    (вердикт владельца: BC-1 доказывает механизм Experience→Conclusion,
    не онтологию). Расширение реестра — только мини-ADR (прецедент
    закрытых реестров, класс ADR-O-349).
    """

    IS_DANGEROUS = "is_dangerous"


# Канал получения знания для вывода. BC-1 реализует только прямой опыт;
# TESTIMONY зарезервирован за BC-5 (передача вывода) и в этом срезе
# запрещён (табу ADR-O-381 L14.6).
CONCLUSION_SOURCE_DIRECT = "direct_experience"
CONCLUSION_SOURCE_TESTIMONY = "testimony"


@dataclass(frozen=True)
class ConclusionProposal:
    """BC-1: предложение вывода — сырьё, НЕ команда (паттерн StateDeltaProposal).

    ConclusionEngine (pure) генерирует; ConclusionGate валидирует
    (predicate-реестр → кламп confidence [0..1] → идемпотентность по
    (trace_id, subject, predicate)); ConclusionStore.apply — единственный
    write-path. Генератор вывода не имеет права писать в conclusion-слой
    напрямую (мембрана класса DeltaGate E2.0; INV-CONCLUSION-GATE).

    trace_id — паттерн E1.0 (content_reference:owner[:from:source]);
    causal_parent — event.id источника опыта: один event.id → один trace →
    <=1 conclusion-дельты на (subject, predicate) — перенос
    AG1-INV-TRACE-ONCE.
    """

    owner_id: str              # кто сделал вывод (= owner опыта, ExperienceTrace.owner_id)
    subject: str               # о ком/о чём вывод (обычно actor_id трейса)
    predicate: ConclusionPredicate
    object: str                # объект суждения; "" для унарных предикатов (IS_DANGEROUS)
    confidence: float          # предложенная уверенность; клампится гейтом [0..1]
    evidence: Tuple[str, ...]  # event_ids → L1-адресуемость (append-only)
    trace_id: str              # идентичность трейса источника (E1.0-паттерн)
    causal_parent: str         # event.id источника (AG1-INV-TRACE-ONCE)

    source: str = CONCLUSION_SOURCE_DIRECT
    rationale: str = ""        # лог/аудит, не для игры (паттерн StateDeltaProposal.rationale)


@dataclass(frozen=True)
class ConclusionRecord:
    """BC-1: запись-вывод в ConclusionStore (per-agent RAM; round-trip через
    scene_state["conclusions"] → Фаза 10 atomic_commit_all, S193-паттерн).

    Идентичность = (owner, subject, predicate, object, source) — см.
    conclusion_id(). DELETE запрещён (append-only); reinforcement (рост
    confidence, union evidence) — политика стора, не записи. НЕТ полей
    MemoryCrystal retrieval_strength / last_reinforced / times_recalled:
    recall-механика не входит в dormant BC-1 (вердикт владельца — только
    необходимое BC-1; semantic-слой поверх EXPERIENCE_DELTA_COMMITTED,
    не вторая память).
    """

    owner_id: str              # чей вывод
    subject: str               # о ком/о чём вывод
    predicate: ConclusionPredicate
    object: str                # "" для унарных предикатов

    confidence: float = 0.5                    # [0..1]; уверенность != truth
    evidence: Tuple[str, ...] = ()             # event_ids → L1
    trace_id: str = ""                         # origin-трейс (первое формирование)
    causal_parent: str = ""                    # event.id источника опыта
    source: str = CONCLUSION_SOURCE_DIRECT
    formed_tick: int = 0                       # тик формирования (якорь §14); ФОРК: при вето владельца — удалить одной строкой

    def conclusion_id(self) -> str:
        """Идентичность вывода: триплет + владелец + канал (без confidence).

        Паттерн MemoryCrystal.crystal_id() (урок 9.6): одинаковые триплеты
        из разных каналов (DIRECT vs TESTIMONY) не схлопываются.
        """
        return (
            f"{self.owner_id}:{self.subject}:"
            f"{self.predicate.value}:{self.object}:{self.source}"
        )
