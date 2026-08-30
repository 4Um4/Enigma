"""
path: backend/app/domain/semantic_action.py
Назначение: W0/W2 — Semantic Action. Интент-уровень действия над объектом мира.
    Реестр закрыт: WorldActionType (19 значений, ТЗ §19.2; В8, ADR-O-372).
    Расширение реестра = мини-ADR (класс ADR-O-349). STAND → STAND_UP
    (канонизация по ТЗ §19.2). INSERT_ITEM/REMOVE_ITEM зарезервированы (W3).
    Не равен animation clip. Не равен traversal. Не равен sprite frame.
    Preconditions — pure predicates over (world_state, npc_body_state).
    INVARIANT (W0): ни одно поле не ссылается на animation, sprite или model.
Зависимости: dataclasses, typing
Основные сущности: WorldActionType, SemanticAction, Precondition
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional, Tuple


class WorldActionType(str, Enum):
    """W2 (ТЗ §19.2): закрытый реестр объектных действий мира.

    Расширение — только мини-ADR (класс ADR-O-349: сырые строки и тихое
    расширение реестра запрещены). Не равен animation clip / traversal /
    sprite frame (W0-инвариант). Таблица W2 выдаёт 17; INSERT_ITEM и
    REMOVE_ITEM зарезервированы до W3 — в SemanticAction нет поля второго
    объекта (compound-контракт, вердикт Мастера).
    """

    OPEN = "OPEN"
    CLOSE = "CLOSE"
    KNOCK = "KNOCK"
    LOCK = "LOCK"
    UNLOCK = "UNLOCK"
    BREAK = "BREAK"
    PASS_THROUGH = "PASS_THROUGH"
    REPAIR = "REPAIR"
    SIT = "SIT"
    STAND_UP = "STAND_UP"          # W0-остаток «STAND» канонизирован
    TAKE = "TAKE"
    MOVE = "MOVE"
    KICK = "KICK"
    PLACE = "PLACE"
    DROP = "DROP"
    THROW = "THROW"
    DISCARD = "DISCARD"
    INSERT_ITEM = "INSERT_ITEM"    # reserved: W3 (compound)
    REMOVE_ITEM = "REMOVE_ITEM"    # reserved: W3 (compound)


@dataclass(frozen=True)
class Precondition:
    """Pure predicate over (world_state, npc_body_state).
    НЕ вызывает LLM. НЕ делает IO. НЕ мутирует state.

    Examples:
        Precondition("STATE_IS", ("door_42", "CLOSED"))
        Precondition("CAN_GRIP_SMALL_OBJECT", ("npc_17",))
        Precondition("IS_ADJACENT_TO", ("npc_17", "door_42"))
    """
    predicate: str             # named rule ID (W2 registry resolves)
    args: Tuple[Any, ...]


@dataclass(frozen=True)
class SemanticAction:
    """Интент-уровень действия над объектом мира.

    INVARIANT (W0): ни одно поле не ссылается на animation, sprite или model.
    Renderer отдельно решает, как показать это действие (TZ §17, §27).
    """
    action_type: WorldActionType                # закрытый реестр (WorldActionType)
    target_object_id: Optional[str] = None     # WorldObject being acted upon
    target_location_id: Optional[str] = None    # for ENTER/EXIT/MOVE
    target_attachment_slot: Optional[str] = None  # for EQUIP (W4: hand.L, waist, ...)
    preconditions: Tuple[Precondition, ...] = ()  # W2: pure predicates

    def __post_init__(self) -> None:
        # Нормализация str → enum на рождении объекта (В8: закрытый реестр).
        # Легальная запись в frozen dataclass (не runtime-мутация NPCState).
        if not isinstance(self.action_type, WorldActionType):
            object.__setattr__(
                self, "action_type", WorldActionType(self.action_type)
            )

    def to_dict(self) -> dict:
        return {
            "action_type": self.action_type.value,
            "target_object_id": self.target_object_id,
            "target_location_id": self.target_location_id,
            "target_attachment_slot": self.target_attachment_slot,
            "preconditions": [
                {"predicate": p.predicate, "args": list(p.args)}
                for p in self.preconditions
            ],
        }
