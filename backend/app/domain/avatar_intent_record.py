"""
path: /project/backend/app/domain/avatar_intent_record.py
Назначение: Avatar agency — thin wrapper для self-formed Intent.
    НЕ новый Intent system — использует существующий Intent (enum) +
    существующий IntentIdentity (for_avatar_initiative) + desire_ref.
    Preserves causal link: Desire → Intent.
    Formation only — execution deferred to BodyArbiter (next step).
Зависимости: app.domain.intent_identity, app.models.npc_state (Intent)
Основные сущности: AvatarIntentRecord
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from app.domain.intent_identity import IntentIdentity
from app.models.npc_state import Intent


@dataclass(frozen=True)
class AvatarIntentRecord:
    """Avatar's self-formed intent — formation only, awaiting arbitration.

    Не новый Intent — wrapper вокруг существующего Intent (enum) +
    IntentIdentity (for_avatar_initiative) + desire_ref.
    Causal link: Desire (source) → AvatarIntentRecord (decision).

    Не запускает исполнение (нет CommunicationIntent, нет MovementIntent).
    BodyArbiter (следующий шаг) читает этот record и решает:
    авторизовать исполнение или отклонить.
    """

    intent: Intent                          # существующий enum (APPROACH, TRADE, etc.)
    identity: IntentIdentity                # for_avatar_initiative ("player")
    desire_ref: str                         # desire_id породившего Desire
    target: Optional[str]                   # intent_target (who/what)
    formed_tick: int                        # когда сформирован
    urgency: float                          # из Desire.urgency (0.0-1.0)

    def to_dict(self) -> dict[str, Any]:
        """Serialization для scene_state round-trip."""
        return {
            "intent": self.intent.value,
            "identity": {
                "intent_owner": self.identity.intent_owner,
                "actor_id": self.identity.actor_id,
                "body_id": self.identity.body_id,
                "control_source": self.identity.control_source.value,
            },
            "desire_ref": self.desire_ref,
            "target": self.target,
            "formed_tick": self.formed_tick,
            "urgency": self.urgency,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AvatarIntentRecord":
        """Deserialization из scene_state."""
        from app.domain.control_source import ControlSource
        return cls(
            intent=Intent(data.get("intent", "idle")),
            identity=IntentIdentity(
                intent_owner=data.get("identity", {}).get("intent_owner", ""),
                actor_id=data.get("identity", {}).get("actor_id", ""),
                body_id=data.get("identity", {}).get("body_id", ""),
                control_source=ControlSource(
                    data.get("identity", {}).get("control_source", "avatar_initiative")
                ),
            ),
            desire_ref=data.get("desire_ref", ""),
            target=data.get("target"),
            formed_tick=data.get("formed_tick", 0),
            urgency=data.get("urgency", 0.0),
        )
