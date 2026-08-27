"""
Канонический контракт traversal_dict — единственный источник истины.

Оба писателя (EventCompiler, SSM.apply_change) обязаны использовать
эту схему для создания traversal_dict. Любой новый ключ добавляется
ТОЛЬКО через изменение этого файла.

ADR-XXX: Traversal Schema Canonization.
"""

from typing import Any, Dict, List

# Ключи, которые ОБЯЗАНЫ присутствовать в каждом traversal_dict
TRAVERSAL_REQUIRED_KEYS: tuple[str, ...] = (
    "npc_id",
    "from_node",
    "target_node",
    "path_waypoints",  # List[List[float]] — нормализованный после JSON round-trip
    "speed",
    "started_tick",
    "duration_ticks",
    "locomotion",
    "status",
    "segment_modes",  # S134.1: Кинематический инвариант
    "segment_arc_heights",  # S134.1: Кинематический инвариант
)

# Дефолтные значения для создания нового traversal_dict
TRAVERSAL_DEFAULTS: dict[str, object] = {
    "speed": 2.0,
    "locomotion": "WALK",
    "status": "MOVING",
    "current_waypoint_idx": 0,  # Фронтенду нужен — добавляем в persistence
    "segment_modes": ["WALK"],  # S132.1: Сохраняем семантику сегментов для Execution Kernel
    "segment_arc_heights": [0.0],  # S132.1: Высота дуги для каждого сегмента
}

# Допустимые значения status (lifecycle state machine)
TRAVERSAL_STATUSES: tuple[str, ...] = (
    "PENDING",
    "MOVING",
    "COMPLETED",
    "CANCELLED",
)

# Валидные переходы (from_status → set(to_status))
TRAVERSAL_TRANSITIONS: dict[str, set[str]] = {
    "PENDING": {"MOVING"},
    "MOVING": {"COMPLETED", "CANCELLED"},
    "COMPLETED": set(),  # terminal — zombie cleanup only
    "CANCELLED": set(),  # terminal — zombie cleanup only
}


def transition_traversal(traversal_dict: Dict[str, Any], new_status: str) -> bool:
    """Выполняет переход статуса traversal через state machine.

    Возвращает True если переход разрешён и выполнен.
    Возвращает False если переход запрещён (и логирует предупреждение).

    Единственный разрешённый способ изменения статуса traversal.
    Прямое присвоение traversal_dict["status"] = ... ЗАПРЕЩЕНО.
    """
    current_status = traversal_dict.get("status", "UNKNOWN")
    allowed = TRAVERSAL_TRANSITIONS.get(current_status, set())

    if new_status not in allowed:
        import logging

        logging.warning(
            f"[TRAVERSAL_FSM] Invalid transition: {current_status} → {new_status} "
            f"for npc={traversal_dict.get('npc_id', '?')}. "
            f"Allowed: {allowed}"
        )
        return False

    traversal_dict["status"] = new_status
    return True


def validate_traversal_dict(data: Dict[str, Any]) -> List[str]:
    """Валидирует traversal_dict против схемы. Возвращает список ошибок."""
    errors = []
    for key in TRAVERSAL_REQUIRED_KEYS:
        if key not in data:
            errors.append(f"missing required key: {key}")
    if data.get("status") not in TRAVERSAL_STATUSES:
        errors.append(f"invalid status: {data.get('status')}")
    if not isinstance(data.get("path_waypoints"), list):
        errors.append("path_waypoints must be list")

    # S134.1: Кинематический инвариант (пустые массивы допустимы при 1 waypoint)
    expected_segments = max(0, len(data.get("path_waypoints", [])) - 1)
    seg_modes = data.get("segment_modes")
    seg_arcs = data.get("segment_arc_heights")

    if seg_modes is None or seg_arcs is None:
        errors.append("missing segment_modes or segment_arc_heights")
    elif not isinstance(seg_modes, list) or not isinstance(seg_arcs, list):
        errors.append("segment_modes and segment_arc_heights must be lists")
    elif len(seg_modes) != expected_segments:
        errors.append(f"len(segment_modes) ({len(seg_modes)}) != expected ({expected_segments})")
    elif len(seg_arcs) != expected_segments:
        errors.append(f"len(segment_arc_heights) ({len(seg_arcs)}) != expected ({expected_segments})")

    return errors


from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class TraversalProposal:
    """Causal artifact: immutable proposal for physical movement.

    ADR-O-323: Created exclusively by MovementPlanner. Contains all
    validated data needed for materialization. Includes topology_version
    to detect stale proposals if spatial authority changed.
    """
    npc_id: str
    source_node: str
    target_node: str
    path_waypoints: tuple[tuple[float, float], ...]
    distance: float
    speed: float
    duration_ticks: int
    source_intent_id: str
    planned_tick: int
    topology_version: int  # ADR-O-323: Stale detection. Mandatory contract.
    # S131: Сохранение семантики сегментов (WALK/JUMP) для будущей кинематики.
    segment_modes: tuple[str, ...] = ("WALK",)
    # S131.1: Источник планирования (Local Traversal или A* Fallback).
    planning_source: str = "LOCAL_TRAVERSAL"
    # S132.1: Высота дуги для каждого сегмента (0.0 для WALK, max_jump_height для JUMP).
    segment_arc_heights: tuple[float, ...] = (0.0,)


