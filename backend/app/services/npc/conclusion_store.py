# backend/app/services/npc/conclusion_store.py
"""
Назначение: BC-1/ADR-O-381 — per-agent RAM-SSOT выводов (ConclusionRecord):
    apply = единственный write-path (диспатч-цель ConclusionGate; caller-guard
    по цензусу), reinforcement при повторной идентичности (union evidence +
    confidence = max), read-API get/get_for, round-trip to_dict/from_dict через
    scene_state["conclusions"] (S193-паттерн: EpistemicStore). Персистенция —
    ВНЕ стора: проекцию в scene_state делает оркестратор; собственная SQLite
    ЗАПРЕЩЕНА (анти-паттерн ExpectationStore).
Зависимости: app.domain.conclusions; sys, logging, typing, enum.
Основные сущности: ConclusionApplyResult, ConclusionStore.
"""

from __future__ import annotations

import logging
import sys
from enum import Enum
from typing import Any, Dict, List, Optional

from app.domain.conclusions import (
    CONCLUSION_SOURCE_DIRECT,
    ConclusionPredicate,
    ConclusionProposal,
    ConclusionRecord,
)

logger = logging.getLogger(__name__)


class ConclusionApplyResult(str, Enum):
    """Результат операции ConclusionStore.apply.

    CREATED — создан новый ConclusionRecord (первое формирование).
    REINFORCED — существующий Conclusion дополнен evidence / обновлён confidence.

    Используется ConclusionGate для решения о публикации CONCLUSION_FORMED:
    событие публикуется только при CREATED (появление нового когнитивного вывода).
    """

    CREATED = "created"
    REINFORCED = "reinforced"


