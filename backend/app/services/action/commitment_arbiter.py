# -*- coding: utf-8 -*-
"""
path: /project/backend/app/services/action/commitment_arbiter.py
Назначение: S203.2 (Stage 2A, ADR-O-363) — Commitment Arbiter: gate перед
    материализацией движения. Решает единственный вопрос: получает ли
    movement candidate право материализоваться при текущем incumbent
    commitment (Мастер: НЕ «можно ли NPC двигаться» — это DecisionHub).
    Один arbiter, два invocation points (simulation.py / movement_bridge.py).
    Вердикт: PASS | REJECT + reason ∈ {DUPLICATE, INCUMBENT} (Мастер:
    вердикт-классификатор запрещён — онтологическая простота Verdict).
    Read-only: арбитр не пишет реестр; единственный commit-писатель —
    существующий mirror при материализации (race-free by construction).
    INTERRUPT — отсутствует до S203.3/4 (право убивать incumbent — не здесь).
Зависимости: app.services.action.commitment_registry (чтение)
Основные сущности: CommitmentArbiter, ARBITER_ENFORCEMENT
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

from app.services.action.commitment_registry import CommitmentRegistry

logger = logging.getLogger(__name__)

# Режимы: LOG_ONLY (замер REJECT-частоты до включения) → ENFORCEMENT.
# Rollback: ENFORCEMENT=False = поведение тика байтово прежнее.
# S203.2: флаг через env — A/B-прогоны без ручных правок файла (класс сбоя:
# 3x «правка в редакторе не выполнена»). Значение читается при импорте;
# тесты monkeypatch-ят атрибут модуля напрямую и не затронуты.
ARBITER_ENFORCEMENT: bool = os.environ.get("ARBITER_ENFORCEMENT", "").strip().lower() in (
    "1",
    "true",
    "yes",
)

# Онтологическая кодировка (ADR-O-363, четыре семантики):
#   PASS            -> COMMIT (через существующий mirror)
#   REJECT(DUPLICATE) -> CONTINUE (инкумбент продолжает; кандидат поглощён —
#                       обобщение suppression Н-48)
#   REJECT(INCUMBENT) -> REJECT (анти-флаппинг исполнения)
#   INTERRUPT       -> вне S203.2 (S203.3/4)
VERDICT_PASS = "PASS"
VERDICT_REJECT = "REJECT"

REASON_DUPLICATE = "DUPLICATE"  # та же цель у инкумбента
REASON_INCUMBENT = "INCUMBENT"  # другая цель; инкумбент сохраняет приоритет


@dataclass(frozen=True)
class ArbitrationResult:
    """Результат арбитража. frozen — value object (§2.3 Устава)."""

    verdict: str
    reason: Optional[str] = None  # только при REJECT
    incumbent_id: Optional[str] = None
    incumbent_target: Optional[str] = None


class CommitmentArbiter:
    """Чистая политика арбитража над реестром. Без состояния, без мутаций."""

    @staticmethod
    def arbitrate(
        scene_state: Dict[str, Any],
        npc_id: str,
        candidate_target: Optional[str],
        candidate_source: str = "",
        tick: int = 0,
    ) -> ArbitrationResult:
        """Гейт материализации movement-кандидата.

        Инкумбент = ACTIVE-обязательство (COMMITTED/EXECUTING/BLOCKED/PROPOSED —
        Мастер: COMMITTED считается занятым, commitment race исключён).
        Осиротевший инкумбент (sweep ещё не прошёл) — пропускаем кандидата:
        суперсессию выполнит существующий mirror (INTERRUPTED/SUPERSEDED).
        """
        incumbent = CommitmentRegistry.get_active(scene_state, npc_id)
        if incumbent is None:
            return ArbitrationResult(verdict=VERDICT_PASS)

        incumbent_status = incumbent.get("status")
        if incumbent_status not in (
            "PROPOSED",
            "COMMITTED",
            "EXECUTING",
            "BLOCKED",
        ):
            # Терминальный осиротевший (sweep ещё не перенёс в history) —
            # кандидат свободен; консистентность восстановит mirror.
            return ArbitrationResult(verdict=VERDICT_PASS)

        incumbent_target = incumbent.get("target_id")

        if candidate_target is not None and candidate_target == incumbent_target:
            reason = REASON_DUPLICATE
        else:
            reason = REASON_INCUMBENT

        # Телеметрия (§11: наблюдение не создаёт причинность): полный контекст
        # для будущей археологии — источник кандидата обязателен (Мастер).
        # S203.2 финализация: logger + env-гейт (был print по Часть VIII.5
        # в период замера — sandbox-захват глушит logger).
        logger.info(
            f"[ARBITER_REJECT] tick={tick} npc={npc_id} "
            f"candidate_target={candidate_target} "
            f"candidate_source={candidate_source} "
            f"incumbent_id={incumbent.get('commitment_id')} "
            f"incumbent_target={incumbent_target} "
            f"incumbent_status={incumbent_status} "
            f"reason={reason}"
        )
        return ArbitrationResult(
            verdict=VERDICT_REJECT,
            reason=reason,
            incumbent_id=incumbent.get("commitment_id"),
            incumbent_target=incumbent_target,
        )

    @staticmethod
    def enforce(
        scene_state: Dict[str, Any],
        npc_id: str,
        candidate_target: Optional[str],
        candidate_source: str = "",
        tick: int = 0,
    ) -> bool:
        """Invocation-point API: разрешить материализацию?

        LOG_ONLY: всегда True (REJECT только в логах — замер частоты).
        ENFORCEMENT: True только при PASS.
        """
        # S203.2 финализация: диагностика вызовов гейта — удалена (print-зонд
        # выполнил миссию: 1006 calls / 359 rejects на 200 тиков, A/B доказан).
        result = CommitmentArbiter.arbitrate(
            scene_state, npc_id, candidate_target, candidate_source, tick
        )
        if result.verdict == VERDICT_PASS:
            return True
        # REJECT: LOG_ONLY — всегда разрешить (замер частоты в логах);
        # ENFORCEMENT — блокировать материализацию.
        if ARBITER_ENFORCEMENT:
            return False
        return True