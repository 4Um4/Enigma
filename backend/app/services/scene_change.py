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


# S118 FIX: Удалены мёртвые фабрики (npc_captured, player_fled и т.д.) по итогам аудита Vulture.
