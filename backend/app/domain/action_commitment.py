"""
path: /project/backend/app/domain/action_commitment.py
Назначение: Доменный контракт поведенческого владения (Commitment Layer, S203.1 / Stage 2A).
    Commitment = "что NPC действительно обязан исполнять" — онтологический слой
    между решением (Intent/Task) и физическим исполнением (Traversal/Windup/Task).
    Три несводимых FSM: TaskState (работа) / TraversalState (физика) /
    CommitmentState (владение) — объединение запрещено (матрица Мастера, №10).
Зависимости: hashlib, typing (чистый домен — без сервисов и моделей)
Основные сущности: COMMITMENT_STATUSES, COMMITMENT_TRANSITIONS,
    COMMITMENT_TERMINAL_STATUSES, build_commitment_id, build_commitment_dict,
    transition_commitment, CAUSE_UNKNOWN_LEGACY_SOURCE
"""

from __future__ import annotations

import hashlib
from typing import Any, Dict, Optional

# ── Status FSM (Stage 2A: Unified Behavioral Ownership) ────────────────────
# PROPOSED/COMMITTED — делиберативные фазы: зазор между решением и исполнением,
# которого traversal никогда не имел (Н-50: PENDING виртуален, рождается MOVING).
# EXECUTING/BLOCKED — фазы исполнения.
# Терминалы — без исходящих переходов: только commitment_history (retained
# bounded, решение Мастера №1) и новый commitment с parent_commitment_id (№3a).

COMMITMENT_STATUSES: tuple[str, ...] = (
    "PROPOSED",
    "COMMITTED",
    "EXECUTING",
    "BLOCKED",
    "COMPLETED",
    "FAILED",
    "INTERRUPTED",
    "EXPIRED",
    "CANCELLED",
)

COMMITMENT_TRANSITIONS: dict[str, set[str]] = {
    "PROPOSED": {"COMMITTED", "CANCELLED"},
    # COMMITTED->BLOCKED: TZ Scenario C (COMMITTED -> BLOCKED -> FAILED / REPLAN).
    "COMMITTED": {"EXECUTING", "BLOCKED", "CANCELLED", "EXPIRED", "INTERRUPTED"},
    # S203.1 fix: CANCELLED (сознательное снятие) доступен из ЛЮБОЙ активной фазы —
    # передумал посреди исполнения = CANCELLED, а не INTERRUPTED (последний требует
    # внешнего каузального события). Поймано test_terminal_variants (семантический
    # слой vs контрактный: матрица тавтологична таблице и не видит таких дыр).
    "EXECUTING": {"COMPLETED", "FAILED", "BLOCKED", "INTERRUPTED", "EXPIRED", "CANCELLED"},
    # BLOCKED->INTERRUPTED: заблокированное обязательство обязано уметь уступать
    # более высокой потребности (TZ §7), иначе BLOCKED = вечный лок.
    # BLOCKED->CANCELLED: REPLAN из Scenario C TZ (BLOCKED -> FAILED / REPLAN).
    "BLOCKED": {"EXECUTING", "FAILED", "EXPIRED", "INTERRUPTED", "CANCELLED"},
    "COMPLETED": set(),  # terminal
    "FAILED": set(),  # terminal
    "INTERRUPTED": set(),  # terminal (№3: резюм = НОВЫЙ commitment, не продолжение)
    "EXPIRED": set(),  # terminal
    "CANCELLED": set(),  # terminal
}

COMMITMENT_TERMINAL_STATUSES: frozenset[str] = frozenset(
    status for status, targets in COMMITMENT_TRANSITIONS.items() if not targets
)

# S203.2 (Мастер, обязательное решение): ACTIVE = статусы, в которых NPC ЗАНЯТ.
# COMMITTED включён явно: обязательство между COMMIT и материализацией НЕ делает
# NPC свободным (защита от commitment race). PROPOSED — превентивно: кандидат
# в рассмотрении тоже занимает владельца (появится в S203.3/4; зеркала его не
# создают). Терминалы в ACTIVE не входят по построению.
ACTIVE_COMMITMENT_STATUSES: frozenset[str] = frozenset({
    "PROPOSED",
    "COMMITTED",
    "EXECUTING",
    "BLOCKED",
})