class MovementPlanStatus(Enum):
    ACCEPTED = "ACCEPTED"  # MACRO_TRAVERSAL
    REJECTED = "REJECTED"
    MICRO_MOVEMENT = "MICRO_MOVEMENT"  # ADR-O-323: Snap или микро-перемещение, не создаёт TraversalProposal
    ALREADY_AT_TARGET = "ALREADY_AT_TARGET"  # S-141: NPC уже на цели, NO-OP


@dataclass(frozen=True)
class MovementPlanResult:
    """Result of MovementPlanner planning attempt.

    If ACCEPTED, contains valid TraversalProposal.
    If REJECTED, contains reason. REJECTED proposals must NOT
    reach materialization layer.
    """
    status: MovementPlanStatus
    proposal: Optional[TraversalProposal] = None
    reason: str = ""

    def __post_init__(self) -> None:
        """ADR-O-323: Инварианты результата планирования."""
        if self.status is MovementPlanStatus.ACCEPTED:
            if self.proposal is None:
                raise ValueError("ACCEPTED result requires proposal")
        # MICRO_MOVEMENT не требует proposal — это snap local_position без Traversal
        # REJECTED также не требует proposal
        if self.status is MovementPlanStatus.REJECTED:
            if self.proposal is not None:
                raise ValueError("REJECTED result cannot contain proposal")


# S203.3 (Stage 2A, ADR-O-363; закон Мастера): INTERRUPT — lifecycle-операция
# над ДВУМЯ рельсами (traversal FSM + commitment registry). Частичный успех
# запрещён: interrupt не успешен, пока оба слоя не достигли согласованного
# terminal. Реализация — prepare-then-commit: обе мутации валидируются ДО
# первой записи; между валидацией и записью детерминированный успех;
# исключение между двумя записями — rollback первой (единственный остаточный
# путь, покрытие тестом atomicity_rollback).
_INTERRUPT_TRAVERSAL_REASONS = frozenset({
    "CROSS_LOCATION_MATERIALIZE",   # Н-46a: ME:330 (был pop)
    "CROSS_LOCATION_TRANSFER",      # Н-46c: ORCH:967 (был pop, BUG-SLEEP-013)
    # S203.4 (ADR-O-365): арбитр-INTERRUPT — кандидат превысил приоритетный
    # порог. Расширение реестра причин = мини-ADR (закон №16): ADR-O-365
    # и есть эта запись.
    "PRIORITY_SUPERSEDE",
})


