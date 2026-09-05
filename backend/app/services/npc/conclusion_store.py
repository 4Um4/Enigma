# backend/app/services/npc/conclusion_store.py
"""
Назначение: BC-1/ADR-O-381 — per-agent RAM-SSOT выводов (ConclusionRecord):
    apply = единственный write-path (диспатч-цель ConclusionGate; caller-guard
    по цензусу), reinforcement при повторной идентичности (union evidence +
    confidence = max), read-API get_for, round-trip to_dict/from_dict через
    scene_state["conclusions"] (S193-паттерн: EpistemicStore). Персистенция —
    ВНЕ стора: проекцию в scene_state делает оркестратор (tick_orchestrator:691-
    паттерн); собственная SQLite ЗАПРЕЩЕНА (анти-паттерн ExpectationStore).
Зависимости: app.domain.conclusions; sys, logging, typing.
Основные сущности: ConclusionStore.
"""

from __future__ import annotations

import logging
import sys
from typing import Dict, List, Optional, Tuple

from app.domain.conclusions import (
    CONCLUSION_SOURCE_DIRECT,
    ConclusionPredicate,
    ConclusionProposal,
    ConclusionRecord,
)

logger = logging.getLogger(__name__)


class ConclusionStore:
    """BC-1: хранилище выводов агентов (per-agent RAM).

    Структура: owner_id -> {conclusion_id -> ConclusionRecord}.
    Идентичность записи = conclusion_id() = (owner, subject, predicate,
    object, source) — паттерн MemoryCrystal.crystal_id() (урок 9.6:
    одинаковые триплеты из разных каналов не схлопываются).

    INV-CONCLUSION-GATE: apply() разрешён ТОЛЬКО ConclusionGate
    (caller-цензус; прецеденты BeliefState-guard S243 / PK-guard).
    Загрузка персистенции (from_dict) заполняет словарь напрямую,
    минуя apply, — прецедент npc_loader/BeliefState: легальный писатель
    найден round-trip-замком.
    ВАЖНО: bc1_conclusion_test в цензус НЕ вносить — D-группа
    экзамена обязана получать ArchitecturalViolationError (замок).
    """

    _APPLY_ALLOWED_WRITERS = {
        "app.services.memory.conclusion_gate",
    }

    def __init__(self) -> None:
        self._conclusions: Dict[str, Dict[str, ConclusionRecord]] = {}

    # ── WRITE (единственный путь — через гейт) ─────────────────────────

    def apply(self, proposal: ConclusionProposal, clamped_confidence: float) -> bool:
        """Диспатч-цель ConclusionGate (ConsumerDispatch-сигнатура).

        Новая идентичность -> запись. Существующая -> reinforcement:
        evidence = union, confidence = max(cur, clamped), origin-поля
        (trace_id/causal_parent/formed_tick) НЕ переписываются — это
        происхождение первого формирования, не текущее состояние.

        confidence = max (не аддитивный рост) — анти-инфляция уверенности;
        пороговое подкрепление (повторяемость -> усиление) = BC-4,
        вне BC-1-скоупа. DELETE запрещён (append-only).

        formed_tick: BC-1-срез кладёт 0 — тик недоступен в мембране без
        расширения proposal (сигнатура диспатча зафиксирована F2б);
        retrofit-заполнение — решение владельца (см. V-FT досье).
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
        return True

    # ── READ (BC-2/сценарий; read-only) ────────────────────────────────

    def get_for(self, owner_id: str) -> Tuple[ConclusionRecord, ...]:
        """Все выводы owner'а (frozen-записи, кортеж наружу)."""
        return tuple(self._conclusions.get(owner_id, {}).values())

    def get(
        self, owner_id: str, subject: str, predicate: ConclusionPredicate
    ) -> Optional[ConclusionRecord]:
        """Точечный read по (owner, subject, predicate) — параллель
        EpistemicStore.get: agent+proposition. Возвращает запись или None."""
        for record in self._conclusions.get(owner_id, {}).values():
            if record.subject == subject and record.predicate == predicate:
                return record
        return None

    def __len__(self) -> int:
        return sum(len(b) for b in self._conclusions.values())

    # ── ROUND-TRIP (S193-паттерн; проекция/восстановление персистенции) ─

    def to_dict(self) -> List[Dict[str, object]]:
        """Сериализация для scene_state["conclusions"] (оркестраторная
        проекция, Фаза 10 atomic_commit_all)."""
        records: List[Dict[str, object]] = []
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
    def from_dict(cls, data: Optional[List[Dict[str, object]]]) -> "ConclusionStore":
        """Восстановление из scene_state (прецедент EpistemicStore.from_dict:
        невалидная запись -> warning + skip, сцена жива). Заполняет напрямую,
        минуя apply (цензус apply — только гейт)."""
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
                # прецедент epistemic_store.py:88-89 — skip + warning,
                # загрузчик не убивает сцену (L4: отказ наблюдаем в логе)
                logger.warning(
                    f"[CONCLUSION_STORE] Failed to deserialize record: {e}"
                )
        return store
