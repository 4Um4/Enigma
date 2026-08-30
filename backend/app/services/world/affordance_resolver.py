"""
path: backend/app/services/world/affordance_resolver.py
Назначение: W2 (ТЗ Часть II §21, ADR-O-372) — AffordanceResolver.
    Pure function: (WorldObject, BodyStateView, npc_position)
    → Tuple[SemanticAction, ...]. Возвращает действия, чьи предусловия
    выполнены СЕЙЧАС; каждое действие несёт полный precondition-кортеж
    для ревалидации W3 (transition_object). Stored-поля affordances на
    WorldObject нет и не будет (ADR-O-371: производная не хранится).
    Ноль LLM, ноль IO, ноль мутаций (ТЗ §21.3). Substrate-only: ноль
    runtime-потребителей (доктрина M1a); первый легальный writer — W3.
Зависимости: app.domain (world_object, semantic_action, body_state_view, constants)
Основные сущности: AffordanceResolver, PRECONDITION_REGISTRY, effective_state
"""
import math
from dataclasses import replace
from typing import Any, Callable, Dict, Tuple

from app.domain.body_state_view import BodyStateView
from app.domain.constants import AFFORDANCE_ADJACENCY_RADIUS_M
from app.domain.semantic_action import Precondition, SemanticAction, WorldActionType
from app.domain.world_object import CarrierMode, WorldObject

# ── Реестр предикатов v1 (В4; закрыт: расширение = мини-ADR) ─────────

PreconditionEvaluator = Callable[
    [WorldObject, BodyStateView, Tuple[float, float], Tuple[Any, ...]],
    bool,
]


def _pred_is_alive(
    obj: WorldObject,
    body: BodyStateView,
    npc_position: Tuple[float, float],
    args: Tuple[Any, ...],
) -> bool:
    """Ось жизни (ADR-123). DISABLED-sentinel даёт False через оси."""
    return body.is_alive


def _pred_is_conscious(
    obj: WorldObject,
    body: BodyStateView,
    npc_position: Tuple[float, float],
    args: Tuple[Any, ...],
) -> bool:
    """Ось сознания (ADR-123)."""
    return body.is_conscious


def _pred_is_capable(
    obj: WorldObject,
    body: BodyStateView,
    npc_position: Tuple[float, float],
    args: Tuple[Any, ...],
) -> bool:
    """Ось дееспособности (ADR-123)."""
    return body.is_capable


def _pred_state_is(
    obj: WorldObject,
    body: BodyStateView,
    npc_position: Tuple[float, float],
    args: Tuple[Any, ...],
) -> bool:
    """Эффективное состояние объекта == ожидаемому.

    Ревалидация W3: состояние/отношения могли измениться между resolve
    и исполнением — устаревшее действие обязано провалиться здесь.
    """
    (expected_state,) = args
    return effective_state(obj) == expected_state


def _pred_is_adjacent_to(
    obj: WorldObject,
    body: BodyStateView,
    npc_position: Tuple[float, float],
    args: Tuple[Any, ...],
) -> bool:
    """Евклидова близость ≤ AFFORDANCE_ADJACENCY_RADIUS_M.

    Позиция авторитетна ТОЛЬКО в CarrierMode.FREE (ADR-O-371);
    в HELD/CONTAINED/ATTACHED смежность честно False (§ENIGMA-003).
    """
    if obj.carrier_mode is not CarrierMode.FREE:
        return False
    return (
        math.hypot(
            obj.position[0] - npc_position[0],
            obj.position[1] - npc_position[1],
        )
        <= AFFORDANCE_ADJACENCY_RADIUS_M
    )


def _pred_holder_is(
    obj: WorldObject,
    body: BodyStateView,
    npc_position: Tuple[float, float],
    args: Tuple[Any, ...],
) -> bool:
    """Объект держит именно этот NPC (HELD_BY ≡ npc_id). Близость не нужна."""
    return obj.holder is not None and obj.holder == body.npc_id


def _pred_occupant_is(
    obj: WorldObject,
    body: BodyStateView,
    npc_position: Tuple[float, float],
    args: Tuple[Any, ...],
) -> bool:
    """Объект занят именно этим NPC (OCCUPIED_BY ≡ npc_id)."""
    return obj.occupancy is not None and obj.occupancy == body.npc_id


