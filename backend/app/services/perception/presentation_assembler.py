# backend/app/services/perception/presentation_assembler.py
"""
Файл: backend/app/services/perception/presentation_assembler.py
Назначение: Собирает ObservedFactsBundle из ObservedFact для DMContractBuilder.
Зависимости: backend.app.domain.observed_facts, backend.app.domain.observed_fact
"""

import logging
from typing import List

from app.domain.observed_fact import ObservedFact
from app.domain.observed_facts import ObservedFactEntry, ObservedFactsBundle

logger = logging.getLogger(__name__)


class PresentationAssembler:
    """
    Собирает данные из Эпистемологии для потребителей (DM).
    ЗАПРЕТ: Не читает Reality, ManifestationState (Инвариант 3).
    """

    def assemble_facts_bundle(self, facts: List[ObservedFact]) -> ObservedFactsBundle:
        entries = []
        by_target = {}

        for fact in facts:
            entry = ObservedFactEntry(
                target_id=fact.target_id,
                fact_name=fact.fact_name,
                value=fact.perceived_value
                if hasattr(fact, "perceived_value")
                else fact.value,
                confidence=fact.confidence,
                via=fact.observed_via,
            )
            entries.append(entry)

            if fact.target_id not in by_target:
                by_target[fact.target_id] = []
            by_target[fact.target_id].append(entry)

        return ObservedFactsBundle(facts=entries, by_target=by_target)
