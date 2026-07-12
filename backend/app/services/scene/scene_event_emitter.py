"""
path: /backend/app/services/scene/scene_event_emitter.py
Назначение: Трансформирует исходы в SceneEvent[]
Зависимости: SceneEvent, SceneEventType
Основные сущности: SceneEventEmitter
"""

from typing import Dict, Any, List
from app.models.scene_event import SceneEvent, SceneEventType


class SceneEventEmitter:
    """Создаёт SceneEvent из различных источников."""

    # Базовые параметры по типу действия
    _TYPE_PROFILES = {
        "player_attacks": {
            "event_type": SceneEventType.VIOLENCE,
            "intensity": 0.9,
            "visibility_radius": 8.0,
            "sound_level": 0.8,
        },
        "player_steals": {
            "event_type": SceneEventType.ITEM_INTERACT,
            "intensity": 0.4,
            "visibility_radius": 3.0,
            "sound_level": 0.2,
        },
        "player_grapples": {
            "event_type": SceneEventType.VIOLENCE,
            "intensity": 0.7,
            "visibility_radius": 5.0,
            "sound_level": 0.6,
        },
        "player_interacts": {
            "event_type": SceneEventType.VERBAL,
            "intensity": 0.3,
            "visibility_radius": 6.0,
            "sound_level": 0.5,
        },
    }

    def emit_from_physical(
        self,
        action_type: str,
        actor_id: str,
        target_id: str,
        location_id: str,
        tick: int,
        action_text: str,
        damage: int = 0,
        damage_type: str = "",
        is_critical: bool = False,
    ) -> List[SceneEvent]:
        """Создаёт SceneEvent из результата физического действия."""
        profile = self._TYPE_PROFILES.get(
            action_type, self._TYPE_PROFILES["player_interacts"]
        )

        events = []

        # Основное событие — само действие
        intensity = profile["intensity"]
        if is_critical:
            intensity = min(1.0, intensity + 0.15)

        events.append(
            SceneEvent(
                event_type=profile["event_type"],
                actor_id=actor_id,
                target_id=target_id,
                location_id=location_id,
                tick=tick,
                intensity=intensity,
                visibility_radius=profile["visibility_radius"],
                summary=action_text[:100],
                damage=damage,
                damage_type=damage_type,
                sound_level=profile["sound_level"],
            )
        )

        # Если есть урон — дополнительное событие для свидетелей
        if damage > 0 and target_id:
            events.append(
                SceneEvent(
                    event_type=SceneEventType.NPC_INJURED,
                    actor_id=actor_id,
                    target_id=target_id,
                    location_id=location_id,
                    tick=tick,
                    intensity=min(1.0, 0.5 + damage * 0.05),
                    visibility_radius=8.0,
                    summary=f"{target_id} получил {damage} урона ({damage_type})",
                    damage=damage,
                    damage_type=damage_type,
                    sound_level=0.7 if damage > 5 else 0.4,
                )
            )

        return events

    def emit_from_verbal(
        self,
        actor_id: str,
        location_id: str,
        tick: int,
        action_text: str,
        target_id: str = "",
    ) -> List[SceneEvent]:
        """Создаёт SceneEvent из вербального действия."""
        # Определяем интенсивность по длине и знакам препинания
        sound_level = 0.5
        if "!" in action_text or "?" in action_text:
            sound_level = 0.7
        if action_text.isupper():
            sound_level = 0.9

        return [
            SceneEvent(
                event_type=SceneEventType.VERBAL,
                actor_id=actor_id,
                target_id=target_id,
                location_id=location_id,
                tick=tick,
                intensity=0.3,
                visibility_radius=6.0 + sound_level * 2.0,  # крик слышен дальше
                summary=action_text[:100],
                sound_level=sound_level,
            )
        ]