PRECONDITION_REGISTRY: Dict[str, PreconditionEvaluator] = {
    "IS_ALIVE": _pred_is_alive,
    "IS_CONSCIOUS": _pred_is_conscious,
    "IS_CAPABLE": _pred_is_capable,
    "STATE_IS": _pred_state_is,
    "IS_ADJACENT_TO": _pred_is_adjacent_to,
    "HOLDER_IS": _pred_holder_is,
    "OCCUPANT_IS": _pred_occupant_is,
}


# ── Эффективное состояние (W2-проекция нормализованных полей W1) ─────


def effective_state(obj: WorldObject) -> str:
    """Нормализованные поля W1 (ADR-O-371) → семантическое состояние ТЗ §19.2.

    door/container: state-поле (настоящий FSM, ТЗ §22.1).
    chair: производная — BROKEN(state) > HELD(holder) > OCCUPIED(occupancy)
    > AVAILABLE (ТЗ-состояния AVAILABLE/OCCUPIED/HELD нормализованы W1 в
    отношения; MOVED — legacy-состояние, вне модели). W3 может канонизировать
    проекцию в домене при переходе к FSM.
    """
    if obj.archetype == "chair":
        if obj.state == "BROKEN":
            return "BROKEN"
        if obj.holder is not None:
            return "HELD"
        if obj.occupancy is not None:
            return "OCCUPIED"
        return "AVAILABLE"
    return obj.state


# ── Таблица affordances v1 (ТЗ §19.2 + В10-правка Мастера) ───────────
# Базовая тройка (В9: явные preconditions, не скрытый гейт) и
# STATE_IS(эффективное состояние) прикрепляются каждому действию (_actions).


_BASE_PRECONDITIONS: Tuple[Precondition, ...] = (
    Precondition("IS_ALIVE", ()),
    Precondition("IS_CONSCIOUS", ()),
    Precondition("IS_CAPABLE", ()),
)
_ADJ: Tuple[Precondition, ...] = (Precondition("IS_ADJACENT_TO", ()),)
_HOLD: Tuple[Precondition, ...] = (Precondition("HOLDER_IS", ()),)
_OCC: Tuple[Precondition, ...] = (Precondition("OCCUPANT_IS", ()),)


def _actions(
    key: Tuple[str, str],
    specs: Tuple[Tuple[WorldActionType, Tuple[Precondition, ...]], ...],
) -> Tuple[SemanticAction, ...]:
    """Строит строку таблицы (статично, на импорте модуля)."""
    _archetype, eff_state = key
    row = []
    for action_type, extra in specs:
        row.append(
            SemanticAction(
                action_type=action_type,
                preconditions=(
                    _BASE_PRECONDITIONS
                    + (Precondition("STATE_IS", (eff_state,)),)
                    + extra
                ),
            )
        )
    return tuple(row)


