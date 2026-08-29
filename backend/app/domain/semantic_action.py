"""
path: backend/app/domain/semantic_action.py
Назначение: W0/W2 — Semantic Action. Интент-уровень действия над объектом мира.
    OPEN, TAKE, CARRY, PLACE, SIT, STAND, USE, ENTER, EXIT, EQUIP, UNEQUIP, ATTACK.
    Не равен animation clip. Не равен traversal. Не равен sprite frame.
    Preconditions — pure predicates over (world_state, npc_body_state).
    INVARIANT (W0): ни одно поле не ссылается на animation, sprite или model.
Зависимости: dataclasses, typing
Основные сущности: SemanticAction, Precondition
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Optional, Tuple


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
    action_type: str                            # OPEN, TAKE, CARRY, PLACE, SIT, ...
    target_object_id: Optional[str] = None     # WorldObject being acted upon
    target_location_id: Optional[str] = None    # for ENTER/EXIT/MOVE
    target_attachment_slot: Optional[str] = None  # for EQUIP (W4: hand.L, waist, ...)
    preconditions: Tuple[Precondition, ...] = ()  # W2: pure predicates

    def to_dict(self) -> dict:
        return {
            "action_type": self.action_type,
            "target_object_id": self.target_object_id,
            "target_location_id": self.target_location_id,
            "target_attachment_slot": self.target_attachment_slot,
            "preconditions": [
                {"predicate": p.predicate, "args": list(p.args)}
                for p in self.preconditions
            ],
        }