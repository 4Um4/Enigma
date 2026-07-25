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

    def __post_init__(self):
        """ADR-O-323: Инварианты результата планирования."""
        if self.status is MovementPlanStatus.ACCEPTED:
            if self.proposal is None:
                raise ValueError("ACCEPTED result requires proposal")
        # MICRO_MOVEMENT не требует proposal — это snap local_position без Traversal
        # REJECTED также не требует proposal
        if self.status is MovementPlanStatus.REJECTED:
            if self.proposal is not None:
                raise ValueError("REJECTED result cannot contain proposal")


def build_traversal_dict(proposal: "TraversalProposal") -> Dict[str, Any]:
    """Механический материализатор TraversalProposal в runtime dict.

    ADR-O-323: Не вычисляет семантику пути. Только сериализует авторизованный proposal.
    Единственный разрешённый способ создания traversal_dict.
    """
    return {
        "npc_id": proposal.npc_id,
        "from_node": proposal.source_node,
        "target_node": proposal.target_node,
        "path_waypoints": [list(wp) for wp in proposal.path_waypoints],
        "speed": proposal.speed,
        "started_tick": proposal.planned_tick,
        "duration_ticks": proposal.duration_ticks,
        "locomotion": "WALK",
        "status": "MOVING",
        "current_waypoint_idx": 0,
        "segment_modes": list(proposal.segment_modes),  # S132.1: Сохраняем семантику сегментов
        "segment_arc_heights": list(proposal.segment_arc_heights),  # S132.1: Сохраняем высоту дуги
    }
