"""
Назначение: BC-2 — pure reducer Conclusion → Expectation + builder ExpectationContext (snapshot доменных сигналов). Reducer не читает Store/SQLite/EventBus/глобального состояния. MVP: сигналы физической силы и прошлой агрессии отсутствуют — context builder возвращает пустой ExpectationContext, reducer корректно производит []. При разблокировке сигналов меняется только build_expectation_context.
Зависимости: app.domain.conclusions, app.domain.expectations; logging, typing.
Основные сущности: PHYSICAL_SUPERIORITY_RATIO, build_expectation_context, conclusion_to_expectations.
"""

from __future__ import annotations

import logging
from typing import Any, List

from app.domain.conclusions import ConclusionPredicate, ConclusionRecord
from app.domain.expectations import (
    ExpectationContext,
    ExpectationPredicate,
    ExpectationRecord,
)

logger = logging.getLogger(__name__)

# Калибруемая policy MVP (прецедент THREAT_CONCLUSION_THRESHOLD).
# Порог 1.2 — консервативный: субъект должен быть заметно сильнее
# owner'а, а не на уровне. Magic number выделен в модульную константу.
PHYSICAL_SUPERIORITY_RATIO: float = 1.2

# MVP: не больше 5 ожиданий на один Conclusion (Master §2 HANDOFF).
# Не зашито в схему DTO — параметр bridge'а, читается из config при
# интеграции.
DEFAULT_MAX_EXPECTATIONS_PER_CONCLUSION: int = 5


def build_expectation_context(
    conclusion: ConclusionRecord,
    ctx: Any,
    orchestrator: Any,
) -> ExpectationContext:
    """Сборка контекста сигналов для bridge. MVP STUB — блокер BC2-2.

    Сигналы, требуемые для двух утверждённых предикатов, ОТСУТСТВУЮТ
    в текущей кодовой базе (см. blocker report BC2-2 §2):

    - subject_physical_strength / owner_physical_strength:
        NPCState.body_state / psyche не содержат полей физической силы
        (grep strength|physique|mass|agility|constitution|body_mass|size —
        0 совпадений). Требуется обогащение NPCState.

    - past_aggression_event_ids:
        L1Chronicle.TraitDriftEvent.event_type — free-string, default
        "generic", provenance-only (ADR-O-305A: запрещён в формулах).
        Резолв event_id из ConclusionRecord.evidence невозможен.
        Требуется либо enum агрессии в L1, либо прямой epistemic predicate.

    Master §4 HANDOFF: «не придумывать эвристику». Возвращаем пустой
    контекст — reducer корректно производит [] (no-signal → no-expectation).

    При разблокировке — расширить сборку здесь, НЕ трогая reducer.
    """
    # TODO(BC2-2 BLOCKER): populate subject/owner physical strength
    #   from ctx.npc_states when NPCState.body_state gains such fields.
    # TODO(BC2-2 BLOCKER): populate past_aggression_event_ids
    #   when L1Chronicle exposes fixed taxonomy of aggression events.
    return ExpectationContext()


def conclusion_to_expectations(
    conclusion: ConclusionRecord,
    context: ExpectationContext,
    current_tick: int,
    max_count: int = DEFAULT_MAX_EXPECTATIONS_PER_CONCLUSION,
) -> List[ExpectationRecord]:
    """BC-2: чистое преобразование Conclusion → Expectation.

    Гарантии:
    - Никаких скрытых чтений Store / SQLite / EventBus / глобального
      состояния. Контекст передан явно.
    - NO-VACUUM: predicate != IS_DANGEROUS → [] (Master §2).
    - NO-SIGNAL-NO-EXPECTATION: отсутствие сигнала → [] (Master §2).
    - Одинаковый вход → одинаковый выход (pure).
    - Максимум max_count записей.
    - Каждое ожидание сохраняет causal_parent_conclusion_id.

    TEMPORARY — MVP confidence inheritance (Master §8):
        confidence = conclusion.confidence без демпфера. НЕ утверждённый
        игровой закон. Review trigger: BC-2 closeout, до BC-3 integration.
    """
    if conclusion.predicate != ConclusionPredicate.IS_DANGEROUS:
        return []

    parent_id = conclusion.conclusion_id()
    results: List[ExpectationRecord] = []

    # MAY_CAUSE_PHYSICAL_HARM:
    # Требует ОБА значения физической силы + superiority ratio.
    # Одно отсутствует → нет сигнала → пропуск (не создавать автоматически
    # из факта IS_DANGEROUS — Master §2 HANDOFF).
    if (
        context.subject_physical_strength is not None
        and context.owner_physical_strength is not None
        and context.owner_physical_strength > 0.0
        and context.subject_physical_strength
        > context.owner_physical_strength * PHYSICAL_SUPERIORITY_RATIO
    ):
        results.append(
            ExpectationRecord(
                owner_id=conclusion.owner_id,
                subject=conclusion.subject,
                predicate=ExpectationPredicate.MAY_CAUSE_PHYSICAL_HARM,
                expected_object=conclusion.object,
                confidence=conclusion.confidence,  # TEMPORARY MVP inheritance
                formed_tick=current_tick,
                causal_parent_conclusion_id=parent_id,
                predicted_context="",
            )
        )

    # MAY_USE_FORCE_IN_CONFLICT:
    # Требует непустой past_aggression_event_ids (сигнал прошлых актов).
    # Пусто → нет сигнала → пропуск (не выводить из IS_DANGEROUS или
    # confidence — Master §2 HANDOFF: «не выводить намерения из
    # возможностей и возможности из намерений»).
    if context.past_aggression_event_ids:
        results.append(
            ExpectationRecord(
                owner_id=conclusion.owner_id,
                subject=conclusion.subject,
                predicate=ExpectationPredicate.MAY_USE_FORCE_IN_CONFLICT,
                expected_object=conclusion.object,
                confidence=conclusion.confidence,  # TEMPORARY MVP inheritance
                formed_tick=current_tick,
                causal_parent_conclusion_id=parent_id,
                predicted_context="",
            )
        )

    return results[:max_count]