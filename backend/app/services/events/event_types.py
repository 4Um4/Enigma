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
from enum import Enum
from typing import Any, Dict, List, Optional
import time


class EventType(str, Enum):
    # ── Физический мир ────────────────────────────────────────────────────
    OBJECT_MOVED     = "object_moved"
    OBJECT_DESTROYED = "object_destroyed"
    OBJECT_CHANGED   = "object_changed"
    LIGHT_CHANGED    = "light_changed"
    SOUND_EMITTED    = "sound_emitted"
    SMELL_EMITTED    = "smell_emitted"

    # ── Игрок ─────────────────────────────────────────────────────────────
    PLAYER_MOVED     = "player_moved"
    PLAYER_ATTACKED  = "PLAYER_ATTACKED"  # сохранено для совместимости со старыми строками
    PLAYER_SPOKE     = "PLAYER_SPOKE"     # сохранено для совместимости со старыми строками
    PLAYER_USED_ITEM = "player_used_item"
    PLAYER_CAST_SPELL = "player_cast_spell"

    # ── NPC ───────────────────────────────────────────────────────────────
    NPC_STATE_CHANGED = "npc_state_changed"
    NPC_MOVED        = "npc_moved"
    NPC_SPOKE        = "npc_spoke"

    # ── Мир ───────────────────────────────────────────────────────────────
    TIME_PASSED      = "time_passed"
    WEATHER_CHANGED  = "weather_changed"
    FACTION_EVENT    = "faction_event"
    WORLD_TICK       = "world_tick"       # проактивный тик мира (Фаза 3.4)

    # ── NPC-NPC взаимодействия (Фаза 3.4) ───────────────────────────────
    NPC_PROXIMITY_CLOSE   = "npc_proximity_close"   # NPC подошёл к другому NPC
    NPC_PROXIMITY_LEAVE   = "npc_proximity_leave"   # NPC отошёл от другого NPC
    NPC_INTERACTS_NPC     = "npc_interacts_npc"     # NPC инициирует контакт с NPC

    # ── Легаси-события (из EventContext и старых JSON) ────────────────────
    # Унифицированы здесь для устранения разрывов (R1.6)
    THEFT            = "theft"
    COMBAT           = "combat"
    HELP             = "help"
    IDLE             = "idle"
    DIALOGUE         = "dialogue"
    INTIMIDATION     = "intimidation"
    BETRAYAL         = "betrayal"
    SAVED_LIFE       = "saved_life"
    MOVEMENT         = "movement"
    PLAYER_ASKS_WHY  = "player_asks_why"
    PLAYER_INTERACTS = "player_interacts"
    PLAYER_ATTACKS   = "player_attacks"
    PLAYER_ATTACK    = "player_attack"
    PLAYER_INSULTS   = "player_insults"
    PLAYER_TALKS     = "player_talks"
    PLAYER_THREATENS = "player_threatens"
    PLAYER_HELPERS   = "player_helpers"
    PROXIMITY_CLOSE  = "proximity_close"
    PROXIMITY_LEAVE  = "proximity_leave"
    UNKNOWN          = "unknown"


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
