"""
path: /project/backend/app/domain/identity_uuids.py
Назначение: Avatar Agency — три устойчивых UUID для разделения
    сознания Player (UUID-P), сознания Avatar (UUID-A), общего тела (UUID-B).
    Генерируются один раз при первом запуске, персистятся в player_avatar.json.
    Восстанавливаются при загрузке без регенерации.
Зависимости: stdlib (dataclasses, uuid)
Основные сущности: IdentityUUIDs
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Dict, Optional
import logging

_logger = logging.getLogger(__name__)


# Ключ в player_avatar.json для хранения UUIDs
_KEY_IDENTITY_UUIDS = "identity_uuids"
_KEY_PLAYER = "player_consciousness"
_KEY_AVATAR = "avatar_consciousness"
_KEY_BODY = "body"


@dataclass(frozen=True)
class IdentityUUIDs:
    """Три устойчивых UUID: Player consciousness, Avatar consciousness, shared body.

    Инварианты (проверяются в __post_init__):
      - player != avatar (разные сознания)
      - player != body (сознание ≠ тело)
      - avatar != body (сознание ≠ тело)

    UUID-P: владелец Player Intent (intent_owner в IntentIdentity)
    UUID-A: владелец Avatar Intent (intent_owner в IntentIdentity)
    UUID-B: общее тело (body_id в IntentIdentity обоих)

    actor_id="player" остаётся runtime-совместимым идентификатором,
    НЕ связан с UUID-B. Это позволяет NPC path и существующий
    execution path работать без изменений.
    """

    player_consciousness: str  # UUID-P
    avatar_consciousness: str  # UUID-A
    body: str                  # UUID-B

    def __post_init__(self) -> None:
        if self.player_consciousness == self.avatar_consciousness:
            raise ValueError(
                f"Player consciousness UUID == Avatar consciousness UUID "
                f"({self.player_consciousness}) — сознания не различаются"
            )
        if self.player_consciousness == self.body:
            raise ValueError(
                f"Player consciousness UUID == body UUID "
                f"({self.player_consciousness}) — сознание = тело"
            )
        if self.avatar_consciousness == self.body:
            raise ValueError(
                f"Avatar consciousness UUID == body UUID "
                f"({self.avatar_consciousness}) — сознание = тело"
            )

    def to_dict(self) -> Dict[str, str]:
        """Сериализация для player_avatar.json."""
        return {
            _KEY_PLAYER: self.player_consciousness,
            _KEY_AVATAR: self.avatar_consciousness,
            _KEY_BODY: self.body,
        }

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> Optional["IdentityUUIDs"]:
        """Десериализация из player_avatar.json. None если данные отсутствуют."""
        if not data or not isinstance(data, dict):
            return None
        try:
            return cls(
                player_consciousness=data[_KEY_PLAYER],
                avatar_consciousness=data[_KEY_AVATAR],
                body=data[_KEY_BODY],
            )
        except (KeyError, TypeError) as exc:
            # L4: громкий отказ — повреждённые данные наблюдаемы, не молчат (Устав §7.21, ADR-O-308)
            _logger.warning(
                "IdentityUUIDs.from_dict: повреждённые данные — %s; keys=%s",
                exc, list(data.keys()) if isinstance(data, dict) else type(data).__name__
            )
            return None

    @classmethod
    def generate_new(cls) -> "IdentityUUIDs":
        """Генерация трёх новых UUID-P, UUID-A, UUID-B (uuid4).

        Вызывается ОДИН РАЗ при первом запуске (когда UUIDs отсутствуют
        в player_avatar.json). Затем персистится и восстанавливается
        при каждой загрузке без регенерации.
        """
        return cls(
            player_consciousness=str(uuid.uuid4()),
            avatar_consciousness=str(uuid.uuid4()),
            body=str(uuid.uuid4()),
        )