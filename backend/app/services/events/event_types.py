# backend/app/services/events/event_types.py
#
# Phase 3B.1 — Event Foundation
#
# EventType описывает что произошло в мире (не намерение игрока).
# PLAYER_ATTACKED — не PLAYER_CHOSE_ATTACK.
#
# Совместимость с существующим scene_change.py:
#   Старый SceneChange (ChangeType) — атомарные изменения полей объектов.
#   Новый GameEvent (EventType)     — событие в мире, видимое NPC и системам.
#   Они дополняют друг друга:
#     sandbox_handler создаёт list[SceneChange] (как раньше)
#     action/processor.py оборачивает их в GameEvent и публикует в EventBus
#   Старый код продолжает работать без изменений.

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional
import time


class EventType(Enum):
    # ── Физический мир ────────────────────────────────────────────────────
    OBJECT_MOVED     = auto()   # объект переместился
    OBJECT_DESTROYED = auto()   # объект уничтожен (слышно, видно)
    OBJECT_CHANGED   = auto()   # состояние изменилось (дверь открыта, свеча погасла)
    LIGHT_CHANGED    = auto()   # освещение изменилось
    SOUND_EMITTED    = auto()   # звук — слышат NPC в радиусе
    SMELL_EMITTED    = auto()   # запах — слышат NPC в радиусе

    # ── Игрок ─────────────────────────────────────────────────────────────
    PLAYER_MOVED     = auto()   # игрок сменил позицию
    PLAYER_ATTACKED  = auto()   # атака (видна всем в локации)
    PLAYER_SPOKE     = auto()   # игрок сказал что-то
    PLAYER_USED_ITEM = auto()   # использование предмета
    PLAYER_CAST_SPELL = auto()  # заклинание

    # ── NPC ───────────────────────────────────────────────────────────────
    NPC_STATE_CHANGED = auto()  # стресс, доверие, hp, conditions
    NPC_MOVED        = auto()   # NPC сменил позицию (LifeEngine)
    NPC_SPOKE        = auto()   # NPC сказал что-то

    # ── Мир ───────────────────────────────────────────────────────────────
    TIME_PASSED      = auto()   # world_tick — прошло игровое время
    WEATHER_CHANGED  = auto()
    FACTION_EVENT    = auto()   # Phase 3E


# Соответствие ChangeType (старый) → EventType (новый)
# Используется в processor.py для автоматического маппинга.
from app.services.scene_change import ChangeType

CHANGE_TO_EVENT: Dict[ChangeType, EventType] = {
    ChangeType.OBJECT_STATE:  EventType.OBJECT_CHANGED,
    ChangeType.OBJECT_ADD:    EventType.OBJECT_CHANGED,
    ChangeType.OBJECT_REMOVE: EventType.OBJECT_DESTROYED,
    ChangeType.OBJECT_MOVE:   EventType.OBJECT_MOVED,
    ChangeType.NPC_POSITION:  EventType.NPC_MOVED,
    ChangeType.NPC_STATE:     EventType.NPC_STATE_CHANGED,
    ChangeType.ENVIRONMENT:   EventType.LIGHT_CHANGED,
    ChangeType.INVENTORY:     EventType.OBJECT_CHANGED,
    ChangeType.EFFECT_ADD:    EventType.OBJECT_CHANGED,
    ChangeType.EFFECT_REMOVE: EventType.OBJECT_CHANGED,
}


@dataclass
class GameEvent:
    """
    Событие в игровом мире — то что видят/слышат NPC и подсистемы.

    Отличие от SceneChange:
      SceneChange — атомарное изменение конкретного поля ("npc_01.state = captured")
      GameEvent   — факт который произошёл в мире ("кто-то захватил NPC")

    Один SceneChange может породить один GameEvent.
    Один GameEvent может охватывать несколько SceneChange.

    visible_to / audible_to:
      [] = видят/слышат все в локации (broadcast)
      ["npc_01", "npc_02"] = только эти NPC

    radius: метры, для звука/запаха. 999 = весь мир.
    """
    event_type:  EventType
    actor_id:    str                         # player_name или npc_id
    location:    str
    campaign_id: str            = ""        
    target_id:   Optional[str]    = None    # на кого/что направлено
    parameters:  Dict[str, Any]   = field(default_factory=dict)
    timestamp:   float            = field(default_factory=time.time)
    visible_to:  List[str]        = field(default_factory=list)
    audible_to:  List[str]        = field(default_factory=list)
    radius:      float            = 999.0
    # Связь с исходным SceneChange (для трассировки)
    source_changes: List[Any]     = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "event_type":  self.event_type.name,
            "actor_id":    self.actor_id,
            "location":    self.location,
            "campaign_id": self.campaign_id,
            "target_id":   self.target_id,
            "parameters":  self.parameters,
            "timestamp":   self.timestamp,
            "radius":      self.radius,
        }

    @classmethod
    def from_scene_change(
        cls,
        change,          # SceneChange (старый формат)
        actor_id: str,
        location: str,
    ) -> "GameEvent":
        """
        Конвертирует старый SceneChange в GameEvent.
        Используется в processor.py для обратной совместимости.
        """
        event_type = CHANGE_TO_EVENT.get(change.type, EventType.OBJECT_CHANGED)
        return cls(
            event_type     = event_type,
            actor_id       = actor_id,
            location       = location,
            target_id      = change.target,
            parameters     = {
                "field": change.field,
                "value": change.value,
                "cause": change.cause,
            },
            source_changes = [change],
        )