# Bounded retention терминальной истории на NPC (решение Мастера №1).
# Прецедент: causal_ledger — bounded runtime history.
COMMITMENT_HISTORY_CAP_PER_NPC: int = 10

# Честный cause для legacy-материализаций без upstream provenance (№8).
# Правило №7: слой проекции (SSM) НЕ придумывает behavioral семантику постфактум.
CAUSE_UNKNOWN_LEGACY_SOURCE: str = "UNKNOWN_LEGACY_SOURCE"

# ── S203.4 (ADR-O-365): реестры причинных констант ─────────────────────────
# Закон №16: причины — реестры констант; расширение = мини-ADR (прецеденты:
# _INTENT_EVENT_MAP ADR-O-349; _INTERRUPT_TRAVERSAL_REASONS S219).

# interrupt_reason — ПОЧЕМУ ПРЕКРАЩЁН (внешнее каузальное событие):
INTERRUPT_PRIORITY_SUPERSEDE: str = "PRIORITY_SUPERSEDE"  # арбитр-INTERRUPT (S203.4)
INTERRUPT_TASK_VANISHED: str = "TASK_VANISHED"  # sweep: task-исполнитель исчез (grace)
INTERRUPT_WINDUP_STALE_INTENT: str = "WINDUP_STALE_INTENT"  # Фаза 7: stale-интент
INTERRUPT_SLEEP_VANISHED: str = "SLEEP_VANISHED"  # reconciliation: спящий исчез

# fail_reason — ПОЧЕМУ ПРОВАЛЕНО (D-6: отдельный контракт; №7 распространён:
# cause ≠ interrupt_reason ≠ fail_reason, универсальное reason запрещено):
FAIL_BLOCKED_TIMEOUT: str = "BLOCKED_TIMEOUT"  # BLOCKED дольше BLOCKED_TIMEOUT_TICKS (Ц5)
FAIL_TASK_ERROR: str = "TASK_ERROR"  # task-исполнитель вернул error-artifact
FAIL_TASK_CRASH: str = "TASK_CRASH"  # исключение в исполнении задачи
# TZ Scenario C: pre-condition провален навсегда (цель уничтожена, путь
# закрыт) — REPLAN-семантика; потребитель — Э5/C-сценарий гейта.
FAIL_TASK_IMPOSSIBLE: str = "TASK_IMPOSSIBLE"


def build_commitment_id(tick: int, npc_id: str, action: str, ordinal: int) -> str:
    """Детерминированная идентичность обязательства.

    same (tick, npc_id, action, ordinal) -> same commitment_id.
    Прецедент: build_snapshot (md5-сид вместо uuid4). Нарушение детерминизма =
    INV-REPLAY-DETERMINISM. Архитектурно важна воспроизводимость, не криптостойкость.
    """
    _seed = f"{tick}:{npc_id}:{action}:{ordinal}".encode("utf-8")
    return f"cmt-{hashlib.md5(_seed).hexdigest()}"