class ConclusionStore:
    """BC-1: хранилище выводов агентов (per-agent RAM).

    Структура: owner_id -> {conclusion_id -> ConclusionRecord}.
    Идентичность записи = conclusion_id() = (owner, subject, predicate,
    object, source) — паттерн MemoryCrystal.crystal_id().

    INV-CONCLUSION-GATE: apply() разрешён ТОЛЬКО ConclusionGate.
    Загрузка персистенции (from_dict) заполняет словарь напрямую,
    минуя apply (легальный писатель найден round-trip-замком).
    """

    _APPLY_ALLOWED_WRITERS = {
        "app.services.memory.conclusion_gate",
    }

    def __init__(self) -> None:
        self._conclusions: Dict[str, Dict[str, ConclusionRecord]] = {}

    # ── WRITE (единственный путь — через гейт) ─────────────────────────

    def apply(
        self, proposal: ConclusionProposal, clamped_confidence: float
    ) -> ConclusionApplyResult:
        """Диспатч-цель ConclusionGate.

        Новая идентичность -> запись -> CREATED.
        Существующая -> reinforcement -> REINFORCED:
        evidence = union, confidence = max(cur, clamped), origin-поля
        (trace_id/causal_parent/formed_tick) НЕ переписываются.
        """
        _caller = sys._getframe(1).f_globals.get("__name__", "")
        if _caller not in self._APPLY_ALLOWED_WRITERS:
            from app.errors import ArchitecturalViolationError

            raise ArchitecturalViolationError(
                f"conclusion_store.apply({proposal.owner_id})",
                _caller,
            )

        record = ConclusionRecord(
            owner_id=proposal.owner_id,
            subject=proposal.subject,
            predicate=proposal.predicate,
            object=proposal.object,
            confidence=max(0.0, min(1.0, clamped_confidence)),
            evidence=tuple(proposal.evidence),
            trace_id=proposal.trace_id,
            causal_parent=proposal.causal_parent,
            source=proposal.source,
            formed_tick=0,
        )
        cid = record.conclusion_id()
        bucket = self._conclusions.setdefault(record.owner_id, {})
        existing = bucket.get(cid)

        if existing is None:
            bucket[cid] = record
            logger.debug(
                f"[CONCLUSION_STORE] formed {cid} conf={record.confidence:.2f} "
                f"evidence={len(record.evidence)}"
            )
            return ConclusionApplyResult.CREATED
        else:
            # Reinforcement: union evidence + max confidence; origin не трогаем.
            merged_evidence = tuple(
                dict.fromkeys(existing.evidence + record.evidence)
            )
            bucket[cid] = ConclusionRecord(
                owner_id=existing.owner_id,
                subject=existing.subject,
                predicate=existing.predicate,
                object=existing.object,
                confidence=max(existing.confidence, record.confidence),
                evidence=merged_evidence,
                trace_id=existing.trace_id,
                causal_parent=existing.causal_parent,
                source=existing.source,
                formed_tick=existing.formed_tick,
            )
            logger.debug(
                f"[CONCLUSION_STORE] reinforced {cid} "
                f"conf={bucket[cid].confidence:.2f} "
                f"evidence={len(merged_evidence)}"
            )
            return ConclusionApplyResult.REINFORCED

    # ── READ ───────────────────────────────────────────────────────────

    def get(
        self, owner_id: str, subject: str, predicate: Any
    ) -> Optional[ConclusionRecord]:
        """Возвращает ConclusionRecord по owner_id, subject и predicate (первый найденный).

        Используется тестами и downstream-слоями для точечной проверки наличия вывода.
        """
        bucket = self._conclusions.get(owner_id)
        if not bucket:
            return None

        # Нормализуем predicate для сравнения (может быть enum или строка)
        target_pred = predicate.value if hasattr(predicate, "value") else str(predicate)

        for record in bucket.values():
            if record.subject == subject and record.predicate.value == target_pred:
                return record
        return None

    def get_for(self, owner_id: str) -> List[ConclusionRecord]:
        """Возвращает все выводы для данного owner_id."""
        bucket = self._conclusions.get(owner_id, {})
        return list(bucket.values())

    def __len__(self) -> int:
        """Возвращает общее количество записей во всех бакетах."""
        return sum(len(bucket) for bucket in self._conclusions.values())

    # ── ROUND-TRIP (S193-паттерн; проекция/восстановление персистенции) ─

    def to_dict(self) -> List[Dict[str, Any]]:
        """Сериализация для scene_state["conclusions"] (оркестраторная
        проекция, Фаза 10 atomic_commit_all)."""
        records: List[Dict[str, Any]] = []
        for bucket in self._conclusions.values():
            for record in bucket.values():
                records.append(
                    {
                        "owner_id": record.owner_id,
                        "subject": record.subject,
                        "predicate": record.predicate.value,
                        "object": record.object,
                        "confidence": record.confidence,
                        "evidence": list(record.evidence),
                        "trace_id": record.trace_id,
                        "causal_parent": record.causal_parent,
                        "source": record.source,
                        "formed_tick": record.formed_tick,
                    }
                )
        return records

    @classmethod
    def from_dict(cls, data: Optional[List[Dict[str, Any]]]) -> "ConclusionStore":
        """Восстановление из scene_state. Заполняет напрямую, минуя apply."""
        store = cls()
        if not data:
            return store
        for item in data:
            try:
                predicate = ConclusionPredicate(item.get("predicate"))
                record = ConclusionRecord(
                    owner_id=str(item.get("owner_id", "")),
                    subject=str(item.get("subject", "")),
                    predicate=predicate,
                    object=str(item.get("object", "")),
                    confidence=max(
                        0.0, min(1.0, float(item.get("confidence", 0.0)))
                    ),
                    evidence=tuple(item.get("evidence") or ()),
                    trace_id=str(item.get("trace_id", "")),
                    causal_parent=str(item.get("causal_parent", "")),
                    source=str(
                        item.get("source", CONCLUSION_SOURCE_DIRECT)
                    ),
                    formed_tick=int(item.get("formed_tick", 0)),
                )
                if not record.owner_id or not record.subject:
                    raise ValueError("пустые owner_id/subject")
                store._conclusions.setdefault(record.owner_id, {})[
                    record.conclusion_id()
                ] = record
            except Exception as e:  # noqa: ENIGMA001
                logger.warning(
                    f"[CONCLUSION_STORE] Failed to deserialize record: {e}"
                )
        return store
