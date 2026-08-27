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

from app.domain.action_commitment import INTERRUPT_PRIORITY_SUPERSEDE
from app.domain.action_priority import INTERRUPT_THRESHOLD
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

# S203.4 (ADR-O-365, D-4): приоритетная политика прерываний. Каскад:
# активна ТОЛЬКО при ARBITER_ENFORCEMENT=True ∧ S203.4_ARBITER_INTERRUPT=True.
# Любой флаг OFF → arbitrate байтово идентичен S203.2 (гейт-тест ниже).
# Оба имени env принимаются: точка неудобна в части шеллов.
S203_4_ARBITER_INTERRUPT: bool = any(
    os.environ.get(_k, "").strip().lower() in ("1", "true", "yes")
    for _k in ("S203.4_ARBITER_INTERRUPT", "S203_4_ARBITER_INTERRUPT")
)

# Онтологическая кодировка (ADR-O-363/365, четыре семантики):
#   PASS            -> COMMIT (через существующий mirror)
#   REJECT(DUPLICATE) -> CONTINUE (инкумбент продолжает; кандидат поглощён —
#                       обобщение suppression Н-48)
#   REJECT(INCUMBENT) -> REJECT (анти-флаппинг исполнения)
#   REJECT(INCUMBENT_PROTECTED) -> REJECT: механизму ЗАПРЕЩЕНО прерывать
#                       (executor-boundary task/windup/sleep | POLICY-защита
#                       EXECUTING) — «проиграл конкуренцию» ≠ «запрещено» (D-6)
#   INTERRUPT(PRIORITY_SUPERSEDE) -> кандидат превысил порог; ИСПОЛНЕНИЕ —
#                       в enforce_for_intent (invocation-side), арбитр read-only
VERDICT_PASS = "PASS"
VERDICT_REJECT = "REJECT"
VERDICT_INTERRUPT = "INTERRUPT"  # S203.4: четвёртая несводимая семантика

REASON_DUPLICATE = "DUPLICATE"  # та же цель у инкумбента
REASON_INCUMBENT = "INCUMBENT"  # другая цель; инкумбент сохраняет приоритет
REASON_INCUMBENT_PROTECTED = "INCUMBENT_PROTECTED"  # S203.4 (D-6)
# INTERRUPT-причина = INTERRUPT_PRIORITY_SUPERSEDE из домена (закон №16:
# единый реестр причин, без локальных дублей константы).
REASON_PRIORITY_SUPERSEDE = INTERRUPT_PRIORITY_SUPERSEDE

# S203.4 (ADR-O-365 §3): non-interruptible boundaries.
#   task   — до координационного ADR с ADR-O-364 (dialogue-исполнение чужая зона);
#   windup — защищён краткостью (окно 2 тика; прерывание ничего не покупает);
#   sleep  — физиологическая власть, конфликт доменов = S203.6 (закон №19).
_NON_INTERRUPTIBLE_EXECUTORS = frozenset({"task", "windup", "sleep"})