def build_commitment_dict(
    tick: int,
    npc_id: str,
    action: str,
    ordinal: int,
    cause: str,
    target_id: Optional[str] = None,
    executor: str = "",
    parent_commitment_id: Optional[str] = None,
    initial_status: str = "PROPOSED",
    # ── S203.4 (ADR-O-365): приоритетная политика + executor-ссылка ─────────
    priority: int = 0,
    priority_policy_version: Optional[str] = None,
    executor_ref: Optional[str] = None,
) -> Dict[str, Any]:
    """Единственный легальный способ создания commitment-записи.

    №4: ordinal — часть персистентной монотонной последовательности идентичностей
    NPC (никогда не уменьшается, никогда не переиспользуется).
    №3a: parent_commitment_id — каузальная связь "новое обязательство произошло
    из прерванного" (C2 произошёл из C1, а не "продолжает" его).
    """
    if initial_status not in COMMITMENT_STATUSES:
        raise ValueError(
            f"build_commitment_dict: unknown initial_status '{initial_status}'"
        )
    if not cause:
        # Обязательство без причины возникновения запрещено (каузальная гигиена).
        raise ValueError("build_commitment_dict: empty cause is forbidden")

    return {
        "commitment_id": build_commitment_id(tick, npc_id, action, ordinal),
        "npc_id": npc_id,
        "action": action,
        "ordinal": ordinal,
        "status": initial_status,
        # cause: ПОЧЕМУ ВОЗНИК (будущая проекция в CausalLedger).
        # interrupt_reason: ПОЧЕМУ ПРЕКРАЩЁН. Смешивание запрещено —
        # универсальное поле reason = semantic sludge (матрица Мастера).
        "cause": cause,
        "interrupt_reason": None,
        "parent_commitment_id": parent_commitment_id,
        "target_id": target_id,
        # Владелец исполнения: "traversal" (S203.1/S203.3) | "windup"/"task"
        # (S203.4, ADR-O-365) | "sleep" (S203.4: state-based reconciliation).
        "executor": executor,
        # S203.4: ссылка на объект исполнителя (task_id / held_intent_id) —
        # join терминальных зеркал и телеметрии с исполнителем.
        "executor_ref": executor_ref,
        # S203.4 (D-5): приоритет — РЕЗУЛЬТАТ policy на момент создания.
        # Replay читает записанное число, пересчёт запрещён. 0 + None-версия
        # = legacy-запись без заявленного права на прерывание.
        "priority": priority,
        "priority_policy_version": priority_policy_version,
        "created_tick": tick,
        "updated_tick": tick,
        # S203.4: старт часов BLOCKED_TIMEOUT (Ц5). None вне фазы BLOCKED;
        # ведётся transition_commitment (Э2-b: вход/выход из BLOCKED).
        "blocked_since_tick": None,
        # fail_reason: ПОЧЕМУ ПРОВАЛЕНО (D-6, №7: cause ≠ interrupt_reason
        # ≠ fail_reason). Заполняется только при переходе в FAILED.
        "fail_reason": None,
    }


def transition_commitment(
    commitment: Dict[str, Any],
    new_status: str,
    tick: Optional[int] = None,
    interrupt_reason: Optional[str] = None,
    fail_reason: Optional[str] = None,
) -> bool:
    """FSM-переход обязательства. True = разрешён и выполнен.

    INTERRUPTED без interrupt_reason запрещён: прерывание обязано нести
    причину прекращения. S203.4 (D-6): FAILED без fail_reason запрещён —
    симметрия; провал обязан нести причину (cause ≠ interrupt_reason
    ≠ fail_reason, №7).
    """
    current: str = commitment.get("status", "")
    allowed = COMMITMENT_TRANSITIONS.get(current, set())
    if new_status not in allowed:
        return False
    if new_status == "INTERRUPTED" and not interrupt_reason:
        return False
    if new_status == "FAILED" and not fail_reason:
        return False

    commitment["status"] = new_status
    if new_status == "INTERRUPTED":
        commitment["interrupt_reason"] = interrupt_reason
    if new_status == "FAILED":
        commitment["fail_reason"] = fail_reason
    # S203.4 (Ц5): часы BLOCKED-фазы для таймаут-продюсера (Э7). Вход в
    # BLOCKED заводит часы (tick=None → часы не заведены: sweep такой записи
    # не таймаутит — честное отсутствие сигнала, не ноль); любой выход из
    # BLOCKED (EXECUTING/терминалы) — сброс.
    if new_status == "BLOCKED":
        commitment["blocked_since_tick"] = tick
    elif current == "BLOCKED":
        commitment["blocked_since_tick"] = None
    if tick is not None:
        commitment["updated_tick"] = tick
    return True