def interrupt_traversal(
    scene_state: Dict[str, Any],
    npc_id: str,
    reason: str,
    tick: int,
) -> bool:
    """Атомарный interrupt traversal+commitment (S203.3).

    True  = INTERRUPTED_NOW: traversal CANCELLED, commitment INTERRUPTED(reason),
            запись живёт до SSM-GC (TES не двигает не-MOVING — executor stop
            самим статусом; guard in-flight блокирует stale-материализацию).
    False = ALREADY_TERMINAL (no-op, консистентно) | NOT_FOUND (записи нет:
            legacy-GC/чужой путь — НЕ то же самое, что уже-interrupted) |
            REJECTED_INVALID_STATE (commitment не прерываем; ни один слой
            не мутирован — частичный interrupt запрещён).
    reason обязан быть из реестра причин — расширение = мини-ADR (класс
    причинных констант, прецедент _INTENT_EVENT_MAP ADR-O-349).
    """
    if reason not in _INTERRUPT_TRAVERSAL_REASONS:
        raise ValueError(f"interrupt_traversal: unknown reason '{reason}'")

    traversals = scene_state.get("active_traversals") or {}
    trav = traversals.get(npc_id)
    if trav is None:
        # NOT_FOUND: записи нет — оценивать commitment-слой нечем;
        # вызывающий путь решает сам (у cross-loc путей commitment
        # осиротеет и будет снят sweep'ом либо суперсессией).
        return False
    if trav.get("status") != "MOVING":
        # ALREADY_TERMINAL (COMPLETED/CANCELLED): физика уже остановлена;
        # no-op успешен по определению атомарности.
        return False

    # ── PREPARE (без мутаций): валидны ли ОБА перехода? ──────────────
    _commitments = scene_state.get("active_commitments") or {}
    cm = _commitments.get(npc_id)
    # Заглушка-двойник для валидации FSM commitment-перехода без мутации:
    # INTERRUPTED разрешён из {COMMITTED, EXECUTING, BLOCKED} и требует
    # interrupt_reason (проверяем локальной копией словаря).
    _cm_transition_ok = False
    if cm is not None:
        _probe = dict(cm)
        _cm_transition_ok = transition_commitment_preview(_probe, "INTERRUPTED", reason)
    # Если активного commitment нет (осиротел / legacy-мир без реестра) —
    # рельс ownership уже terminal-consistent (нет владельца = нечему
    # прерываться); interrupt traversal валиден и атомарен по факту.

    # traversal-переход валидируем так же без мутации:
    _trav_probe = dict(trav)
    _trav_transition_ok = transition_traversal(_trav_probe, "CANCELLED")

    if not _trav_transition_ok:
        return False  # REJECTED_INVALID_STATE; ничего не мутировано
    if cm is not None and not _cm_transition_ok:
        return False  # REJECTED_INVALID_STATE; ничего не мутировано

    # ── COMMIT (обе записи; после валидации обе обязаны удаться) ─────
    # §1.2 (domain purity): запись commitment-рельса — доменным API
    # transition_commitment + перенос в history (структура реестра:
    # active_commitments / commitment_history / cap — константы домена).
    # Никаких импортов services из domain.
    from app.domain.action_commitment import (
        COMMITMENT_HISTORY_CAP_PER_NPC,
        transition_commitment,
    )

    transition_traversal(trav, "CANCELLED")
    if cm is not None:
        if not transition_commitment(cm, "INTERRUPTED", tick=tick,
                                     interrupt_reason=reason):
            # Невозможно после preview: атомарность нарушена. Полный откат
            # недостижим (CANCELLED terminal) — падаем громко (L4):
            # падение лучше тихого рассинхрона рельсов.
            raise RuntimeError(
                f"interrupt_traversal: commitment-interrupt failed after "
                f"preview for npc={npc_id} — atomicity violated"
            )
        _commitments.pop(npc_id, None)
        _history = scene_state.setdefault("commitment_history", {})
        _bucket = _history.setdefault(npc_id, [])
        _bucket.append(cm)
        if len(_bucket) > COMMITMENT_HISTORY_CAP_PER_NPC:
            del _bucket[: len(_bucket) - COMMITMENT_HISTORY_CAP_PER_NPC]
    return True


def transition_commitment_preview(
    commitment: Dict[str, Any],
    new_status: str,
    interrupt_reason: str = "",
    fail_reason: Optional[str] = None,
) -> bool:
    """S203.3: безмутационная валидация commitment-FSM перехода
    (зеркало transition_commitment из action_commitment).

    S203.4: паритет с fail_reason-контрактом обязателен — рассинхрон
    preview/transition = частичный interrupt (закон №14). interrupt_reason
    получил дефолт: существующий вызов positional-safe."""
    from app.domain.action_commitment import COMMITMENT_TRANSITIONS

    current = commitment.get("status", "")
    if new_status not in COMMITMENT_TRANSITIONS.get(current, set()):
        return False
    if new_status == "INTERRUPTED" and not interrupt_reason:
        return False
    if new_status == "FAILED" and not fail_reason:
        return False
    return True


def build_traversal_dict(proposal: "TraversalProposal") -> Dict[str, Any]:
    """Механический материализатор TraversalProposal в runtime dict.

    ADR-O-323: Не вычисляет семантику пути. Только сериализует авторизованный proposal.
    Единственный разрешённый способ создания traversal_dict.
    BUG-SPATIAL-005 FIX: Используем transition_traversal() FSM для установки статуса MOVING.
    """
    _traversal_dict = {
        "npc_id": proposal.npc_id,
        "from_node": proposal.source_node,
        "target_node": proposal.target_node,
        "path_waypoints": [list(wp) for wp in proposal.path_waypoints],
        "speed": proposal.speed,
        "started_tick": proposal.planned_tick,
        "duration_ticks": proposal.duration_ticks,
        "locomotion": "WALK",
        "status": "PENDING",
        "current_waypoint_idx": 0,
        "segment_modes": list(proposal.segment_modes),  # S132.1: Сохраняем семантику сегментов
        "segment_arc_heights": list(proposal.segment_arc_heights),  # S132.1: Сохраняем высоту дуги
    }
    # S203.1 (Н-49): fail-fast против silent-PENDING. Игнорирование отказа
    # порождает мёртвую запись: TES не двигает не-MOVING, zombie-GC не чистит
    # не-terminal, SSM-suppression блокирует новые traversal к той же цели.
    # Ловится здесь, а не превращается в "иногда NPC перестаёт двигаться".
    if not transition_traversal(_traversal_dict, "MOVING"):
        raise ValueError(
            "build_traversal_dict: FSM rejected PENDING->MOVING — "
            "silent PENDING traversal is forbidden (S203.1, Stage 2A)"
        )
    return _traversal_dict