@dataclass(frozen=True)
class ArbitrationResult:
    """Результат арбитража. frozen — value object (§2.3 Устава)."""

    verdict: str
    reason: Optional[str] = None  # при REJECT и INTERRUPT (S203.4)
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
        candidate_priority: int = 0,
    ) -> ArbitrationResult:
        """Гейт материализации movement-кандидата.

        Инкумбент = ACTIVE-обязательство (COMMITTED/EXECUTING/BLOCKED/PROPOSED —
        Мастер: COMMITTED считается занятым, commitment race исключён).
        Осиротевший инкумбент (sweep ещё не прошёл) — пропускаем кандидата:
        суперсессию выполнит существующий mirror (INTERRUPTED/SUPERSEDED).

        S203.4: candidate_priority — результат доменной policy (D-5; Э3 не
        читает существующий float intent.priority — DRF-шкала разведена).
        Приоритет 0 = право на прерывание не заявлено. Арбитр read-only:
        INTERRUPT — вердикт, не действие (закон №9).
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

        # ── S203.4 (ADR-O-365): приоритетная политика прерываний ─────────
        # Каскад D-4: только ENFORCEMENT ∧ S203.4_ARBITER_INTERRUPT. Любой
        # флаг OFF → политика обойдена, путь ниже байтово идентичен S203.2.
        # Mutual-INTERRUPT невозможен конструктивно: приоритет скалярен (R8).
        if ARBITER_ENFORCEMENT and S203_4_ARBITER_INTERRUPT:
            _is_dup = (
                candidate_target is not None and candidate_target == incumbent_target
            )
            _inc_executor = incumbent.get("executor") or ""
            _inc_priority = int(incumbent.get("priority") or 0)
            if not _is_dup:
                # Вердикт Мастера Тая B (S203.4-Э4) — нормативная таблица:
                #   traversal EXECUTING  ← прерываем (только PRIORITY_SUPERSEDE;
                #                          SURVIVAL/WINDOWED вытесняют, SOCIAL — нет)
                #   task/windup EXECUTING ← protected
                #   sleep                 ← protected (non-superseding)
                # Обоснование: traversal рождается EXECUTING (Н-50) — строгая
                # защита делала INTERRUPT недостижимым (коллизия с гейтом §5.3).
                # POLICY, НЕ онтология: emergency-продюсер (смерть/травма/пожар/
                # разрушение цели) расширит политику отдельным ADR.
                _executing_protected = (
                    incumbent_status == "EXECUTING" and _inc_executor != "traversal"
                )
                if (
                    _inc_executor in _NON_INTERRUPTIBLE_EXECUTORS
                    or _executing_protected
                ):
                    # Два разных «нельзя» под одним reason (D-6): boundary
                    # (executor) и POLICY-защита EXECUTING не-traversal
                    # исполнителей.
                    logger.info(
                        f"[ARBITER_REJECT] tick={tick} npc={npc_id} "
                        f"candidate_target={candidate_target} "
                        f"candidate_source={candidate_source} "
                        f"candidate_priority={candidate_priority} "
                        f"incumbent_id={incumbent.get('commitment_id')} "
                        f"incumbent_status={incumbent_status} "
                        f"incumbent_executor={_inc_executor} "
                        f"reason=INCUMBENT_PROTECTED"
                    )
                    return ArbitrationResult(
                        verdict=VERDICT_REJECT,
                        reason=REASON_INCUMBENT_PROTECTED,
                        incumbent_id=incumbent.get("commitment_id"),
                        incumbent_target=incumbent_target,
                    )
                # ТЗ §9.1: PROPOSED прерываем любым строго большим
                # приоритетом (без порога); COMMITTED/BLOCKED — через порог.
                # (PROPOSED-инкумбентов зеркала не создляют — ветка
                # превентивная, матрица полноты.)
                _threshold = 0 if incumbent_status == "PROPOSED" else INTERRUPT_THRESHOLD
                if (
                    candidate_priority > 0
                    and candidate_priority > _inc_priority + _threshold
                ):
                    logger.info(
                        f"[ARBITER_INTERRUPT] tick={tick} npc={npc_id} "
                        f"candidate_target={candidate_target} "
                        f"candidate_source={candidate_source} "
                        f"candidate_priority={candidate_priority} "
                        f"incumbent_id={incumbent.get('commitment_id')} "
                        f"incumbent_target={incumbent_target} "
                        f"incumbent_status={incumbent_status} "
                        f"incumbent_executor={_inc_executor} "
                        f"incumbent_priority={_inc_priority} "
                        f"reason=PRIORITY_SUPERSEDE"
                    )
                    return ArbitrationResult(
                        verdict=VERDICT_INTERRUPT,
                        reason=REASON_PRIORITY_SUPERSEDE,
                        incumbent_id=incumbent.get("commitment_id"),
                        incumbent_target=incumbent_target,
                    )

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

    @staticmethod
    def enforce_for_intent(
        scene_state: Dict[str, Any],
        intent: Any,
        tick: int,
    ) -> bool:
        """S203.4 invocation-point API: вердикт + ИСПОЛНЕНИЕ INTERRUPT.

        Арбитр (arbitrate) остаётся read-only (закон №9); единственное место
        исполнения прерывания — здесь, invocation-side (закон №13: право
        ПРОСИТЬ — у арбитра, действие — у invocation point).
        Приоритет кандидата — результат доменной policy; существующий float
        intent.priority (DRF-шкала PRIORITY_*) НЕ читается — три приоритетные
        семантики разведены (queue TaskPriority | DRF float | arbitration int).
        """
        from app.domain.action_priority import resolve_candidate_priority

        _result = CommitmentArbiter.arbitrate(
            scene_state,
            getattr(intent, "actor_id", ""),
            getattr(intent, "target_node_id", None),
            getattr(intent, "reason", ""),
            tick,
            candidate_priority=resolve_candidate_priority(
                intent_type=getattr(intent, "intent_type", "") or "",
                intent_domain=getattr(intent, "domain", None),
            ),
        )
        if _result.verdict == VERDICT_INTERRUPT:
            from app.domain.traversal_schema import interrupt_traversal

            # False = NOT_FOUND/ALREADY_TERMINAL (инкумбент без живого
            # traversal, окно COMMITTED): прервать нечем; кандидат блокируется
            # этим тиком — инкумбент уйдёт sweep'ом/суперсессией.
            return interrupt_traversal(
                scene_state,
                getattr(intent, "actor_id", ""),
                INTERRUPT_PRIORITY_SUPERSEDE,
                tick,
            )
        if _result.verdict == VERDICT_PASS:
            return True
        # REJECT: LOG_ONLY — разрешить (замер частоты); ENFORCEMENT — блок.
        if ARBITER_ENFORCEMENT:
            return False
        return True
