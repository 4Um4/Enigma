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

COMMITMENT_TERMINAL_STATUSES: frozenset = frozenset(
    status for status, targets in COMMITMENT_TRANSITIONS.items() if not targets
)

# Bounded retention терминальной истории на NPC (решение Мастера №1).
# Прецедент: causal_ledger — bounded runtime history.
COMMITMENT_HISTORY_CAP_PER_NPC: int = 10

# Честный cause для legacy-материализаций без upstream provenance (№8).
# Правило №7: слой проекции (SSM) НЕ придумывает behavioral семантику постфактум.
CAUSE_UNKNOWN_LEGACY_SOURCE: str = "UNKNOWN_LEGACY_SOURCE"


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
        # Владелец исполнения: "traversal" (S203.1 shadow) | "windup"/"task"
        # (S203.3/4 — только после доказательства их ownership-контрактов, №6).
        "executor": executor,
        "created_tick": tick,
        "updated_tick": tick,
    }


def transition_commitment(
    commitment: Dict[str, Any],
    new_status: str,
    tick: Optional[int] = None,
    interrupt_reason: Optional[str] = None,
) -> bool:
    """FSM-переход обязательства. True = разрешён и выполнен.

    INTERRUPTED без interrupt_reason запрещён: прерывание обязано нести
    причину прекращения.
    """
    current: str = commitment.get("status", "")
    allowed = COMMITMENT_TRANSITIONS.get(current, set())
    if new_status not in allowed:
        return False
    if new_status == "INTERRUPTED" and not interrupt_reason:
        return False

    commitment["status"] = new_status
    if new_status == "INTERRUPTED":
        commitment["interrupt_reason"] = interrupt_reason
    if tick is not None:
        commitment["updated_tick"] = tick
    return True