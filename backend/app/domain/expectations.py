"""
Назначение: BC-2/ADR-O-XXX — доменные контракты Expectation-слоя: закрытый predicate-реестр, статусы жизненного цикла, ExpectationRecord (SSOT-запись прогноза), ExpectationContext (snapshot сигналов для bridge).
Зависимости: dataclasses, enum, typing (domain-purity: только stdlib).
Основные сущности: ExpectationPredicate, ExpectationStatus, ExpectationRecord, ExpectationContext.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple


class ExpectationPredicate(Enum):
    """BC-2: ЗАКРЫТЫЙ predicate-реестр (прецедент ADR-O-349).

    MVP — два предиката (Master §2 HANDOFF):
    - MAY_CAUSE_PHYSICAL_HARM — оценка физической способности субъекта
      причинить вред; НЕ предполагает намерения, агрессии, готовности.
    - MAY_USE_FORCE_IN_CONFLICT — условный прогноз: если возникнет
      конфликт, субъект может применить силу; НЕ означает готовности
      начать конфликт.

    Расширение — только мини-ADR. MAY_TAKE_RESOURCES, MAY_COMPETE_FOR_POSITION
    не входят в MVP (Master §2: семантика не утверждена).
    """

    MAY_CAUSE_PHYSICAL_HARM = "may_cause_physical_harm"
    MAY_USE_FORCE_IN_CONFLICT = "may_use_force_in_conflict"


class ExpectationStatus(Enum):
    """APPROVED Master §3: расширяемый жизненный цикл.

    BC-2 MVP: только ACTIVE. Переходы состояний не реализуются сейчас,
    но DTO/Store не исключают их появление.
    """

    ACTIVE = "active"
    CONFIRMED = "confirmed"
    REFUTED = "refuted"
    PARTIALLY_CONFIRMED = "partially_confirmed"
    REVISED = "revised"
    STALE = "stale"
    FORGOTTEN = "forgotten"


@dataclass(frozen=True)
class ExpectationRecord:
    """BC-2: запись-прогноз в ContextualExpectationStore.

    Per-agent RAM; round-trip через scene_state["expectations"] → Фаза 10
    atomic_commit_all (S193-паттерн). Собственная SQLite ЗАПРЕЩЕНА
    (Master §5).

    TEMPORARY — MVP confidence inheritance (Master §8):
        confidence Expectation = conclusion.confidence без изменения
        значения. НЕ утверждённый игровой закон. Review trigger:
        BC-2 closeout, ДО интеграции с BC-3.

    Идентичность = (owner, subject, predicate, expected_object,
    predicted_context, causal_parent_conclusion_id) — см. expectation_id().
    Один первичный причинный родитель на запись (Master §3).
    """

    owner_id: str
    subject: str
    predicate: ExpectationPredicate
    expected_object: str

    confidence: float = 0.5
    formed_tick: int = 0
    causal_parent_conclusion_id: str = ""

    predicted_context: str = ""
    status: ExpectationStatus = ExpectationStatus.ACTIVE

    def expectation_id(self) -> str:
        """Детерминированная идентичность прогноза.

        Компоненты: владелец, субъект, предикат, объект, контекст,
        первичный родительский Conclusion. Одинаковые входы из разных
        Conclusion-источников не схлопываются (входят через
        causal_parent_conclusion_id).
        """
        return (
            f"{self.owner_id}:{self.subject}:"
            f"{self.predicate.value}:{self.expected_object}:"
            f"{self.predicted_context}:{self.causal_parent_conclusion_id}"
        )


@dataclass(frozen=True)
class ExpectationContext:
    """Master §4: явный snapshot доменных данных для bridge.

    Не источник истины, не Store — только значения, переданные bridge'ом.

    BC-2 MVP: все поля None/() — сигналы физической силы и прошлой
    агрессии отсутствуют в текущей кодовой базе (см. blocker report
    BC2-2). Bridge корректно производит [] при отсутствии сигналов
    (Master §4: «не подменять выдумкой»).

    При разблокировке (см. blocker report §10) — заполнять здесь,
    без изменения DTO ExpectationRecord и контракта Store.
    """

    # MAY_CAUSE_PHYSICAL_HARM: физическая сила субъекта и владельца.
    # Требуется: body_state.physical_strength (или эквивалент) в NPCState.
    subject_physical_strength: Optional[float] = None
    owner_physical_strength: Optional[float] = None

    # MAY_USE_FORCE_IN_CONFLICT: прошлые акты агрессии субъекта.
    # Требуется: L1Chronicle taxonomy с фиксированными event_type значениями
    # для агрессии (attacked/aggression) ИЛИ прямой epistemic predicate.
    past_aggression_event_ids: Tuple[str, ...] = ()