_AFFORDANCE_TABLE: Dict[Tuple[str, str], Tuple[SemanticAction, ...]] = {
    # ── door: state-поле = FSM (ТЗ §22.1) ──
    ("door", "CLOSED"): _actions(
        ("door", "CLOSED"),
        (
            (WorldActionType.OPEN, _ADJ),
            (WorldActionType.KNOCK, _ADJ),
            (WorldActionType.LOCK, _ADJ),
            (WorldActionType.UNLOCK, _ADJ),
            (WorldActionType.BREAK, _ADJ),
        ),
    ),
    # В10-правка (Мастер): пара OPEN+CLOSE в состоянии OPEN — FSM door
    # допускает оба перехода (CLOSED→OPEN, OPEN→CLOSED). Физическая
    # доступность (ручка) ≠ FSM-легальность; легальность решает W3.
    ("door", "OPEN"): _actions(
        ("door", "OPEN"),
        (
            (WorldActionType.OPEN, _ADJ),
            (WorldActionType.CLOSE, _ADJ),
            (WorldActionType.PASS_THROUGH, _ADJ),
            (WorldActionType.LOCK, _ADJ),
        ),
    ),
    ("door", "LOCKED"): _actions(
        ("door", "LOCKED"),
        (
            (WorldActionType.UNLOCK, _ADJ),
            (WorldActionType.BREAK, _ADJ),
            (WorldActionType.KNOCK, _ADJ),
        ),
    ),
    ("door", "BROKEN"): _actions(
        ("door", "BROKEN"),
        (
            (WorldActionType.REPAIR, _ADJ),
            (WorldActionType.PASS_THROUGH, _ADJ),
        ),
    ),
    # ── chair: derived rows (см. effective_state) ──
    ("chair", "AVAILABLE"): _actions(
        ("chair", "AVAILABLE"),
        (
            (WorldActionType.SIT, _ADJ),
            (WorldActionType.TAKE, _ADJ),
            (WorldActionType.MOVE, _ADJ),
            (WorldActionType.KICK, _ADJ),
        ),
    ),
    ("chair", "OCCUPIED"): _actions(
        ("chair", "OCCUPIED"),
        (
            (WorldActionType.STAND_UP, _OCC),
            (WorldActionType.KICK, _ADJ),
        ),
    ),
    # HELD: близость не требуется — объект в руках носителя
    ("chair", "HELD"): _actions(
        ("chair", "HELD"),
        (
            (WorldActionType.PLACE, _HOLD),
            (WorldActionType.DROP, _HOLD),
            (WorldActionType.THROW, _HOLD),
        ),
    ),
    ("chair", "BROKEN"): _actions(
        ("chair", "BROKEN"),
        (
            (WorldActionType.REPAIR, _ADJ),
            (WorldActionType.DISCARD, _ADJ),
        ),
    ),
    # ── container: state-поле = FSM (ТЗ §22.1) ──
    ("container", "CLOSED"): _actions(
        ("container", "CLOSED"),
        (
            (WorldActionType.OPEN, _ADJ),
            (WorldActionType.LOCK, _ADJ),
            (WorldActionType.UNLOCK, _ADJ),
            (WorldActionType.BREAK, _ADJ),
        ),
    ),
    # В10-правка: пара OPEN+CLOSE. INSERT_ITEM/REMOVE_ITEM зарезервированы
    # до W3 (нет поля второго объекта в SemanticAction — вердикт Мастера).
    ("container", "OPEN"): _actions(
        ("container", "OPEN"),
        (
            (WorldActionType.OPEN, _ADJ),
            (WorldActionType.CLOSE, _ADJ),
        ),
    ),
    # Известный v1-пробел: container/LOCKED и /DESTROYED ТЗ §19.2 не
    # определяет → честный () (расширение = правка таблицы + тест).
}


class AffordanceResolver:
    """ТЗ §21.1: (object_state, npc_body_state) → доступные действия.

    Pure: ноль LLM / IO / мутаций. Возвращает ТОЛЬКО действия с
    выполненными сейчас предусловиями (ТЗ §21.1: «доступные»); кортежи
    предусловий сохранены для ревалидации W3.
    Caller-контракт: npc_position — в локации объекта (композиция через
    WorldObjectStore.query_objects_at гарантирует это).
    """

    @staticmethod
    def resolve(
        obj: WorldObject,
        npc_body_state: BodyStateView,
        npc_position: Tuple[float, float],
    ) -> Tuple[SemanticAction, ...]:
        candidates = _AFFORDANCE_TABLE.get(
            (obj.archetype, effective_state(obj)), ()
        )
        result = []
        for action in candidates:
            if all(
                _evaluate(obj, npc_body_state, npc_position, p)
                for p in action.preconditions
            ):
                result.append(replace(action, target_object_id=obj.object_id))
        return tuple(result)


def _evaluate(
    obj: WorldObject,
    body: BodyStateView,
    npc_position: Tuple[float, float],
    p: Precondition,
) -> bool:
    evaluator = PRECONDITION_REGISTRY.get(p.predicate)
    if evaluator is None:
        # Громкий онтологический отказ: реестр закрыт (ADR-O-372)
        raise KeyError(
            f"Неизвестный предикат {p.predicate!r}: реестр v1 закрыт "
            "(расширение = мини-ADR, ADR-O-372)"
        )
    return evaluator(obj, body, npc_position, p.args)


def compute_affordances(
    obj: WorldObject,
    npc_body_state: BodyStateView,
    npc_position: Tuple[float, float],
) -> Tuple[SemanticAction, ...]:
    """ТЗ §19.2: каноническое имя pure-функции (алиас resolver'а).

    ВОЗВРАЩАЕТ действия — stored-поля нет (удалён by design, ADR-O-371).
    """
    return AffordanceResolver.resolve(obj, npc_body_state, npc_position)
