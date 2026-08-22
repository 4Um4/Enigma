"""
path: /project/backend/app/services/action/commitment_registry.py
Назначение: Единственный писатель реестра поведенческого владения (S203.1, shadow).
    scene_state["active_commitments"] — только АКТИВНЫЕ обязательства
        (<=1 traversal-commitment на NPC, структурно: active_traversals — dict[npc_id]).
    scene_state["commitment_history"]  — bounded терминальная история (cap/NPC).
    scene_state["commitment_ordinals"] — персистентные монотонные счётчики.
    Shadow mode: реестр ЗЕРКАЛИТ факты исполнителей и НЕ меняет поведение
    (acceptance S203.1: не отвергает интенты, не меняет игровой результат).
    Право говорить "нет" (COMMIT/CONTINUE/REJECT) получает арбитр в S203.2.
Зависимости: app.domain.action_commitment (чистый домен)
Основные сущности: CommitmentRegistry, COMMITMENT_REGISTRY_ENABLED
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from app.domain.action_commitment import (
    CAUSE_UNKNOWN_LEGACY_SOURCE,
    COMMITMENT_HISTORY_CAP_PER_NPC,
    build_commitment_dict,
    transition_commitment,
)

logger = logging.getLogger(__name__)

# Rollback-флаг S203.1 (Мастер: первый проход — за флагом).
# False -> все mirror_* и sweep = no-op, реестр не растёт, поведение тика
# байтово идентично текущему. Откат = одна константа.
COMMITMENT_REGISTRY_ENABLED: bool = True

_KEY_ACTIVE = "active_commitments"
_KEY_HISTORY = "commitment_history"
_KEY_ORDINALS = "commitment_ordinals"

# Зеркало Н-46b: перезапись traversal без CANCELLED.
_INTERRUPT_SUPERSEDED = "SUPERSEDED_BY_NEW_MATERIALIZATION"
# Sweep: traversal исчез вне зеркалируемых путей (Н-46-класс).
_INTERRUPT_VANISHED = "TRAVERSAL_VANISHED"


class CommitmentRegistry:
    """Статический сервис над scene_state (прецедент: TraversalExecutionSystem).

    Только эти методы легально мутируют реестр (единый писатель).
    Прямая dict-хирургия active_commitments извне = ArchitecturalViolation.
    Политика ошибок shadow-режима: рассогласование зеркала = ERROR-лог
    и продолжение (реестр — измерительный прибор, не владелец тика).
    В enforcement-режиме (S203.2+) запрещённые переходы станут
    SimulationIntegrityError — громкое падение.
    """

    # ── Чтение (проекции) ────────────────────────────────────────────────

    @staticmethod
    def has_active_commitment(scene_state: Dict[str, Any], npc_id: str) -> bool:
        """Проекция владения: 'есть ли у NPC поведенческий владелец'.

        Stage 2A §7: замена сниффинга traversal==MOVING (Н-35).
        Потребители (npc_tick_pipeline) переподключаются в S203.2 — не раньше.
        """
        return npc_id in (scene_state.get(_KEY_ACTIVE) or {})

    @staticmethod
    def get_active(
        scene_state: Dict[str, Any], npc_id: str
    ) -> Optional[Dict[str, Any]]:
        """Активное обязательство NPC (или None). Read-only."""
        return (scene_state.get(_KEY_ACTIVE) or {}).get(npc_id)

    # ── Внутренние примитивы ─────────────────────────────────────────────

    @staticmethod
    def _next_ordinal(scene_state: Dict[str, Any], npc_id: str) -> int:
        """Монотонный персистентный счётчик идентичностей (№4):
        никогда не уменьшается, никогда не переиспользуется."""
        ordinals = scene_state.setdefault(_KEY_ORDINALS, {})
        nxt = int(ordinals.get(npc_id, 0)) + 1
        ordinals[npc_id] = nxt
        return nxt

    @staticmethod
    def _to_history(
        scene_state: Dict[str, Any], npc_id: str, commitment: Dict[str, Any]
    ) -> None:
        """Терминальная запись -> bounded history (№1: retained, cap)."""
        bucket = scene_state.setdefault(_KEY_HISTORY, {}).setdefault(npc_id, [])
        bucket.append(commitment)
        if len(bucket) > COMMITMENT_HISTORY_CAP_PER_NPC:
            del bucket[: len(bucket) - COMMITMENT_HISTORY_CAP_PER_NPC]

    @staticmethod
    def _terminate(
        scene_state: Dict[str, Any],
        npc_id: str,
        tick: int,
        new_status: str,
        interrupt_reason: Optional[str] = None,
    ) -> bool:
        """Терминальный переход + перенос в history. False = нечего/нельзя."""
        active = scene_state.setdefault(_KEY_ACTIVE, {})
        commitment = active.get(npc_id)
        if commitment is None:
            return False
        if not transition_commitment(
            commitment, new_status, tick=tick, interrupt_reason=interrupt_reason
        ):
            logger.error(
                f"[COMMITMENT] transition rejected: npc={npc_id} "
                f"{commitment.get('status')} -> {new_status} "
                f"(interrupt_reason={interrupt_reason})"
            )
            return False
        active.pop(npc_id, None)
        CommitmentRegistry._to_history(scene_state, npc_id, commitment)
        return True

    # ── Публичные lifecycle-примитивы (арбитр S203.2 будет звать сам) ────

    @staticmethod
    def commit(
        scene_state: Dict[str, Any],
        tick: int,
        npc_id: str,
        action: str,
        cause: str,
        target_id: Optional[str] = None,
        executor: str = "traversal",
        parent_commitment_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Создаёт активное обязательство (status=COMMITTED).

        Если у NPC уже есть активное — оно INTERRUPTED(SUPERSEDED...) и
        становится parent нового: каузальная цепочка C1->C2 (№3a).
        Каждая суперсессия в shadow = измеренный факт двойного исполнения
        (baseline-метрика churn для S203.2).
        Пустой cause -> UNKNOWN_LEGACY_SOURCE (№8: не выдумывать семантику).
        """
        active = scene_state.setdefault(_KEY_ACTIVE, {})
        _parent = parent_commitment_id
        existing = active.get(npc_id)
        if existing is not None:
            _parent = existing.get("commitment_id")
            CommitmentRegistry._terminate(
                scene_state,
                npc_id,
                tick,
                "INTERRUPTED",
                interrupt_reason=_INTERRUPT_SUPERSEDED,
            )
        ordinal = CommitmentRegistry._next_ordinal(scene_state, npc_id)
        commitment = build_commitment_dict(
            tick=tick,
            npc_id=npc_id,
            action=action,
            ordinal=ordinal,
            cause=cause or CAUSE_UNKNOWN_LEGACY_SOURCE,
            target_id=target_id,
            executor=executor,
            parent_commitment_id=_parent,
            initial_status="COMMITTED",
        )
        active[npc_id] = commitment
        logger.debug(
            f"[COMMITMENT] COMMIT npc={npc_id} action={action} "
            f"cause={cause} ordinal={ordinal} parent={_parent}"
        )
        return commitment

    @staticmethod
    def mark_executing(scene_state: Dict[str, Any], npc_id: str, tick: int) -> bool:
        """COMMITTED -> EXECUTING: исполнитель начал работу."""
        commitment = CommitmentRegistry.get_active(scene_state, npc_id)
        if commitment is None:
            return False
        if not transition_commitment(commitment, "EXECUTING", tick=tick):
            logger.error(
                f"[COMMITMENT] EXECUTING rejected for npc={npc_id} "
                f"(status={commitment.get('status')})"
            )
            return False
        return True

    @staticmethod
    def complete(scene_state: Dict[str, Any], npc_id: str, tick: int) -> bool:
        """-> COMPLETED (+history). Verification-семантика (evidence) — S203.2+."""
        return CommitmentRegistry._terminate(scene_state, npc_id, tick, "COMPLETED")

    @staticmethod
    def fail(scene_state: Dict[str, Any], npc_id: str, tick: int) -> bool:
        """-> FAILED (+history)."""
        return CommitmentRegistry._terminate(scene_state, npc_id, tick, "FAILED")

    @staticmethod
    def interrupt(
        scene_state: Dict[str, Any], npc_id: str, tick: int, interrupt_reason: str
    ) -> bool:
        """-> INTERRUPTED (+history). Причина прекращения обязательна."""
        return CommitmentRegistry._terminate(
            scene_state, npc_id, tick, "INTERRUPTED", interrupt_reason=interrupt_reason
        )

    @staticmethod
    def expire(scene_state: Dict[str, Any], npc_id: str, tick: int) -> bool:
        """-> EXPIRED (+history): срок истёк без исполнения."""
        return CommitmentRegistry._terminate(scene_state, npc_id, tick, "EXPIRED")

    @staticmethod
    def cancel(scene_state: Dict[str, Any], npc_id: str, tick: int) -> bool:
        """-> CANCELLED (+history): сознательное снятие (актор/арбитр).
        Отличается от INTERRUPTED: причина прекращения — решение, не событие."""
        return CommitmentRegistry._terminate(scene_state, npc_id, tick, "CANCELLED")

    # ── Shadow-зеркала S203.1: единственные точки интеграции ─────────────

    @staticmethod
    def mirror_traversal_materialized(
        scene_state: Dict[str, Any],
        tick: int,
        npc_id: str,
        cause: str,
        target_node: Optional[str],
    ) -> None:
        """SSM материализовал traversal (запись born-MOVING, Н-50).

        cause — VERBATIM upstream-строка (SceneChange.cause); классификацию
        need/schedule/random выполняет только будущий арбитр (№7: SSM не
        придумывает behavioral семантику постфактум).
        """
        if not COMMITMENT_REGISTRY_ENABLED:
            return
        commitment = CommitmentRegistry.commit(
            scene_state,
            tick,
            npc_id,
            action="MOVE",
            cause=cause,
            target_id=target_node,
            executor="traversal",
        )
        if commitment is not None:
            CommitmentRegistry.mark_executing(scene_state, npc_id, tick)

    @staticmethod
    def mirror_traversal_completed(
        scene_state: Dict[str, Any], npc_id: str, tick: int
    ) -> None:
        """TES: traversal достиг цели (EXECUTING -> COMPLETED)."""
        if not COMMITMENT_REGISTRY_ENABLED:
            return
        CommitmentRegistry.complete(scene_state, npc_id, tick)

    @staticmethod
    def mirror_traversal_interrupted(
        scene_state: Dict[str, Any], npc_id: str, tick: int, interrupt_reason: str
    ) -> None:
        """Обходной путь убил traversal (Н-46a cross-loc и др.)."""
        if not COMMITMENT_REGISTRY_ENABLED:
            return
        CommitmentRegistry.interrupt(scene_state, npc_id, tick, interrupt_reason)

    @staticmethod
    def sweep(scene_state: Dict[str, Any], tick: int) -> int:
        """Консистентность: активный traversal-commitment без живого traversal
        -> INTERRUPTED(TRAVERSAL_VANISHED).

        Измерительный прибор S203.1: ловит ВСЕ незеркалированные обходы
        (Н-46-класс), включая ещё не обнаруженные пути (boundary transfer,
        dead-NPC cleanup). Каждый sweep-хит = кандидат на явное зеркало.
        """
        if not COMMITMENT_REGISTRY_ENABLED:
            return 0
        active = scene_state.get(_KEY_ACTIVE) or {}
        traversals = scene_state.get("active_traversals") or {}
        swept = 0
        for npc_id in list(active.keys()):
            commitment = active[npc_id]
            if commitment.get("executor") == "traversal" and npc_id not in traversals:
                CommitmentRegistry.interrupt(
                    scene_state, npc_id, tick, _INTERRUPT_VANISHED
                )
                swept += 1
        if swept:
            logger.warning(
                f"[COMMITMENT][SWEEP] tick={tick} vanished={swept} "
                f"(unmirrored bypass paths)"
            )
        return swept