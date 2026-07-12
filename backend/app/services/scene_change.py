# -*- coding: utf-8 -*-
from __future__ import annotations

# C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\scene_change.py
"""
SceneChange — типы и структура изменений состояния сцены.
backend/app/services/scene_change.py

Принцип Фазы S: Python — единственный источник истины о мире.
LLM не меняет SceneState. Только Python-движки создают SceneChange объекты,
SceneStateManager применяет их и логирует.

Этот файл — самодостаточный. SceneStateManager (Фаза S) его импортирует,
sandbox_handler уже его использует для генерации изменений.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any


# ADR-RCG-EXT: ChangeType represents routing domain only.
# It MUST NOT encode field semantics.
# Field semantics are expressed via SceneChange.field.
class ChangeType(Enum):
    OBJECT_STATE = "object_state"  # барная стойка: intact → damaged
    OBJECT_ADD = "object_add"  # добавить объект (нашли нож на полу)
    OBJECT_REMOVE = "object_remove"  # убрать объект (украли свечи)
    OBJECT_MOVE = "object_move"  # переместить объект
    NPC_POSITION = "npc_position"  # NPC переместился (или стал hidden)
    NPC_STATE = "npc_state"  # NPC изменил состояние (связан, свободен)
    ENVIRONMENT = "environment"  # свет, шум, погода внутри
    INVENTORY = "inventory"  # игрок взял/положил предмет
    EFFECT_ADD = "effect_add"  # добавить активный эффект (горит стол)
    EFFECT_REMOVE = "effect_remove"  # убрать эффект
    NPC_METADATA = "npc_metadata"  # activity, initiative_suppression, semantic tags
    SCENE_METADATA = "scene_metadata"  # line_of_sight, environment flags


@dataclass
class SceneChange:
    """
    Одно атомарное изменение состояния сцены.

    Поля:
      type   — тип изменения (ChangeType)
      target — id объекта, NPC или игрока (str)
      field  — какое поле меняется (str)
      value  — новое значение (любой тип)
      cause  — источник изменения (player_action, life_engine, combat, etc.)
      tick   — игровой тик когда произошло (0 пока нет тик-системы)
    """

    type: ChangeType
    target: str
    field: str
    value: Any
    cause: str
    target_local_xy: Optional[tuple[float, float]] = (
        None  # ADR-065: Точные координаты внутри узла (для подхода к игроку)
    )
    tick: int = 0
    target_location_id: str = ""  # ADR-060: для кросс-локационных перемещений

    def to_dict(self) -> dict:
        """Сериализация для JSONL логирования и передачи в orchestrator."""
        return {
            "type": self.type.value,
            "target": self.target,
            "field": self.field,
            "value": self.value,
            "cause": self.cause,
            "tick": self.tick,
            "target_location_id": self.target_location_id,
        }


# ──────────────────────────────────────────────────────────────────────────────
# Утилиты для создания типовых изменений
# ──────────────────────────────────────────────────────────────────────────────


def npc_captured(
    npc_id: str, cause: str = "player_action", tick: int = 0
) -> list[SceneChange]:
    """NPC захвачен: добавить chains, изменить state."""
    return [
        SceneChange(
            ChangeType.NPC_STATE, npc_id, "psyche_state", "coerced", cause, tick
        ),
        SceneChange(
            ChangeType.NPC_STATE, npc_id, "visible_markers", "+chains", cause, tick
        ),
        SceneChange(
            ChangeType.NPC_STATE, npc_id, "flags.is_enslaved", True, cause, tick
        ),
    ]


def player_fled(
    player_name: str, location_id: str, cause: str = "player_action", tick: int = 0
) -> list[SceneChange]:
    """Игрок сбежал из локации."""
    return [
        SceneChange(
            ChangeType.NPC_POSITION,
            player_name,
            "location",
            f"fled_from_{location_id}",
            cause,
            tick,
        ),
        SceneChange(
            ChangeType.NPC_POSITION, player_name, "visible", False, cause, tick
        ),
    ]


def player_hidden(
    player_name: str, cause: str = "player_action", tick: int = 0
) -> list[SceneChange]:
    """Игрок успешно спрятался."""
    return [
        SceneChange(
            ChangeType.NPC_POSITION, player_name, "visible", False, cause, tick
        ),
        SceneChange(
            ChangeType.EFFECT_ADD,
            player_name,
            "condition",
            {"type": "hidden", "duration": 3},
            cause,
            tick,
        ),
    ]


def gold_stolen(
    player_name: str, amount: int, cause: str = "player_action", tick: int = 0
) -> list[SceneChange]:
    """Игрок украл золото."""
    return [
        SceneChange(
            ChangeType.INVENTORY, player_name, "add", {"gold": amount}, cause, tick
        ),
    ]


def lock_opened(
    object_id: str, cause: str = "player_action", tick: int = 0
) -> list[SceneChange]:
    """Замок вскрыт."""
    return [
        SceneChange(ChangeType.OBJECT_STATE, object_id, "state", "open", cause, tick),
    ]


def object_damaged(
    object_id: str, damage: int, cause: str = "player_action", tick: int = 0
) -> list[SceneChange]:
    """Объект получил урон от импровизированного оружия."""
    return [
        SceneChange(
            ChangeType.OBJECT_STATE, object_id, "hp", f"-{damage}", cause, tick
        ),
        SceneChange(
            ChangeType.OBJECT_STATE, object_id, "state", "damaged", cause, tick
        ),
    ]


def npc_poisoned(
    npc_id: str, duration: int = 3, cause: str = "player_action", tick: int = 0
) -> list[SceneChange]:
    """NPC отравлен."""
    return [
        SceneChange(
            ChangeType.EFFECT_ADD,
            npc_id,
            "condition",
            {"type": "poisoned", "duration": duration},
            cause,
            tick,
        ),
    ]


def player_surrendered(
    player_name: str, cause: str = "player_action", tick: int = 0
) -> list[SceneChange]:
    """Игрок сдался."""
    return [
        SceneChange(
            ChangeType.EFFECT_ADD,
            player_name,
            "condition",
            {"type": "prisoner", "duration": -1},
            cause,
            tick,
        ),
        SceneChange(
            ChangeType.NPC_STATE, player_name, "state", "surrendered", cause, tick
        ),
    ]


def item_crafted(
    player_name: str,
    item_name: str,
    quality: str,
    cause: str = "player_action",
    tick: int = 0,
) -> list[SceneChange]:
    """Создан предмет."""
    return [
        SceneChange(
            ChangeType.OBJECT_ADD,
            f"crafted_{item_name}",
            "object",
            {"name": item_name, "quality": quality, "owner": player_name},
            cause,
            tick,
        ),
        SceneChange(
            ChangeType.INVENTORY,
            player_name,
            "add",
            {item_name: 1, "_quality": quality},
            cause,
            tick,
        ),
    ]


def environment_disturbed(
    location_id: str,
    field: str,
    value: Any,
    cause: str = "player_action",
    tick: int = 0,
) -> list[SceneChange]:
    """Изменение окружающей среды (шум, свет)."""
    return [
        SceneChange(ChangeType.ENVIRONMENT, location_id, field, value, cause, tick),
    ]
