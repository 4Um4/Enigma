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
)

# Дефолтные значения для создания нового traversal_dict
TRAVERSAL_DEFAULTS: dict[str, object] = {
    "speed": 2.0,
    "locomotion": "WALK",
    "status": "MOVING",
    "current_waypoint_idx": 0,  # Фронтенду нужен — добавляем в persistence
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
    return errors


def build_traversal_dict(
    npc_id: str,
    from_node: str,
    target_node: str,
    path_waypoints: List[Any],
    started_tick: int,
    duration_ticks: int,
    speed: float = 2.0,
    locomotion: str = "WALK",
    current_waypoint_idx: int = 0,
) -> Dict[str, Any]:
    """Единственный разрешённый способ создания traversal_dict.

    Запрещено собирать dict вручную. Все писатели обязаны использовать
    эту функцию.
    """
    return {
        "npc_id": npc_id,
        "from_node": from_node,
        "target_node": target_node,
        "path_waypoints": path_waypoints,
        "speed": speed,
        "started_tick": started_tick,
        "duration_ticks": duration_ticks,
        "locomotion": locomotion,
        "status": "MOVING",
        "current_waypoint_idx": current_waypoint_idx,
    }
