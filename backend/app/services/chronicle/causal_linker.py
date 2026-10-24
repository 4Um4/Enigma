"""S366 — CausalLinker.

Ядро S366. Три ответственности:
  (a) validate(doc) — проверка существующих causes (origin_ref в entry_id текущего документа,
      roadmap §284). Существующий валидатор chronicle_store.py:282-284 допускает white_spot_id
      (backward compat) — здесь это репортится как VALIDATION_WARNING.
  (b) detect_candidates(doc) — детерминированная детекция (СЛОЙ 3):
      TEMPORAL_ORDER + TARGET_HINT_MATCH. НЕ проставляет causes.
  (c) link(doc) — объединение validate + detect + idempotency.

НЕ мутирует ChronicleDocument (только читает, возвращает LinkResult).
Endpoints сохраняют изменения через ChronicleStore.

ТРИ ЗАПРЕТА (вердикт Мастера §1):
1. TEMPORAL_ORDER — детекция, не проставление.
2. ACCEPT — НЕ создаёт NpcCausalBelief.
3. MISTAKEN — НЕ выводится из отсутствия CauseRef.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from app.domain.chronicle import (
    CandidateBasis,
    CandidateStatus,
    CauseCandidate,
    CauseKind,
    ChronicleDocument,
    ChronicleEntry,
    EntryKind,
    EntryProvenance,
    make_candidate_id,
)

logger = logging.getLogger(__name__)


# ТЕХНИЧЕСКИЕ настройки детектора (НЕ игровые правила — veridict Master §4):
# Лимит Δ возраста для TEMPORAL_ORDER — ограничитель выборки, не свойство причинности.
DETECTION_MAX_AGE_DELTA_YEARS = 30
# Лимит выдачи кандидатов на один effect — для управляемости (без комбинаторного взрыва).
DETECTION_MAX_CANDIDATES_PER_EFFECT = 5


@dataclass(frozen=True)
class ValidationError:
    """Структурированная ошибка валидации для отображения автору."""
    entry_id: str
    error_code: str  # INV-CANON-CAUSE-REF | VALIDATION_WARNING | INV-CANON-BELIEF-REF
    message: str


@dataclass(frozen=True)
class LinkResult:
    """Результат link-causes: валидация + детекция + idempotency-статус."""
    validation_errors: Tuple[ValidationError, ...] = ()
    new_candidates: Tuple[CauseCandidate, ...] = ()
    existing_candidates: Tuple[CauseCandidate, ...] = ()
    truncated: bool = False
    truncation_reason: str = ""
    stats: Dict[str, int] = field(default_factory=dict)


class CausalLinker:
    """Ядро S366. Чистые функции, без состояния."""

    def validate(self, doc: ChronicleDocument) -> List[ValidationError]:
        """(a) Проверка существующих causes.
        - origin_ref должен быть в entry_ids текущего документа (roadmap §284).
        - Если origin_ref в white_spot_id — VALIDATION_WARNING (store допускает, roadmap §284 — нет).
        - Если origin_ref ни там ни там — INV-CANON-CAUSE-REF (фиктивный UUID / другой документ).
        - npc_beliefs и cause_candidates уже валидируются в store (dangling).
        """
        errors: List[ValidationError] = []
        entry_ids = {e.entry_id for e in doc.entries}
        ws_ids = {ws.white_spot_id for ws in doc.white_spots}

        for e in doc.entries:
            for c in e.causes:
                if c.origin_ref is None:
                    continue  # UNKNOWN — легальный ответ автора (CauseKind.UNKNOWN)
                if c.origin_ref in entry_ids:
                    continue  # OK — entry_id в текущем документе
                if c.origin_ref in ws_ids:
                    # Backward compat: store допускает, roadmap §284 — нет → WARNING
                    errors.append(ValidationError(
                        entry_id=e.entry_id,
                        error_code="VALIDATION_WARNING",
                        message=(
                            f"origin_ref '{c.origin_ref}' указывает на white_spot_id — "
                            f"roadmap §284 требует entry_id-only (mini-ADR v6 §3)"
                        ),
                    ))
                else:
                    # INV-CANON-CAUSE-REF — фиктивный UUID или entry_id из другого документа
                    errors.append(ValidationError(
                        entry_id=e.entry_id,
                        error_code="INV-CANON-CAUSE-REF",
                        message=(
                            f"origin_ref '{c.origin_ref}' не найден ни в entry_id, "
                            f"ни в white_spot_id текущего документа"
                        ),
                    ))
        return errors

    def detect_candidates(self, doc: ChronicleDocument) -> Tuple[CauseCandidate, ...]:
        """(b) Детерминированная детекция кандидатов. Два basis:
        - TEMPORAL_ORDER: EVENT с historical_age=N → ищем EVENT с M<N
          (life-bounded DETECTION_MAX_AGE_DELTA_YEARS=30 — техническая настройка).
        - TARGET_HINT_MATCH: EFFECT с target_hint → ищем RELATIONSHIP с тем же target_hint.

        НЕ проставляет causes. Только детекция (СЛОЙ 3).
        Idempotency: candidate_id детерминирован (effect+candidate+basis) — повторная детекция
        даёт тот же набор (см. LinkResult.new_candidates в link()).
        """
        candidates: List[CauseCandidate] = []

        # === TEMPORAL_ORDER ===
        events = [e for e in doc.entries
                  if e.kind is EntryKind.EVENT and e.historical_age is not None]
        events_sorted = sorted(events, key=lambda x: (x.historical_age, x.entry_id))

        for effect in events:
            n = effect.historical_age
            if n is None:
                continue
            cands_for_effect: List[CauseCandidate] = []
            for cand in events_sorted:
                if cand.entry_id == effect.entry_id:
                    continue
                m = cand.historical_age
                if m is None or not (0 <= m < n):
                    continue
                if (n - m) > DETECTION_MAX_AGE_DELTA_YEARS:
                    continue
                cands_for_effect.append(CauseCandidate(
                    candidate_id=make_candidate_id(
                        effect.entry_id, cand.entry_id, CandidateBasis.TEMPORAL_ORDER
                    ),
                    effect_entry_id=effect.entry_id,
                    candidate_entry_id=cand.entry_id,
                    candidate_kind=CauseKind.EVENT,
                    basis=CandidateBasis.TEMPORAL_ORDER,
                    rationale=(
                        f"EVENT {cand.entry_id} с historical_age={m} предшествует "
                        f"EVENT {effect.entry_id} с historical_age={n}. "
                        f"Хронология — НЕ причина (запрет 1, §1 Мастера). "
                        f"Δ={n-m} лет ≤ {DETECTION_MAX_AGE_DELTA_YEARS} "
                        f"(техническая настройка детектора, не игровое правило)."
                    ),
                ))
            # Детерминированный отбор: сначала по Δ возраста (минимальный), потом по entry_id
            cands_for_effect.sort(
                key=lambda c: (n - self._entry_age(doc, c.candidate_entry_id), c.candidate_entry_id)
            )
            candidates.extend(cands_for_effect[:DETECTION_MAX_CANDIDATES_PER_EFFECT])

        # === TARGET_HINT_MATCH ===
        effects = [e for e in doc.entries if e.kind is EntryKind.EFFECT]
        relationships = [e for e in doc.entries if e.kind is EntryKind.RELATIONSHIP]

        for effect in effects:
            target_hint = (effect.payload or {}).get("target_hint")
            if not target_hint:
                continue
            cands_for_effect = []
            for cand in relationships:
                cand_target = (cand.payload or {}).get("target_hint")
                if not cand_target or cand_target != target_hint:
                    continue
                cands_for_effect.append(CauseCandidate(
                    candidate_id=make_candidate_id(
                        effect.entry_id, cand.entry_id, CandidateBasis.TARGET_HINT_MATCH
                    ),
                    effect_entry_id=effect.entry_id,
                    candidate_entry_id=cand.entry_id,
                    candidate_kind=CauseKind.RELATIONSHIP,
                    basis=CandidateBasis.TARGET_HINT_MATCH,
                    rationale=(
                        f"EFFECT {effect.entry_id} и RELATIONSHIP {cand.entry_id} "
                        f"имеют общий target_hint='{target_hint}'. "
                        f"Совпадение имени — НЕ причина (veridict Master §4)."
                    ),
                ))
            # Детерминированный отбор: по entry_id кандидата
            cands_for_effect.sort(key=lambda c: c.candidate_entry_id)
            candidates.extend(cands_for_effect[:DETECTION_MAX_CANDIDATES_PER_EFFECT])

        return tuple(candidates)

    def link(self, doc: ChronicleDocument) -> LinkResult:
        """(c) Объединение validate + detect + idempotency.
        PENDING-кандидаты с уже существующим candidate_id НЕ создаются повторно.
        REJECTED/ACCEPTED кандидаты НЕ возобновляются.
        """
        validation_errors = self.validate(doc)
        detected = self.detect_candidates(doc)

        existing_ids = {c.candidate_id for c in doc.cause_candidates}
        new_candidates = [c for c in detected if c.candidate_id not in existing_ids]

        stats = {
            "entries_total": len(doc.entries),
            "entries_with_causes": sum(1 for e in doc.entries if e.causes),
            "candidates_new": len(new_candidates),
            "candidates_existing": len(existing_ids),
            "candidates_pending": sum(
                1 for c in doc.cause_candidates
                if c.status.value == "PENDING"
            ),
            "validation_errors_count": len(validation_errors),
            "validation_warnings_count": sum(
                1 for e in validation_errors if e.error_code == "VALIDATION_WARNING"
            ),
        }

        return LinkResult(
            validation_errors=tuple(validation_errors),
            new_candidates=tuple(new_candidates),
            existing_candidates=tuple(doc.cause_candidates),
            truncated=False,
            truncation_reason="",
            stats=stats,
        )

    @staticmethod
    def _entry_age(doc: ChronicleDocument, entry_id: str) -> int:
        """Безопасное чтение historical_age для сортировки (default 0)."""
        for e in doc.entries:
            if e.entry_id == entry_id:
                return e.historical_age if e.historical_age is not None else 0
        return 0


__all__ = ["CausalLinker", "LinkResult", "ValidationError", "DETECTION_MAX_AGE_DELTA_YEARS", "DETECTION_MAX_CANDIDATES_PER_EFFECT"]
