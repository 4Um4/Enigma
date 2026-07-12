# -*- coding: utf-8 -*-
"""
Замороженный срез реальности в момент t.

ADR-O-201: Causal Kernel Architecture — Snapshot Kernel.
Единственный источник истины для EventCompiler.
Не вычисляет. Не мутирует. Только хранит.

Rule 125: Snapshot mutation после создания ЗАПРЕЩЕНА.

Первый закон причинности ENIGMA:
  Одинаковый Snapshot + Одинаковый Event = Одинаковый Result
"""
from __future__ import annotations


import copy
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict
from uuid import UUID, uuid4

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WorldSnapshot:
    """Замороженный срез реальности в момент t.

    frozen=True предотвращает переназначение полей.
    Вложенные dict — логически immutable (architectural invariant, Rule 125).
    Нарушение = архитектурный баг уровня ADR-O-201.
    """

    # ── Идентификация снимка ──────────────────────────────────────
    snapshot_id: UUID
    created_at: float

    # ── Время симуляции ───────────────────────────────────────────
    tick: int
    campaign_id: str
    location_id: str

    # ── Пространственная истина ───────────────────────────────────
    # Reference на уже построенный SpatialService (НЕ rebuild!).
    # SpatialService immutable после конструирования (ADR-065).
    # build_for_location() вызывается ОДИН раз за сессию.
    spatial_service: Any  # Optional[SpatialService]

    # ── NPC позиции ───────────────────────────────────────────────
    # Frozen copy: {"npc_id": {"local_position": {"x":..., "y":...}, ...}}
    npc_positions: Dict[str, Dict[str, Any]]

    # ── Активные транзиты ─────────────────────────────────────────
    # Frozen copy: {"npc_id": {"status": "MOVING", "path_waypoints": [...], ...}}
    active_traversals: Dict[str, Dict[str, Any]]

    # ── Геометрия мира ────────────────────────────────────────────
    # Стены для is_blocked_by_wall (EventCompiler читает вместо live scene_state)
    spatial_walls: Any
    # Мебель / препятствия (LOD0)
    spatial_obstacles: Any

    # ── Детерминизм ───────────────────────────────────────────────
    # RNG seed для воспроизведения jitter и других случайных выборов
    rng_seed: int


def build_snapshot(
    tick: int,
    campaign_id: str,
    location_id: str,
    spatial_service: Any,
    scene_state: Dict[str, Any],
    rng_seed: int = 0,
) -> WorldSnapshot:
    """Строит замороженный снимок из живого состояния.

    Принцип: не вычисляет, только фотографирует.
    SpatialService — reference (не rebuild, ADR-065).
    npc_positions / active_traversals — deep copy (гарантия immutability).
    """
    # Deep copy — гарантия что мутация scene_state не повлияет на снимок
    _npc_pos = copy.deepcopy(scene_state.get("npc_positions", {}))
    _active_travs = copy.deepcopy(scene_state.get("active_traversals", {}))

    snapshot = WorldSnapshot(
        snapshot_id=uuid4(),
        created_at=time.time(),
        tick=tick,
        campaign_id=campaign_id,
        location_id=location_id,
        spatial_service=spatial_service,
        npc_positions=_npc_pos,
        active_traversals=_active_travs,
        spatial_walls=scene_state.get("spatial_walls"),
        spatial_obstacles=scene_state.get("spatial_obstacles"),
        rng_seed=rng_seed,
    )

    # Observability: лог создания снимка (ФАЗА 0 — shadow mode)
    logger.info(
        f"[SNAPSHOT_CREATED] id={snapshot.snapshot_id.hex[:8]} "
        f"tick={tick} location={location_id} "
        f"npcs={len(_npc_pos)} traversals={len(_active_travs)} "
        f"rng_seed={rng_seed}"
    )

    return snapshot
