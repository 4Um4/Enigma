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
    ACTIVE_COMMITMENT_STATUSES,
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

# S203.4 (ADR-O-365, D-4): зеркала владения task/windup/sleep. OFF (default) =
# зеркала не создаются, поведение байтово прежнее. Оба имени env принимаются
# (точка неудобна в части шеллов) — прецедент S203_4_ARBITER_INTERRUPT.
import os as _os  # noqa: E402  (локальный: заголовок модуля не читан — якорь-безопасность)

S203_4_OWNERSHIP_MIRRORS: bool = any(
    _os.environ.get(_k, "").strip().lower() in ("1", "true", "yes")
    for _k in ("S203.4_OWNERSHIP_MIRRORS", "S203_4_OWNERSHIP_MIRRORS")
)
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
        S203.2 (Мастер): status ∈ ACTIVE_COMMITMENT_STATUSES — COMMITTED
        считается занятым, commitment race исключён.
        """
        entry = (scene_state.get(_KEY_ACTIVE) or {}).get(npc_id)
        return entry is not None and entry.get("status") in ACTIVE_COMMITMENT_STATUSES

    @staticmethod
    def has_behavioral_owner(scene_state: Dict[str, Any], npc_id: str) -> bool:
        """S203.2: registry-first проекция с legacy-fallback (миграция
        npc_tick_pipeline, Мастер: сейчас, как рефактор).

        Нет записи в реестре → старая формула traversal==MOVING (Н-35).
        Гарантии: traversal-only реестр → NEW == OLD (зеркало покрывает все
        материализации); FLAG=OFF (реестр пуст) → fallback → байтовая
        нейтральность no-op-контракта сохранена. Чтение флагом не гейтится:
        проекция над пустым реестром безопасна.
        """
        entry = (scene_state.get(_KEY_ACTIVE) or {}).get(npc_id)
        if entry is not None:
            return entry.get("status") in ACTIVE_COMMITMENT_STATUSES
        trav = (scene_state.get("active_traversals") or {}).get(npc_id, {})
        return trav.get("status") == "MOVING"

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
        fail_reason: Optional[str] = None,
    ) -> bool:
        """Терминальный переход + перенос в history. False = нечего/нельзя."""
        active = scene_state.setdefault(_KEY_ACTIVE, {})
        commitment = active.get(npc_id)
        if commitment is None:
            return False
        if not transition_commitment(
            commitment,
            new_status,
            tick=tick,
            interrupt_reason=interrupt_reason,
            fail_reason=fail_reason,
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
    def fail(scene_state: Dict[str, Any], npc_id: str, tick: int, fail_reason: str) -> bool:
        """-> FAILED (+history). Причина провала ОБЯЗАТЕЛЬНА (D-6: симметрия
        INTERRUPTED). fail_reason ∈ FAIL_* — реестр констант, закон №16."""
        return CommitmentRegistry._terminate(
            scene_state, npc_id, tick, "FAILED", fail_reason=fail_reason
        )

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
        # D-1 (ADR-O-365): parent-цепочка при арбитр-INTERRUPT. Гейт прервал
        # инкумбента этим же тиком (enforce_for_intent); зеркало материализации
        # нового кандидата восстанавливает каузальную связь (№3a) поиском по
        # истории: PRIORITY_SUPERSEDE-терминал с updated_tick == тику зеркала —
        # не более одного на NPC/тик (после interrupt инкумбента нет).
        # Fallback: parent=None (разрыв цепочки лучше ложной связи — Мастер).
        from app.domain.action_commitment import INTERRUPT_PRIORITY_SUPERSEDE

        _parent: Optional[str] = None
        _hist = (scene_state.get("commitment_history") or {}).get(npc_id, [])
        for _prev in reversed(_hist):
            if (
                _prev.get("interrupt_reason") == INTERRUPT_PRIORITY_SUPERSEDE
                and _prev.get("updated_tick") == tick
            ):
                _parent = _prev.get("commitment_id")
                break
        commitment = CommitmentRegistry.commit(
            scene_state,
            tick,
            npc_id,
            action="MOVE",
            cause=cause,
            target_id=target_node,
            executor="traversal",
            parent_commitment_id=_parent,
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

    # ── S203.4 (ADR-O-365): зеркала не-traversal исполнителей ────────────

    @staticmethod
    def _commit_nonsuperseding(
        scene_state: Dict[str, Any],
        tick: int,
        npc_id: str,
        action: str,
        cause: str,
        executor: str,
        target_id: Optional[str] = None,
        executor_ref: Optional[str] = None,
        priority: int = 0,
        priority_policy_version: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """R2/F12: non-superseding создание зеркала владения.

        Зеркало НИКОГДА не убивает инкумбента: auto-supersede в зеркалах =
        зомби (мёртвый commitment при живом исполнителе; закон №14). Коллизия
        → None + телеметрия (частота walk+talk — вход будущей модели
        конкурентности TZ §6). Priority — уже вычисленный результат policy
        (зеркало не классифицирует семантику, №7).
        """
        if not (COMMITMENT_REGISTRY_ENABLED and S203_4_OWNERSHIP_MIRRORS):
            return None
        active = scene_state.setdefault(_KEY_ACTIVE, {})
        existing = active.get(npc_id)
        if existing is not None:
            logger.info(
                f"[{executor.upper()}_MIRROR_COLLISION] tick={tick} npc={npc_id} "
                f"action={action} executor_ref={executor_ref} "
                f"incumbent={existing.get('commitment_id')} "
                f"incumbent_executor={existing.get('executor')}"
            )
            return None
        ordinal = CommitmentRegistry._next_ordinal(scene_state, npc_id)
        commitment = build_commitment_dict(
            tick=tick,
            npc_id=npc_id,
            action=action,
            ordinal=ordinal,
            cause=cause or CAUSE_UNKNOWN_LEGACY_SOURCE,
            target_id=target_id,
            executor=executor,
            executor_ref=executor_ref,
            priority=priority,
            priority_policy_version=priority_policy_version,
            initial_status="COMMITTED",
        )
        active[npc_id] = commitment
        logger.debug(
            f"[COMMITMENT] MIRROR-COMMIT npc={npc_id} action={action} "
            f"executor={executor} executor_ref={executor_ref}"
        )
        return commitment

    @staticmethod
    def mirror_task_committed(
        scene_state: Dict[str, Any],
        tick: int,
        npc_id: str,
        cause: str,
        task_id: str,
        priority: int = 0,
    ) -> Optional[Dict[str, Any]]:
        """Ц1: canonical-задача поставлена в очередь (Фаза 6, Э5-b).

        cause — verbatim upstream; классификацию canonical/ambient выполняет
        вызывающая сторона (D-8): ambient в реестр не попадает.
        """
        from app.domain.action_priority import PRIORITY_POLICY_VERSION

        return CommitmentRegistry._commit_nonsuperseding(
            scene_state, tick, npc_id, action="TALK", cause=cause,
            executor="task", executor_ref=task_id,
            priority=priority,
            priority_policy_version=(PRIORITY_POLICY_VERSION if priority else None),
        )

    @staticmethod
    def mirror_task_terminal(
        scene_state: Dict[str, Any],
        npc_id: str,
        tick: int,
        outcome: str,
        fail_reason: Optional[str] = None,
        interrupt_reason: Optional[str] = None,
        executor: str = "task",
    ) -> bool:
        """Терминал task/windup-исполнителя (D-2 outbox / Phase 7 sync).

        outcome ∈ {EXECUTING, COMPLETED, FAILED, CANCELLED, EXPIRED, INTERRUPTED}.
        FAILED требует fail_reason (D-6); INTERRUPTED — interrupt_reason.
        Executor-мисматч → False без мутации (гонка/сменённый исполнитель).
        """
        if not (COMMITMENT_REGISTRY_ENABLED and S203_4_OWNERSHIP_MIRRORS):
            return False
        commitment = CommitmentRegistry.get_active(scene_state, npc_id)
        if commitment is None or commitment.get("executor") != executor:
            logger.info(
                f"[{executor.upper()}_MIRROR_STALE] tick={tick} npc={npc_id} "
                f"outcome={outcome} "
                f"active_executor={(commitment or {}).get('executor')}"
            )
            return False
        if outcome == "EXECUTING":
            return CommitmentRegistry.mark_executing(scene_state, npc_id, tick)
        if outcome == "COMPLETED":
            return CommitmentRegistry.complete(scene_state, npc_id, tick)
        if outcome == "FAILED":
            return CommitmentRegistry.fail(scene_state, npc_id, tick, fail_reason or "")
        if outcome == "INTERRUPTED":
            return CommitmentRegistry.interrupt(
                scene_state, npc_id, tick, interrupt_reason or "UNKNOWN"
            )
        if outcome == "CANCELLED":
            return CommitmentRegistry.cancel(scene_state, npc_id, tick)
        if outcome == "EXPIRED":
            return CommitmentRegistry.expire(scene_state, npc_id, tick)
        raise ValueError(f"mirror_task_terminal: unknown outcome '{outcome}'")

    @staticmethod
    def mirror_windup_committed(
        scene_state: Dict[str, Any],
        tick: int,
        npc_id: str,
        action_type: str,
        target_id: Optional[str],
        cause: str,
    ) -> Optional[Dict[str, Any]]:
        """Э5-c: windowed-подготовка начата (Фаза 6). Приоритет — WINDOWED
        (шкала v1); held_intent_id вызывающая сторона берёт = commitment_id
        (детерминизм ID; Н-31-класс не размножается)."""
        from app.domain.action_priority import (
            PRIORITY_POLICY_VERSION,
            resolve_candidate_priority,
        )

        return CommitmentRegistry._commit_nonsuperseding(
            scene_state, tick, npc_id, action=action_type.upper(), cause=cause,
            executor="windup", executor_ref=None, target_id=target_id,
            priority=resolve_candidate_priority(intent_type=action_type),
            priority_policy_version=PRIORITY_POLICY_VERSION,
        )

    @staticmethod
    def mirror_task_expired_by_ref(
        scene_state: Dict[str, Any], npc_id: str, task_id: str, tick: int
    ) -> bool:
        """M-29 purge: EXPIRED строго по executor_ref — иначе можно убить
        чужое (следующее) обязательство того же NPC."""
        if not (COMMITMENT_REGISTRY_ENABLED and S203_4_OWNERSHIP_MIRRORS):
            return False
        commitment = CommitmentRegistry.get_active(scene_state, npc_id)
        if (
            commitment is None
            or commitment.get("executor") != "task"
            or commitment.get("executor_ref") != task_id
        ):
            return False
        return CommitmentRegistry.expire(scene_state, npc_id, tick)

    @staticmethod
    def reconcile_sleep_ownership(
        scene_state: Dict[str, Any], npcs: list, tick: int
    ) -> None:
        """Э5-d (D-3): state-based сверка инварианта Y6 после Фазы 0.6.

        coupling ∈ {SLEEPING, REM} ∧ нет владельца → sleep-зеркало;
        sleep-владелец ∧ вышел из сна → COMPLETED; sleep-владелец ∧ NPC
        мёртв/отсутствует → INTERRUPTED(SLEEP_VANISHED). Идемпотентно;
        конфликт с чужим инкумбентом → коллизия-телеметрия (S203.6, №19).
        """
        if not (COMMITMENT_REGISTRY_ENABLED and S203_4_OWNERSHIP_MIRRORS):
            return
        _alive = set()
        for _npc in npcs or []:
            _nid = _npc.get("npc_id") or _npc.get("id") or ""
            if not _nid:
                continue
            _alive.add(_nid)
            if (_npc.get("body_state", {}).get("life_status")) == "DEAD":
                continue
            _mode = (
                (_npc.get("body_state", {}) or {})
                .get("coupling_profile", {})
                .get("coupling_mode", "")
            )
            _cm = CommitmentRegistry.get_active(scene_state, _nid)
            if _mode in ("SLEEPING", "REM"):
                if _cm is None:
                    _created = CommitmentRegistry._commit_nonsuperseding(
                        scene_state, tick, _nid, action="SLEEP",
                        cause="sleep:coupling", executor="sleep",
                    )
                    if _created is not None:
                        # Сон = born-EXECUTING (NPC спит СЕЙЧАС, не «обязуется»);
                        # COMPLETED доступен только из EXECUTING (FSM-закон).
                        CommitmentRegistry.mark_executing(scene_state, _nid, tick)
            elif _cm is not None and _cm.get("executor") == "sleep":
                CommitmentRegistry.complete(scene_state, _nid, tick)
        for _nid, _cm in list((scene_state.get(_KEY_ACTIVE) or {}).items()):
            if _cm.get("executor") == "sleep" and _nid not in _alive:
                CommitmentRegistry.interrupt(
                    scene_state, _nid, tick, "SLEEP_VANISHED"
                )

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
        from app.domain.action_commitment import (
            INTERRUPT_SLEEP_VANISHED,
            INTERRUPT_TASK_VANISHED,
            INTERRUPT_WINDUP_STALE_INTENT,
        )

        # S203.4 (Э5-e): grace safety-net для не-traversal исполнителей.
        # > худшей резиденции canonical в очереди (~20 тиков при pacing 1/тик).
        _TASK_GRACE_TICKS = 25
        _GRACE_REASONS = {
            "task": INTERRUPT_TASK_VANISHED,
            "windup": INTERRUPT_WINDUP_STALE_INTENT,
            "sleep": INTERRUPT_SLEEP_VANISHED,
        }
        active = scene_state.get(_KEY_ACTIVE) or {}
        traversals = scene_state.get("active_traversals") or {}
        swept = 0
        for npc_id in list(active.keys()):
            commitment = active[npc_id]
            _executor = commitment.get("executor") or ""
            if _executor == "traversal" and npc_id not in traversals:
                CommitmentRegistry.interrupt(
                    scene_state, npc_id, tick, _INTERRUPT_VANISHED
                )
                swept += 1
            elif commitment.get("status") == "BLOCKED":
                # S203.4 (Ц5): BLOCKED → FAILED после BLOCKED_TIMEOUT_TICKS=10.
                # Dead-but-ready: продюсера BLOCKED пока нет (TZ Scenario C
                # «impossible» — закроется когда появится mark_blocked producer).
                _bsince = commitment.get("blocked_since_tick")
                if _bsince is not None and tick - _bsince > 10:
                    from app.domain.action_commitment import FAIL_BLOCKED_TIMEOUT

                    CommitmentRegistry.fail(
                        scene_state, npc_id, tick, FAIL_BLOCKED_TIMEOUT
                    )
                    swept += 1
            elif _executor in _GRACE_REASONS:
                # Outbox-дренаж — основной путь терминалов; sweep ловит
                # осиротевших (save/load-потеря очереди, async-гонки,
                # забытые хуки). Grace > worst-case резиденции → ложных
                # срабатываний нет при здоровом outbox-дренаже.
                _last = (
                    commitment.get("updated_tick")
                    or commitment.get("created_tick")
                    or 0
                )
                if tick - _last > _TASK_GRACE_TICKS:
                    CommitmentRegistry.interrupt(
                        scene_state, npc_id, tick, _GRACE_REASONS[_executor]
                    )
                    swept += 1
        if swept:
            logger.warning(
                f"[COMMITMENT][SWEEP] tick={tick} vanished={swept} "
                f"(unmirrored bypass paths / grace timeout)"
            )
        return swept
