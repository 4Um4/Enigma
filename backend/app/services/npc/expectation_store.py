"""
Назначение: BC-2 — per-agent RAM-SSOT ожиданий (ExpectationRecord). apply = единственный write-path (диспатч-цель expectation_bridge; caller-guard по цензусу), reinforcement при повторной идентичности (confidence = max, origin не переписывается), read-API, round-trip to_dict/from_dict через scene_state["expectations"] (S193-паттерн: EpistemicStore, ConclusionStore). Собственная SQLite ЗАПРЕЩЕНА.
Зависимости: app.domain.expectations; logging, sys, typing, enum.
Основные сущности: ExpectationApplyResult, ContextualExpectationStore.
"""

from __future__ import annotations

import logging
import sys
from enum import Enum
from typing import Any, Dict, List, Optional

from app.domain.expectations import (
    ExpectationPredicate,
    ExpectationRecord,
    ExpectationStatus,
)

logger = logging.getLogger(__name__)


class ExpectationApplyResult(str, Enum):
    """Результат операции ContextualExpectationStore.apply.

    CREATED — новый ExpectationRecord (первое формирование прогноза).
    REINFORCED — существующий прогноз усилен (confidence = max, origin
    сохранён — Master §5: «reinforcement не должен перезаписывать
    происхождение»).
    """

    CREATED = "created"
    REINFORCED = "reinforced"


class ContextualExpectationStore:
    """BC-2: хранилище прогнозов агентов (per-agent RAM).

    Структура: owner_id -> {expectation_id -> ExpectationRecord}.
    Идентичность = expectation_id() — (owner, subject, predicate,
    expected_object, predicted_context, causal_parent_conclusion_id).

    Имя Contextual* — отсекает коллизию с прежним Active Inference Store
    (npc_tick_pipeline.py:466-469, state_applicator.py:794,
    conclusion_store.py:9).

    INV-EXPECTATION-GATE: apply() разрешён ТОЛЬКО expectation_bridge.
    """

    _APPLY_ALLOWED_WRITERS = {
        "app.services.memory.expectation_runtime",
        "app.services.npc.expectation_bridge",
    }

    def __init__(self) -> None:
        self._expectations: Dict[str, Dict[str, ExpectationRecord]] = {}

    def apply(self, record: ExpectationRecord) -> ExpectationApplyResult:
        """Диспатч-цель expectation_bridge / runtime wrapper.

        Новая идентичность → CREATED. Существующая → REINFORCED:
        confidence = max(cur, new); origin-поля (formed_tick,
        causal_parent_conclusion_id, predicted_context) не переписываются.
        """
        _caller = sys._getframe(1).f_globals.get("__name__", "")
        if _caller not in self._APPLY_ALLOWED_WRITERS:
            from app.errors import ArchitecturalViolationError

            raise ArchitecturalViolationError(
                f"expectation_store.apply({record.owner_id})", _caller
            )

        eid = record.expectation_id()
        bucket = self._expectations.setdefault(record.owner_id, {})
        existing = bucket.get(eid)

        if existing is None:
            bucket[eid] = record
            logger.debug(
                f"[EXPECTATION_STORE] formed {eid} "
                f"pred={record.predicate.value} conf={record.confidence:.2f}"
            )
            return ExpectationApplyResult.CREATED

        bucket[eid] = ExpectationRecord(
            owner_id=existing.owner_id,
            subject=existing.subject,
            predicate=existing.predicate,
            expected_object=existing.expected_object,
            confidence=max(existing.confidence, record.confidence),
            formed_tick=existing.formed_tick,
            causal_parent_conclusion_id=existing.causal_parent_conclusion_id,
            predicted_context=existing.predicted_context,
            status=existing.status,
        )
        logger.debug(
            f"[EXPECTATION_STORE] reinforced {eid} "
            f"conf={bucket[eid].confidence:.2f}"
        )
        return ExpectationApplyResult.REINFORCED

    def get_all(
        self,
        owner_id: str,
        subject: str,
        predicate: Optional[ExpectationPredicate] = None,
    ) -> List[ExpectationRecord]:
        """Все прогнозы, удовлетворяющие (owner_id, subject[, predicate]).

        Master §5: «Если несколько записей имеют одинаковые owner_id,
        subject и predicate, API не должен произвольно возвращать одну
        из них» — возвращаем список, а не первый найденный.
        """
        bucket = self._expectations.get(owner_id)
        if not bucket:
            return []
        target_pred = predicate.value if predicate else None
        results: List[ExpectationRecord] = []
        for record in bucket.values():
            if record.subject != subject:
                continue
            if target_pred is not None and record.predicate.value != target_pred:
                continue
            results.append(record)
        return results

    def get_by_id(self, owner_id: str, expectation_id: str) -> Optional[ExpectationRecord]:
        """Точная идентичность — избегает неоднозначности."""
        return self._expectations.get(owner_id, {}).get(expectation_id)

    def get_for(self, owner_id: str) -> List[ExpectationRecord]:
        bucket = self._expectations.get(owner_id, {})
        return list(bucket.values())

    def get_by_parent(self, causal_parent_conclusion_id: str) -> List[ExpectationRecord]:
        """Все прогнозы, порождённые конкретным Conclusion (Master §5)."""
        results: List[ExpectationRecord] = []
        for bucket in self._expectations.values():
            for record in bucket.values():
                if record.causal_parent_conclusion_id == causal_parent_conclusion_id:
                    results.append(record)
        return results

    def __len__(self) -> int:
        return sum(len(bucket) for bucket in self._expectations.values())

    def to_dict(self) -> List[Dict[str, Any]]:
        """Сериализация для scene_state["expectations"]."""
        records: List[Dict[str, Any]] = []
        for bucket in self._expectations.values():
            for record in bucket.values():
                records.append(
                    {
                        "owner_id": record.owner_id,
                        "subject": record.subject,
                        "predicate": record.predicate.value,
                        "expected_object": record.expected_object,
                        "confidence": record.confidence,
                        "formed_tick": record.formed_tick,
                        "causal_parent_conclusion_id": record.causal_parent_conclusion_id,
                        "predicted_context": record.predicted_context,
                        "status": record.status.value,
                    }
                )
        return records

    @classmethod
    def from_dict(cls, data: Optional[List[Dict[str, Any]]]) -> "ContextualExpectationStore":
        """Восстановление из scene_state. Заполняет напрямую, минуя apply."""
        store = cls()
        if not data:
            return store
        for item in data:
            try:
                record = ExpectationRecord(
                    owner_id=str(item.get("owner_id", "")),
                    subject=str(item.get("subject", "")),
                    predicate=ExpectationPredicate(item.get("predicate")),
                    expected_object=str(item.get("expected_object", "")),
                    confidence=max(0.0, min(1.0, float(item.get("confidence", 0.0)))),
                    formed_tick=int(item.get("formed_tick", 0)),
                    causal_parent_conclusion_id=str(
                        item.get("causal_parent_conclusion_id", "")
                    ),
                    predicted_context=str(item.get("predicted_context", "")),
                    status=ExpectationStatus(
                        item.get("status", ExpectationStatus.ACTIVE.value)
                    ),
                )
                if not record.owner_id or not record.subject:
                    raise ValueError("пустые owner_id/subject")
                store._expectations.setdefault(record.owner_id, {})[
                    record.expectation_id()
                ] = record
            except Exception as e:  # noqa: ENIGMA001
                logger.warning(
                    f"[EXPECTATION_STORE] Failed to deserialize record: {e}"
                )
        return store