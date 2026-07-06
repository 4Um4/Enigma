# -*- coding: utf-8 -*-
"""
Полный физический контракт события.

ADR-O-201: Causal Kernel Architecture — Causal Event Layer.
SceneChange = thin (семантика, "что произошло").
ThickSceneChange = full (физика, "как это выглядит в мире").
ProjectionEngine применяет ThickSceneChange БЕЗ вычислений.

Rule 123: SceneChange без полного SpatialResolution при NPC_POSITION — запрещён.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional, Tuple


class SpatialTransitionMode(str, Enum):
    """Политика применения позиции (Authoritative vs Presentation)."""
    IMMEDIATE = "IMMEDIATE"       # Snap (телепортация, серверная коррекция, завершение маршрута)
    INTERPOLATED = "INTERPOLATED" # Плавное движение (создание TraversalState)


@dataclass(frozen=True)
class SpatialResolution:
    """Разрешённая пространственная информация — вычислена EventCompiler.

    Ответственность перенесена из apply_change (Мутации E1-E6).
    """
    source_location: str
    target_location: str
    source_node: str            # canonical node ID (пусто если неизвестен)
    target_node: str            # canonical node ID
    source_xy: Tuple[float, float]  # (x, y) старта
    target_xy: Tuple[float, float]  # (x, y) финиша


@dataclass(frozen=True)
class MotionPlan:
    """Физический план перемещения — вычислен EventCompiler.

    Ответственность перенесена из apply_change (Мутации E9-E16).
    """
    is_teleport: bool           # микро-перемещение (< 0.1), traversal не нужен
    is_path_blocked: bool       # стена блокирует прямую линию
    waypoints: Tuple[Tuple[float, float], ...]  # полный маршрут
    distance: float             # длина маршрута (сумма сегментов)
    duration_ticks: int         # время в тиках
    speed: float                # скорость (м/с)


@dataclass(frozen=True)
class BoundaryResolution:
    """Разрешение пересечения границы чанка — вычислено EventCompiler.

    Ответственность перенесена из _process_traversals (Мутации E18-E19).
    """
    is_boundary: bool
    neighbor_chunk: str         # целевой чанк (пусто если не boundary)
    entry_node: str             # node входа в новом чанке (пусто если не boundary)


@dataclass(frozen=True)
class TraversalContract:
    """Контракт создания/завершения транзита — вычислен EventCompiler.

    Ответственность перенесена из apply_change (Мутация E16-E17)
    и _process_traversals (Мутация E20).
    """
    status: str                 # "NEW" | "COMPLETED" | "" (пусто = не нужен)
    fields: Dict                # все поля для scene_state["active_traversals"][npc_id]
    # Логически immutable после создания (architectural invariant).
    # frozen=True на ThickSceneChange защищает от переназначения traversal,
    # но не от мутации вложенного dict. Нарушение = Rule 120/122.


@dataclass(frozen=True)
class ThickSceneChange:
    """Полный физический контракт события (ADR-O-201).

    ProjectionEngine применяет ThickSceneChange БЕЗ вычислений.
    Ноль SpatialService queries. Ноль RNG. Ноль pathfinding.
    Только запись.

    Для не-пространственных изменений (OBJECT_STATE, NPC_STATE и т.д.)
    spatial/motion/boundary/traversal = None.
    EventCompiler в ФАЗЕ 0 обрабатывает только NPC_POSITION.
    """
    # ── Исходная семантика (из SceneChange) ──────────────────────
    change_type: str            # ChangeType.value
    target: str                 # NPC ID или object ID
    field: str                  # "position" | "local_position" | etc
    value: Any                  # semantic value (node name, xy dict, etc)
    cause: str                  # источник изменения
    tick: int
    target_local_xy: Optional[Tuple[float, float]] = None
    target_location_id: str = ""

    # ── Вычисленная физика (заполняется EventCompiler) ────────────
    spatial: Optional[SpatialResolution] = None
    motion: Optional[MotionPlan] = None
    boundary: Optional[BoundaryResolution] = None
    traversal: Optional[TraversalContract] = None
    spatial_mode: SpatialTransitionMode = SpatialTransitionMode.IMMEDIATE

    @property
    def is_spatial(self) -> bool:
        """Является ли это пространственным изменением."""
        return self.change_type == "npc_position"

    @property
    def needs_traversal(self) -> bool:
        """Требуется ли создание/изменение транзита."""
        return (
            self.traversal is not None
            and self.traversal.status in ("NEW", "COMPLETED")
        )